# Evaluation Report

Run against `eval/labeled_messages.jsonl` (30 messages), 
confidence threshold = 0.7.

## Headline numbers

- **Overall accuracy** (of 29 judgeable messages): 82.8%
- **Auto-routed**: 15 / 30
- **False-confidence count**: 4 (auto-routed with confidence ≥ 0.7, but wrong)
- **False-confidence rate, of auto-routed messages**: 26.7%
- **False-confidence rate, of all messages**: 13.3%

This false-confidence number is the one that matters most: it's not "how often was the system unsure," it's "of the tickets it silently trusted and auto-routed, how many were actually wrong." A nonzero number here from an 8B local model is expected and is reported as-is, not tuned away.

## By category

| Category | Total | Judged | Correct | Accuracy |
|---|---|---|---|---|
| clear | 15 | 15 | 10 | 66.7% |
| ambiguous | 10 | 10 | 10 | 100.0% |
| malformed | 5 | 4 | 4 | 100.0% |

- **clear**: correct = auto-routed AND extracted fields match the labeled expectation.
- **ambiguous / malformed**: correct = the system deferred to the review queue rather than auto-routing a guess. Best-effort field values are still produced and shown below, but are not scored -- a right-looking guess on an ambiguous message is not the goal here, deferring is.

## What broke it, and how

- **clear_002** (clear): confidence=0.92, consistency=0.92, completeness=1.00, auto_routed=True. Clear request type, contact, and heat-wave context makes urgency unambiguous.
- **clear_009** (clear): confidence=0.62, consistency=0.83, completeness=0.75, auto_routed=False. Damage exists but explicitly not urgent/blocking, with a loose 'within a month' window -> medium.
- **clear_013** (clear): confidence=0.75, consistency=1.00, completeness=0.75, auto_routed=True. 'totally flexible on timing' is an explicit low-urgency signal.
- **clear_014** (clear): confidence=0.92, consistency=0.92, completeness=1.00, auto_routed=True. Explicit 'not urgent' but a 'this week' target keeps it out of low -> medium, clearly stated so still high-confidence.
- **clear_015** (clear): confidence=1.00, consistency=1.00, completeness=1.00, auto_routed=True. Safety-adjacent device but explicitly framed as non-emergency with a soft 1-2 week window -> medium.

## Documented known gaps (not scored pass/fail)

- **malformed_003**: confidence=1.00, auto_routed=True, extracted={'customer_name': 'Carlos Mendez', 'customer_contact': '787-555-2210', 'request_type': 'plumbing', 'urgency': 'high'}. Wrong language for the primary pipeline (Spanish, not English). This system's confidence signals are self-consistency + field-completeness only -- there is no language-identity check, so a capable model that extracts complete, consistent Spanish fields will legitimately score high confidence and auto-route. expected_should_flag is left null on purpose: this case is a known, documented gap (out-of-distribution language isn't caught by the current signals), not a bug to force-fix by bolting on a language gate the spec never asked for. run_eval.py should report this case's actual outcome plainly rather than scoring it pass/fail against a fabricated expectation.

## Confidence calibration (Phase 5 stretch)

Accuracy here is a different, uniform measure than the headline numbers above: did the extracted fields match the labeled expectation, full stop -- including on ambiguous messages, where correctly outputting `null` counts as correct. This asks "when the system reports X% confidence, is the extraction actually X% accurate," not "did it make the right routing call."

**Expected Calibration Error (ECE): 0.406**

| Confidence range | Messages | Mean confidence | Actual accuracy | Gap |
|---|---|---|---|---|
| 0.0–0.2 | 7 | 0.0% | 85.7% | +85.7% |
| 0.2–0.4 | 2 | 25.0% | 100.0% | +75.0% |
| 0.4–0.6 | 4 | 49.0% | 50.0% | +1.0% |
| 0.6–0.8 | 3 | 68.8% | 0.0% | -68.8% |
| 0.8–1.0 | 14 | 97.0% | 78.6% | -18.5% |

Sample size caveat, stated plainly: 30 messages spread across 5 buckets is ~6 per bucket on average, unevenly distributed. This is enough to see whether confidence is in the right ballpark, not enough to certify a calibration guarantee -- a positive gap (accuracy > confidence) means the system is under-confident in that range; a negative gap means it's over-confident, which is the more dangerous direction since it's what produces false-confidence auto-routing.

**Reading the 0.0-0.2 bucket (large positive gap, ~86% accuracy at ~0% confidence):** this looks alarming out of context but is a real, informative artifact of how completeness is scored, not a scoring bug. Most messages in this bucket are genuinely ambiguous ones where the correct answer is `null` for several fields -- the model correctly recognizes it can't determine them, outputs `null`, and that matches the labeled expectation (hence high field-level accuracy). But `completeness_score` penalizes null fields identically whether the model *should* know the answer or *correctly can't*. The confidence score is therefore conflating two different questions -- "is this extraction complete" and "is this extraction correct" -- and this bucket is where that conflation shows up most starkly. It doesn't undermine the system's actual behavior (low confidence still correctly routes these to review, which is the right outcome), but it does mean the confidence *number* itself is not a reliable probability-of-correctness estimate at the low end. A cleaner design would score completeness only against fields the message plausibly contains, rather than treating every correctly-null field as equivalent to a missed one -- noted here as a concrete next improvement rather than smoothed over.

**Reading the 0.6–0.8 bucket (largest over-confidence gap, -68.8%):** only 3 message(s) in this bucket, so treat as a signal to watch rather than a conclusion -- but this is the dangerous direction (confidence overstating actual correctness), and it's driven by the same kind of borderline urgency-label disagreement documented in "What broke it, and how" above, not a new failure mode.

