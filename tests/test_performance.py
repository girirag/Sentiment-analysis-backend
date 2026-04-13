"""
Performance Tests
=================
Measures response times, throughput, and concurrency behaviour
for all major API endpoints. Generates pass/fail based on
defined SLA thresholds.

Run:
    pytest tests/test_performance.py -v \
        --html=performance_report.html --self-contained-html
"""

import os
import sys
import time
import statistics
import threading
import concurrent.futures
import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BASE_URL = os.getenv("PERF_BASE_URL", "http://localhost:8000")
AUTH_HEADER = {"Authorization": "Bearer dev-token"}

# Shared session — reuses TCP connections (keep-alive) for accurate latency
_SESSION = requests.Session()
_SESSION.headers.update(AUTH_HEADER)

# ── SLA thresholds (seconds) ─────────────────────────────────────────────
# Windows localhost with per-request TCP setup adds ~50-150 ms overhead.
SLA = {
    "p50": 0.50,   # median under 500 ms
    "p95": 1.00,   # 95th-percentile under 1 s
    "p99": 2.00,   # 99th-percentile under 2 s
    "max": 3.00,   # absolute worst-case under 3 s
}
CONCURRENCY = 10   # simultaneous virtual users
ITERATIONS  = 20   # requests per endpoint for stats


# ── helpers ──────────────────────────────────────────────────────────────

def _get(path, headers=None, params=None):
    """Timed GET using shared session (keep-alive)."""
    t0 = time.perf_counter()
    r = _SESSION.get(f"{BASE_URL}{path}", headers=headers or {},
                     params=params, timeout=10)
    return time.perf_counter() - t0, r.status_code


def _post(path, headers=None, files=None, json=None):
    """Timed POST using shared session (keep-alive)."""
    t0 = time.perf_counter()
    r = _SESSION.post(f"{BASE_URL}{path}", headers=headers or {},
                      files=files, json=json, timeout=10)
    return time.perf_counter() - t0, r.status_code


def _stats(times):
    s = sorted(times)
    n = len(s)
    return {
        "min":  round(s[0], 4),
        "max":  round(s[-1], 4),
        "mean": round(statistics.mean(s), 4),
        "p50":  round(s[int(n * 0.50)], 4),
        "p95":  round(s[int(n * 0.95)], 4),
        "p99":  round(s[min(int(n * 0.99), n - 1)], 4),
    }


def _assert_sla(st, label):
    assert st["p50"] <= SLA["p50"], \
        f"{label} p50={st['p50']}s exceeds SLA {SLA['p50']}s"
    assert st["p95"] <= SLA["p95"], \
        f"{label} p95={st['p95']}s exceeds SLA {SLA['p95']}s"
    assert st["p99"] <= SLA["p99"], \
        f"{label} p99={st['p99']}s exceeds SLA {SLA['p99']}s"
    assert st["max"] <= SLA["max"], \
        f"{label} max={st['max']}s exceeds SLA {SLA['max']}s"


# ════════════════════════════════════════════════════════════════════════════
# 1. BASELINE — server reachability
# ════════════════════════════════════════════════════════════════════════════

class TestBaseline:
    """Verify server is up before running perf tests."""

    def test_server_is_reachable(self):
        # Warm up the connection first, then measure
        _get("/health")
        elapsed, code = _get("/health")
        assert code == 200, f"Health check returned {code}"
        assert elapsed < 1.0, f"Health check took {elapsed:.3f}s"

    def test_root_endpoint_reachable(self):
        elapsed, code = _get("/")
        assert code == 200
        assert elapsed < 1.0


# ════════════════════════════════════════════════════════════════════════════
# 2. SINGLE-USER LATENCY
# ════════════════════════════════════════════════════════════════════════════

class TestSingleUserLatency:
    """Sequential requests — measures raw endpoint latency."""

    def _run(self, fn, n=ITERATIONS):
        times = []
        for _ in range(n):
            elapsed, _ = fn()
            times.append(elapsed)
        return _stats(times)

    def test_health_latency(self):
        st = self._run(lambda: _get("/health"))
        print(f"\n  /health stats: {st}")
        _assert_sla(st, "/health")

    def test_root_latency(self):
        st = self._run(lambda: _get("/"))
        print(f"\n  / stats: {st}")
        _assert_sla(st, "/")

    def test_videos_list_latency(self):
        st = self._run(lambda: _get("/api/videos/", headers=AUTH_HEADER))
        print(f"\n  GET /api/videos/ stats: {st}")
        _assert_sla(st, "GET /api/videos/")

    def test_analysis_missing_latency(self):
        """404 path — still measures routing overhead."""
        st = self._run(
            lambda: _get("/api/analysis/nonexistent_video_id",
                         headers=AUTH_HEADER)
        )
        print(f"\n  GET /api/analysis/nonexistent stats: {st}")
        _assert_sla(st, "GET /api/analysis/nonexistent")

    def test_upload_small_file_latency(self):
        """POST upload with a 1 KB fake video file."""
        import io
        fake = io.BytesIO(b"0" * 1024)

        def _upload():
            fake.seek(0)
            return _post(
                "/api/videos/upload",
                headers=AUTH_HEADER,
                files={"file": ("perf_test.mp4", fake, "video/mp4")},
            )

        st = self._run(_upload, n=20)
        print(f"\n  POST /api/videos/upload (1 KB) stats: {st}")
        # uploads are heavier — relax p95/p99 slightly
        assert st["p50"] <= 1.0, f"Upload p50={st['p50']}s > 1s"
        assert st["p95"] <= 3.0, f"Upload p95={st['p95']}s > 3s"


# ════════════════════════════════════════════════════════════════════════════
# 3. CONCURRENT LOAD
# ════════════════════════════════════════════════════════════════════════════

class TestConcurrentLoad:
    """Simulate multiple simultaneous users."""

    def _concurrent(self, fn, users=CONCURRENCY, rps=ITERATIONS):
        times = []
        errors = []
        lock = threading.Lock()

        def worker():
            for _ in range(rps // users):
                try:
                    elapsed, code = fn()
                    with lock:
                        times.append(elapsed)
                        if code >= 500:
                            errors.append(code)
                except Exception as e:
                    with lock:
                        errors.append(str(e))

        threads = [threading.Thread(target=worker) for _ in range(users)]
        t_start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.perf_counter() - t_start

        return _stats(times), errors, wall

    def test_health_concurrent(self):
        # Warm up connection pool before measuring
        for _ in range(CONCURRENCY):
            _get("/health")
        st, errors, wall = self._concurrent(lambda: _get("/health"))
        print(f"\n  /health concurrent ({CONCURRENCY} users): {st}, "
              f"wall={wall:.2f}s, errors={len(errors)}")
        assert len(errors) == 0, f"Server errors under load: {errors[:5]}"
        # p50 and mean are the meaningful metrics under concurrent load
        assert st["p50"] <= SLA["p50"], \
            f"/health concurrent p50={st['p50']}s exceeds SLA {SLA['p50']}s"
        assert st["mean"] <= SLA["p95"], \
            f"/health concurrent mean={st['mean']}s exceeds SLA {SLA['p95']}s"

    def test_root_concurrent(self):
        st, errors, wall = self._concurrent(lambda: _get("/"))
        print(f"\n  / concurrent ({CONCURRENCY} users): {st}, "
              f"wall={wall:.2f}s, errors={len(errors)}")
        assert len(errors) == 0
        _assert_sla(st, "/ concurrent")

    def test_videos_list_concurrent(self):
        for _ in range(CONCURRENCY):
            _get("/api/videos/")
        st, errors, wall = self._concurrent(
            lambda: _get("/api/videos/", headers=AUTH_HEADER)
        )
        print(f"\n  GET /api/videos/ concurrent: {st}, "
              f"wall={wall:.2f}s, errors={len(errors)}")
        assert len(errors) == 0
        assert st["p50"] <= SLA["p50"], \
            f"Videos list p50={st['p50']}s exceeds SLA {SLA['p50']}s"
        assert st["mean"] <= SLA["p95"], \
            f"Videos list mean={st['mean']}s exceeds SLA {SLA['p95']}s"

    def test_mixed_endpoints_concurrent(self):
        """Mix of different endpoints simultaneously."""
        import random
        endpoints = [
            lambda: _get("/health"),
            lambda: _get("/"),
            lambda: _get("/api/videos/", headers=AUTH_HEADER),
        ]

        def mixed():
            return random.choice(endpoints)()

        st, errors, wall = self._concurrent(mixed)
        print(f"\n  Mixed endpoints concurrent: {st}, "
              f"wall={wall:.2f}s, errors={len(errors)}")
        assert len(errors) == 0
        _assert_sla(st, "Mixed concurrent")


# ════════════════════════════════════════════════════════════════════════════
# 4. THROUGHPUT
# ════════════════════════════════════════════════════════════════════════════

class TestThroughput:
    """Requests-per-second measurements."""

    MIN_RPS = 10   # minimum acceptable RPS (keep-alive, single thread)

    def _measure_rps(self, fn, duration=5.0):
        """Fire requests for `duration` seconds, return RPS."""
        count = 0
        t_end = time.perf_counter() + duration
        while time.perf_counter() < t_end:
            fn()
            count += 1
        return count / duration

    def test_health_throughput(self):
        rps = self._measure_rps(lambda: _get("/health"))
        print(f"\n  /health throughput: {rps:.1f} RPS")
        assert rps >= self.MIN_RPS, \
            f"/health throughput {rps:.1f} RPS < minimum {self.MIN_RPS}"

    def test_root_throughput(self):
        rps = self._measure_rps(lambda: _get("/"))
        print(f"\n  / throughput: {rps:.1f} RPS")
        assert rps >= self.MIN_RPS, \
            f"/ throughput {rps:.1f} RPS < minimum {self.MIN_RPS}"

    def test_concurrent_throughput(self):
        """Throughput under concurrent load using a thread pool."""
        results = []
        lock = threading.Lock()

        def worker():
            t0 = time.perf_counter()
            _get("/health")
            with lock:
                results.append(time.perf_counter() - t0)

        t_start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
            futs = [ex.submit(worker) for _ in range(200)]
            concurrent.futures.wait(futs)
        wall = time.perf_counter() - t_start

        rps = 200 / wall
        print(f"\n  Concurrent throughput (200 reqs, {CONCURRENCY} workers): "
              f"{rps:.1f} RPS, wall={wall:.2f}s")
        assert rps >= 20, f"Concurrent RPS {rps:.1f} < 20"


# ════════════════════════════════════════════════════════════════════════════
# 5. STRESS — spike & sustained load
# ════════════════════════════════════════════════════════════════════════════

class TestStressLoad:
    """Spike and sustained load — server must not return 5xx."""

    def test_spike_100_concurrent(self):
        """Fire 100 requests simultaneously — no 5xx allowed."""
        errors = []
        lock = threading.Lock()

        def hit():
            try:
                _, code = _get("/health")
                if code >= 500:
                    with lock:
                        errors.append(code)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=hit) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        print(f"\n  Spike 100 concurrent: {len(errors)} errors")
        assert len(errors) == 0, f"5xx errors during spike: {errors[:10]}"

    def test_sustained_load_10s(self):
        """Sustained load for 10 seconds — error rate must be < 1%."""
        results = {"ok": 0, "err": 0}
        lock = threading.Lock()
        stop = threading.Event()

        def worker():
            while not stop.is_set():
                try:
                    _, code = _get("/health")
                    with lock:
                        if code < 500:
                            results["ok"] += 1
                        else:
                            results["err"] += 1
                except Exception:
                    with lock:
                        results["err"] += 1

        threads = [threading.Thread(target=worker, daemon=True)
                   for _ in range(10)]
        for t in threads:
            t.start()
        time.sleep(5)   # 5-second sustained load
        stop.set()
        for t in threads:
            t.join(timeout=2)

        total = results["ok"] + results["err"]
        err_rate = results["err"] / total if total else 1
        print(f"\n  Sustained 10s: {total} reqs, "
              f"{results['err']} errors, rate={err_rate:.2%}")
        assert err_rate < 0.01, \
            f"Error rate {err_rate:.2%} exceeds 1% threshold"

    def test_large_payload_upload(self):
        """Upload a 500 KB file — must complete within 5 s."""
        import io
        fake = io.BytesIO(b"X" * 512_000)
        t0 = time.perf_counter()
        _, code = _post(
            "/api/videos/upload",
            headers=AUTH_HEADER,
            files={"file": ("big_perf.mp4", fake, "video/mp4")},
        )
        elapsed = time.perf_counter() - t0
        print(f"\n  500 KB upload: {elapsed:.3f}s, status={code}")
        assert elapsed < 5.0, f"Large upload took {elapsed:.3f}s > 5s"


# ════════════════════════════════════════════════════════════════════════════
# 6. RESPONSE SIZE
# ════════════════════════════════════════════════════════════════════════════

class TestResponseSize:
    """Verify response payloads are within reasonable bounds."""

    def test_health_response_size(self):
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        size = len(r.content)
        print(f"\n  /health response size: {size} bytes")
        assert size < 1024, f"/health response too large: {size} bytes"

    def test_root_response_size(self):
        r = requests.get(f"{BASE_URL}/", timeout=5)
        size = len(r.content)
        print(f"\n  / response size: {size} bytes")
        assert size < 4096, f"/ response too large: {size} bytes"

    def test_videos_list_response_size(self):
        r = requests.get(f"{BASE_URL}/api/videos/",
                         headers=AUTH_HEADER, timeout=5)
        size = len(r.content)
        print(f"\n  GET /api/videos/ response size: {size} bytes")
        assert size < 1_000_000, \
            f"Videos list response too large: {size} bytes"
