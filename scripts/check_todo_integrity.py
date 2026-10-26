"""Fail when TODO requirement text drifts from its baseline commit."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

BASELINES = (
    ("docs/TODO.md", "5f245be"),
    ("docs/REMEDIATION_TODO.md", "ca3a444"),
    ("docs/REMEDIATION_2_TODO.md", "54e4554"),
    ("docs/TEST_COVERAGE_TODO.md", "c4eb4f1"),
    ("docs/REMEDIATION_3_TODO.md", "3205580"),
)

ITEM = re.compile(r"^- \[[ xX]\] \*\*(?P<id>[A-Za-z0-9-]+)\*\* (?P<text>.*)$")
SUB_BULLET = re.compile(r"^  - (?P<text>.*)$")
REQUIREMENT_PREFIXES = ("Test:", "Acceptance:")
OWNER_DECISION = re.compile(r"^Owner decision \(\d{4}-\d{2}-\d{2}\):")
GATE = re.compile(r"^\*\*Gate [^*]+:\*\*")


@dataclass
class Item:
    text: str
    requirements: list[str] = field(default_factory=list)
    owner_decision: bool = False


@dataclass
class TodoDocument:
    items: dict[str, Item]
    gates: list[str]


def parse(text: str) -> TodoDocument:
    items: dict[str, Item] = {}
    gates: list[str] = []
    current: Item | None = None
    for line in text.splitlines():
        item_match = ITEM.match(line)
        if item_match:
            current = Item(item_match["text"].rstrip())
            items[item_match["id"]] = current
            continue
        sub_match = SUB_BULLET.match(line)
        if sub_match and current is not None:
            sub_text = sub_match["text"].rstrip()
            if sub_text.startswith(REQUIREMENT_PREFIXES):
                current.requirements.append(sub_text)
            elif OWNER_DECISION.match(sub_text):
                current.owner_decision = True
            continue
        if line.startswith("    ") and current is not None:
            continue
        current = None
        if GATE.match(line):
            gates.append(line.rstrip())
    return TodoDocument(items, gates)


def compare(baseline: TodoDocument, current: TodoDocument, path: str) -> list[str]:
    violations = []
    for item_id, original in baseline.items.items():
        updated = current.items.get(item_id)
        if updated is None:
            violations.append(f"{path}: {item_id}: item was removed")
            continue
        if updated.owner_decision:
            continue
        if updated.text != original.text:
            violations.append(f"{path}: {item_id}: requirement text changed")
        for requirement in original.requirements:
            if requirement not in updated.requirements:
                violations.append(
                    f"{path}: {item_id}: requirement sub-bullet changed or removed: "
                    f"{requirement}"
                )
    for gate in baseline.gates:
        if gate not in current.gates:
            violations.append(f"{path}: gate line changed or removed: {gate}")
    return violations


def check(repo: Path, baselines: tuple[tuple[str, str], ...]) -> list[str]:
    violations = []
    for path, commit in baselines:
        try:
            original = subprocess.run(
                ["git", "show", f"{commit}:{path}"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
        except subprocess.CalledProcessError:
            violations.append(f"{path}: baseline {commit} could not be read")
            continue
        try:
            updated = (repo / path).read_text(encoding="utf-8")
        except OSError:
            violations.append(f"{path}: file could not be read")
            continue
        violations.extend(compare(parse(original), parse(updated), path))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--baseline",
        action="append",
        metavar="PATH@COMMIT",
        help="override the built-in baselines (repeatable)",
    )
    args = parser.parse_args(argv)
    baselines = BASELINES
    if args.baseline:
        pairs = [entry.rsplit("@", 1) for entry in args.baseline]
        if any(len(pair) != 2 for pair in pairs):
            parser.error("--baseline must use PATH@COMMIT")
        baselines = tuple((path, commit) for path, commit in pairs)
    violations = check(args.repo, baselines)
    for violation in violations:
        print(violation)
    if violations:
        print(f"{len(violations)} TODO integrity violation(s)", file=sys.stderr)
        return 1
    print("TODO integrity check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
