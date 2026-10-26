import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_todo_integrity.py"

BASELINE = """# TODO

- [ ] **T-001** Build the widget.
  - Test: the widget renders.
  - Acceptance: the widget is documented.
- [ ] **T-002** Ship the widget.

**Gate A:** Widgets work.
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "TODO.md").write_text(BASELINE, encoding="utf-8")
    _git(tmp_path, "add", "TODO.md")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    return tmp_path


@pytest.fixture
def check(load_script, run_main):
    """Run the checker's ``main()`` in-process against ``PATH@COMMIT`` baselines."""
    module = load_script("scripts/check_todo_integrity.py")

    def run(repo: Path, *baselines: str):
        arguments = ["--repo", str(repo)]
        for baseline in baselines:
            arguments += ["--baseline", baseline]
        return run_main(module, *arguments)

    return run


@pytest.fixture
def run_todo(repo: Path, check):
    """Write ``todo`` into the repo and check it against the first commit."""

    def run(todo: str):
        (repo / "TODO.md").write_text(todo, encoding="utf-8")
        commit = _git(repo, "rev-list", "--max-parents=0", "HEAD")
        return check(repo, f"TODO.md@{commit}")

    return run


def test_entry_point_exits_1_on_drift_without_a_traceback(repo: Path) -> None:
    """The one subprocess test: the script really runs as a program."""
    commit = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    (repo / "TODO.md").write_text(
        BASELINE.replace("Ship the widget.", "Ship part of the widget."),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo",
            str(repo),
            "--baseline",
            f"TODO.md@{commit}",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "T-002: requirement text changed" in result.stdout
    assert "Traceback" not in result.stderr


def test_clean_file_with_checked_items_and_evidence_passes(run_todo) -> None:
    todo = BASELINE.replace("- [ ] **T-001**", "- [x] **T-001**").replace(
        "  - Acceptance: the widget is documented.\n",
        "  - Acceptance: the widget is documented.\n  - Evidence: test_widget.\n",
    )
    result = run_todo(todo)
    assert result.returncode == 0, result.stdout
    assert "passed" in result.stdout


@pytest.mark.parametrize(
    ("todo", "message"),
    [
        (BASELINE.replace("- [ ] **T-002** Ship the widget.\n", ""), "T-002: item was"),
        (
            BASELINE.replace("Ship the widget.", "Ship part of the widget."),
            "T-002: requirement text changed",
        ),
        (
            BASELINE.replace("  - Test: the widget renders.\n", ""),
            "T-001: requirement sub-bullet changed or removed: Test:",
        ),
        (
            BASELINE.replace("the widget is documented", "the widget exists"),
            "T-001: requirement sub-bullet changed or removed: Acceptance:",
        ),
        (
            BASELINE.replace("Widgets work.", "Most widgets work."),
            "gate line changed or removed",
        ),
    ],
)
def test_detects_requirement_drift(run_todo, todo: str, message: str) -> None:
    result = run_todo(todo)
    assert result.returncode == 1
    assert message in result.stdout


def test_owner_decision_allows_dated_change(run_todo) -> None:
    todo = BASELINE.replace(
        "- [ ] **T-002** Ship the widget.",
        "- [ ] **T-002** Ship a smaller widget.\n"
        "  - Owner decision (2026-10-26): ship the smaller widget first.",
    )
    assert run_todo(todo).returncode == 0


def test_undated_owner_decision_does_not_allow_change(run_todo) -> None:
    todo = BASELINE.replace(
        "- [ ] **T-002** Ship the widget.",
        "- [ ] **T-002** Ship a smaller widget.\n"
        "  - Owner decision: ship the smaller widget first.",
    )
    result = run_todo(todo)
    assert result.returncode == 1
    assert "T-002: requirement text changed" in result.stdout


def test_unknown_baseline_commit_is_reported(repo: Path, check) -> None:
    result = check(repo, "TODO.md@deadbeef")
    assert result.returncode == 1
    assert "TODO.md: baseline deadbeef could not be read" in result.stdout


def test_missing_todo_file_is_reported(repo: Path, check) -> None:
    commit = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    (repo / "TODO.md").unlink()
    result = check(repo, f"TODO.md@{commit}")
    assert result.returncode == 1
    assert "TODO.md: file could not be read" in result.stdout


def test_baseline_without_commit_is_a_usage_error(repo: Path, check) -> None:
    result = check(repo, "TODO.md")
    assert result.returncode == 2
    assert "--baseline must use PATH@COMMIT" in result.stderr
