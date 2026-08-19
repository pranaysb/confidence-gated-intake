-- Confidence-Gated Intake Automation — schema
-- Postgres / Supabase. Applied automatically by docker-compose on first boot
-- (mounted into /docker-entrypoint-initdb.d/).

create extension if not exists pgcrypto;

-- Raw inbound messages, used for idempotency + audit trail
create table if not exists message_log (
    id UUID primary key default gen_random_uuid(),
    channel TEXT not null,              -- 'email' | 'telegram'
    message_hash TEXT unique not null,  -- sha256 of normalized content
    raw_content TEXT not null,
    received_at TIMESTAMPTZ default now()
);

-- Successfully auto-routed tickets
create table if not exists tickets (
    id UUID primary key default gen_random_uuid(),
    message_id UUID references message_log(id),
    customer_name TEXT,
    customer_contact TEXT,
    request_type TEXT,
    urgency TEXT,                       -- 'low' | 'medium' | 'high'
    confidence FLOAT not null,
    status TEXT default 'open',
    created_at TIMESTAMPTZ default now()
);

-- Low-confidence extractions awaiting human review
create table if not exists review_queue (
    id UUID primary key default gen_random_uuid(),
    message_id UUID references message_log(id),
    extracted_json JSONB,               -- best-effort extraction, unconfirmed
    confidence FLOAT not null,
    reason TEXT,                        -- why it was flagged
    resolved BOOLEAN default false,
    created_at TIMESTAMPTZ default now()
);

-- Evaluation runs against the labeled test set
create table if not exists eval_runs (
    id UUID primary key default gen_random_uuid(),
    run_at TIMESTAMPTZ default now(),
    total_messages INT,
    correct_extractions INT,
    false_confidence_count INT,         -- high confidence but wrong
    accuracy FLOAT,
    notes TEXT
);

create index if not exists idx_message_log_hash on message_log(message_hash);
create index if not exists idx_review_queue_resolved on review_queue(resolved);
create index if not exists idx_tickets_status on tickets(status);
