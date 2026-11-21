# Shishir - progress log (Role B: triage model)

## Step 1 - Setup and base check (2026-11-21)

**Built:** nothing new in code; local data, model and index rebuilt or verified on `Shishir-Branch` (main @ 8744c79 merged).

**Data and build**
- `make sentinel-split`: kb_train 22,869 / holdout 5,718. The CSVs are byte-identical to the earlier split
  (md5 kb_train 843536b5..., holdout e7f13526...). Leakage report ok (ticket_id overlap 0, 1 identical body).
- `make sentinel-train` (2 min 30 s), current model = full kb_train, not yet calibrated. **Baseline holdout metrics
  for Step 2 (Macro-F1 must not drop by more than 0.01):**

  | metric | value |
  |---|---|
  | type_macro_f1 | 0.8738 |
  | queue_macro_f1 | 0.5763 |
  | priority_macro_f1 | 0.6252 |
  | language_accuracy | 0.907 |
  | high_priority_incident_recall | 0.6553 (via gate 0.7477, n=995) |
  | high_priority_recall | 0.6777 |
  | latency_ms_per_ticket | 0.733 |

- Index: **not rebuilt.** `data/sentinel.sqlite` already holds all 22,869 kb_train tickets embedded with
  `ollama-embeddinggemma-2:570m`, the same embedder `.env` selects, and the split did not change, so a rebuild
  would be identical. Rebuild with `make sentinel-index` only if the split or embedder changes.

**Pipeline runs** (`python -m sentinel.pipeline "Our VPN is down since the firewall update"`, MEMORY_PATH=data/sentinel.sqlite)

| | extractive | ollama (gemma4:e4b) |
|---|---|---|
| triage | Problem / Technical Support / high | same |
| tier | PAGE_ONCALL (R2) | PAGE_ONCALL (R2) |
| grounded | true, cites TKT-18467 | true, cites TKT-18467 + TKT-17145, 0 rejected |
| fell_back | false | false |
| latency | 7.7 s (retrieval 7.7 s: cold Ollama embedder load) | 19.1 s (generation 18.7 s, retrieval 0.4 s) |

Nothing broke from the prompt/fallback/citation move to sentinel/writer.py: `extractive_draft` now returns
`refused=false` and validates.

**Verified:** `pytest -q` -> 56 passed. `python scripts/check_ownership.py` clean for committed files.

**Odd things noticed**
1. R2 reason text contradicts itself when priority is already `high` but type is not `Incident`:
   "P(high)=0.56 >= 0.50 although the top label is 'high'". In `sentinel/escalation.py` (Kaushik); request filed in
   docs/requests/Shishir.md. Behaviour (paging) is fine, only the wording.
2. `explanations` is `{}` (stub, my Step 3) and `briefing` is `""` (not yet filled by pipeline/writer).
3. Extractive draft cuts the quote mid-word ("...recommending suita"). Cosmetic, in sentinel/writer.py (Sujitha).
4. Triage confidence is low on this ticket (queue 0.39, priority 0.56); calibration (Step 2) will show whether
   these numbers mean what they say.
5. First retrieval call is ~7.7 s because Ollama loads embeddinggemma; warm calls ~0.4 s. Keep `OLLAMA_KEEP_ALIVE`
   for the demo.
6. Local note: `uv run` creates an untracked `uv.lock` (not owned by anyone). I do not commit it; Je may want it
   in .gitignore or committed on main.
