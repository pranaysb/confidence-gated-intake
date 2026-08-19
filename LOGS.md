# Build Log

Reverse-chronological. One entry per session/decision, not per file edit.

## 2026-08-18 — Project kickoff

- Received full build spec (`Confidence_Gated_Intake_Automation_Spec.pdf`,
  one directory up from this repo). Read in full; not summarized.
- Environment check on this Mac: Docker and Ollama were **not** installed
  (Docker's `/usr/local/bin/docker` symlink was broken — pointed at a
  non-existent `/Applications/Docker.app`; `ollama` not found anywhere).
  Python 3.12.4, Node 24.7.0, git 2.39.3 already present.
- Disk: 20GB free at kickoff. Combined install estimate ~9-10GB
  (Docker Desktop app+images ~3-4GB, Ollama app+Llama 3.1 8B model ~5GB).
  Confirmed with user before installing.
- Installed via Homebrew:
  - `brew install ollama` — failed first attempt (`curl: (35) Recv failure:
    Connection reset by peer` fetching the bottle from ghcr.io — transient
    network issue, not a real blocker). Retried, succeeded.
  - `brew install --cask docker` — Docker.app itself downloaded and moved to
    `/Applications/Docker.app` successfully, but the post-install step that
    symlinks the `docker-compose` CLI plugin into `/usr/local/cli-plugins`
    needs `sudo` and Homebrew can't prompt for a password non-interactively
    in this environment. **Action needed from the user:** launch Docker
    Desktop once from `/Applications` and click through its first-run setup
    (it will ask for the admin password itself for its privileged helper —
    this is normal Docker Desktop behavior, unrelated to the brew failure).
    After that, `docker compose version` should work; if the CLI plugin
    symlink is still missing, `brew reinstall --cask docker` will retry it
    now that Docker.app exists.
- Started `ollama serve` in the background and kicked off
  `ollama pull llama3.1:8b` (~4.7GB, quantized default).
- Repo scaffolded at `confidence-gated-intake/` (sibling to the spec PDF)
  matching spec §8 structure exactly. `git init` run inside it — this is
  its own repo, separate from the parent "AI Automations" folder (which is
  not a git repo).
- Decision: run Ollama **natively** (`ollama serve`), not inside
  `docker-compose.yml`. Ollama's official Docker image doesn't get Metal
  GPU acceleration on Apple Silicon — running natively is meaningfully
  faster for local dev and is still zero-cost/zero-API-key, so it doesn't
  violate the "everything free" constraint. `docker-compose.yml` covers
  n8n + Postgres only; the extraction service reaches Ollama at
  `http://host.docker.internal:11434` from inside Docker.

## 2026-08-16 — Crash, full uninstall, and pivot to a Docker-free / Groq stack

**Incident.** While testing the extraction pipeline end-to-end (Docker
Desktop running Postgres + n8n + extraction-service, plus `ollama serve`
running natively with the Llama 3.1 8B model loaded), the user's Mac became
unstable and shut down. User asked to uninstall everything installed this
session and clear related caches, explicitly *not* touching anything
pre-existing.

**Recovery (same session):**
- Stopped `docker compose` stack, killed `ollama serve`, quit Docker Desktop.
- `brew uninstall ollama` + `rm -rf ~/.ollama` — removed the ~4.9GB model.
- Docker Desktop: `brew uninstall --cask docker` reported "not installed"
  (the cask was never fully registered — the original install's sudo step
  had failed, see the 2026-08-18 entry above... [note: that entry is
  timestamped 2026-08-18 but appears to actually be same-day/adjacent to
  this one; dates in this log may be slightly off from system clock
  confusion earlier in the session — treat ordering, not absolute dates, as
  authoritative between these two entries]). Removed manually instead:
  `/Applications/Docker.app` (2.1GB) and
  `~/Library/Containers/com.docker.docker` (3.4GB, mostly the VM disk image
  `Docker.raw`) — this second path couldn't be fully `rm -rf`'d due to a
  macOS sandbox-protected metadata plist, but its actual disk-heavy contents
  (the VM disk) were removed before that permission error hit. Also cleared
  `~/.docker`, `~/Library/Application Support/Docker Desktop`, Docker
  preferences/caches/HTTPStorages, and stray `/usr/local/bin` symlinks.
- `brew cleanup -s`, `npm cache clean --force`, `pip cache purge` — freed
  another ~930MB combined.
- Net result: disk went from 14GB free (mid-crash) to 26GB free.
  **Confirmed untouched:** the native Homebrew `postgresql@16` service and
  its data (per explicit user instruction) — though it was independently
  found to be in a stopped/error state afterward (see below); this was not
  caused by the uninstall steps.
- Project source files (`confidence-gated-intake/`, including
  `extraction-service/.venv` ~51MB and `dashboard/node_modules` ~250MB) were
  deliberately left alone — small, plain project files, not what caused the
  incident.

**Root-cause discussion with user.** Explained the likely cause: Docker
Desktop's Linux VM (continuous RAM reservation + ~3.4GB disk) running
alongside Ollama loading a ~4.9GB model into memory at the same time. Laid
out a lighter alternative architecture (Groq for LLM instead of local
Ollama, `npx`/npm n8n instead of Docker, Supabase or existing native
Postgres instead of a new Docker Postgres) and asked which pieces to adopt.
User initially deferred ("let me think"), then came back wanting: **n8n
installed locally (not Docker)**, everything else as originally planned.

**Rebuilding, this time checking resources before reinstalling anything
heavy:**
- Checked actual RAM before touching Ollama again:
  `sysctl hw.memsize` → **8GB total**. `top`/`memory_pressure` → only
  ~326MB unused at idle, before even starting Ollama. This is a hard
  constraint this machine has regardless of Docker — running an 8B local
  model here was always going to be tight-to-risky. Surfaced this to the
  user explicitly before proceeding (did not silently plow ahead a second
  time). User chose: **keep the LLM on Groq's free cloud tier instead of
  local Ollama**, keep n8n and Postgres local/native as planned.
  - Ollama had already been briefly reinstalled via brew at this point (no
    model pulled yet) — uninstalled again immediately once the Groq
    decision was made. Nothing Ollama-related remains installed.
- **Postgres**: rather than reinstalling Docker just for this, pointed the
  project at the **existing native `postgresql@16`** Homebrew service
  already on this machine. Found it in a stopped `error` state with a
  **stale `postmaster.pid` lock file** (from PID 553, confirmed dead — that
  PID had been reassigned to an unrelated app by macOS). Standard, safe
  recovery: removed the stale lock file, `launchctl bootout` to clear a
  stuck launchd registration, then `brew services start postgresql@16`
  succeeded. **This service also hosts unrelated pre-existing databases**
  (`apiforge`, `optisense`, `optisense_dev`, `optisense_edge_dev`,
  `optisense_test`) — did not touch any of them. Created a new, isolated
  `intake` database for this project only and applied `db/schema.sql` to
  it. Local auth is trust-based for the current OS user (`pranaysb`), no
  password needed. Updated `db.py`'s default `DATABASE_URL`,
  `dashboard/app/db.ts`, and `dashboard/.env.example` accordingly (was
  previously pointing at a Docker-mapped `localhost:5433`, which no longer
  applies to the default path).
- **n8n**: `npm install -g n8n` (unpinned/latest) failed —
  `ETARGET No matching version found for ai@7.0.67`, a broken transitive
  dependency in the very latest release at install time (`npm view ai
  versions` showed it existed, so likely a registry propagation issue tied
  to how new that release was, not a real missing version). Pinned to
  `n8n@2.35.3` instead, which installed cleanly (~2.3GB in
  `node_modules`, no VM, no background daemon unless started — a very
  different resource profile than Docker Desktop's VM). Worth retrying
  `n8n@latest` in a future session in case the registry issue clears.
- **LLM swap to Groq**: renamed `extraction-service/ollama_client.py` →
  `ollama_client.py.bak` (kept for reference / for anyone with more RAM to
  revert to it) and wrote `extraction-service/llm_client.py` calling Groq's
  OpenAI-compatible `/chat/completions` endpoint
  (`llama-3.1-8b-instant`, `response_format: json_object`, same
  system-prompt injection-defense stance as the original). Updated
  `confidence.py`'s import accordingly. This is a documented, deliberate
  deviation from the spec's "no API key required to clone-and-run" ideal —
  see CLAUDE.md constraint #1. `python-dotenv` added so
  `extraction-service/.env` (gitignored; see `.env.example`) is loaded
  automatically by `app.py`, a new `conftest.py`, and `run_eval.py`.
  Updated `tests/test_confidence.py`'s eval-set-smoke-test skip condition
  to check for `GROQ_API_KEY` instead of a reachable Ollama instance. All
  12 pure-logic confidence tests re-verified passing after the refactor
  (they were already Ollama-independent by design, via the injectable
  `extractor` parameter — only the live eval-set smoke tests, which skip
  without a key, were affected).
- `docker-compose.yml` kept in the repo (spec asks for a literal
  one-command-up story) but re-documented at the top as the untested,
  heavier alternative path, not what this repo actually runs on day to day.
  Its `extraction-service` service now loads `GROQ_API_KEY` via `env_file`
  instead of the old `OLLAMA_HOST`/`OLLAMA_MODEL` vars, so it stays
  consistent with the current code if anyone does use it.
- User was still asked to sign up for a free Groq API key themselves
  (console.groq.com) — account creation isn't something this assistant does
  on a user's behalf.

## 2026-08-16 (cont'd) — Groq keys wired up, model swap, full test suite green

- User provided 14 Groq API keys for round-robin use (to spread load across
  free-tier rate limits — self-consistency sampling makes 3 calls/message,
  and a 30-message eval run is 90 calls back to back). Validated all 14
  against `GET /openai/v1/models`: **12 valid, 2 invalid** (keys 7 and 9 in
  the order given returned `401 Invalid API Key`). Stored the 12 working
  keys as comma-separated `GROQ_API_KEYS` in `extraction-service/.env`
  (gitignored). First attempt at writing this file transcribed one of the
  invalid keys by mistake — caught and fixed before anything ran against it.
- Rewrote `llm_client.py`'s key handling: `GROQ_API_KEYS` (comma-separated,
  falls back to singular `GROQ_API_KEY`) round-robins via
  `itertools.cycle` behind a lock; `extract_once` retries up to 3 keys on a
  401/429 before giving up, so one bad or momentarily-limited key doesn't
  fail the whole extraction.
- **Model swap**: the spec's named model, and this project's original
  `llama-3.1-8b-instant`, is **no longer in Groq's model catalog** (`GET
  /models` doesn't list it; a live request 404s with "does not exist or you
  do not have access to it" — Groq has rotated their hosted lineup since
  the spec was written). Checked `GET /models` for what's actually live,
  test-drove three candidates for JSON-mode extraction quality/cleanliness
  (`openai/gpt-oss-20b`, `allam-2-7b`, `qwen/qwen3.6-27b`) with real
  business-message prompts. Picked **`openai/gpt-oss-20b`**: clean JSON in
  the `content` field (reasoning trace, if any, lands in a separate
  `reasoning` field that's simply not read), correct extractions on manual
  spot checks, and it's an actual open-weight model in spirit-if-not-name
  with the original Llama pick. Updated `GROQ_MODEL` default in
  `llm_client.py` and `.env.example` accordingly.
- Full test suite re-run after both changes: **42/42 passed** — the 12
  pure-logic tests plus, for the first time, all 30 live eval-set smoke
  tests (real Groq calls, ~60s total), including confirming the prompt-
  injection case (`malformed_005`) still forces `confidence == 0`. This is
  the first real end-to-end confirmation the Groq pivot actually works, not
  just compiles.
- Not yet done: the formal Phase 3 `run_eval.py` pass (accuracy /
  false-confidence-rate numbers for the README), full n8n workflow import
  and manual trigger test, and dashboard smoke test against live data.

## 2026-08-19 — Telegram bot wired up; email still pending

- User set up n8n's owner account themselves (in their own browser — this
  assistant does not create accounts or set passwords). Confirmed n8n
  reachable and both workflows imported cleanly.
- User created a dedicated Telegram bot via @BotFather
  (`@pranaybusinessinboxbot`) and provided the bot token directly in chat.
  Wired it in via n8n's **file-based credential import**
  (`n8n import:credentials`) rather than typing it into n8n's live web UI —
  same reasoning as writing the Groq keys to `.env`: this is local file
  config for the user's own tool, not entering a credential into a
  third-party form. Had to add an explicit `id` (UUID) to the credential
  JSON — n8n's import rejects records without one
  (`SQLITE_CONSTRAINT: NOT NULL constraint failed: credentials_entity.id`).
  n8n was stopped before running the import (avoids SQLite lock contention
  with the live server) and restarted after.
- Updated `n8n/workflows/telegram_intake.json`'s Telegram Trigger node to
  reference the imported credential's real ID, re-imported via CLI
  (confirmed via `n8n list:workflow` that this updated the existing
  workflow in place, no duplicate created).
- **Caught a real bug while doing this**: both workflow JSON files still
  pointed their HTTP Request node at `http://extraction-service:8000/extract`
  — the Docker-network hostname from the original spec's containerized
  design. Since this project runs n8n and extraction-service both natively
  now (no Docker, see the 2026-08-16 entries), that hostname doesn't
  resolve at all outside a Docker network. Fixed both to
  `http://localhost:8000/extract` and added a note in each workflow
  pointing out the swap needed if someone does use the `docker-compose.yml`
  path instead. Verified post-fix by exporting the workflow back out via
  `n8n export:workflow` and checking the credential ID and URL directly
  rather than trusting the edit went through.
- **Email channel**: user doesn't want to use their personal Gmail. They
  asked about temp-mail inboxes as an alternative — explained these
  generally don't support IMAP (n8n needs actual IMAP polling, not a web
  page) and expire too fast to be useful here, so that path was dropped.
  Offered a dedicated new Gmail / Outlook.com / Zoho Mail as free
  IMAP-capable alternatives. User settled on: set up IMAP through Gmail
  after all (a Gmail account either way, mechanism TBD by user). Not yet
  wired in as of this entry — waiting on the App Password.
- Sensitive scratch files (the plaintext credential JSON used for import,
  and the exported workflow used to verify it) were deleted from the
  scratchpad immediately after use.

## 2026-08-19 (cont'd) — Email channel wired up; both channels now live-ready

- User confirmed 2-Step Verification is required for Gmail App Passwords
  (asked directly; confirmed there's no way around it for this method short
  of switching to Gmail OAuth2, which is meaningfully more setup). User
  enabled it and generated an app password, named "claude" in Google's UI,
  for a **new, dedicated account** (`pranaysb9@gmail.com`) rather than their
  personal Gmail — matches the same "dedicated business persona" pattern as
  the Telegram bot.
- Wired in via the same file-based `n8n import:credentials` pattern used for
  the Telegram token: stop n8n, write a credential JSON (type `imap`, host
  `imap.gmail.com`, port 993, `secure: true`) to a scratch file with an
  explicit UUID `id`, import, update `email_intake.json`'s Email Trigger
  node to reference the real credential ID, re-import the workflow, restart
  n8n. Verified via `n8n export:workflow` that both the credential ID and
  the (already-fixed) `localhost:8000` URL are correct.
- **Additionally verified the credential actually authenticates** — logged
  into `imap.gmail.com:993` directly with Python's `imaplib` using the same
  user/password before considering this done, rather than trusting the n8n
  import succeeded silently. Login confirmed OK.
- App password was stripped of the spaces Google displays it with (Google
  shows it as four 4-character groups; only the concatenated 16 characters
  are the actual secret) before storing.
- Scratch files containing the plaintext app password were deleted
  immediately after the verification step.
- **Both channels are now fully wired**: credentials attached, endpoint
  URLs correct, IMAP login independently verified. Workflows are still
  imported as `active: false` (as authored) — activating them starts a live
  listener that will call the Groq API and write to the production
  `tickets`/`review_queue` tables on any real incoming message, so that's
  left as an explicit decision for the user rather than something done
  silently as a side effect of wiring credentials.

## 2026-08-19 (cont'd) — Email channel debugged to a genuine live pass; Telegram blocked on public webhook

Activated both workflows to test for real. Found three separate real bugs
along the way, each verified and fixed rather than assumed:

1. **Telegram registration fails outright.** `n8n publish:workflow` for the
   Telegram workflow entered an infinite exponential-backoff retry loop:
   `400 Bad Request: An HTTPS URL must be provided for webhook`. Telegram
   requires a public HTTPS endpoint to deliver updates to; a bare
   `localhost:5678` n8n instance has nothing to offer. Confirmed independently
   via `getWebhookInfo` on the bot (empty `url`). **Unpublished the Telegram
   workflow** to stop the pointless retry storm — this needs a public tunnel
   (ngrok/cloudflared, still free) to actually go live, not a code fix.
2. **Inbox backlog.** The Gmail account (`pranaysb9@gmail.com`) turned out to
   not be a truly fresh account — 261 unread messages already in it (Google
   Skills-lab notifications, device setup, security alerts). The IMAP
   trigger's default search is `UNSEEN`, so activating it would have tried
   to run the *entire backlog* through the Groq extraction pipeline as if
   each were a real customer message, burning API quota and filling
   `tickets`/`review_queue` with garbage. Confirmed via debug-level n8n logs
   (`N8N_LOG_LEVEL=debug`) showing `New emails received... numEmails: 261`
   right on connect. Asked the user how to handle it; they chose to keep the
   account. Marked all 261 as read via direct IMAP `STORE +FLAGS \Seen`
   (non-destructive, nothing deleted) so only genuinely new mail triggers
   the pipeline going forward.
3. **`ECONNREFUSED` calling the extraction service, despite it demonstrably
   being up** (`curl http://localhost:8000/health` succeeded seconds before
   and after each failed execution). Root cause, confirmed via
   `node -e "require('dns').lookup('localhost', {all:true}, ...)"`: Node
   resolves `localhost` to `::1` (IPv6) first, but `uvicorn --host 0.0.0.0`
   only binds IPv4 (confirmed via `lsof -iTCP:8000` showing `*:8000` with no
   IPv6 listener). n8n's HTTP client doesn't fall back to IPv4 the way curl
   does. Fixed by changing both workflows' HTTP Request node URL from
   `localhost:8000` to `127.0.0.1:8000` explicitly. Re-imported, republished
   (workflow import silently deactivates a changed active workflow --
   re-published after re-importing), restarted n8n.
4. Debugged all of this by reading n8n's actual execution records out of its
   SQLite DB directly (`execution_entity`, `execution_data` tables) rather
   than guessing from the editor UI, since this assistant doesn't have a
   logged-in browser session there. Cross-checked file-based edits against
   what n8n's CLI export reported, every time, rather than trusting an edit
   "should have" applied.

**Result: sent a real email through Gmail → confirmed it flowed through
n8n's IMAP trigger → extraction-service → Groq → confidence scoring →
correctly landed in `tickets` with the right fields (name, contact, HVAC,
high urgency, confidence 1.0).** This is the first genuine, live,
end-to-end pass of the email channel — not a curl test against the
endpoint directly. Test ticket and message_log row deleted after
confirming. Telegram is code-complete and credential-wired but not
live-testable without a public tunnel; see README for status.

## 2026-08-19 (cont'd) — Telegram channel also verified live end-to-end

- User wanted Telegram live too, not just wired. Set up a free Cloudflare
  Quick Tunnel (`cloudflared tunnel --url http://localhost:5678`, no
  account needed) to give n8n a public HTTPS URL --
  `https://knitting-somewhat-printable-seven.trycloudflare.com`. Note:
  quick tunnels are ephemeral -- this URL dies when the `cloudflared`
  process stops and a new one is issued next time; not a stable long-term
  URL. Fine for demo/testing, not for a permanently-running bot.
- Restarted n8n with `WEBHOOK_URL` pointed at the tunnel (n8n logged a
  deprecation notice preferring `N8N_WEBHOOK_URL` instead -- functionally
  still worked, but worth switching next time). Hit a port-conflict restart
  race (killed the old process, health-checked too early against a
  not-yet-dead listener, new process then failed to bind and exited
  entirely) -- resolved by confirming via `lsof -iTCP:5678` that nothing
  was actually listening before starting cleanly once more.
- Published the Telegram workflow again; confirmed via Telegram's own
  `getWebhookInfo` API that the webhook URL is now registered
  (previously empty). Workflow confirmed `active=1` in n8n's DB.
- **Could not test the final leg myself** -- receiving a Telegram message
  requires an actual Telegram account messaging the bot, which isn't
  something this assistant can do. Asked the user to send a real message
  to `@pranaybusinessinboxbot` themselves.
- User sent: *"Hi this is a test, my kitchen sink is leaking, please call
  me at 555-0100"*. Confirmed in the database: correctly extracted as
  customer_name="Pranay" (from Telegram's own first_name, prepended per
  the workflow's design), customer_contact="555-0100",
  request_type="plumbing", urgency=null (not stated in the message --
  correctly left null rather than guessed), confidence=0.75 (1.0
  consistency x 0.75 completeness, 3 of 4 fields present), auto-routed to
  `tickets`. This is the confidence design working exactly as intended on
  a real, live, unscripted message -- not a curated eval-set case.
- **Both channels are now genuinely proven end-to-end**, not just built
  and unit-tested. Test ticket and message_log row deleted after
  confirming.

## 2026-08-19 (cont'd) — Phase 5 stretch: confidence calibration check

- Added `compute_calibration()` to `eval/run_eval.py`: buckets all 30 eval
  messages by confidence into 5 ranges, compares mean confidence per bucket
  against actual accuracy per bucket, reports Expected Calibration Error
  (ECE) and a reliability table in `eval_report.md`.
- Deliberately used a **different correctness definition** than the
  headline accuracy metric: field-level match against the labeled
  expectation for every message uniformly (including ambiguous ones, where
  a correctly-null output counts as correct), versus the headline metric's
  category-dependent definition (routing-correctness for
  ambiguous/malformed, field-match for clear). Documented explicitly in the
  report why these differ -- calibration asks "is the confidence number
  itself an accurate probability of correctness," not "did the system make
  the right routing call," and conflating the two would have been
  misleading.
- **Found a real, interesting result, not just a number**: the 0.0-0.2
  confidence bucket shows ~86% actual accuracy despite ~0% mean confidence
  -- a large apparent under-confidence gap. Investigated rather than just
  reporting it: this happens because `completeness_score` penalizes a
  `null` field identically whether the model *should* know the answer or
  *correctly recognizes it can't*. Most low-confidence messages are
  genuinely ambiguous ones where null is the right answer, so they score
  low confidence (appropriately deferring) while still being "field-level
  correct" (null matches null). This is an honest finding about a real
  design limitation -- the confidence score conflates "complete" with
  "correct" -- written into the report as a concrete next improvement
  rather than smoothed over or hidden.
- First draft of the "which bucket is most over-confident" callout used a
  hardcoded message count ("only 2 messages") based on one run's numbers.
  Caught before committing that the eval calls a live, non-deterministic
  LLM -- re-running produced different bucket populations (2, then 4, then
  3 messages in that bucket across three runs). Rewrote it to compute the
  worst-gap bucket and its count dynamically from the actual results
  instead of a stale guess, since a hardcoded number that goes wrong on
  the next run would undermine exactly the honesty the calibration section
  is trying to demonstrate.
- Full test suite (42/42) re-confirmed passing after the change; verified
  the calibration report renders correctly by re-running `run_eval.py`
  three times and eyeballing the output each time, not just once.

## 2026-08-19 (cont'd) — Deployment prep: dashboard's eval report moved into the DB

Started setting up dashboard deployment (Vercel + a cloud Postgres, since
n8n/extraction-service stay local per the spec's own guidance on
serverless not suiting always-on automations -- see README's Deployment
section).

- **Supabase blocked**: account already at its 2-free-project cap
  (account-wide, not per-org -- confirmed the limit persists across the
  org switcher). Declined creating a second Supabase account to route
  around it (against most providers' ToS, and account creation isn't
  something this assistant does regardless). Used **Neon.tech** instead --
  a genuinely separate free provider, not a workaround.
- Applied `db/schema.sql` to the new Neon database, verified all 4 tables
  created.
- **Caught a real bug before it shipped**: `dashboard/app/page.tsx` was
  reading `eval_report.md` from a sibling directory
  (`path.join(process.cwd(), "..", "eval", "eval_report.md")`), which
  works locally (`dashboard/` and `eval/` side by side) but would silently
  break on Vercel with Root Directory set to `dashboard` -- that config
  typically doesn't expose sibling directories to the deployed function at
  runtime. Rather than discovering this after a broken deploy, fixed it
  properly: added a `report_markdown TEXT` column to `eval_runs`,
  `run_eval.py` now stores the full rendered report text in the DB on
  every run, and the dashboard reads `report_markdown` from the latest
  `eval_runs` row as the source of truth (the filesystem read is kept as a
  local-dev-only fallback, clearly commented as such).
- Migrated the new column onto both existing databases (local `intake` and
  the new Neon one) via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
  Re-ran `eval/run_eval.py` and confirmed via the dashboard (still running
  locally) that it now renders the report from `report_markdown`, not the
  file -- verified by reading the actual page content, not assumed from
  the code change alone.
- Verified before committing: `npx tsc --noEmit` (no type errors),
  `npm run build` (production build succeeds), and the full pytest suite
  (42/42) -- a build artifact (`tsconfig.tsbuildinfo`) briefly appeared
  untracked from the build check; added to `.gitignore` before it could
  get committed.

## 2026-08-19 (cont'd) — Dashboard deployed to Vercel, debugged with real API access

First deploy attempt returned a bare `404: NOT_FOUND` from Vercel's edge
(not a Next.js 404 page -- infrastructure-level, no matching build).
Debugged with a project-scoped Vercel API token (user generated it, same
pattern as Groq/Gmail: they create it, hand it over, get deleted from
scratch files after use) rather than guessing from the outside.

- First token the user pasted came back `{"error":"User not found"}` from
  `/v2/user` -- asked for a fresh one rather than assuming it was my
  mistake. Second token hit the same error on the *account* endpoint, but
  worked fine on a *project* endpoint (`/v9/projects`) -- turned out to be
  a project-scoped token (visible in their screenshot: scope
  "confidence-gated-intake"), which can't call account-level endpoints.
  Not a bad token, just the wrong endpoint for its scope -- caught by
  trying a different endpoint rather than asking for a third token.
- Root cause of the 404, confirmed via the API rather than guessed:
  `GET /v9/projects` showed `rootDirectory: null, framework: null` --
  the "Root Directory: dashboard" setting from the manual Vercel UI setup
  never actually saved. Vercel had been building from the repo root
  (no valid Next.js app there), producing a deployment that was
  technically READY but had nothing real to serve.
- Fixed directly via the API: `PATCH /v9/projects/{id}` with
  `{"rootDirectory": "dashboard", "framework": "nextjs"}`. Confirmed the
  patch applied by reading the values back, not just trusting a 200
  response.
- Existing settings changes don't retroactively fix a deployment --
  triggered a fresh one via `POST /v13/deployments` (redeploy of the
  latest commit against corrected settings), polled `readyState` until
  `READY`.
- Verified the fix by actually loading the production URL, not just
  checking deployment status: title changed from "404: NOT_FOUND" to
  "Confidence-Gated Intake — Dashboard", full page content confirmed via
  `get_page_text`.
- **Found a second real gap while verifying**: the eval report text was
  rendering correctly, but the summary tiles (accuracy, false-confidence
  count) showed "—". Investigated rather than assuming success: queried
  Neon's `eval_runs` table directly -- **0 rows**. `run_eval.py` had only
  ever been run against the local Postgres `DATABASE_URL`, never against
  Neon, so the deployed dashboard had no eval data of its own to read from
  `getLatestEvalRun()`. The report text rendering anyway was a separate,
  interesting finding: Next.js's build-time output file tracing had
  apparently detected and bundled the sibling `eval/eval_report.md` file
  referenced by the (now-fallback-only) disk-read path, despite Root
  Directory scoping -- a real but implicit/fragile behavior, not something
  to rely on. The DB-backed `report_markdown` fix from the previous entry
  was the right call regardless of this accident working out.
  Fixed properly by running `eval/run_eval.py` with `DATABASE_URL` pointed
  at Neon directly, confirmed the row landed (`accuracy: 0.8276,
  false_confidence_count: 3, report_markdown` populated), then reloaded
  the production URL and confirmed the summary tiles now show real
  numbers instead of placeholders.
- Vercel token used only in shell commands (never written to a repo file);
  no cleanup needed there. User may want to revoke/rotate it from
  vercel.com/account/tokens now that setup is done, purely as routine
  hygiene for a token that's served its purpose.

**Dashboard is now genuinely live**: https://confidence-gated-intake.vercel.app

## 2026-08-19 (cont'd) — Dashboard UI redesign

User feedback: UI looked "funky," wanted premium/elegant/modern instead.
Rebuilt against the `dataviz` skill's method rather than eyeballing colors:

- Swapped the ad-hoc dark palette for the skill's validated reference
  tokens (dark column) -- chart surface, ink, gridline, and status colors
  are the exact hex values from `references/palette.md`, not invented.
- Confidence histogram rebuilt to the mark spec: bars capped at 24px,
  4px rounded data-ends, hover reveals the exact count (was a bare
  `title` attribute before).
- Review queue badges switched from arbitrary red/yellow/green thresholds
  to the fixed status palette (good/warning/critical), each still paired
  with the confidence percentage as text -- never color alone.
- Eval report was a raw `<pre>` dump of markdown source (part of what
  read as "funky"). Now parsed with `marked` and rendered as real HTML
  (headings, tables, bold, lists), styled to match the rest of the page.
- Restructured layout into a 2-column grid (histogram + failure-rate
  table side by side on desktop, stacking on mobile -- checked at both
  widths, not just assumed from the CSS).
- Along the way: `npm install` hit `ENOSPC` -- disk was at 649MB free,
  a system-wide issue unrelated to this session (confirmed my own scratch
  usage was trivial). Cleared npm/Homebrew caches to get enough headroom
  to finish, flagged the underlying disk pressure to the user rather than
  silently working around it every time it recurs.
  Also noticed `npm audit` flagging Next.js 14.2.15 at critical severity
  (accumulated CVEs); bumped to the latest 14.2.x patch (14.2.35) --
  drops it to high/fewer-CVEs without a major-version jump. Not fully
  clean (some advisories need Next 16+), left as a known tradeoff rather
  than forcing a breaking upgrade mid-redesign.
- Verified with `tsc --noEmit`, `npm run build`, and by actually loading
  the page (desktop + mobile viewport) with live test data pushed through
  the pipeline -- not just reading the JSX and assuming it renders right.

<!-- New entries go above this line -->
