import os

from dotenv import load_dotenv

load_dotenv()  # must run before llm_client reads GROQ_API_KEY at import time

from fastapi import FastAPI

import db
from confidence import build_reason, score_extraction
from idempotency import compute_message_hash
from models import ConfidenceBreakdown, ExtractedFields, ExtractRequest, ExtractResponse

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.7"))

app = FastAPI(title="Confidence-Gated Intake — Extraction Service")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/extract", response_model=ExtractResponse)
def extract(req: ExtractRequest) -> ExtractResponse:
    message_hash = compute_message_hash(req.raw_content)

    existing_message = db.get_message_by_hash(message_hash)
    if existing_message:
        record = db.get_routed_record_for_message(existing_message["id"])
        return ExtractResponse(
            duplicate=True,
            message_id=str(existing_message["id"]),
            record_id=str(record["id"]),
            routed_to=record["routed_to"],
            extracted=ExtractedFields(**record["extracted"]),
            confidence=record["confidence"],
            confidence_breakdown=None,
            reason=record["reason"],
        )

    message_id = db.insert_message(req.channel, message_hash, req.raw_content)

    result = score_extraction(req.raw_content)
    confidence = result["confidence"]
    reason = build_reason(result)

    should_auto_route = confidence >= CONFIDENCE_THRESHOLD and not result["injection_suspected"]

    if should_auto_route:
        record_id = db.insert_ticket(message_id, result["extracted"], confidence)
        routed_to = "ticket"
    else:
        record_id = db.insert_review_queue(message_id, result["extracted"], confidence, reason)
        routed_to = "review_queue"

    return ExtractResponse(
        duplicate=False,
        message_id=message_id,
        record_id=record_id,
        routed_to=routed_to,
        extracted=ExtractedFields(**result["extracted"]),
        confidence=confidence,
        confidence_breakdown=ConfidenceBreakdown(
            consistency_score=result["consistency_score"],
            completeness_score=result["completeness_score"],
            injection_suspected=result["injection_suspected"],
            confidence=confidence,
        ),
        reason=reason,
    )
