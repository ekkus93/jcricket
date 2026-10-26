import re
from pathlib import Path

from second_brain_mcp.budget import (
    MESSAGE_OVERHEAD_TOKENS,
    MIN_INPUT_TOKENS,
    available_input,
)
from second_brain_mcp.config import Limits
from second_brain_mcp.prompts import MODE_PROMPTS, system_prompt

ROOT = Path(__file__).resolve().parents[2]
SOURCES = sorted((ROOT / "src" / "second_brain_mcp").glob("*.py"))
PROFILES = {"4k": 4096, "32k": 32768, "128k": 131072, "256k": 262144}
# The example configuration lowers the 4k reserve; other profiles use the default.
COMPLETION = {"4k": 1024}


def test_estimator_constants_and_formula_live_only_in_budget_module() -> None:
    constant = re.compile(
        r"^(MESSAGE_OVERHEAD_TOKENS|PROMPT_OVERHEAD_TOKENS|MIN_INPUT_TOKENS)\s*=",
        re.MULTILINE,
    )
    formula = re.compile(r'encode\("utf-8"\)\)\s*\+|\+\s*(8|16|256)\b')
    offenders = [
        path.name
        for path in SOURCES
        if path.name != "budget.py"
        and (constant.search(path.read_text()) or formula.search(path.read_text()))
    ]
    assert offenders == []


def test_operations_input_table_matches_estimator() -> None:
    longest = max(
        (system_prompt(mode) for mode in MODE_PROMPTS),
        key=lambda prompt: len(prompt.encode("utf-8")),
    )
    text = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
    documented = {
        name: int(value.replace(",", ""))
        for name, value in re.findall(
            r"^\| `(\w+)` \| [\d,]+ \| [\d,]+ \| ([\d,]+) bytes \|$", text, re.MULTILINE
        )
    }
    expected = {
        name: available_input(
            context, COMPLETION.get(name, Limits().completion_tokens), longest
        )
        for name, context in PROFILES.items()
    }
    assert documented == expected


def test_available_input_leaves_room_for_framing() -> None:
    system = "s" * 100
    assert (
        available_input(1000, 200, system)
        == 1000 - 200 - (100 + MESSAGE_OVERHEAD_TOKENS + 16) - MESSAGE_OVERHEAD_TOKENS
    )
    assert MIN_INPUT_TOKENS == 256
