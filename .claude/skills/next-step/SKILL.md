---
name: next-step
description: Find your next unfinished step in your plan and start it - read the plan, sync main, then build the step autonomously with subagents.
---

1. Work out who you are from the branch: `git rev-parse --abbrev-ref HEAD` gives `<YourName>-Branch`.
   If you are on `main`, stop and ask the user to run the starter prompt first (docs/prompts/00-starter.md).
2. Read docs/prompts/<YourName>.md (your plan) and docs/progress/<YourName>.md (what is done). The next step is
   the first one not logged as done. If the plan is missing locally, fetch it:
   `curl -sL https://raw.githubusercontent.com/pjsk02/GDG-Hackathon-X-Northeastern/main/docs/prompts/<YourName>.md`
3. Run the `sync-main` skill so you build on the latest main.
4. Tell the user in two lines which step you are starting and what "done" means for it.
5. Build it. Split independent pieces across `builder` subagents (several at once when they touch different
   files), use the `Explore` subagent to read code you do not own, and only ask the user when truly blocked
   (missing API key or data, a change needed in someone else's file, anything destructive).
6. When the step's "Done when" list is satisfied, run the `ship-step` skill with the step number.
