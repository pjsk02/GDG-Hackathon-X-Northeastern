---
name: ship-step
description: Finish the current step - verify, check ownership, commit, push to your own branch, log progress, then stop and ask the user before the next step.
argument-hint: "[step number]"
---

Ship step $ARGUMENTS of your plan (docs/prompts/<YourName>.md).

1. Use the `test-runner` subagent to run `pytest -q` plus the step's "Done when" checks. Fix failures in your own
   files; do not continue with failing checks.
2. Use the `ownership-reviewer` subagent. If it reports FAIL, undo the changes to files you do not own.
3. Append to docs/progress/<YourName>.md: step number and title, what was built, files changed, how it was
   verified (commands and results), open issues, and anything a teammate must know (interfaces, new data files).
4. `git add` only your own files, `git commit -m "<YourName> step <N>: <title>"`, then
   `git push -u origin <YourName>-Branch`. Never push to main, never force-push.
5. STOP. Post this report to the user and end your turn:

   **Step N done: <title>**
   - Built: ...
   - Verified: ...
   - Pushed: <YourName>-Branch @ <short sha>
   - Needs from others / open issues: ...
   - Next: Step N+1 - <title> (one line on what it does)

   Reply **yes, you can proceed** to start Step N+1.

Do not start the next step until the user replies with that approval.
