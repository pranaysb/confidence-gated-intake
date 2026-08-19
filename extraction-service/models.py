from typing import Literal, Optional

from pydantic import BaseModel

Channel = Literal["email", "telegram"]
Urgency = Literal["low", "medium", "high"]
RoutedTo = Literal["ticket", "review_queue"]


class ExtractRequest(BaseModel):
    channel: Channel
    raw_content: str


class ExtractedFields(BaseModel):
    customer_name: Optional[str] = None
    customer_contact: Optional[str] = None
    request_type: Optional[str] = None
    urgency: Optional[Urgency] = None


class ConfidenceBreakdown(BaseModel):
    consistency_score: float
    completeness_score: float
    injection_suspected: bool
    confidence: float


class ExtractResponse(BaseModel):
    duplicate: bool
    message_id: str
    record_id: str
    routed_to: RoutedTo
    extracted: ExtractedFields
    confidence: float
    # None on a duplicate replay: message_log/tickets/review_queue only persist
    # the final confidence float (per schema.sql), not the full per-field
    # consistency/completeness breakdown, so a replayed duplicate can report
    # the original routing decision but not reconstruct the original breakdown.
    confidence_breakdown: Optional[ConfidenceBreakdown] = None
    reason: Optional[str] = None
