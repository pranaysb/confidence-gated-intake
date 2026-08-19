#!/usr/bin/env python3
"""
Phase 3 — run the full confidence-scoring pipeline against the labeled eval
set and report, honestly, how it actually performed.

This calls the real extraction pipeline (live LLM via Groq, 3 self-consistency
samples per message) via extraction-service/confidence.py directly -- it does
NOT go through the FastAPI /extract endpoint or write to tickets/review_queue,
so running eval never pollutes real pipeline data. It optionally logs a
summary row to eval_runs if a database is reachable (dashboard reads this).

Usage:
    cd eval && python3 run_eval.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "extraction-service"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / "extraction-service" / ".env")  # must run before llm_client imports

from confidence import score_extraction  # noqa: E402

EVAL_SET_PATH = REPO_ROOT / "eval" / "labeled_messages.jsonl"
REPORT_PATH = REPO_ROOT / "eval" / "eval_report.md"
RAW_OUTPUT_DIR = REPO_ROOT / "eval" / "eval_run_output"
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))


def load_eval_set() -> list[dict]:
    cases = []
    with open(EVAL_SET_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def normalize(value):
    if value is None:
        return None
    return re.sub(r"[^a-z0-9]", "", value.lower())


def fields_match(extracted: dict, expected: dict) -> bool:
    for field in ("customer_name", "customer_contact", "request_type", "urgency"):
        if normalize(extracted.get(field)) != normalize(expected.get(field)):
            return False
    return True


def evaluate_case(case: dict) -> dict:
    result = score_extraction(case["raw_message"])
    confidence = result["confidence"]
    auto_routed = confidence >= CONFIDENCE_THRESHOLD and not result["injection_suspected"]

    category = case["category"]
    expected_should_flag = case.get("expected_should_flag")

    if expected_should_flag is None:
        # documented known gap (see labeled_messages.jsonl malformed_003) --
        # report the outcome, don't force a pass/fail judgment
        judged = None
        correct = None
    elif category == "clear":
        judged = True
        correct = auto_routed and fields_match(result["extracted"], case["expected"])
    else:
        # ambiguous + malformed (excluding the null-judgment case above):
        # correct behavior is deferring to review, regardless of what
        # best-effort fields it produced
        judged = True
        correct = not auto_routed

    false_confidence = bool(judged and auto_routed and not correct)

    return {
        "id": case["id"],
        "category": category,
        "confidence": confidence,
        "consistency_score": result["consistency_score"],
        "completeness_score": result["completeness_score"],
        "injection_suspected": result["injection_suspected"],
        "auto_routed": auto_routed,
        "extracted": result["extracted"],
        "expected": case.get("expected"),
        "judged": judged,
        "correct": correct,
        "false_confidence": false_confidence,
        "notes": case.get("notes", ""),
    }


def run() -> list[dict]:
    cases = load_eval_set()
    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} ({case['category']})...", end=" ", flush=True)
        start = time.time()
        r = evaluate_case(case)
        elapsed = time.time() - start
        status = "?" if r["judged"] is None else ("OK" if r["correct"] else "MISS")
        print(f"{status}  confidence={r['confidence']:.2f}  ({elapsed:.1f}s)")
        results.append(r)
    return results


def summarize(results: list[dict]) -> dict:
    judged = [r for r in results if r["judged"] is not None]
    correct = [r for r in judged if r["correct"]]
    false_confidences = [r for r in results if r["false_confidence"]]
    auto_routed = [r for r in results if r["auto_routed"]]

    by_category = {}
    for cat in ("clear", "ambiguous", "malformed"):
        cat_results = [r for r in results if r["category"] == cat]
        cat_judged = [r for r in cat_results if r["judged"] is not None]
        cat_correct = [r for r in cat_judged if r["correct"]]
        by_category[cat] = {
            "total": len(cat_results),
            "judged": len(cat_judged),
            "correct": len(cat_correct),
            "accuracy": (len(cat_correct) / len(cat_judged)) if cat_judged else None,
        }

    return {
        "total_messages": len(results),
        "total_judged": len(judged),
        "total_correct": len(correct),
        "overall_accuracy": (len(correct) / len(judged)) if judged else None,
        "total_auto_routed": len(auto_routed),
        "false_confidence_count": len(false_confidences),
        "false_confidence_rate_of_auto_routed": (
            len(false_confidences) / len(auto_routed) if auto_routed else None
        ),
        "false_confidence_rate_of_total": len(false_confidences) / len(results),
        "by_category": by_category,
    }


def write_report(results: list[dict], summary: dict) -> None:
    lines = []
    lines.append("# Evaluation Report")
    lines.append("")
    lines.append(f"Run against `eval/labeled_messages.jsonl` ({summary['total_messages']} messages), ")
    lines.append(f"confidence threshold = {CONFIDENCE_THRESHOLD}.")
    lines.append("")
    lines.append("## Headline numbers")
    lines.append("")
    acc = summary["overall_accuracy"]
    lines.append(f"- **Overall accuracy** (of {summary['total_judged']} judgeable messages): "
                  f"{acc:.1%}" if acc is not None else "- **Overall accuracy**: n/a")
    lines.append(f"- **Auto-routed**: {summary['total_auto_routed']} / {summary['total_messages']}")
    lines.append(f"- **False-confidence count**: {summary['false_confidence_count']} "
                 f"(auto-routed with confidence ≥ {CONFIDENCE_THRESHOLD}, but wrong)")
    fcr_auto = summary["false_confidence_rate_of_auto_routed"]
    lines.append(f"- **False-confidence rate, of auto-routed messages**: "
                  f"{fcr_auto:.1%}" if fcr_auto is not None else "- n/a")
    lines.append(f"- **False-confidence rate, of all messages**: "
                  f"{summary['false_confidence_rate_of_total']:.1%}")
    lines.append("")
    lines.append("This false-confidence number is the one that matters most: it's not \"how often "
                  "was the system unsure,\" it's \"of the tickets it silently trusted and auto-routed, "
                  "how many were actually wrong.\" A nonzero number here from an 8B local model is "
                  "expected and is reported as-is, not tuned away.")
    lines.append("")
    lines.append("## By category")
    lines.append("")
    lines.append("| Category | Total | Judged | Correct | Accuracy |")
    lines.append("|---|---|---|---|---|")
    for cat, stats in summary["by_category"].items():
        acc_str = f"{stats['accuracy']:.1%}" if stats["accuracy"] is not None else "n/a"
        lines.append(f"| {cat} | {stats['total']} | {stats['judged']} | {stats['correct']} | {acc_str} |")
    lines.append("")
    lines.append("- **clear**: correct = auto-routed AND extracted fields match the labeled expectation.")
    lines.append("- **ambiguous / malformed**: correct = the system deferred to the review queue rather "
                  "than auto-routing a guess. Best-effort field values are still produced and shown "
                  "below, but are not scored -- a right-looking guess on an ambiguous message is not "
                  "the goal here, deferring is.")
    lines.append("")
    lines.append("## What broke it, and how")
    lines.append("")
    misses = [r for r in results if r["judged"] and not r["correct"]]
    if not misses:
        lines.append("No misses on this run.")
    else:
        for r in misses:
            lines.append(f"- **{r['id']}** ({r['category']}): confidence={r['confidence']:.2f}, "
                          f"consistency={r['consistency_score']:.2f}, "
                          f"completeness={r['completeness_score']:.2f}, "
                          f"auto_routed={r['auto_routed']}. {r['notes']}")
    lines.append("")
    unjudged = [r for r in results if r["judged"] is None]
    if unjudged:
        lines.append("## Documented known gaps (not scored pass/fail)")
        lines.append("")
        for r in unjudged:
            lines.append(f"- **{r['id']}**: confidence={r['confidence']:.2f}, "
                          f"auto_routed={r['auto_routed']}, extracted={r['extracted']}. {r['notes']}")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nWrote {REPORT_PATH}")


def write_raw_results(results: list[dict]) -> None:
    RAW_OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = RAW_OUTPUT_DIR / f"results_{int(time.time())}.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote raw results to {out_path}")


def log_to_db(summary: dict) -> None:
    try:
        sys.path.insert(0, str(REPO_ROOT / "extraction-service"))
        import db  # noqa: E402

        with db.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into eval_runs
                        (total_messages, correct_extractions, false_confidence_count, accuracy, notes)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        summary["total_messages"],
                        summary["total_correct"],
                        summary["false_confidence_count"],
                        summary["overall_accuracy"],
                        "run via eval/run_eval.py",
                    ),
                )
        print("Logged run to eval_runs table.")
    except Exception as e:  # noqa: BLE001 -- eval must still succeed w/o a DB
        print(f"(skipped logging to database: {e})")


if __name__ == "__main__":
    results = run()
    summary = summarize(results)
    write_raw_results(results)
    write_report(results, summary)
    log_to_db(summary)

    print("\n--- Summary ---")
    print(json.dumps(summary, indent=2))
