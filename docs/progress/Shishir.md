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

## Step 2 - Train on the train slice and calibrate (F2) (2026-11-21)

**Built**
- `sentinel/triage.py`: `--train` fits on the TRAIN slice (20,582) from `dataset.load_train_val_test()` and
  calibrates each head on the VALIDATION slice (2,287). New: `TriageModel.calibrate(val_df)`,
  `predict_proba_heads(texts, calibrated=True)`, `is_calibrated`, `classes`, `metadata()`, per-head
  `HEAD_PARAMS`. The model file now stores `trained_on`, `calibrated`, `calibrated_on`, `calibrators`,
  `calibration_method`, `calibration_selection` (validation log-loss and F1 per candidate), `classes`,
  `sklearn_version` and `saved_at`. Older model files load as uncalibrated. `predict()` still takes about 1.4 ms.
- `sentinel/calibration.py` (new): `report(model, df) -> dict` returns top-label ECE, log-loss and 10-bin
  reliability per head, before and after calibration. `write(model, df, split)` writes the JSON and the PNG.
  `main()` writes `data/eval/calibration.json` and `data/eval/calibration.png` (holdout by default, `--split val`
  for validation). `python -m sentinel.triage --train` also writes both files.
- `tests/test_calibration.py`: 13 offline tests on tiny synthetic data, about 5 s.

**Calibration method: temperature scaling, chosen by the data, not the plan's sigmoid/isotonic.**
Candidates per head are none, temperature (softmax(logits/T)), and `CalibratedClassifierCV(FrozenEstimator(head))`
with sigmoid or isotonic. Each is cross-fitted on the two halves of validation and the lowest out-of-fold log-loss
wins. A candidate that costs more than 0.005 validation Macro-F1 is not allowed. Validation log-loss:

| head | none | temperature | sigmoid | isotonic | picked |
|---|---|---|---|---|---|
| type | 0.3218 | **0.3214** | 0.3496 | 0.4871 | temperature, T=0.893 |
| queue | 1.2824 | **1.2640** | 1.2832 | 1.4752 | temperature, T=0.815 |
| priority | 0.8640 | **0.8375** | 0.8490 | 0.9017 | temperature, T=1.426 |

Sigmoid and isotonic calibrate one-vs-rest and then renormalize. On about 1.1k tickets per fold they did worse
than no calibration, and they cut validation type Macro-F1 by up to 0.035. Temperature scaling never changes a
predicted label, and a test checks this. Queue was *under*confident because `class_weight="balanced"` spreads
probability over 10 classes, so T<1 sharpens it. Priority with C=8 is overconfident, so T>1 softens it.

**Priority head retuned on validation.** Training on 90% of kb_train cost priority 0.0195 holdout Macro-F1.
A validation sweep (C 1-64, balanced or unweighted) picked C=8 with no class weights: validation Macro-F1
0.602 -> 0.620, high-priority recall 0.657 -> 0.691. Balanced C=32 had F1 0.626 but recall 0.672 and log-loss
0.956, and the 0.006 F1 gap is noise at n=2,287. Type and queue keep C=4, balanced.

**ECE before -> after calibration** (top label, 10 bins; reliability plot in data/eval/calibration.png)

| head | holdout (5,718) | validation (in-sample for T) |
|---|---|---|
| type | 0.0146 -> 0.0084 | see `--split val` |
| queue | 0.0698 -> 0.0093 | |
| priority | 0.0601 -> 0.0193 | |

**Holdout vs Step 1 baseline** (Step 1 = full kb_train, uncalibrated)

| metric | Step 1 | Step 2 | change |
|---|---|---|---|
| type_macro_f1 | 0.8738 | 0.8683 | -0.0055 |
| queue_macro_f1 | 0.5763 | 0.5670 | -0.0093 |
| priority_macro_f1 | 0.6252 | 0.6125 | **-0.0127 (over the 0.01 limit)** |
| high_priority_incident_recall | 0.6553 | 0.6613 | +0.0060 |
| high_priority_incident_recall_via_gate | 0.7477 | 0.7457 | -0.0020 |
| high_priority_recall | 0.6777 | 0.6925 | +0.0148 |
| language_accuracy | 0.907 | 0.9052 | -0.0018 |
| latency_ms_per_ticket (batch) | 0.73 | 1.41 | |

The priority drop is 0.0027 over the limit. The cause is the 10% of tickets held back for validation, not
calibration: temperature scaling keeps every label, and the same features without tuning scored 0.6057.
Shishir accepted it: shipping keeps validation truly held out for threshold tuning and Step 4. Refitting on
train+val would pass the F1 rule but make validation in-sample.

**Verified:** `pytest -q` -> 69 passed. Pipeline run (extractive, VPN ticket): Problem / Technical Support /
high, `tier=PAGE_ONCALL`, grounded, triage 8.5 ms.

**Teammates must know**
- **Je:** confidences changed. Priority is softer (T=1.43) and queue is sharper (T=0.81). Thresholds tuned on the
  old model's probabilities (`make tune`, `make dial`) must be re-run with this model. The validation slice is
  still truly held out: the heads never trained on it, and only 3 temperatures were fitted on it.
- **Je (eval/README):** `sentinel.calibration.report(model, df)` and `data/eval/calibration.json` hold
  before/after ECE and 10-bin reliability per head, and `calibration.png` is ready for the README.
- **Step 3 (explain):** raw linear heads are `model.heads[head]` (LogisticRegression). Temperature does not
  change coefficient ranking.
- Rebuild the model with `make sentinel-train`, about 3.5 min.

## Step 3 - Why-this-label (N3) (2026-11-21)

**Built**
- `sentinel/explain.py`: `explain(model, text, top_n=3) -> dict[str, list[str]]`, with the contract unchanged.
  For each head it takes the predicted class c (the calibrated argmax, so it matches the label on screen) and
  ranks this ticket's word 1-2-gram features by `tfidf_j x (w_cj - mean_k w_kj)`. That is the feature's push on
  c's logit relative to the other classes; the coefficients already sum to zero across classes. Character
  n-grams are skipped.
  - Only positive evidence is kept.
  - Stopword-only and digit-only n-grams are dropped. Edge stopwords are trimmed ("the firewall" -> "firewall").
  - A phrase that shares a content word with a stronger one is skipped.
  - A bigram that only exists across punctuation ("service? Thank") is skipped. Hyphenated words are kept
    ("Projektmanagement-SaaS").
  - Phrases are returned with the ticket's own casing ("VPN", "Rechnung").
- The coefficient arrays are cached per model and rebuilt automatically when a head object changes, for example
  after Step 4 promotes a challenger.
- `sentinel/triage.py`: new `TriageModel.features(texts)` that caches the last single-text tf-idf pass, which
  `predict_proba_heads` now uses. When `explain()` runs right after `predict()` on the same ticket, as in the
  pipeline, it reuses those rows instead of redoing the character n-gram pass.
- `tests/test_explain.py`: 20 offline tests covering correct words per head, `top_n`, no repeated words,
  casing, stopwords and digits, positive-only evidence, punctuation, odd input (empty, emoji, 5,000 chars,
  German-only), an unusable model giving `{}`, an uncalibrated model, cache invalidation, feature cache and speed.

**Never raises:** `None`, a test double or any object without linear heads gives `{}`. Empty, emoji-only or
digit-only text gives `{"type": [], "queue": [], "priority": []}`. Any other internal error gives empty lists.

**5 real tickets** (validation slice; the holdout was not used):

| # | lang | ticket (subject) | predicted type / queue / priority | why: type | why: queue | why: priority |
|---|---|---|---|---|---|---|
| 1 | en | Incident of Data Leakage in Medical Records Encrypted w | Incident / Technical Support / medium | Incident, involving, secure settings | Docker, exist, involving medical | secure settings, Leakage, involving medical |
| 2 | de | Sicherung medizinischer Daten-Systeme | Request / Billing and Payments / medium | Sicherung, medizinischer Daten, Details | Hospital, Daten, relevanter Vorschriften | Praktiken, Möchten, besten |
| 3 | en | Customer Support Inquiry | Request / Returns and Exchanges / low | provide, details, digital strategies | services, growth, business | assist, business, appreciate information |
| 4 | de | Unterstützung für Projektmanagement SaaS | Request / Billing and Payments / medium | Könnten, Details, SaaS | Details, Gebühren, bereitstellen | eventuelle, Details, Projektmanagement |
| 5 | en | Details on Project Management SaaS Pricing | Request / Billing and Payments / medium | Details, possible, SaaS | Pricing, Details, tiers | SaaS Pricing, Details, tiers |

Latency over 1,000 validation tickets: p50 4.36 ms, p95 6.09 ms, max 8.45 ms.

Pipeline (extractive, "Our VPN is down since the firewall update"): `explanations = {"type": ["firewall update",
"down"], "queue": ["firewall"], "priority": ["firewall", "VPN", "down"]}`, tier PAGE_ONCALL, no error.

**Latency** (1,000 validation tickets, on a busy machine where `predict()` alone took about 5 ms p50, against
1.4 ms earlier): explain right after predict, as in the pipeline, p50 0.83 ms and p95 1.32 ms. Standalone
explain needs one full vectorizer pass: p50 3.6 ms, p95 5.5 ms. The 5 ms target is met in the pipeline.

**Reading the results honestly**
- The words are the model's real reasons, not curated ones. Generic request words ("Details", "provide",
  "Könnten", "possible") rank high for type=Request because in this dataset they *are* what separates Request
  from Incident.
- Explanations also show mistakes. Ticket 2 is routed to Billing and Payments instead of Technical Support, and
  "Hospital, Daten, relevanter Vorschriften" shows the compliance wording pulled it there. That is the
  point of the feature in the agent panel.
- Priority words are the weakest: priority is the hardest head, Macro-F1 0.61.

**Verified:** `pytest -q` -> 90 passed. An independent test-runner found no raises on empty text, "hi", emoji,
5,000 characters, German-only or the VPN ticket; `explain(None, ...)` gives `{}`. On a quieter machine it measured
explain after predict at p50 0.33 ms and p95 0.53 ms. Pipeline explanations are filled, error null.
The ownership review caught one gap: `fit()` refits the vectorizer in place, so the one-entry feature cache could
serve rows from before the refit. `fit()` now clears it, and a test checks this.

**Teammates must know**
- **Kaushik:** `result.explanations` is now filled, `{head: [up to 3 phrases]}`; a head can have an empty
  list. Show the phrases as given, already in the ticket's casing. Highlighting them in the ticket body is safe:
  each phrase is a real substring of the text, apart from rare lowercase unigram fallbacks.
- **Step 4 (feedback):** after promotion, set `triage._CACHED = None`. The explain cache follows the new heads
  by itself.
