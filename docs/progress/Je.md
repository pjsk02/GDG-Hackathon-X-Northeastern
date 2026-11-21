# Je - progress log (Role A: data, evaluation, thresholds, safety dial, README, demo)

## How to get the data (teammates: copy these)

Run from the repo root, on your own branch, after `uv venv --python 3.12 && uv pip install -e ".[all]"`.

```bash
source .venv/bin/activate          # Windows: .venv\Scripts\activate
mkdir -p data/raw && curl -L -o data/raw/aa_dataset-tickets-multi-lang-5-2-50-version.csv \
  https://huggingface.co/datasets/Tobi-Bueck/customer-support-tickets/resolve/main/aa_dataset-tickets-multi-lang-5-2-50-version.csv
make sentinel-split                       # 80/20 split + leakage report -> data/sentinel/{kb_train,holdout_test}.csv
make sentinel-train                       # triage model -> data/sentinel/triage_model.joblib (~1 min)
EMBED_PROVIDER=hash make sentinel-index   # offline hash index of kb_train -> data/sentinel.sqlite (~2 s)
```

- The CSV is about 25 MB. Everything under `data/` is gitignored; never commit it.
- The split is deterministic (seed 42), so everyone gets the same ticket ids.
- For tuning or calibration use `sentinel.dataset.load_train_val_test()` -> `(train, val, holdout)`.
  Tune on `val` only. The holdout is for final scoring inside eval code.
- Tip: running `uv run ...` creates an untracked `uv.lock` that fails `make check-ownership`. Use the activated
  venv (or `.venv/bin/python`) instead, or delete `uv.lock` before pushing.

## Step 1 - Data and baseline numbers (2026-11-21)

**Built:** no code; downloaded the dataset, ran the split, trained the triage model, built the hash index and took
baseline metrics. This log is the only file changed.

### Split and leakage report (`make sentinel-split`)

| Slice | Tickets | Share |
|---|---|---|
| kb_train (indexed, answers visible) | 22,869 | 80.0% of 28,587 |
| - train (`load_train_val_test()[0]`) | 20,582 | 90.0% of kb |
| - validation (`load_train_val_test()[1]`) | 2,287 | 10.0% of kb |
| holdout (`load_train_val_test()[2]`) | 5,718 | 20.0% of 28,587 |

Leakage: `ticket_id_overlap: 0`, `identical_body_overlap: 1`, `kb_has_answers: True`, **`ok: True`**.

The one identical body (for judges): kb `TKT-07313` (subject "Issue with SaaS Platform Integration") and holdout
`TKT-23177` (subject "Medical Data Security") both have the 17-character body `"Assistance needed"`. The subjects
differ and the body is a generic placeholder, so this is a duplicate filler phrase rather than a leaked ticket.

kb_train label mix: type Incident 40.3% / Request 28.6% / Problem 21.0% / Change 10.1%; priority medium 40.2% /
high 39.1% / low 20.6%; language en 57.1% / de 42.9%; 10 queues (Technical Support largest at 29.3%, General
Inquiry smallest at 1.4%).

### Baseline triage metrics on the full holdout (`python -m eval.sentinel_eval --triage-only`)

TF-IDF + logistic regression trained on all of kb_train (`make sentinel-train`), untuned default thresholds.

| Metric | Value |
|---|---|
| type Macro-F1 / accuracy | 0.874 / 0.863 |
| queue Macro-F1 / accuracy | 0.579 / 0.567 |
| priority Macro-F1 / accuracy | 0.623 / 0.633 |
| language accuracy | 0.907 |
| high-priority incidents in holdout | 995 |
| high-priority-incident recall (classifier) | 0.655 |
| high-priority-incident recall via gate | 0.743 |
| high-priority recall (any type) | 0.674 |
| latency per ticket | 0.35 ms |

Report written to `data/eval/sentinel-20261121-115954/` (local, gitignored).

### Verified

- `make sentinel-split`: leakage `ok: True`, 0 id overlap.
- `make sentinel-train`: exit 0. `EMBED_PROVIDER=hash make sentinel-index`: 22,869 ticket chunks indexed, exit 0.
- `load_train_val_test()` sizes: 20,582 / 2,287 / 5,718.
- `pytest -q`: 56 passed (2.5 s). Contract tests pass.
- `scripts/check_ownership.py`: OK. Files changed: `docs/progress/Je.md` only.

### Open issues / notes for teammates

- High-priority-incident recall via the gate is 0.743, below the 0.90 target. Step 2 tunes the gate thresholds
  on the validation slice to raise it.
- Queue Macro-F1 (0.58) is the weakest head; small queues (HR, General Inquiry) pull it down. Shishir may want
  class weighting.
- `uv.lock` is not gitignored. Lead fix on main: add it to `.gitignore`.
- `scripts/check_ownership.py` reads `git status --porcelain`, which collapses a brand-new untracked folder to
  `docs/progress/` and so fails a teammate's first progress log. Workaround: `git add docs/progress/<You>.md`
  before `make check-ownership`. Lead fix on main: use `git status --porcelain -uall`.
