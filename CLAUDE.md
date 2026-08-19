# CLAUDE.md

Guidance for Claude Code (or any future session) working in this repo.

## What this project is

Confidence-Gated Intake Automation — a small business intake pipeline (email +
Telegram → structured tickets) where every extraction carries a **measured**
confidence score. High-confidence extractions auto-route; low-confidence ones
go to a human review queue instead of being written as if certain.

Full spec: `../Confidence_Gated_Intake_Automation_Spec.pdf` (one directory up).
Read it in full before making architectural changes — it is the source of
truth, not this file. This file is a working summary + rules of engagement.

The point of this project is the reliability layer, not the extraction. A
reviewer who has built these before will look first at `confidence.py` and
`eval/eval_report.md`. Do not let effort drift toward the dashboard.

## Hard constraints (do not violate these to "simplify")

1. **No paid services, ever.** Everything must stay free with no credit card.
   The spec's original pick was Ollama (Llama 3.1 8B, self-hosted, zero API
   key) with Groq as optional/stretch only. **This machine has 8GB RAM with
   very little free at idle** — running Ollama's 8B model here was a
   confirmed, repeated crash risk (see LOGS.md's 2026-08-16 incident and the
   pivot that followed). Groq's free tier was promoted to primary here as a
   result: still $0, still no card, but it does require a `GROQ_API_KEY` (see
   `extraction-service/.env.example`), which breaks the original "zero API
   key to clone-and-run" ideal. That's a documented, deliberate tradeoff for
   this machine's constraints, not an oversight — don't silently revert it to
   Ollama without re-checking available RAM first, and don't treat the
   GROQ_API_KEY requirement as something to hide or apologize away in the
   README; state it plainly.
2. **Confidence is never raw LLM self-reported confidence.** Do not ask the
   model "how confident are you 1-10" and use that number. Real signal comes
   from (a) self-consistency sampling — 2-3 low-temperature extraction runs,
   agreement across runs = confidence — and (b) deterministic field-completeness
   checking. This is the entire thesis of the project; a shortcut here quietly
   guts it. See spec §5.
3. **n8n owns triggers/orchestration only.** Extraction, confidence scoring,
   and idempotency logic live in the FastAPI service (`extraction-service/`)
   as real, unit-tested Python — not in n8n's node graph.
4. **Idempotency is real.** Same message delivered twice → one ticket. Enforced
   via `message_hash` (sha256 of normalized content) UNIQUE constraint in
   `message_log`, checked before extraction runs.
5. **Build in phase order (spec §7).** Do not jump to the dashboard (Phase 4)
   before Phase 1-3 are real and tested:
   - Phase 1: core pipeline, email only, fully working + tested
   - Phase 2: Telegram (should be a small diff if Phase 1's service boundary
     is clean)
   - Phase 3: evaluation — labeled set, accuracy, false-confidence rate,
     reported honestly
   - Phase 4: dashboard
   - Phase 5 (stretch): calibration check, third channel, WhatsApp docs-only
6. **The eval set is a hard requirement, not optional.** 30+ labeled messages
   (~15 clear, ~10 ambiguous, ~5 malformed/adversarial), built before/alongside
   Phase 1 extraction code so `tests/test_confidence.py` can run against it.
7. **Report the false-confidence rate honestly.** High-confidence-but-wrong
   cases are the number that matters most. A nonzero rate on the ambiguous set
   is expected with a small local model — report it, don't hide it or tune
   the eval set to avoid it.

## Flag shortcuts explicitly

If you (the assistant) substitute a simpler approach than the spec calls for
anywhere — especially raw LLM self-confidence instead of self-consistency,
skipping the eval set, or skipping ahead in phase order — say so explicitly
in your response, don't let it pass silently as "done per spec."

## Repo structure (spec §8)

```
confidence-gated-intake/
├── README.md              # leads with the reliability design, not the demo
├── docker-compose.yml     # n8n + Postgres + Ollama, one command up
├── n8n/workflows/         # exported workflow JSON
├── extraction-service/    # FastAPI: app.py, confidence.py, idempotency.py,
│                          #   models.py, tests/test_confidence.py
├── eval/                  # labeled_messages.jsonl, run_eval.py, eval_report.md
├── dashboard/             # Next.js app (Phase 4)
├── db/schema.sql
└── docs/architecture.md
```

## Local environment (this machine)

**No Docker.** Docker Desktop was installed, then fully uninstalled after it
(combined with Ollama) crashed this 8GB-RAM Mac. `docker-compose.yml` is kept
as a documented alternative for a beefier machine, but is NOT what this repo
actually runs on day to day. The real setup:

- **LLM**: Groq free tier via `extraction-service/llm_client.py`
  (`GROQ_API_KEY` in `extraction-service/.env`, gitignored — get a free key at
  console.groq.com). Ollama's original client is preserved at
  `extraction-service/ollama_client.py.bak` for anyone with RAM to spare.
- **Database**: the native Homebrew `postgresql@16` service already on this
  machine (NOT a new install, NOT Docker) — started via
  `brew services start postgresql@16`. This project uses its own isolated
  `intake` database on that instance (created via `db/schema.sql`); other
  databases on the same instance (`apiforge`, `optisense*`) belong to
  unrelated projects and must never be touched. Local connections use trust
  auth as the current OS user (`pranaysb`), no password. Default
  `DATABASE_URL` in `db.py` and `dashboard/app/db.ts` already points at this.
- **n8n**: installed globally via `npm install -g n8n@2.35.3` (pinned — latest
  had a broken transitive dependency at install time, see LOGS.md). Run with
  the plain `n8n` command, no Docker. `n8n@latest`/unpinned may work again
  later; check before repinning.
- **Extraction service**: plain Python venv (`extraction-service/.venv`) +
  `uvicorn`, no container.
- **Dashboard**: plain `npm run dev`, no container.

See LOGS.md's entries from 2026-08-16 onward for the full incident, root
causes (Docker's VM *and* this machine's tight RAM independently mattered),
and every step of the recovery/pivot.

## Commands

- Run extraction-service tests: `cd extraction-service && source .venv/bin/activate && python3 -m pytest`
- Run eval: `cd eval && python3 run_eval.py`
- Extraction service dev server: `cd extraction-service && source .venv/bin/activate && uvicorn app:app --reload`
- Start Postgres (if not running): `brew services start postgresql@16`
- Start n8n: `n8n start` (or just `n8n`)
- Dashboard dev server: `cd dashboard && npm run dev`

## Logs

Significant build decisions, environment quirks, and phase completions are
recorded in [LOGS.md](LOGS.md). Update it as you go — don't batch it at the
end.
