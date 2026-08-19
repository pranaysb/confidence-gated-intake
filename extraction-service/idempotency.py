import hashlib
import re


def normalize_content(raw_content: str) -> str:
    """Collapse whitespace and case so trivially-different re-deliveries of the
    same message (e.g. a webhook retry with different line endings) still hash
    the same."""
    text = raw_content.strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def compute_message_hash(raw_content: str) -> str:
    normalized = normalize_content(raw_content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
