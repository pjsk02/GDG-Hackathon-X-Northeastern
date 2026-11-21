---
name: sync-main
description: Bring the latest main into your own branch safely (merge, never rebase), then run the tests.
---

1. Run `git rev-parse --abbrev-ref HEAD`. If it is `main`, stop and tell the user to switch to their own branch.
2. If `git status --porcelain` shows uncommitted changes, commit them first on your branch
   (`git add <your files> && git commit -m "WIP before sync"`).
3. Run `git fetch origin && git merge --no-edit origin/main`.
   - Files are owned by one person each, so this should never conflict. If it does, stop, show the
     conflicting files, and ask the user; never resolve conflicts in files you do not own.
4. If pyproject.toml changed, run `uv pip install -e ".[all]"`. Then run `pytest -q`.
5. Report: commits merged from main, test result, and anything that changed in shared files (`shared/`, `docs/team/`).
