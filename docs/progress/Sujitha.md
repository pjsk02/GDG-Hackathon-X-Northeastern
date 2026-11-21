# Sujitha — Progress Log (Role D: Gemini writer and guardrails)

## Step 1: Make the Gemini path work (F5)

### Recommended `.env` Gemini settings for teammates
Copy these into `.env` (do not edit `shared/settings.py`):
```env
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_THINKING_LEVEL=low
```
- **Fastest reliable drafting model:** `gemini-3.5-flash-lite` (~1.1–1.5 s per grounded `SentinelDraft` JSON call with `GEMINI_THINKING_LEVEL=low` or `minimal`; supports structured output with `response_schema=SentinelDraft`).
- **Backup fast model:** `gemini-3.1-flash-lite` (~1.7 s with `GEMINI_THINKING_LEVEL=low`).
- **Models to avoid right now:**
  - `gemini-4-hydrogen` / `gemini-3.5-flash`: slow / hitting `504 DEADLINE_EXCEEDED` under load (`gemini-4-hydrogen` also rejects `GEMINI_THINKING_LEVEL=minimal` with HTTP 400).
  - `gemini-3.8-flash`: returning `503 UNAVAILABLE` (high demand).
  - `gemini-2.5-flash` / `gemini-2.5-flash-lite`: returning `404 NOT_FOUND` ("no longer available to new users").
- **Embedding models listed for this key (for Rithwik / Role C):** `models/gemini-embedding-001` and `models/gemini-embedding-2`.

### What was built
- Set up local data (`data/raw/aa_dataset-tickets-multi-lang-5-2-50-version.csv`, `data/sentinel/kb_train.csv`, `holdout_test.csv`, `data/sentinel/triage_model.joblib`, and 22,869-ticket hash index `data/sentinel.sqlite`).
- Updated `agent/llm_router.py` (`LLMRouter._gemini` / `_gemini_once`) to mirror `_ollama` with one fast retry (0.5 s backoff) on transient HTTP `500`/`503` high-demand spikes or truncated/invalid `SentinelDraft` JSON, while failing fast without retrying `4xx` client errors, `504` deadlines, or network/timeout errors.
- Expanded `tests/test_gemini_config.py` with offline unit tests covering `SentinelDraft` structured output, transient `503` retry, invalid JSON retry, and non-retryable `400`/`403`/`404`/`504` errors.

### Files changed
- `agent/llm_router.py`
- `tests/test_gemini_config.py`
- `docs/progress/Sujitha.md`

### Verification
1. **5 real tickets via `python -m sentinel.pipeline "<ticket text>"` (`LLM_PROVIDER=gemini`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `GEMINI_THINKING_LEVEL=low`, hash index):**
   All **5/5** returned via `gemini` with `fell_back=False`, **0 rejected citations**, and either grounded verified citations or a correct refusal:

   | # | Ticket | Lang | Result | Verified / Rejected | Cited IDs | Gen Latency | Total Latency |
   |---|---|---|---|---|---|---|---|
   | 1 | VPN down after firewall update | en | Refused (no VPN/firewall precedent in hash top-k) | 0 / 0 | `[]` | 1190.9 ms | 1413.7 ms |
   | 2 | Billing discrepancies on digital strategy tools | en | Grounded | 1 / 0 | `['TKT-20587']` | 1229.4 ms | 1278.0 ms |
   | 3 | 4th floor meeting room printer jamming | en | Refused (no printer precedent in hash top-k) | 0 / 0 | `[]` | 1128.0 ms | 1177.2 ms |
   | 4 | Team login access denied after update | de | Grounded | 2 / 0 | `['TKT-18411', 'TKT-18411']` | 1309.4 ms | 1359.5 ms |
   | 5 | Unrecognized charge on latest invoice | de | Grounded | 2 / 0 | `['TKT-16560', 'TKT-16560']` | 1489.8 ms | 1554.5 ms |

   - Median Gemini generation latency: **1229.4 ms** (range 1128.0–1489.8 ms).

2. **Test suite & ownership checks:**
   - `.venv/bin/pytest -q`: **63 passed, 0 failed** (including 10 tests in `tests/test_gemini_config.py` and 6 in `tests/test_team_contracts.py`).
   - `.venv/bin/python scripts/check_ownership.py`: **OK** (every changed file on `Sujitha-Branch` belongs to Sujitha).

### Open issues / notes for teammates
- None blocking. Hash retrieval missed semantic matches for the VPN and printer tickets (causing Gemini to correctly refuse); once Rithwik's Gemini embeddings index lands, grounded rate on those topics should improve.
- Notice on tickets #4 and #5, Gemini sometimes cites two quotes from the same `ticket_id` (both verified verbatim); `cited_ticket_ids` in `pipeline.py` keeps duplicates (`['TKT-18411', 'TKT-18411']`), which is fine for now.
