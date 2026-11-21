"""Agent workspace: tickets board grouped by tier + side panel for the selected ticket."""

from __future__ import annotations

import html

import streamlit as st

from sentinel import feedback, ticket_store
from sentinel.ticket_store import TicketRecord
from shared.contracts import LabelCorrection
from ui.shared import (
    PRESETS,
    TIER_META,
    badge,
    build_board_dataframe,
    get_agent,
    get_tracker,
    group_tickets_by_tier,
    highlight,
    triage_and_store,
)


def _render_side_panel(rec: TicketRecord) -> None:
    res = rec.result
    st.subheader(f"Ticket `{rec.ticket_id}`")
    st.caption(f"Status: **{rec.status}** · Source: `{rec.source}`")

    if res is None:
        st.info("This ticket has not been triaged yet.")
        return

    tier = res.tier or ("PAGE_ONCALL" if res.escalation == "ESCALATE" else "AUTO_DRAFT")
    tier_label, tier_icon, tier_color = TIER_META.get(tier, ("Page on-call", "🔴", "#dc2626"))

    # 1. Briefing
    st.markdown("**Briefing**")
    if res.briefing:
        st.info(res.briefing)
    else:
        st.caption("Briefing will appear once the LLM writer generates a one-line summary.")

    # 2. Verdict + reason + main action
    st.markdown("**Verdict & action**")
    if tier == "PAGE_ONCALL":
        st.error(f"{tier_icon} **{tier_label}** — requires on-call / human escalation")
    elif tier == "AGENT_REVIEW":
        st.warning(f"{tier_icon} **{tier_label}** — agent should review before sending")
    else:
        st.success(f"{tier_icon} **{tier_label}** — grounded and ready to send")

    if res.escalation_reasons:
        for reason in res.escalation_reasons:
            st.markdown(f"- {reason}")
    else:
        st.caption("No escalation rules fired.")

    action_label = (
        "Approve & Send Reply"
        if tier == "AUTO_DRAFT"
        else ("Approve & Mark Replied" if tier == "AGENT_REVIEW" else "Mark Handled / Close")
    )
    target_status = "closed" if tier == "PAGE_ONCALL" else "replied"
    if rec.status in ("replied", "closed"):
        st.caption(f"Already marked `{rec.status}`.")
    elif st.button(action_label, key=f"action_{rec.ticket_id}", type="primary"):
        ticket_store.set_status(rec.ticket_id, target_status)
        st.rerun()

    st.divider()

    # 3. Message with Original / "What the AI saw" toggle
    st.markdown("**Message**")
    view_mode = st.radio(
        "Message view",
        ["Original", "What the AI saw"],
        horizontal=True,
        key=f"msg_view_{rec.ticket_id}",
        label_visibility="collapsed",
    )
    if view_mode == "Original":
        if rec.subject:
            st.markdown(f"**Subject:** {html.escape(rec.subject)}")
        else:
            st.caption("Subject: *(none)*")
        st.text(rec.body)
    else:
        if res.pii_masked_body:
            if res.pii_masked:
                counts = ", ".join(f"{k}×{v}" for k, v in res.pii_found.items())
                st.caption(f"🔒 PII redacted before LLM saw it: {counts}")
            else:
                st.caption("No PII detected; identical to original.")
            st.text(res.pii_masked_body)
        else:
            st.caption("Masked text will appear here when PII masking runs.")

    st.divider()

    # 4. Three triage questions with confidence and explanation words
    st.markdown("**Triage predictions & why**")
    t = res.triage
    prio_tone = {"high": "#fecaca", "medium": "#fde68a", "low": "#d1fae5"}.get(t.priority, "#e2e8f0")
    st.markdown(
        "".join(
            [
                badge("Type", f"{t.type} ({t.type_confidence:.0%})"),
                badge("Team", f"{t.queue} ({t.queue_confidence:.0%})"),
                badge("Priority", f"{t.priority} ({t.priority_confidence:.0%})", prio_tone),
            ]
        ),
        unsafe_allow_html=True,
    )
    if res.explanations:
        for head in ("type", "queue", "priority"):
            words = res.explanations.get(head, [])
            if words:
                st.caption(f"**{head}**: " + ", ".join(f"`{w}`" for w in words))
    else:
        st.caption("Explanation words (`result.explanations`) will appear here once `sentinel/explain.py` is active.")

    st.divider()

    # 5. Safety checks (fired rules + injection flags)
    st.markdown("**Safety checks**")
    if res.escalation_reasons or res.injection_flags:
        for reason in res.escalation_reasons:
            st.markdown(f"- {reason}")
        for flag in res.injection_flags:
            st.markdown(f"- R7 injection flag: `{flag}`")
    else:
        st.caption("All safety checks passed (no rules fired).")

    st.divider()

    # 6. Past tickets (precedents)
    st.markdown(f"**Past tickets ({len(res.precedents)})**")
    if not res.precedents:
        st.caption("No past tickets retrieved (index empty or retrieval skipped).")
    else:
        cited = {v.ticket_id: v.evidence_quote for v in res.verified_citations}
        for p in res.precedents:
            mark = "✅ cited" if p.ticket_id in cited else ""
            with st.expander(
                f"`{p.ticket_id}` · sim {p.similarity:.3f} · {p.language} · {p.queue} · "
                f"{p.type}/{p.priority} {mark}",
                expanded=p.ticket_id in cited,
            ):
                if p.subject:
                    st.markdown(f"**{html.escape(p.subject)}**")
                st.caption(p.body_snippet[:260])
                st.markdown(
                    f"<div style='font-size:14px;white-space:pre-wrap'>"
                    f"{highlight(p.answer[:1200], [cited[p.ticket_id]] if p.ticket_id in cited else [])}</div>",
                    unsafe_allow_html=True,
                )

    st.divider()

    # 7. Reply with verified citations and guard findings
    st.markdown("**Drafted reply & citations**")
    if res.refused:
        st.info(f"Model refused: {res.refusal_reason or 'no precedent supports an answer'}")
    if res.draft_reply:
        st.markdown(
            f"<div style='background:#f8fafc;border-left:4px solid {tier_color};padding:14px;"
            f"border-radius:6px;white-space:pre-wrap'>{html.escape(res.draft_reply)}</div>",
            unsafe_allow_html=True,
        )
    elif not res.refused:
        st.caption("No draft reply produced yet.")

    if res.verified_citations:
        st.markdown("**Verified citations:** " + ", ".join(f"`{v.ticket_id}`" for v in res.verified_citations))
    else:
        st.caption("Verified citations will appear here once a reply is grounded.")

    if res.rejected_citations:
        with st.expander(f"❌ {len(res.rejected_citations)} citation(s) rejected"):
            for rej in res.rejected_citations:
                st.markdown(f"- `{rej.citation.ticket_id}` **{rej.kind}** — {rej.reason}")

    st.markdown("**Guard findings**")
    if res.guard_findings:
        for g in res.guard_findings:
            st.warning(f"`{g.kind}` (`{g.text}`): {g.reason}")
    else:
        st.caption("No guard findings (number-and-promise guard will appear here when triggered).")

    st.divider()

    # 8. Correct labels form
    with st.expander("✏️ Correct labels", expanded=False):
        with st.form(f"correct_labels_{rec.ticket_id}"):
            head = st.selectbox("Field", ["type", "queue", "priority"], key=f"corr_head_{rec.ticket_id}")
            predicted_val = str(getattr(res.triage, head))
            corrected_val = st.text_input(
                f"Corrected {head} (predicted: {predicted_val})",
                value=predicted_val,
                key=f"corr_val_{rec.ticket_id}",
            )
            if st.form_submit_button("Save correction"):
                cleaned = corrected_val.strip()
                if not cleaned:
                    st.warning("Enter a corrected label first.")
                else:
                    text = f"{rec.subject or ''}\n{rec.body}".strip()
                    feedback.record_correction(
                        LabelCorrection(
                            ticket_id=rec.ticket_id,
                            text=text,
                            head=head,  # type: ignore[arg-type]
                            predicted=predicted_val,
                            corrected=cleaned,
                        )
                    )
                    st.success(f"Saved {head} correction: `{predicted_val}` → `{cleaned}`.")


def render_agent_page() -> None:
    st.title("🛡️ Agent Workspace")

    agent = get_agent()
    tracker = get_tracker()
    provider = st.session_state.get("llm_provider", agent.settings.llm_provider)
    fallback = st.session_state.get("llm_fallback", True)
    k = st.session_state.get("sentinel_top_k", agent.settings.sentinel_top_k)

    alert = tracker.check()
    if alert:
        st.markdown(
            f"<div style='background:#b91c1c;color:white;padding:12px 16px;border-radius:8px;"
            f"font-weight:700;font-size:16px;margin-bottom:12px'>🚨 {html.escape(alert.headline)}</div>",
            unsafe_allow_html=True,
        )

    # Preset buttons add demo tickets and run SentinelAgent().triage on them
    st.caption("Quick demo presets (adds to board and triages):")
    cols = st.columns(len(PRESETS))
    for i, (name, (subj, body)) in enumerate(PRESETS.items()):
        if cols[i].button(name, use_container_width=True, key=f"preset_{i}"):
            with st.spinner(f"Triaging {name}…"):
                tid, res = triage_and_store(
                    agent, subj, body, source="preset", k=k, provider=provider, fallback=fallback
                )
                tracker.observe(res)
                st.session_state.selected_ticket_id = tid
            st.rerun()

    with st.expander("➕ Triage custom ticket", expanded=False):
        with st.form("custom_ticket_form"):
            subj = st.text_input("Subject (optional)", placeholder="leave empty to test null-subject path")
            body = st.text_area("Body", height=120, placeholder="Paste a ticket in English or German…")
            if st.form_submit_button("Triage ticket", type="primary"):
                if (body or "").strip():
                    with st.spinner("Triaging ticket…"):
                        tid, res = triage_and_store(
                            agent, subj, body, source="preset", k=k, provider=provider, fallback=fallback
                        )
                        tracker.observe(res)
                        st.session_state.selected_ticket_id = tid
                    st.rerun()
                else:
                    st.warning("Paste a ticket body first.")

    tickets = ticket_store.list_tickets()
    if not tickets:
        st.info("No tickets on the board yet. Click a preset button above or submit a custom ticket.")
        return

    grouped = group_tickets_by_tier(tickets)
    board_col, panel_col = st.columns([1.15, 1.0], gap="large")

    sections: list[tuple[str, str, list[TicketRecord]]] = [
        ("PAGE_ONCALL", "🔴 Page on-call", grouped["PAGE_ONCALL"]),
        ("AGENT_REVIEW", "🟡 Agent review", grouped["AGENT_REVIEW"]),
        ("AUTO_DRAFT", "🟢 Auto-draft ready", grouped["AUTO_DRAFT"]),
        ("RESOLVED", "✅ Resolved", grouped["RESOLVED"]),
    ]
    if grouped["PENDING"]:
        sections.append(("PENDING", "⏳ Pending", grouped["PENDING"]))

    with board_col:
        st.subheader(f"Tickets board ({len(tickets)})")
        for key, title, group in sections:
            st.markdown(f"**{title} ({len(group)})**")
            if not group:
                st.caption("No tickets in this tier.")
                continue
            df = build_board_dataframe(group)
            event = st.dataframe(
                df[["ticket", "type", "team", "priority", "AI confidence", "waiting time"]],
                key=f"board_{key}",
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
                use_container_width=True,
                column_config={
                    "AI confidence": st.column_config.ProgressColumn(
                        "AI confidence", min_value=0.0, max_value=1.0, format="%.2f"
                    )
                },
            )
            selected_rows = event.selection.rows if event and hasattr(event, "selection") else []
            if selected_rows:
                idx = selected_rows[0]
                if 0 <= idx < len(group):
                    st.session_state.selected_ticket_id = group[idx].ticket_id

    selected_id = st.session_state.get("selected_ticket_id") or tickets[0].ticket_id
    selected_rec = ticket_store.get_ticket(selected_id) or tickets[0]

    with panel_col:
        _render_side_panel(selected_rec)


render_agent_page()
