import pytest

from second_brain_mcp.errors import ERROR_MESSAGES, SecondBrainError


@pytest.mark.parametrize(("code", "message"), ERROR_MESSAGES.items())
def test_second_brain_errors_have_stable_codes_and_messages(
    code: str, message: str
) -> None:
    error = SecondBrainError(code)
    assert error.code == code
    assert str(error) == f"{code}: {message}"


def test_second_brain_errors_reject_unknown_codes() -> None:
    with pytest.raises(ValueError, match="unknown Second Brain error code"):
        SecondBrainError("made_up")
