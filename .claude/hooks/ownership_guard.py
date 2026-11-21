"""PreToolUse hook: block Edit/Write on files this branch does not own.

Claude Code sends the tool call as JSON on stdin. Exit 2 + a message on stderr blocks the edit and
shows Claude the message. Anything else lets the edit through (the guard never blocks on its own
errors). Python 3.8+, stdlib only.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    try:
        event = json.load(sys.stdin)
        tool_input = event.get("tool_input") or {}
        path = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")
        if not path:
            return 0
        from ownership import current_branch, verdict  # noqa: E402

        abs_path = os.path.abspath(os.path.join(event.get("cwd") or ROOT, path))
        rel = os.path.relpath(abs_path, ROOT).replace("\\", "/")
        if rel.startswith(".."):
            return 0  # outside the repo
        allowed, message = verdict(rel, current_branch(ROOT))
        if allowed:
            return 0
        sys.stderr.write("BLOCKED by the team ownership guard: " + message + "\n")
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
