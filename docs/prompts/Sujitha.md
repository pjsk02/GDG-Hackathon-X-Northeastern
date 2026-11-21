# Sujitha - Role D: Gemini writer and guardrails

Branch: `Sujitha-Branch` · Your files: see `Sujitha-Branch` in docs/team/ownership.json · Progress log: docs/progress/Sujitha.md

## Kickoff prompt (paste into your agent after the starter prompt)

```text
You are Sujitha's coding agent for the SentinelDesk hackathon repo (https://github.com/pjsk02/GDG-Hackathon-X-Northeastern). I am Sujitha, role D (Gemini reply writer and guardrails: number-and-promise guard, prompt-injection rule, PII "What the AI saw").

1. Make sure you are inside the repo on branch Sujitha-Branch with the latest main merged. If not, do the starter checks in docs/prompts/00-starter.md first.
2. Fetch my plan from GitHub: https://raw.githubusercontent.com/pjsk02/GDG-Hackathon-X-Northeastern/main/docs/prompts/Sujitha.md (the same file is at docs/prompts/Sujitha.md). Also read CLAUDE.md, docs/team/README.md and docs/PRD.md.
3. Follow the plan one step at a time, in order. Inside a step, work autonomously: split independent pieces across subagents (builder for code in my files, Explore for reading other people's code, test-runner for checks, ownership-reviewer before pushing) and run them in parallel when they touch different files. Only ask me when you are truly blocked (for example, I still need to put GEMINI_API_KEY in .env).
4. Edit only my files (docs/team/ownership.json, Sujitha-Branch). Push only to Sujitha-Branch. Never push to main.
5. When a step's "Done when" list is met, run /ship-step <N>, give me the report, and stop. Start the next step only after I reply "yes, you can proceed".

Start with Step 1 now.
```

## What you own and who depends on you

- sentinel/writer.py (prompt, fallback draft, citation checks), sentinel/claims.py, sentinel/injection.py,
  sentinel/pii.py, agent/llm_router.py, eval/cases_guardrails.jsonl (new).
- The pipeline already calls `detect_injection(text)` (adds rule R7) and `check_claims(reply, verified)`
  (adds R6 findings), and copies `SentinelDraft.briefing` into `result.briefing`. Kaushik shows all of them.
- Je's eval loads your `eval/cases_guardrails.jsonl` if it exists.

## Step 1 - Make the Gemini path work (F5)

- Put your key in .env (`GEMINI_API_KEY=...`, never commit it) and set `LLM_PROVIDER=gemini`.
  Check in AI Studio which model names your key can use; set `GEMINI_MODEL=<name>` in your .env (do not edit
  shared/settings.py). Note a fast model for drafting.
- Build the data locally (CLAUDE.md "Setup", hash index is fine), then draft 5 real tickets:
  `python -m sentinel.pipeline "<ticket text>"`. Fix agent/llm_router.py if the SDK call fails
  (structured output with `response_schema=SentinelDraft`).
- Log latency per call and the model name to use in docs/progress/Sujitha.md (teammates copy it).

Done when: 5 Gemini drafts come back grounded (at least one verified citation each, or a correct refusal), tests pass.

## Step 2 - Number-and-promise guard (N4)

Implement `check_claims(reply, verified)` in sentinel/claims.py (contract in the file): numbers, money
(€, $, EUR, USD), percentages, durations and dates (EN and DE: "24 hours", "48 Stunden", "within 2 days",
"bis Freitag"), and promise phrases ("we guarantee", "full refund", "free of charge", "wir erstatten",
"kostenlos") must appear in some verified quote; otherwise return a `GuardFinding`. Ignore TKT-ids.

Done when: `tests/test_claims*.py` has at least 12 pass/fail cases in both languages and passes.

## Step 3 - Prompt-injection rule R7 (N9) and guardrail cases

- Implement `detect_injection(text)` in sentinel/injection.py (contract in the file), EN and DE, with tests that
  include normal tickets that must NOT trigger ("please ignore my previous email").
- Create `eval/cases_guardrails.jsonl` (same fields as eval/sentinel_cases.jsonl, `expect_escalation`): at least 8
  cases covering injections (EN/DE), invented SLA promises, number traps and PII.

Done when: tests pass, and `python -m eval.sentinel_eval --sample 5 --compare extractive` shows your cases caught
(after Je's Step 4 merges; until then, run them through `SentinelAgent().triage` in a quick check).

## Step 4 - Writer upgrades

In sentinel/writer.py:
- Add a prompt rule for `briefing`: one English sentence, at most 25 words, what the ticket is about, no advice.
- Strengthen refusals for commitments (refund, credit, legal) so the reply says a colleague will follow up.
- German replies: natural, formal ("Sie"); keep citations-first and quotes in their original language.
- Measure on 20 validation tickets: grounded rate and refusal rate, extractive vs gemini. Log the numbers.

Done when: tests in `tests/test_writer*.py` pass (prompt contains the rules, extractive fallback unchanged), and
the measurement is logged.

## Step 5 - PII and "What the AI saw" (B3)

- Improve sentinel/pii.py: fewer false positives (dates, version numbers, ticket ids), German phone numbers,
  German IBANs, street addresses if cheap. Add `mask_spans(text) -> list[tuple[int, int, str]]` so the UI can
  highlight what was masked. Keep `mask_pii(text)` unchanged.
- `result.pii_masked_body` already holds the masked text; write in your log how Kaushik should highlight spans.

Done when: `tests/test_pii*.py` passes with tricky cases. Open a PR into main and tell Je.
