import json
import os
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get(
    # This project runs against the native Homebrew postgresql@16 already on
    # the host (Docker was removed entirely -- see LOGS.md). "intake" is a
    # dedicated database created for this project only; it does not touch
    # any other database on that instance. Local connections use Homebrew
    # Postgres's default trust auth (current OS user, no password).
    "DATABASE_URL",
    "postgresql://pranaysb@localhost:5432/intake",
)


@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_message_by_hash(message_hash: str) -> Optional[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "select id, channel, raw_content, received_at from message_log where message_hash = %s",
                (message_hash,),
            )
            return cur.fetchone()


def insert_message(channel: str, message_hash: str, raw_content: str) -> str:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into message_log (channel, message_hash, raw_content)
                values (%s, %s, %s)
                returning id
                """,
                (channel, message_hash, raw_content),
            )
            return str(cur.fetchone()[0])


def insert_ticket(message_id: str, extracted: dict, confidence: float) -> str:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into tickets
                    (message_id, customer_name, customer_contact, request_type, urgency, confidence)
                values (%s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    message_id,
                    extracted.get("customer_name"),
                    extracted.get("customer_contact"),
                    extracted.get("request_type"),
                    extracted.get("urgency"),
                    confidence,
                ),
            )
            return str(cur.fetchone()[0])


def insert_review_queue(
    message_id: str, extracted: dict, confidence: float, reason: Optional[str]
) -> str:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into review_queue (message_id, extracted_json, confidence, reason)
                values (%s, %s, %s, %s)
                returning id
                """,
                (message_id, json.dumps(extracted), confidence, reason),
            )
            return str(cur.fetchone()[0])


def get_routed_record_for_message(message_id: str) -> Optional[dict]:
    """Look up whichever record (ticket or review_queue entry) a given
    message_id was already routed to. Used for idempotent replay: a duplicate
    delivery should return the *original* routing decision, not re-run
    extraction and potentially get a different answer."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "select id, customer_name, customer_contact, request_type, urgency, confidence "
                "from tickets where message_id = %s",
                (message_id,),
            )
            ticket = cur.fetchone()
            if ticket:
                return {
                    "id": ticket["id"],
                    "routed_to": "ticket",
                    "extracted": {
                        "customer_name": ticket["customer_name"],
                        "customer_contact": ticket["customer_contact"],
                        "request_type": ticket["request_type"],
                        "urgency": ticket["urgency"],
                    },
                    "confidence": ticket["confidence"],
                    "reason": None,
                }

            cur.execute(
                "select id, extracted_json, confidence, reason "
                "from review_queue where message_id = %s",
                (message_id,),
            )
            review = cur.fetchone()
            if review:
                return {
                    "id": review["id"],
                    "routed_to": "review_queue",
                    "extracted": review["extracted_json"],
                    "confidence": review["confidence"],
                    "reason": review["reason"],
                }

            return None
