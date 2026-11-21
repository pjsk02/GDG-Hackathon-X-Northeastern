# Requests from Rithwik

## 2026-11-21 12:15 -> Je: check_ownership.py drops the first letter of unstaged modified files
File: scripts/check_ownership.py
Why: `git()` strips every output line, so the porcelain line ` M memory/embedder.py` becomes `M memory/embedder.py`
and `line[3:]` gives `emory/embedder.py`, which fails the check. Staged and committed files are read correctly,
so it only bites before `git add`, but every teammate will hit it.
Change: in `changed_files()`, do not strip the `git status --porcelain` lines before slicing, e.g.
`out = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout` and then
`files.add(line[3:].split(" -> ")[-1].strip('"'))` for each non-empty line.
Until then: `git add` my files before running the check.
Status: open
