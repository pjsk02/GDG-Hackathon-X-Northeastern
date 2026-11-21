# Starter prompt (everyone, once)

Paste this into Claude Code (or your coding agent) and replace `<YourName>` with exactly one of:
`Je`, `Shishir`, `Rithwik`, `Sujitha`, `Kaushik`. It makes sure your local copy matches main and puts you on your
own branch. When it reports back, paste the kickoff prompt from the top of `docs/prompts/<YourName>.md`.

```text
Set up my local copy of the SentinelDesk hackathon repo and put me on my own branch. My name is <YourName>.

1. If the current folder is not a git clone of https://github.com/pjsk02/GDG-Hackathon-X-Northeastern, clone it into a new folder named GDG-Hackathon-X-Northeastern and work there from now on.
2. Run `git status`. If there are uncommitted changes or untracked files that are not in .gitignore, show them to me and ask what to do before going further. Do not discard anything without my yes.
3. Run `git fetch origin`, `git switch main`, `git pull --ff-only origin main`. Confirm that `git rev-parse main` equals `git rev-parse origin/main`, and that CLAUDE.md, docs/team/README.md, docs/team/ownership.json and docs/prompts/<YourName>.md exist.
4. Switch to my branch: `git switch <YourName>-Branch` (it already exists on GitHub; if git cannot find it, run `git switch -c <YourName>-Branch --track origin/<YourName>-Branch`). Then run `git merge --no-edit origin/main` and confirm my branch contains the latest main commit.
5. Set up Python 3.12 with uv: `uv venv --python 3.12` then `uv pip install -e ".[all]"`. If uv is missing, tell me and point me to https://docs.astral.sh/uv/getting-started/installation/ . If .env does not exist, copy .env.example to .env. Never print, log or commit API keys.
6. Run `uv run pytest -q` and `uv run python scripts/check_ownership.py`.
7. Read CLAUDE.md and docs/team/README.md so you know the team rules.
8. Report back in a short list: repo path, current branch, main commit hash, my branch commit hash, test result, and anything missing (uv, Python 3.12, the dataset in data/raw/, GEMINI_API_KEY in .env). Then stop and wait for my kickoff prompt.
```

If Claude Code asks whether to trust this folder, say yes: the shared permissions and the ownership guard only
apply in a trusted folder.
