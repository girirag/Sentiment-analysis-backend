import csv
import io
import json
import re

RECOGNISED_FIELDS = ("headline", "title", "summary", "keywords", "text")


def _normalise(value: str) -> str:
    """Strip leading/trailing whitespace and collapse internal whitespace to a single space."""
    return re.sub(r"\s+", " ", value.strip())


def _extract_from_object(obj: dict) -> str | None:
    """Extract and join recognised text fields from a single dict object (case-insensitive)."""
    # Build a lowercase-key lookup so Title/TITLE/title all match
    lower_obj = {k.lower().strip(): v for k, v in obj.items()}
    parts = []
    for field in RECOGNISED_FIELDS:
        value = lower_obj.get(field)
        if isinstance(value, str):
            normalised = _normalise(value)
            if normalised:
                parts.append(normalised)
    return " ".join(parts) if parts else None


class DatasetParser:
    def parse(self, content: bytes, filename: str) -> list[str]:
        """Parse dataset file content and return a list of normalised text strings.

        Args:
            content: Raw file bytes.
            filename: Original filename used to detect format via extension.

        Returns:
            Non-empty list of normalised text strings.

        Raises:
            ValueError: If the file format is unsupported or no entries could be extracted.
        """
        lower = filename.lower()

        if lower.endswith(".json"):
            return self._parse_json(content)
        elif lower.endswith(".csv"):
            return self._parse_csv(content)
        elif lower.endswith(".txt"):
            return self._parse_txt(content)
        else:
            raise ValueError(
                f"Unsupported file format: '{filename}'. Expected .json, .csv, or .txt."
            )

    def _parse_json(self, content: bytes) -> list[str]:
        try:
            data = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid JSON file: {exc}") from exc

        if isinstance(data, list):
            objects = data
        elif isinstance(data, dict):
            objects = [data]
        else:
            raise ValueError(
                "JSON content must be an array of objects or a single object."
            )

        entries: list[str] = []
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            entry = _extract_from_object(obj)
            if entry:
                entries.append(entry)

        if not entries:
            raise ValueError(
                "No extractable text entries found in JSON file. "
                "Expected objects with fields: headline, title, summary, keywords, or text."
            )
        return entries

    def _parse_csv(self, content: bytes) -> list[str]:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text))
        entries: list[str] = []

        for row in reader:
            # Normalise keys to lowercase for case-insensitive matching
            lower_row = {k.lower().strip(): v for k, v in row.items() if k}
            parts = []
            for field in RECOGNISED_FIELDS:
                value = lower_row.get(field)
                if isinstance(value, str):
                    normalised = _normalise(value)
                    if normalised:
                        parts.append(normalised)
            if parts:
                entries.append(" ".join(parts))

        if not entries:
            raise ValueError(
                "No extractable text entries found in CSV file. "
                "Expected columns named: headline, title, summary, keywords, or text."
            )
        return entries

    def _parse_txt(self, content: bytes) -> list[str]:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        entries: list[str] = []
        for line in text.splitlines():
            normalised = _normalise(line)
            if normalised:
                entries.append(normalised)

        if not entries:
            raise ValueError(
                "No extractable text entries found in plain text file. "
                "The file appears to be empty or contains only whitespace."
            )
        return entries
