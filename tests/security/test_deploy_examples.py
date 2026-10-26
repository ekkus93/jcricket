import re
from pathlib import Path

PROXY_EXAMPLE = Path(__file__).resolve().parents[2] / "deploy" / "reverse-proxy.example"


def _mcp_location() -> str:
    text = PROXY_EXAMPLE.read_text(encoding="utf-8")
    match = re.search(r"location = /mcp \{(?P<body>.*?)\n    \}", text, re.DOTALL)
    assert match, "reverse-proxy example must contain a `location = /mcp` block"
    return match["body"]


def test_proxy_example_strips_client_authorization() -> None:
    body = _mcp_location()
    assert 'proxy_set_header Authorization "";' in body
    assert "proxy_set_header Host $host;" in body
    assert "proxy_set_header Host 127.0.0.1" not in body
