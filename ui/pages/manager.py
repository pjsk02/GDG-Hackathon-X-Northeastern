"""Manager dashboard: ticket counts, tier rates, safety dial, holdout metrics, calibration, and retrain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from sentinel import feedback, ticket_store
from sentinel.ticket_store import TicketRecord
from ui.shared import TIER_META, TIER_ORDER, get_tracker, render_outage_banner


def compute_ticket_counts(tickets: list[TicketRecord]) -> dict[str, int]:
    """Compute open, in_progress, closed, and total ticket counts."""
    open_count = sum(1 for r in tickets if r.status in ("new", "queued", "processing"))
    in_progress = sum(1 for r in tickets if r.status == "triaged")
    closed = sum(1 for r in tickets if r.status in ("replied", "closed"))
    return {
        "open": open_count,
        "in_progress": in_progress,
        "closed": closed,
        "total": len(tickets),
    }


def compute_tier_rates(tickets: list[TicketRecord]) -> dict[str, tuple[int, float]]:
    """Return tier -> (count, rate_0_to_1) across triaged tickets."""
    triaged = [r for r in tickets if r.result is not None]
    total = len(triaged)
    counts = {tier: 0 for tier in TIER_ORDER}
    for r in triaged:
        tier = r.result.tier if r.result and r.result.tier in counts else (
            "PAGE_ONCALL" if r.result and r.result.escalation == "ESCALATE" else "AUTO_DRAFT"
        )
        counts[tier] += 1
    return {tier: (c, (c / total) if total else 0.0) for tier, c in counts.items()}


def _load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _extract_dial_df(data: Any) -> pd.DataFrame | None:
    rows = data if isinstance(data, list) else (
        data.get("points") or data.get("sweep") or data.get("rows") if isinstance(data, dict) else None
    )
    if not isinstance(rows, list) or not rows:
        return None
    df = pd.DataFrame(rows)
    return df if not df.empty else None


def render_manager_page(eval_dir: Path = Path("data/eval")) -> None:
    st.title("📊 Manager Dashboard")
    st.caption("Queue health, tier distribution, evaluation metrics, and challenger retraining.")
    render_outage_banner(get_tracker(), key_prefix="manager")

    tickets = ticket_store.list_tickets()
    counts = compute_ticket_counts(tickets)
    rates = compute_tier_rates(tickets)

    # 1. Ticket counts
    st.subheader("Ticket counts")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Open", counts["open"])
    c2.metric("In progress", counts["in_progress"])
    c3.metric("Closed / Replied", counts["closed"])
    c4.metric("Total", counts["total"])

    # 2. Tier rates
    st.subheader("Tier rates")
    t_cols = st.columns(len(TIER_ORDER))
    for i, tier in enumerate(TIER_ORDER):
        label, icon, _ = TIER_META[tier]
        cnt, rate = rates[tier]
        t_cols[i].metric(f"{icon} {label}", f"{rate:.0%}", f"{cnt} ticket(s)")

    st.divider()

    # 3. Safety dial chart
    st.subheader("Safety dial")
    dial_data = _load_json(eval_dir / "safety_dial.json")
    if dial_data is None:
        st.info("No safety dial data found — run `make dial` to generate `data/eval/safety_dial.json`.")
    else:
        dial_df = _extract_dial_df(dial_data)
        if dial_df is not None:
            numeric_cols = [c for c in dial_df.columns if pd.api.types.is_numeric_dtype(dial_df[c])]
            x_col = next((c for c in numeric_cols if "thresh" in c.lower()), None)
            if x_col and len(numeric_cols) > 1:
                y_cols = [c for c in numeric_cols if c != x_col]
                st.line_chart(dial_df.set_index(x_col)[y_cols])
            elif numeric_cols:
                st.line_chart(dial_df[numeric_cols])
            st.dataframe(dial_df, hide_index=True, use_container_width=True)
        else:
            st.json(dial_data)

    # 4. Holdout metrics
    st.subheader("Holdout metrics")
    report_data = _load_json(eval_dir / "latest" / "report.json")
    if report_data is None:
        st.info("No holdout report found — run `make sentinel-eval` to generate `data/eval/latest/report.json`.")
    elif isinstance(report_data, dict):
        scalars = {k: v for k, v in report_data.items() if isinstance(v, (int, float, str))}
        if scalars:
            cols = st.columns(min(4, len(scalars)))
            for idx, (k, v) in enumerate(list(scalars.items())[:8]):
                val = f"{v:.3f}" if isinstance(v, float) else str(v)
                cols[idx % len(cols)].metric(k, val)
        with st.expander("Full holdout report JSON", expanded=not bool(scalars)):
            st.json(report_data)
    else:
        st.json(report_data)

    # 5. Calibration (if present)
    st.subheader("Calibration")
    cal_data = _load_json(eval_dir / "calibration.json")
    if cal_data is None:
        st.caption("Calibration report (`data/eval/calibration.json`) not present yet.")
    else:
        st.json(cal_data)

    st.divider()

    # 6. Label corrections & Retrain
    st.subheader("Learning loop & Retrain")
    corrections = feedback.list_corrections()
    st.caption(f"Saved agent label corrections: **{len(corrections)}**")
    if corrections:
        with st.expander(f"Recent corrections ({len(corrections)})"):
            for corr in corrections[-10:][::-1]:
                st.markdown(
                    f"- `{corr.ticket_id}` **{corr.head}**: `{corr.predicted}` → `{corr.corrected}`"
                )

    if st.button("Retrain", type="primary", key="retrain_btn"):
        with st.spinner("Evaluating challenger model…"):
            st.session_state.last_retrain_result = feedback.retrain_challenger()

    retrain_out = st.session_state.get("last_retrain_result")
    if isinstance(retrain_out, dict):
        status = retrain_out.get("status", "unknown")
        msg = retrain_out.get("message", "")
        used = retrain_out.get("corrections_used", 0)
        st.markdown(f"**Retrain status:** `{status}` · Corrections used: `{used}`")
        if msg:
            st.info(msg)
        for model_key in ("champion", "challenger"):
            if isinstance(retrain_out.get(model_key), dict):
                st.markdown(f"**{model_key.title()} metrics:**")
                st.json(retrain_out[model_key])


render_manager_page()
