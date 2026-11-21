"""Pre-push check: does this branch only change files its owner owns?

    python scripts/check_ownership.py            # exit 0 = clean, 1 = violations listed

Compares the branch with origin/main (three-dot diff, so changes merged in from main are ignored)
plus any uncommitted changes. Python 3.8+, stdlib only.
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ownership import ROOT, current_branch, load_map, verdict  # noqa: E402


def changed_files():
    def git(*args):
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return [line.strip() for line in out.stdout.splitlines() if line.strip()]

    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, capture_output=True)
    files = set(git("diff", "--name-only", "origin/main...HEAD"))
    for line in git("status", "--porcelain"):
        files.add(line[3:].split(" -> ")[-1].strip('"'))
    return sorted(files)


def main():
    branch = current_branch()
    m = load_map()
    if branch not in m["branches"]:
        print(f"Branch '{branch}' is not a team branch; nothing to check.")
        return 0
    bad = []
    for f in changed_files():
        ok, msg = verdict(f, branch, m)
        if not ok:
            bad.append((f, msg))
    if not bad:
        print(f"OK: every changed file on {branch} belongs to {m['branches'][branch]['person']}.")
        return 0
    print(f"Ownership check FAILED on {branch}:")
    for f, msg in bad:
        print(f"  - {f}: {msg}")
    print("Undo those changes (git checkout origin/main -- <file>) before pushing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
