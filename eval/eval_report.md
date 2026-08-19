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
- **clear_009** (clear): confidence=0.83, consistency=0.83, completeness=1.00, auto_routed=True. Damage exists but explicitly not urgent/blocking, with a loose 'within a month' window -> medium.
- **clear_013** (clear): confidence=0.69, consistency=0.92, completeness=0.75, auto_routed=False. 'totally flexible on timing' is an explicit low-urgency signal.
- **clear_014** (clear): confidence=1.00, consistency=1.00, completeness=1.00, auto_routed=True. Explicit 'not urgent' but a 'this week' target keeps it out of low -> medium, clearly stated so still high-confidence.
- **clear_015** (clear): confidence=1.00, consistency=1.00, completeness=1.00, auto_routed=True. Safety-adjacent device but explicitly framed as non-emergency with a soft 1-2 week window -> medium.

## Documented known gaps (not scored pass/fail)

- **malformed_003**: confidence=1.00, auto_routed=True, extracted={'customer_name': 'Carlos Mendez', 'customer_contact': '787-555-2210', 'request_type': 'plumbing', 'urgency': 'high'}. Wrong language for the primary pipeline (Spanish, not English). This system's confidence signals are self-consistency + field-completeness only -- there is no language-identity check, so a capable model that extracts complete, consistent Spanish fields will legitimately score high confidence and auto-route. expected_should_flag is left null on purpose: this case is a known, documented gap (out-of-distribution language isn't caught by the current signals), not a bug to force-fix by bolting on a language gate the spec never asked for. run_eval.py should report this case's actual outcome plainly rather than scoring it pass/fail against a fabricated expectation.

