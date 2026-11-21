# Requests from Je

## 2026-11-21 -> Sujitha: Gemini through Vertex AI with a gcloud login (no API key)
File: agent/llm_router.py (`LLMRouter._gemini`)
Why: our credits are on Google Cloud (Vertex AI), not on AI Studio. The plan is to authenticate with
`gcloud auth application-default login` (ADC) instead of an API key. Today `_gemini` raises
"GEMINI_API_KEY is not set" without a key and always passes `api_key=` to `genai.Client`. With a key the SDK goes
to Vertex express mode and ignores the project, so ADC is never used. (Checked offline with google-genai 3.6.1:
with `GOOGLE_GENAI_USE_VERTEXAI=true` and `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` set, `genai.Client()`
with no key resolves to Vertex + that project; `genai.Client(api_key=...)` resolves to express mode with project None.)
Change: in `_gemini`, when the environment variable `GOOGLE_GENAI_USE_VERTEXAI` is "true" (case-insensitive):
- skip the `if not s.gemini_api_key` check;
- create the client without the key: `genai.Client(http_options=types.HttpOptions(timeout=...))`. The SDK reads
  `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT` and `GOOGLE_CLOUD_LOCATION` from the environment and uses ADC.

Otherwise keep today's behaviour exactly (AI Studio key). No contract or settings change: environment variables
only, so `shared/settings.py` stays frozen. A test in `tests/test_llm_router*.py` with a monkeypatched
`genai.Client` can assert that no `api_key` is passed when the variable is set and that the key check is skipped.
Run with:
```bash
export GOOGLE_GENAI_USE_VERTEXAI=true GOOGLE_CLOUD_PROJECT=<project-id> GOOGLE_CLOUD_LOCATION=global
```
Until then: Gemini drafting runs on the AI Studio key (free tier) or falls back to Ollama/extractive. Rithwik:
the planned Gemini embedder (`memory/embedder.py`) needs the same switch so the index can be built on Vertex.
Status: done (2026-11-21, Sujitha, commit 964efd0, merged in PR #6: agent/llm_router.py skips the key and uses ADC when GOOGLE_GENAI_USE_VERTEXAI=true). Rithwik's embedder switch is still open.

## 2026-11-21 -> Kaushik: queue page tests and "Group into one incident" break on current main (patch ready)
File: tests/test_ui_queue.py, ui/shared.py (`render_outage_banner`)
Why: main now has Rithwik's real SmartQueue and sentinel/incidents.py (PR #1). On top of main your branch fails 2 tests,
so your PR cannot be merged yet:
- `test_fire_burst_and_outage_banner_raises_alert`: the real SmartQueue works in background threads, so
  `stats().done` is 0 right after `fire_burst`. Fix: `q.wait_idle(timeout=30)` first.
- `test_queue_page_apptest_fire_10_and_concurrency_and_group_burst`: AppTest does not run the `run_every="1s"`
  fragment, so the banner never sees the finished tickets. Fix: `q.wait_idle(...)` then `at.run()`.
- **Real bug, not just a test:** `render_outage_banner` calls `group_fn(alert)`, but Rithwik's contract is
  `group_burst(alert, tickets) -> Incident` (raises ValueError when no ticket matches). In the real app the
  "Group into one incident" button crashes with a TypeError. The test hid it with a fake one-argument
  `group_burst`; the patch tests against the real module instead.
Change: apply the patch below on Kaushik-Branch (checked: `git apply --check` is clean on 1c64b0b). Verified on
Kaushik-Branch merged with main 5faf069: `tests/test_ui_queue.py` 2/2 three runs in a row, full suite 173 passed
three runs in a row. With the fix the button shows e.g. "Grouped 3 tickets into INC-1003: VPN outage" plus the
incident's status update (only the 3 VPN tickets of the mixed 10-ticket burst belong to the incident).
```bash
git switch Kaushik-Branch && make sync      # merge main first
# save the diff below as fix.patch, then:
git apply fix.patch
pytest -q
```
If your newer UI pushes already changed these lines and `git apply` refuses, make the same 3 edits by hand: the two
`wait_idle` lines (+ `at.run()`), the real-module assertion instead of the fake, and `group_fn(alert, ticket_store.list_tickets())`.
Until then: Kaushik-Branch stays unmerged; main is green (145 passed).
Status: done (2026-11-21, Kaushik, commit 29c9384, merged in PR #7; full suite 444 passed on main).

```diff
diff --git a/tests/test_ui_queue.py b/tests/test_ui_queue.py
index 5808f6b..549e3c1 100644
--- a/tests/test_ui_queue.py
+++ b/tests/test_ui_queue.py
@@ -2,9 +2,7 @@
 
 from __future__ import annotations
 
-import sys
 from pathlib import Path
-from types import ModuleType
 
 import pandas as pd
 
@@ -62,6 +60,7 @@ def test_fire_burst_and_outage_banner_raises_alert():
     q = SmartQueue(agent, concurrency=2)
     fired = fire_burst(q)
     assert fired == 10
+    assert q.wait_idle(timeout=30)  # the real SmartQueue works in background threads
     assert q.stats().done == 10
 
     tracker = OutageTracker()
@@ -85,12 +84,6 @@ def test_queue_page_apptest_fire_10_and_concurrency_and_group_burst(monkeypatch)
     monkeypatch.setattr("ui.shared.get_agent", lambda: agent)
     monkeypatch.setattr("ui.shared.get_queue", lambda _a: q)
 
-    # Provide a fake sentinel.incidents module to verify "Group into one incident" button
-    fake_incidents = ModuleType("sentinel.incidents")
-    grouped_calls: list[object] = []
-    fake_incidents.group_burst = lambda alert: grouped_calls.append(alert) or "INC-001"  # type: ignore[attr-defined]
-    monkeypatch.setitem(sys.modules, "sentinel.incidents", fake_incidents)
-
     queue_page = Path(__file__).resolve().parents[1] / "ui/pages/queue.py"
     at = AppTest.from_file(queue_page, default_timeout=15)
     at.run()
@@ -105,11 +98,16 @@ def test_queue_page_apptest_fire_10_and_concurrency_and_group_burst(monkeypatch)
     fire_btn = next(b for b in at.button if b.key == "fire_10_btn")
     fire_btn.click().run()
     assert not at.exception
+    assert q.wait_idle(timeout=30)  # background workers finish the burst
+    at.run()  # AppTest does not run the 1 s live fragment; re-render so the banner sees the done tickets
+    assert not at.exception
     assert q.stats().done == 10
 
     # Banner should now be visible with "Group into one incident" button
     group_btn = next(b for b in at.button if b.key == "queue_group_burst")
     group_btn.click().run()
     assert not at.exception
-    assert len(grouped_calls) == 1
+    # Rithwik's real sentinel.incidents.group_burst(alert, tickets) grouped the burst
+    # (only the VPN outage tickets of the mixed burst belong to the incident)
+    assert any(s.value.startswith("Grouped ") and "INC-" in s.value and "VPN outage" in s.value for s in at.success)
     ticket_store.reset()
diff --git a/ui/shared.py b/ui/shared.py
index c42d201..63d3ac4 100644
--- a/ui/shared.py
+++ b/ui/shared.py
@@ -97,8 +97,13 @@ def render_outage_banner(tracker: OutageTracker, *, key_prefix: str = "banner")
         if group_fn is None:
             st.info("`incidents.group_burst` is not available yet.")
             return
-        grouped = group_fn(alert)
-        st.success(f"Grouped burst into one incident: {grouped}")
+        try:
+            incident = group_fn(alert, ticket_store.list_tickets())
+        except ValueError as e:  # none of the stored tickets belong to this alert
+            st.warning(f"Could not group this burst: {e}")
+            return
+        st.success(f"Grouped {len(incident.ticket_ids)} tickets into {incident.incident_id}: {incident.title}")
+        st.markdown(incident.status_update)
 
 
 def highlight(text: str, quotes: list[str]) -> str:
```
