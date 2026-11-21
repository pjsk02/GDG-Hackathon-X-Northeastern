"""Shared ownership logic for the edit guard hook and the pre-push check. Python 3.8+, stdlib only.

    from ownership import verdict
    ok, message = verdict("ui/pages/customer.py", branch="Kaushik-Branch")
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(ROOT, "docs", "team", "ownership.json")


def load_map():
    with open(MAP_PATH, encoding="utf-8") as f:
        return json.load(f)


def current_branch(cwd=ROOT):
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except Exception:
        return ""


def is_gitignored(rel_path, cwd=ROOT):
    try:
        out = subprocess.run(["git", "check-ignore", "-q", rel_path], cwd=cwd, capture_output=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False


def owner_of(rel_path, m):
    for branch, spec in m["branches"].items():
        if any(fnmatch.fnmatch(rel_path, g) for g in spec["owns"]):
            return branch, spec["person"]
    return None, None


def verdict(rel_path, branch, m=None):
    """(allowed, message). rel_path is relative to the repo root with forward slashes."""
    m = m or load_map()
    rel_path = rel_path.replace("\\", "/")
    if rel_path.startswith("./"):
        rel_path = rel_path[2:]
    if rel_path in m.get("always_allowed", []) or is_gitignored(rel_path):
        return True, ""
    if branch == "main":
        if os.environ.get("SENTINEL_ALLOW_MAIN") == "1":
            return True, ""
        return False, (
            "You are on main. Nobody edits on main: switch to your own branch first "
            "(git switch <YourName>-Branch). See docs/team/README.md."
        )
    spec = m["branches"].get(branch)
    if spec is None:
        return True, ""  # not a team branch: the guard stays out of the way
    if any(fnmatch.fnmatch(rel_path, g) for g in spec["owns"]):
        return True, ""
    if any(fnmatch.fnmatch(rel_path, g) for g in m["frozen"]["paths"]):
        return False, (
            f"'{rel_path}' is a shared file that nobody edits on their branch. Write what you need in "
            f"docs/requests/{spec['person']}.md and ask your user to send it to Je, who changes it on main. "
            f"Then run `make sync`."
        )
    other_branch, other = owner_of(rel_path, m)
    if other:
        return False, (
            f"'{rel_path}' belongs to {other} ({other_branch}). Do not edit it. If you need a change, "
            f"describe it in docs/requests/{spec['person']}.md and tell your user so they can ask {other}. "
            f"Meanwhile code against the documented interface (the docstring at the top of that file)."
        )
    return False, (
        f"'{rel_path}' is not assigned to anyone in docs/team/ownership.json. You ({spec['person']}) may only "
        f"create or edit files listed under {branch}. If you need a new file, ask your user to ask Je to add "
        f"it to your list, or put the code in one of your own files."
    )
