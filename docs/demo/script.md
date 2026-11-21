# Demo script (5 minutes)

Follows the PRD demo: problem -> customer raises a German ticket with an email -> agent board + panel -> refund trap
and injection caught -> fire 10 tickets, burst banner -> manager page with safety dial and metrics.
Tickets are in [demo_tickets.md](demo_tickets.md).

## Before going on stage (T-10 min)

- [ ] Ollama running with `embeddinggemma-2:570m` (index) and `gemma4:12b` (fallback writer): `ollama list`.
- [ ] `.env`: `LLM_PROVIDER=gemini`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `LLM_FALLBACK=ollama,extractive`,
      `OLLAMA_MODEL=gemma4:12b`, `EMBED_PROVIDER=ollama`, `GEMINI_API_KEY` set. Optional: `OLLAMA_KEEP_ALIVE=-1m`.
- [ ] Data built once (skip if present): `make sentinel-split`, the calibrated model, the index
      (`EMBED_PROVIDER=ollama make sentinel-index`, ~6 min), `make tune && make dial`, `make sentinel-eval`.
- [ ] `make console` (http://localhost:8501); the sidebar shows Embedder `ollama-embeddinggemma-2:570m` and 22,869
      tickets. Open the Customer, Agent, Smart queue and Manager pages in four browser tabs.
- [ ] Empty the board: `python -c "from sentinel import ticket_store; ticket_store.reset()"`, then "Clear outage
      buffer" in the sidebar. `data/eval/latest/report.json` and `data/eval/safety_dial.json` exist.
- [ ] Warm-up run: submit ticket 11 once (first call loads the models), then reset again.
- [ ] Paste tickets 1, 3 and 4 into a text file ready to copy. Browser zoom at 125%. Notifications off.
- [ ] Timer visible to the speaker.

## Script

| Time | Screen | Say / do |
|---|---|---|
| **0:00-0:30** | Title / README | "Support teams get thousands of tickets in two languages. An AI that answers everything will eventually promise a refund it can't give or miss an outage. SentinelDesk triages every ticket, answers only what past resolutions can back, and sends the rest to the right human with a reason." |
| **0:30-1:15** | Customer page | Paste **ticket 1** (German login outage with an email). Submit. "A customer in Germany, with personal details in the ticket." Show the customer sees only a status. |
| **1:15-2:15** | Agent board + side panel | Open the ticket on the board: it sits under **Page on-call**. In the panel: the briefing; **What the AI saw** (email, phone, customer number masked); the three triage answers with confidence and **why this label** words; the gate reasons in plain language; the past tickets it found. "Nothing here is a model's opinion: every escalation is a rule with a reason." |
| **2:15-3:15** | Customer page -> board | Paste **ticket 3** (refund + SLA + lawyer): R5 lists refund, SLA and legal, page on-call. Paste **ticket 4** (injection): R7 flag, no fake guarantee. Then paste **ticket 11** (data analytics inquiry): it lands in **Auto-draft** with no reasons, the reply cites two past tickets and every citation is verified verbatim; any unbacked number would have been caught by the guard. "It answers when it can prove it, and says why when it can't." |
| **3:15-4:00** | Queue page | Click **Fire 10 tickets**. Urgent tickets jump the line while N LLM calls run at once; slots, waiting and throughput update live. The similar outage tickets trigger the **burst banner** / one incident. |
| **4:00-4:45** | Manager page | Counts and tier rates. The **safety dial**: "This curve is every threshold setting on the validation slice. Here is what each one costs in on-call pages and buys in caught incidents; we chose this point." Then the holdout metrics table (from `report.json`), calibration, and the leakage line: "tuned on validation only; the index never saw a holdout ticket." |
| **4:45-5:00** | README / title | "SentinelDesk: triage with confidence, answers with proof, and a dial for how careful you want to be." Thank the judges. |

## If something breaks

| Problem | Do this |
|---|---|
| Gemini slow or down | Keep going: the fallback chain answers with local Gemma or an extractive quote, and the panel shows "answered by X instead". Say so; it is a feature. |
| Wi-Fi gone | `EMBED_PROVIDER=hash`, `LLM_PROVIDER=extractive` work offline; skip ticket 8 (cross-lingual needs Gemini). |
| A page errors | Switch to `make console` main view or `POST /triage` in the API docs; show the same ticket's reasons there. |
| Running long at 3:15 | Skip the auto-draft example and go straight to Fire 10. |
| Running long at 4:00 | Show only the safety dial and the leakage line. |

## Likely judge questions

- **Did you tune on the test set?** No. Thresholds and calibration use the last 10% of kb_train with the ticket's
  own index entry removed; the holdout is scored once. See README "Evaluation and leakage".
- **Any leakage between the split halves?** 0 shared ids, the index holds kb only; one identical body ("Assistance
  needed", a placeholder under two different subjects).
- **Why not let the LLM decide escalation?** Deterministic rules give the same decision every time and a reason an
  operator can audit; the LLM only writes, and its output is verified.
- **What does the dial mean for a business?** Each point is a workload/risk trade-off; a manager can move it
  without retraining.
