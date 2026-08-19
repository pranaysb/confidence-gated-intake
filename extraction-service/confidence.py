"""
Confidence scoring — the core design decision of this project.

This deliberately does NOT ask the model "how confident are you" and use that
number. LLM self-reported confidence is well known to be poorly calibrated;
shipping that as a "confidence score" would be decoration, not measurement.

Instead, confidence is built from two independent, checkable signals:

1. Self-consistency: run extraction N times at low temperature. If a field's
   value agrees across runs, that's real structural evidence the message
   states it unambiguously. If it flips between runs, that's a real signal
   the message is ambiguous -- not a guess about ambiguity, a measurement of it.

2. Field completeness: did the model produce a value for every required
   field, or leave something null? This is checked deterministically against
   the extraction output, not asked of the model's opinion of itself.

confidence = consistency_score * completeness_score (multiplicative, not
averaged) on purpose: a extraction that is very consistent about returning
nothing useful (e.g. an emoji-only message where the model reliably outputs
all-null, or reliably hallucinates the same wrong field) must not average up
to a middling-looking confidence. Both dimensions have to hold for the score
to be high.

A third, independent, fully deterministic check runs regardless of sampling:
a pattern check for prompt-injection attempts in the raw message content. If
tripped, confidence is forced to 0 -- this is a safety gate, not a confidence
measurement, and is reported separately in the breakdown so it's never
confused with "the model was uncertain."
"""

import re
from collections import Counter
from typing import Callable, Optional

from llm_client import extract_once

REQUIRED_FIELDS = ["customer_name", "customer_contact", "request_type", "urgency"]
N_SAMPLES = 3
SAMPLE_TEMPERATURE = 0.2

# Deterministic, not model-based: string patterns aimed at making the
# extractor override its own instructions or fabricate a confidence value.
# This is a coarse net for an intake form's threat model, not a general
# prompt-injection defense -- see llm_client.py's system prompt for the
# other half of the mitigation.
INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above)\s+instructions",
    r"disregard (all |any )?(previous|prior)\s+(instructions|prompts)",
    r"you are now (in )?(an? )?(admin|developer|system)\s*mode",
    r"act as (an? )?admin",
    r"system\s*prompt",
    r"set\s+(confidence|urgency)\s+(to|as)",
    r"without (running|performing) any checks",
    r"mark confidence as\s+1(\.0)?",
]
_INJECTION_RE = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

Extractor = Callable[[str, float], dict]


def detect_injection(raw_content: str) -> bool:
    return any(pattern.search(raw_content) for pattern in _INJECTION_RE)


def _mode_with_agreement(values: list) -> tuple[Optional[str], float]:
    """Most common value in a list (None counts as its own value) and the
    fraction of the list that agreed with it."""
    counts = Counter(values)
    value, count = counts.most_common(1)[0]
    return value, count / len(values)


def score_extraction(
    raw_content: str,
    extractor: Extractor = extract_once,
    n_samples: int = N_SAMPLES,
) -> dict:
    """Run self-consistency sampling + deterministic completeness scoring.

    `extractor` is injectable so unit tests can supply a fake, deterministic
    sampler instead of calling a live LLM.
    """
    injection_suspected = detect_injection(raw_content)

    samples = [extractor(raw_content, SAMPLE_TEMPERATURE) for _ in range(n_samples)]

    majority: dict = {}
    field_agreement: dict = {}
    for field in REQUIRED_FIELDS:
        values = [sample.get(field) for sample in samples]
        value, agreement = _mode_with_agreement(values)
        majority[field] = value
        field_agreement[field] = agreement

    consistency_score = sum(field_agreement.values()) / len(REQUIRED_FIELDS)
    completeness_score = sum(
        1 for field in REQUIRED_FIELDS if majority[field] is not None
    ) / len(REQUIRED_FIELDS)

    confidence = consistency_score * completeness_score
    if injection_suspected:
        confidence = 0.0

    return {
        "extracted": majority,
        "field_agreement": field_agreement,
        "consistency_score": round(consistency_score, 4),
        "completeness_score": round(completeness_score, 4),
        "injection_suspected": injection_suspected,
        "confidence": round(confidence, 4),
        "samples": samples,
    }


def build_reason(result: dict) -> Optional[str]:
    """Human-readable explanation for why a result was routed to review,
    written to review_queue.reason. None means "not flagged"."""
    if result["injection_suspected"]:
        return "suspected prompt injection in message content"

    reasons = []
    for field in REQUIRED_FIELDS:
        if result["extracted"][field] is None:
            reasons.append(f"missing {field}")
    for field, agreement in result["field_agreement"].items():
        if agreement < 1.0 and result["extracted"][field] is not None:
            reasons.append(f"{field} was inconsistent across extraction runs")

    return "; ".join(reasons) if reasons else None
