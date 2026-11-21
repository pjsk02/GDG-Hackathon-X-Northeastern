"""Offline tests for scripts/check_ownership.py: parsing `git status --porcelain -z` output."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_ownership  # noqa: E402


def test_unstaged_modification_keeps_the_first_letter():
    # " M path": the leading space is a status column, not whitespace to strip.
    out = " M eval/sentinel_eval.py\0 M docs/demo/demo_tickets.md\0"
    assert check_ownership.parse_status_z(out) == ["eval/sentinel_eval.py", "docs/demo/demo_tickets.md"]


def test_staged_untracked_and_both_columns():
    out = "M  README.md\0?? uv.lock\0MM sentinel/triage.py\0A  tests/test_new.py\0"
    assert check_ownership.parse_status_z(out) == ["README.md", "uv.lock", "sentinel/triage.py", "tests/test_new.py"]


def test_rename_reports_the_new_path_only():
    out = "R  docs/new name.md\0docs/old name.md\0 M ui/app.py\0"
    assert check_ownership.parse_status_z(out) == ["docs/new name.md", "ui/app.py"]


def test_empty_output():
    assert check_ownership.parse_status_z("") == []


def test_matches_real_git_in_a_temp_repo(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, capture_output=True, text=True, check=True).stdout

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "eval").mkdir()
    (tmp_path / "eval" / "a.py").write_text("x\n")
    git("add", ".")
    git("commit", "-q", "-m", "init")
    (tmp_path / "eval" / "a.py").write_text("y\n")
    (tmp_path / "new dir").mkdir()
    (tmp_path / "new dir" / "b.md").write_text("z\n")
    out = git("status", "--porcelain", "-z", "-uall")
    assert sorted(check_ownership.parse_status_z(out)) == ["eval/a.py", "new dir/b.md"]
