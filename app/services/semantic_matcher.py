from sentence_transformers import SentenceTransformer, util

from app.services.clip_models import MatchResult


class SemanticMatcher:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def match(
        self,
        dataset_entries: list[str],
        segments: list[dict],
        threshold: float = 0.5,
    ) -> list[MatchResult]:
        """Returns deduplicated list of MatchResult above threshold."""
        if not dataset_entries or not segments:
            return []

        # Determine the text to use for each segment
        segment_texts = []
        for seg in segments:
            if (
                seg.get("original_language") == "ta"
                and seg.get("translated_text")
            ):
                segment_texts.append(seg["translated_text"])
            else:
                segment_texts.append(seg.get("text", ""))

        # Batch-encode all entries and segment texts
        dataset_embeddings = self.model.encode(
            dataset_entries, convert_to_tensor=True, show_progress_bar=False
        )
        segment_embeddings = self.model.encode(
            segment_texts, convert_to_tensor=True, show_progress_bar=False
        )

        # Cosine similarity matrix: shape (len(dataset_entries), len(segments))
        similarity_matrix = util.cos_sim(dataset_embeddings, segment_embeddings)

        results: list[MatchResult] = []
        for seg_idx, segment in enumerate(segments):
            # Max similarity across all dataset entries for this segment
            scores = similarity_matrix[:, seg_idx]
            best_dataset_idx = int(scores.argmax())
            best_score = float(scores[best_dataset_idx])

            if best_score >= threshold:
                results.append(
                    MatchResult(
                        segment=segment,
                        dataset_entry=dataset_entries[best_dataset_idx],
                        similarity_score=best_score,
                    )
                )

        return results
