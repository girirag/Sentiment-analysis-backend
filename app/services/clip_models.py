from dataclasses import dataclass


@dataclass
class MatchResult:
    segment: dict          # full transcript segment dict
    dataset_entry: str     # best-matching dataset string
    similarity_score: float
