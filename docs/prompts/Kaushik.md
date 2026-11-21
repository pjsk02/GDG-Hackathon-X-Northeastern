# Kaushik - Role E: three-tier gate, UI pages, API, pipeline wiring

Branch: `Kaushik-Branch` · Your files: see `Kaushik-Branch` in docs/team/ownership.json · Progress log: docs/progress/Kaushik.md

## Kickoff prompt (paste into your agent after the starter prompt)

```text
You are Kaushik's coding agent for the SentinelDesk hackathon repo (https://github.com/pjsk02/GDG-Hackathon-X-Northeastern). I am Kaushik, role E (three-tier safety gate, the Streamlit app: tickets board with side panel, customer, manager and smart-queue pages, the FastAPI endpoint, and pipeline wiring).

1. Make sure you are inside the repo on branch Kaushik-Branch with the latest main merged. If not, do the starter checks in docs/prompts/00-starter.md first.
2. Fetch my plan from GitHub: https://raw.githubusercontent.com/pjsk02/GDG-Hackathon-X-Northeastern/main/docs/prompts/Kaushik.md (the same file is at docs/prompts/Kaushik.md). Also read CLAUDE.md, docs/team/README.md and docs/PRD.md (UI section).
3. Follow the plan one step at a time, in order. Inside a step, work autonomously: split independent pieces across subagents (builder for code in my files, Explore for reading other people's code, test-runner for checks, ownership-reviewer before pushing) and run them in parallel when they touch different files, for example one builder per UI page. Only ask me when you are truly blocked.
4. Edit only my files (docs/team/ownership.json, Kaushik-Branch). Push only to Kaushik-Branch. Never push to main.
5. When a step's "Done when" list is met, run /ship-step <N>, give me the report, and stop. Start the next step only after I reply "yes, you can proceed".

Start with Step 1 now.
```

## What you own and who depends on you

- sentinel/escalation.py, sentinel/pipeline.py, ui/ (all pages), api/, .streamlit/.
- You call other people's modules only through their documented functions (docs/team/README.md, "Contracts").
  All of them exist on main already as stubs with the final signatures, so you can build every page now and they
  light up as teammates merge: explanations (Shishir), guard findings, injection flags, briefing and masked text
  (Sujitha), ticket store, queue, simulator, incidents (Rithwik), safety dial and report files (Je).
- Target look: the UI mockup canvas linked from docs/PRD.md (tickets board grouped by tier + side panel).

## Step 1 - Three-tier gate (N1)

Replace the placeholder `decide_tier(decision, reasons)` in sentinel/escalation.py:
R1, R2, R5, R7 -> "PAGE_ONCALL"; only R3, R4, R6 -> "AGENT_REVIEW"; no reasons -> "AUTO_DRAFT". Parse the rule code
at the start of each reason string. Keep the signature (the pipeline calls it).

Done when: `tests/test_escalation*.py` covers every rule and mixes (R3 + R1 -> PAGE_ONCALL), `pytest -q` passes.

## Step 2 - App shell and agent workspace (board + side panel)

- `ui/sentinel_console.py` becomes the entry: `st.navigation` with pages Agent, Customer, Manager, Smart queue in
  `ui/pages/`, and a role picker in the sidebar (`st.session_state.role`). `make console` still starts it.
- Agent page (`ui/pages/agent.py`): left, a tickets board from `ticket_store.list_tickets()` grouped by
  `result.tier` (Page on-call, Agent review, Auto-draft ready, Resolved) using `st.dataframe` with single-row
  selection (`on_select="rerun"`), columns: ticket, type, team, priority, AI confidence (progress column),
  waiting time. Right, the side panel for the selected ticket: briefing, verdict + reason + main action, message
  with an Original / "What the AI saw" toggle, the three triage questions with confidence and the
  `result.explanations` words, safety checks (fired rules), past tickets, reply with verified citations and guard
  findings. Preset buttons add demo tickets and run `SentinelAgent().triage` on them.
- Keep the old console's useful bits (presets, threshold sliders) where they fit.

Done when: you can add a preset ticket, see it on the board in the right tier, click it, and see every panel
section (empty sections say what will appear). `pytest -q` passes.

## Step 3 - Customer page and API roles

- `ui/pages/customer.py`: raise-a-ticket form (subject optional) and "My tickets" with Received / In progress /
  Replied. Customers never see confidence, precedents, reasons or masked text.
- `api/main.py`: `POST /triage` taking `TicketInput`, reading an `X-Role` header (customer | agent | manager);
  for customers return only status and approved reply. Tests with FastAPI's TestClient and a fake agent in
  `tests/test_api*.py`.

Done when: tests pass and the customer page shows a submitted ticket's status.

## Step 4 - Manager page and corrections

- `ui/pages/manager.py`: counts (open, in progress, closed), tier rates, the safety dial chart from
  `data/eval/safety_dial.json` (if missing, say "run make dial"), holdout metrics from
  `data/eval/latest/report.json`, calibration from `data/eval/calibration.json` if present, and a Retrain button
  calling `feedback.retrain_challenger()` that shows the returned status and numbers.
- In the agent panel, a "Correct labels" form that calls `feedback.record_correction(LabelCorrection(...))`.

Done when: the page renders with and without those data files, and a correction is saved.

## Step 5 - Smart queue page and outage banner

- `ui/pages/queue.py`: "Fire 10 tickets" (Rithwik's `simulator.fire`), concurrency control
  (`SmartQueue.set_concurrency`), live slots / waiting / done / throughput from `stats()` and `snapshot()`,
  refreshed with `st.fragment(run_every="1s")`.
- Major Incident banner from `OutageTracker.observe(result)` on agent and manager pages, with a
  "Group into one incident" button that calls Rithwik's `incidents.group_burst` once it exists.

Done when: firing 10 tickets shows urgent ones finishing first and the burst raises the banner.

## Step 6 - Polish and demo run-through

- Walk through docs/demo/script.md with Je on the demo laptop; fix UI bugs; consistent tier colours and labels.
- Send Je 3 screenshots for the README (board + panel, customer page, manager page).

Done when: the full demo runs without errors. Open a PR into main and tell Je.
