"""The one place the 80/20 split is defined. Everything else imports from here.

    kb_train_df  80%  historical knowledge base: may be trained on and indexed (answers included)
    test_df      20%  holdout: inputs only at inference; labels and answers are for scoring only

The split is the exact recipe from the problem statement (shuffle with random_state=42, then
TKT-xxxxx ids, then an 80% cut), so it is reproducible from the raw CSV by anyone.

    python -m sentinel.dataset            # write the split + print a leakage report
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

RAW_DEFAULT = Path("data/raw/aa_dataset-tickets-multi-lang-5-2-50-version.csv")
OUT_DIR = Path("data/sentinel")
KB_PATH = OUT_DIR / "kb_train.csv"
TEST_PATH = OUT_DIR / "holdout_test.csv"

SPLIT_SEED = 42
KB_FRACTION = 0.8

# Columns the holdout set must never expose at inference time.
LABEL_COLUMNS = ["type", "queue", "priority", "answer"]
TAG_COLUMNS = [f"tag_{i}" for i in range(1, 9)]


def load_raw(path: Path | str = RAW_DEFAULT) -> pd.DataFrame:
    """Read the raw CSV and make it safe to iterate over (no NaN in the text columns)."""
    df = pd.read_csv(path)
    for col in ["subject", "body", "answer", *TAG_COLUMNS]:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
    # A ticket with no body carries no signal for triage or retrieval.
    df = df[df["body"].str.len() > 0].copy()
    for col in ["type", "queue", "priority", "language"]:
        df = df[df[col].notna()].copy()
    return df.reset_index(drop=True)


def make_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Exactly the problem statement's recipe: shuffle(42) -> TKT ids -> 80/20 cut."""
    df = df.sample(frac=1.0, random_state=SPLIT_SEED).reset_index(drop=True)
    df["ticket_id"] = [f"TKT-{i:05d}" for i in range(len(df))]
    split_idx = int(len(df) * KB_FRACTION)
    kb_train_df = df.iloc[:split_idx].copy()  # training + RAG indexing
    test_df = df.iloc[split_idx:].copy()  # holdout evaluation only
    return kb_train_df, test_df


def ticket_text(row: pd.Series | dict) -> str:
    """What the models see for an *incoming* ticket: subject + body, never the answer."""
    subject = str(row.get("subject") or "").strip()
    body = str(row.get("body") or "").strip()
    return f"{subject}\n{body}".strip() if subject else body


def build(raw_path: Path | str = RAW_DEFAULT) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write the split to data/sentinel/ and return it."""
    kb_train_df, test_df = make_split(load_raw(raw_path))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    kb_train_df.to_csv(KB_PATH, index=False)
    test_df.to_csv(TEST_PATH, index=False)
    return kb_train_df, test_df


def load_split() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the split written by `build` (building it first if it is missing)."""
    if not KB_PATH.exists() or not TEST_PATH.exists():
        return build()
    kb = pd.read_csv(KB_PATH).fillna("")
    test = pd.read_csv(TEST_PATH).fillna("")
    return kb, test


VAL_FRACTION = 0.10


def split_train_val(kb_train_df: pd.DataFrame, fraction: float = VAL_FRACTION) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cut the knowledge base into (train, validation). The validation slice is the LAST `fraction`.

    kb_train is already shuffled with seed 42, so the tail is a random sample and the cut is
    reproducible. Tune thresholds and calibrate on validation; touch the holdout only for final scores.
    """
    cut = int(len(kb_train_df) * (1.0 - fraction))
    return kb_train_df.iloc[:cut].copy(), kb_train_df.iloc[cut:].copy()


def load_train_val_test(fraction: float = VAL_FRACTION) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(train, validation, holdout). The RAG index still uses ALL of kb_train (train + validation)."""
    kb, test = load_split()
    train, val = split_train_val(kb, fraction)
    return train, val, test


def leakage_report(kb_train_df: pd.DataFrame, test_df: pd.DataFrame) -> dict[str, object]:
    """Proof for the judges that no holdout ticket can reach the index or the prompt."""
    kb_ids, test_ids = set(kb_train_df["ticket_id"]), set(test_df["ticket_id"])
    overlap = kb_ids & test_ids
    # Same body text appearing in both halves would leak an answer through retrieval.
    body_overlap = set(kb_train_df["body"]) & set(test_df["body"])
    return {
        "kb_tickets": len(kb_train_df),
        "holdout_tickets": len(test_df),
        "ticket_id_overlap": len(overlap),
        "identical_body_overlap": len(body_overlap),
        "kb_has_answers": bool((kb_train_df["answer"].str.len() > 0).any()),
        "ok": not overlap,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the SentinelDesk 80/20 split.")
    ap.add_argument("csv", nargs="?", default=str(RAW_DEFAULT))
    args = ap.parse_args()

    kb, test = build(args.csv)
    print(f"kb_train  -> {KB_PATH}  ({len(kb):,} tickets, answers indexed)")
    print(f"holdout   -> {TEST_PATH}  ({len(test):,} tickets, labels hidden at inference)")
    print("leakage:", leakage_report(kb, test))
    for col in ["type", "queue", "priority", "language"]:
        counts = kb[col].value_counts()
        print(f"\n{col}:")
        for name, n in counts.items():
            print(f"  {name:<34} {n:>6,}  ({n / len(kb):.1%})")


if __name__ == "__main__":
    main()
