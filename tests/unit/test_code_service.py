import pytest
from unittest.mock import AsyncMock, patch
from services.code_service import generate_code, _extract_code_and_explanation


# ── Code extraction ───────────────────────────────────────────────────────────

def test_extract_code_from_markdown():
    text = "Here is the code:\n```python\ndef hello():\n    return 'hi'\n```\nThis function returns hi."
    code, lang, explanation = _extract_code_and_explanation(text, "python")
    assert "def hello" in code
    assert lang == "python"
    assert "function" in explanation.lower()


def test_extract_code_no_block():
    text = "x = 1 + 1"
    code, lang, explanation = _extract_code_and_explanation(text, "python")
    assert code == "x = 1 + 1"
    assert lang == "python"
    assert explanation == ""


# ── generate_code ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_code_calls_inference():
    mock_response = "```python\ndef add(a, b):\n    return a + b\n```\nAdds two numbers."
    with patch(
        "services.code_service.generate_full_response",
        new=AsyncMock(return_value=(mock_response, "cerebras", "qwen3-235b"))
    ):
        code, lang, explanation, provider, model = await generate_code(
            prompt="write a function that adds two numbers",
            language="python",
        )
    assert "def add" in code
    assert lang == "python"
    assert provider == "cerebras"
    assert model == "qwen3-235b"


@pytest.mark.asyncio
async def test_generate_code_handles_failure():
    with patch(
        "services.code_service.generate_full_response",
        new=AsyncMock(side_effect=Exception("provider down"))
    ):
        code, lang, explanation, provider, model = await generate_code(
            prompt="write a sort function",
        )
    assert provider == "none"
    assert code == ""
