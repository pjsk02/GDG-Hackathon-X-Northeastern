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


def parse_status_z(output):
    """Paths from `git status --porcelain -z`.

    Each entry is "XY path" (two status letters, a space, the path) ending in NUL; a rename or copy is
    followed by a second NUL-terminated entry holding the old path, which is skipped. With -z git never
    quotes paths, and the leading status columns must not be stripped (" M path" is a modified file).
    """
    entries = output.split("\0")
    paths, i = [], 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            i += 1  # the original path of a rename or copy
    return paths


def changed_files():
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout

    subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=ROOT, capture_output=True)
    files = {line.strip() for line in git("diff", "--name-only", "origin/main...HEAD").splitlines() if line.strip()}
    # -uall lists every file inside a new folder instead of just "folder/".
    files.update(parse_status_z(git("status", "--porcelain", "-z", "-uall")))
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
