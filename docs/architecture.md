# Architecture

See [`README.md`](../README.md) for the pitch, confidence design, and
evaluation results. This doc covers implementation detail the README doesn't:
the n8n/service split rationale, and channel credential setup.

## Why the split between n8n and a custom service

n8n handles triggers, retries, and orchestration well — that's what it's for,
and it's the visible, expected tool for this kind of role. But confidence
scoring and structured extraction logic belong in real, testable code, not
n8n's node graph:

- It needs to be unit-tested against the labeled evaluation set
  (`extraction-service/tests/test_confidence.py`).
- The confidence-scoring logic is the actual intellectual content of the
  project and should be inspectable as code, not buried in a visual workflow.
- It needs to be swappable (Groq today, Ollama or another provider later —
  see `extraction-service/llm_client.py` vs the archived
  `ollama_client.py.bak`) without touching the orchestration layer.

So: **n8n owns triggers and routing. The FastAPI service owns extraction,
confidence scoring, and idempotency.** n8n calls it as a single HTTP node per
workflow — see `n8n/workflows/*.json`. This is also why adding the Telegram
channel after email was a small diff: same `/extract` endpoint, only the
trigger node and the raw-content assembly expression differ.

## Channel credential setup

Both workflows are built and import cleanly into n8n, but need real
credentials added in n8n's own Credentials UI before they'll actually
trigger on live messages.

### Email (Gmail IMAP)

1. Requires a Gmail account with 2-Step Verification enabled.
2. Google Account → Security → 2-Step Verification → App passwords → create
   one (e.g. named "n8n"). Copy the 16-character password.
3. In n8n: **Credentials → Add Credential → IMAP**
   - Host: `imap.gmail.com`
   - Port: `993`
   - User: your Gmail address
   - Password: the app password (not your normal Gmail password)
   - SSL/TLS: enabled
4. Open **Email Intake (IMAP)** → "Email Trigger (IMAP)" node → select the
   credential.

### Telegram (Bot API)

1. Message **@BotFather** in Telegram, send `/newbot`, follow the prompts
   (display name, then a username ending in `bot`).
2. BotFather returns a token (`123456789:ABCdef...`) — copy it.
3. In n8n: **Credentials → Add Credential → Telegram API** → paste the
   token.
4. Open **Telegram Intake** → "Telegram Trigger" node → select the
   credential.

**Note on webhooks:** Telegram delivers messages to a webhook n8n registers.
A fully local, non-tunneled n8n instance can still receive them via n8n's
built-in "Listen for test event" while the workflow editor is open, but
that's a demo/dev pattern, not an always-on production webhook — a
permanently-live setup needs n8n reachable over a public HTTPS URL (e.g. via
a tunnel, or the hosted `docker-compose.yml` path on a machine that can stay
up). Worth knowing going in, not a bug.
