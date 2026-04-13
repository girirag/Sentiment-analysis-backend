# Render Deployment Troubleshooting Guide

Common errors and solutions for deploying the Video Sentiment Analysis backend to Render.

---

## 🔴 Build Errors

### Error: "No module named 'app'"

**Cause:** Incorrect root directory or Python path issues

**Solutions:**
1. Set **Root Directory** to `backend` in Render dashboard
2. Or update start command to:
   ```bash
   cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
3. Verify your directory structure matches:
   ```
   backend/
   ├── app/
   │   ├── __init__.py
   │   ├── main.py
   │   └── ...
   └── requirements.txt
   ```

---

### Error: "Could not find a version that satisfies the requirement torch"

**Cause:** PyTorch installation issues on Render's build environment

**Solutions:**
1. Update `requirements.txt` to use CPU-only PyTorch:
   ```txt
   torch==2.2.0+cpu
   torchvision==0.17.0+cpu
   torchaudio==2.2.0+cpu
   --extra-index-url https://download.pytorch.org/whl/cpu
   ```

2. Or use a smaller version:
   ```txt
   torch==2.0.0
   ```

---

### Error: "ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device"

**Cause:** Build disk space exceeded

**Solutions:**
1. Reduce dependencies in `requirements.txt`
2. Remove unused packages
3. Use smaller model versions
4. Contact Render support to increase build disk space

---

### Error: "ffmpeg: command not found"

**Cause:** FFmpeg not installed in build environment

**Solutions:**
1. Add build script `render-build.sh`:
   ```bash
   #!/usr/bin/env bash
   set -o errexit
   
   # Install system dependencies
   apt-get update
   apt-get install -y ffmpeg
   
   # Install Python dependencies
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. Update Build Command in Render:
   ```bash
   chmod +x render-build.sh && ./render-build.sh
   ```

3. Or use Dockerfile deployment instead

---

## 🔴 Runtime Errors

### Error: "Application startup failed"

**Cause:** Missing environment variables or initialization errors

**Solutions:**
1. Check logs for specific error message
2. Verify all required environment variables are set:
   - `FIREBASE_STORAGE_BUCKET`
   - `REDIS_URL`
   - `FIREBASE_CREDENTIALS` or `FIREBASE_CREDENTIALS_PATH`

3. Test locally with same environment variables:
   ```bash
   export REDIS_URL=redis://localhost:6379
   export FIREBASE_STORAGE_BUCKET=your-bucket.appspot.com
   uvicorn app.main:app --reload
   ```

---

### Error: "redis.exceptions.ConnectionError: Error connecting to Redis"

**Cause:** Redis URL incorrect or Redis instance not running

**Solutions:**
1. Verify Redis instance is created and running in Render
2. Use **Internal Redis URL** (not External):
   ```
   redis://red-xxxxx:6379
   ```
3. Ensure Redis and web service are in the **same region**
4. Check Redis instance logs for errors
5. Test Redis connection:
   ```python
   import redis
   r = redis.from_url("redis://red-xxxxx:6379")
   r.ping()  # Should return True
   ```

---

### Error: "Firebase credentials not found"

**Cause:** Firebase credentials not properly configured

**Solutions:**

**Option 1: Using Secret File**
1. Go to service → Environment → Secret Files
2. Add file:
   - Filename: `firebase-key.json`
   - Contents: Your Firebase service account JSON
3. Add environment variable:
   ```
   FIREBASE_CREDENTIALS_PATH=/etc/secrets/firebase-key.json
   ```

**Option 2: Using Environment Variable**
1. Minify your `firebase-key.json` to single line:
   ```bash
   cat firebase-key.json | jq -c
   ```
2. Add environment variable:
   - Key: `FIREBASE_CREDENTIALS`
   - Value: Paste the minified JSON
3. The code will automatically use this (already updated in firebase_service.py)

---

### Error: "Port 8000 is already in use"

**Cause:** Not using Render's `$PORT` environment variable

**Solution:**
Update start command to use `$PORT`:
```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render automatically sets `$PORT` to the correct value.

---

### Error: "Out of memory" or "Killed"

**Cause:** Instance ran out of RAM (usually during model loading)

**Solutions:**
1. **Use smaller Whisper model:**
   ```env
   WHISPER_MODEL=tiny
   ```
   Model sizes:
   - `tiny`: ~75 MB RAM
   - `base`: ~150 MB RAM
   - `small`: ~500 MB RAM
   - `medium`: ~1.5 GB RAM
   - `large`: ~3 GB RAM

2. **Upgrade instance type:**
   - Starter (512 MB) → Standard (2 GB)
   - Standard (2 GB) → Pro (4 GB)

3. **Lazy load models:**
   Update services to load models only when needed, not at startup

4. **Reduce concurrent workers:**
   For Celery worker, use `--concurrency=1`

---

### Error: "Health check failed"

**Cause:** Health endpoint not responding or returning error

**Solutions:**
1. Verify health endpoint works:
   ```bash
   curl https://your-app.onrender.com/health
   ```

2. Check if endpoint exists in `app/main.py`:
   ```python
   @app.get("/health")
   async def health_check():
       return {"status": "healthy"}
   ```

3. Increase health check timeout in Render settings

4. Check logs for startup errors

---

## 🔴 Celery Worker Errors

### Error: "celery.exceptions.ImproperlyConfigured: Cannot mix AMQP/Redis"

**Cause:** Celery configuration issues

**Solution:**
Ensure `REDIS_URL` is set correctly in worker environment variables

---

### Error: "Worker not processing tasks"

**Cause:** Worker not connected to same Redis instance as web service

**Solutions:**
1. Verify worker has same `REDIS_URL` as web service
2. Check worker logs for connection errors
3. Restart worker service
4. Ensure Redis instance is accessible

---

### Error: "kombu.exceptions.OperationalError: [Errno 111] Connection refused"

**Cause:** Cannot connect to Redis broker

**Solutions:**
1. Verify `REDIS_URL` format:
   ```
   redis://red-xxxxx:6379
   ```
2. Check Redis instance is running
3. Ensure worker and Redis are in same region
4. Test connection from worker logs

---

## 🔴 CORS Errors

### Error: "CORS policy: No 'Access-Control-Allow-Origin' header"

**Cause:** Frontend domain not allowed in CORS configuration

**Solution:**
Update `backend/app/main.py`:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Local development
        "https://your-frontend.vercel.app",  # Production frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Or use environment variable:
```python
import os
origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
```

Then set in Render:
```env
ALLOWED_ORIGINS=https://your-frontend.vercel.app,https://custom-domain.com
```

---

## 🔴 Performance Issues

### Issue: Slow response times

**Solutions:**
1. **Upgrade instance type** (more CPU/RAM)
2. **Use smaller models:**
   - Whisper: `tiny` or `base`
   - Sentiment: Keep default (already optimized)
3. **Enable caching** for repeated requests
4. **Optimize video processing:**
   - Reduce `MAX_VIDEO_SIZE`
   - Increase `STREAM_CHUNK_DURATION`
5. **Add Redis caching** for analysis results

---

### Issue: Cold starts (Free tier)

**Cause:** Free tier spins down after 15 minutes of inactivity

**Solutions:**
1. Upgrade to Starter plan ($7/month) - always running
2. Use a ping service to keep it alive (not recommended)
3. Accept cold starts for development/testing

---

## 🔴 Deployment Issues

### Error: "Deploy failed: Build exceeded maximum time"

**Cause:** Build taking too long (usually PyTorch/Transformers installation)

**Solutions:**
1. Use Docker deployment instead of native Python
2. Reduce dependencies
3. Use pre-built wheels
4. Contact Render support for build timeout increase

---

### Error: "Deploy failed: No such file or directory: 'requirements.txt'"

**Cause:** Incorrect root directory setting

**Solutions:**
1. Set Root Directory to `backend` in Render dashboard
2. Or move `requirements.txt` to repository root
3. Verify file exists in repository

---

## 🔧 Debugging Tips

### View Detailed Logs

1. Go to service → Logs
2. Enable "Show timestamps"
3. Filter by error level
4. Download logs for analysis

### Test Locally with Render Environment

```bash
# Set environment variables
export REDIS_URL=redis://localhost:6379
export FIREBASE_STORAGE_BUCKET=your-bucket.appspot.com
export WHISPER_MODEL=base
export PORT=8000

# Run application
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### Check Service Status

```bash
# Using Render CLI
render status -s video-sentiment-backend

# Or check health endpoint
curl https://your-app.onrender.com/health
```

### Monitor Resource Usage

1. Go to service → Metrics
2. Check:
   - CPU usage
   - Memory usage
   - Request count
   - Response times

---

## 📞 Getting Help

### Render Support Channels

1. **Community Forum:** https://community.render.com
2. **Documentation:** https://render.com/docs
3. **Support Email:** support@render.com
4. **Status Page:** https://status.render.com

### Useful Commands

```bash
# Install Render CLI
npm install -g render

# Login
render login

# View logs
render logs -s video-sentiment-backend

# Restart service
render restart -s video-sentiment-backend

# Deploy manually
render deploy -s video-sentiment-backend
```

---

## ✅ Pre-Deployment Checklist

Before deploying, verify:

- [ ] `requirements.txt` is complete and correct
- [ ] All environment variables are documented
- [ ] Firebase credentials are prepared
- [ ] Redis instance is created
- [ ] Health check endpoint exists
- [ ] CORS is configured for frontend domain
- [ ] Start command uses `$PORT` variable
- [ ] Models are appropriate size for instance
- [ ] Logs show no critical errors locally
- [ ] All tests pass locally

---

## 🎯 Quick Fixes Summary

| Error | Quick Fix |
|-------|-----------|
| Module not found | Set root directory to `backend` |
| Redis connection failed | Use internal Redis URL |
| Firebase credentials not found | Add as secret file or env var |
| Out of memory | Use smaller Whisper model (`tiny` or `base`) |
| Port binding error | Use `$PORT` in start command |
| CORS error | Add frontend domain to allowed origins |
| Health check failed | Verify `/health` endpoint exists |
| Build timeout | Use Docker or reduce dependencies |
| Worker not processing | Check Redis URL in worker env vars |

---

**Still having issues?** Share your error logs and I'll help you troubleshoot!
