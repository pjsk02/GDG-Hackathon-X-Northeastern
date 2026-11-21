# Kaushik Progress Log

## Step 1 - Three-tier gate (N1)
- **Built:** Replaced the placeholder `decide_tier(decision, reasons)` in `sentinel/escalation.py` with rule-code parsing (`R1`/`R2`/`R5`/`R7` -> `"PAGE_ONCALL"`, only `R3`/`R4`/`R6` -> `"AGENT_REVIEW"`, empty `reasons` -> `"AUTO_DRAFT"`), keeping the signature unchanged. Added unit and gate-integration tests in `tests/test_escalation.py`.
- **Files changed:** `sentinel/escalation.py`, `tests/test_escalation.py`, `docs/progress/Kaushik.md`
- **Verified:** `uv run --no-sync pytest -q` -> `68 passed in 2.40s` (including all 12 tests in `tests/test_escalation.py`).
- **Open issues / notes for teammates:** None.

## Step 2 - App shell and agent workspace (board + side panel)
- **Built:** Converted `ui/sentinel_console.py` to a `st.navigation` multipage app with sidebar role picker (`st.session_state.role`) and operator/threshold controls. Added `ui/shared.py` for shared presets, board grouping/dataframe helpers, and ticket triage persistence. Built `ui/pages/agent.py` with preset buttons, custom ticket form, tier-grouped `st.dataframe` board (`on_select="rerun"`, `single-row`) and full side panel (briefing, verdict + action, Original/"What the AI saw" toggle, triage predictions + explanations, safety checks, past tickets, drafted reply + verified/rejected citations + guard findings). Added placeholder pages for `ui/pages/customer.py`, `ui/pages/manager.py`, and `ui/pages/queue.py`.
- **Files changed:** `ui/sentinel_console.py`, `ui/shared.py`, `ui/pages/agent.py`, `ui/pages/customer.py`, `ui/pages/manager.py`, `ui/pages/queue.py`, `tests/test_ui_agent.py`, `docs/progress/Kaushik.md`
- **Verified:** `uv run --no-sync pytest -q` -> `72 passed in 3.26s` (including Streamlit `AppTest` preset -> board -> side panel test in `tests/test_ui_agent.py`).
- **Open issues / notes for teammates:** None.

## Step 3 - Customer page and API roles
- **Built:** Implemented `ui/pages/customer.py` with an optional-subject ticket submission form and "My tickets" status list (`Received` / `In progress` / `Replied`), hiding all internal fields (confidence, precedents, reasons, masked text). Added `customer_status_label` in `ui/shared.py`. Added `POST /triage` in `api/main.py` accepting `TicketInput` and `X-Role` (`customer` | `agent` | `manager`), returning `CustomerTriageResponse` (status + approved reply only) for customers and full `SentinelResult` for agents/managers. Added `tests/test_api.py` and `tests/test_ui_customer.py`.
- **Files changed:** `ui/shared.py`, `ui/pages/customer.py`, `api/main.py`, `tests/test_api.py`, `tests/test_ui_customer.py`, `docs/progress/Kaushik.md`
- **Verified:** `uv run --no-sync pytest -q` -> `78 passed in 2.88s` (all API TestClient and Customer AppTest checks pass).
- **Open issues / notes for teammates:** None.
