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

## Step 4 - Manager page and corrections
- **Built:** Implemented `ui/pages/manager.py` with open/in-progress/closed/total ticket counts, tier rates, safety dial chart from `data/eval/safety_dial.json` (with `make dial` prompt when missing), holdout metrics from `data/eval/latest/report.json`, calibration from `data/eval/calibration.json` if present, saved corrections list, and a Retrain button calling `feedback.retrain_challenger()`. Added the "Correct labels" form to `ui/pages/agent.py` calling `feedback.record_correction(LabelCorrection(...))`. Added `tests/test_ui_manager.py`.
- **Files changed:** `ui/pages/manager.py`, `ui/pages/agent.py`, `tests/test_ui_manager.py`, `docs/progress/Kaushik.md`
- **Verified:** `uv run --no-sync pytest -q` -> `82 passed in 3.33s` (Manager page renders with/without eval files, Retrain displays status/metrics, and Agent panel saves corrections).
- **Open issues / notes for teammates:** None.

## Step 5 - Smart queue page and outage banner
- **Built:** Implemented `ui/pages/queue.py` with "Fire 10 tickets" (`fire_burst` in `ui/shared.py`, calling Rithwik's `simulator.fire` when available with a built-in fallback burst), worker concurrency slider (`SmartQueue.set_concurrency`), and a live `st.fragment(run_every="1s")` view showing waiting / processing / done / throughput from `stats()` and `snapshot()`. Added shared `render_outage_banner` in `ui/shared.py` (with "Group into one incident" calling `incidents.group_burst` when available) and wired it into `ui/pages/agent.py`, `ui/pages/manager.py`, and `ui/pages/queue.py`. Added `tests/test_ui_queue.py`.
- **Files changed:** `ui/shared.py`, `ui/pages/queue.py`, `ui/pages/agent.py`, `ui/pages/manager.py`, `tests/test_ui_queue.py`, `docs/progress/Kaushik.md`
- **Verified:** `uv run --no-sync pytest -q` -> `84 passed in 3.46s` (burst raises Major Incident banner, concurrency updates, and "Group into one incident" invokes `incidents.group_burst`).
- **Open issues / notes for teammates:** None.

## Step 6 - Polish (pre-demo)
- **Built:** Added `.streamlit/config.toml` for consistent light theme colors and aligned `ui/pages/queue.py` ticket items with `TIER_META` icons/labels.
- **Files changed:** `.streamlit/config.toml`, `ui/pages/queue.py`, `docs/progress/Kaushik.md`
- **Verified:** `uv run --no-sync pytest -q` -> `84 passed in 3.74s`; `tests/test_team_contracts.py` -> `6 passed in 1.62s`.
- **Open issues / notes for teammates:** `docs/demo/script.md`, the dataset (`data/raw/`), and teammates' merged branches are not yet on `main`; full demo walkthrough, 3 README screenshots, and PR into `main` remain once those are ready.
