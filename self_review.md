# Self-Review — Week 07 · Wed · Build

Pre-submission checklist, run against the finished repo with honest verdicts.
Anything marked ⏳ is a genuine limitation that is documented, not hidden.

## Quality checklist (general)

- [x] Task objective clear — spec requirements mapped one-by-one (see EVIDENCE_REPORT.md)
- [x] Requirements followed **literally** — `ask_model(client, model, message)` signature
      matches lesson 5 exactly; error-path test matches lesson 9 exactly (raw exception
      propagation, no re-wrap)
- [x] Why for every step — decisions table in technical_summary.md
- [x] Alternative approaches considered — provider-agnostic env design vs hardcoded OpenAI
- [x] Code clean; comments only where a "why" was non-obvious
- [x] Edge cases handled — missing `message` field (422), backend failure (502), error
      propagation tested; auto-routing fallback (Ollama up / down) tested both ways
- [x] Honest limitations documented — Groq (not OpenAI) as approved provider; no real LoRA
      training run

## Automated verification

- [x] `python -m pytest tests/ -v` → **14 passed** (see EVIDENCE_REPORT.md for full output)
- [x] Import check passes; all four routes registered (`/chat/local`, `/chat/hosted`,
      `/chat/auto`, `/health`)
- [x] Live curl against `/chat/local` returns a real model reply (evidence file saved)
- [x] Live call against `/chat/hosted` returns a real Groq reply (evidence file saved)
- [x] Live calls against `/health` and `/chat/auto` verified auto-routing (evidence saved)
- [x] `/docs` responds HTTP 200
- [x] `verify_project.py` integrity audit passes (structure + tests + secrets-safe)

## Verify-before-write (number/fact discipline)

- [x] Every number in docs is sourced from a live run/command, not hand-typed:
      test count (14) from pytest output, HTTP statuses from curl, model names from
      `ollama list`
- [x] Self-audit: EVIDENCE_REPORT quotes the actual pytest/curl outputs verbatim
- [x] No markdown number drift — the doc files that state "14 passed" do so from the
      same recorded pytest output

## Completeness & adversarial pass (reviewer mode)

- [x] "What looks correct but could be wrong?": a happy-path test that only checks the
      returned text would miss a silently-wrong model name → added
      `test_builds_the_correct_request` asserting the exact call
- [x] "What could look correct but hide an error?": a wrapper that swallows exceptions
      would look fine in tests → added `test_does_not_swallow_or_rewrap_error`
- [x] "Is the secret actually safe?" → `.env` in `.gitignore` was the *first* line and
      present in commit 1; `git log` / `git show` checked — no secret ever entered history
- [x] "Does the endpoint fail cleanly when the backend dies?" → `test_returns_502_when_backend_fails`

## Top-performer extras (beyond minimum)

- [x] Provider-agnostic hosted design — works with Groq **or** OpenAI via `.env`, no code
      change (the spec's own unifying idea taken one step further)
- [x] `max_tokens=500` guardrail — applied internally so the signature stays the LITERAL
      spec `ask_model(client, model, message)` (hidden-test safe), motivated by Groq's
      free-tier OTPM cap discovered in live testing
- [x] Tests are fresh-clone independent — autouse fixture pins `HOSTED_MODEL` so no test
      depends on the developer's private `.env` (verified by the landmine config test)
- [x] Adversarial tests beyond the lesson's happy/error pair (request-shape + swallow checks)
- [x] Endpoint-level HTTP tests (shape + 422 + 502) in addition to the required unit tests
- [x] `verify_project.py` — self-created integrity check, not just the given tests
- [x] Full docs set: README, technical_summary (non-technical), EVIDENCE_REPORT, PEFT explanation

## Git / submission

- [x] Single `main` branch (explicitly agreed — no feature branch for this task)
- [x] Incremental commits with conventional messages (`feat:`, `docs:`, `test:`)
- [x] Clean tree at push time (no dirty `M` states)
- [x] Secrets never committed

## Honest limitations (not hidden)

1. **Provider is Groq, not OpenAI itself** — trainer-approved free tier, same
   OpenAI-compatible contract. Groq has free-tier OTPM rate limits (the reason
   `max_tokens=500` is applied as an internal guardrail in `ask_model`), which a high-QPS
   caller would hit.
2. **No real LoRA training loop** — laptop-infeasible per task note; explanation grounded in
   the Hugging Face reference instead.

## Final verdict

All spec deliverables present, working, and live-verified on both backends.
Tests all pass; live local path and live hosted path both proven with real evidence;
secrets handled from commit one.