import pytest
from services.plugins.calculator import needs_calculator, run_calculator
from services.plugins.datetime_plugin import needs_datetime, run_datetime
from services.plugins.currency import needs_currency
from services.plugins.weather import needs_weather
from services.plugins.wikipedia import needs_wikipedia
from services.plugins.bible import needs_bible


# ── Calculator ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "what is 25 * 4?",
    "calculate 100 / 5",
    "how much is 2 + 2",
    "what's 15% of 200",
])
def test_needs_calculator_true(msg):
    assert needs_calculator(msg) is True


def test_needs_calculator_false():
    assert needs_calculator("what is the capital of Ghana?") is False


def test_run_calculator_basic():
    result = run_calculator("what is 10 + 5?")
    assert "15" in result


def test_run_calculator_percentage():
    result = run_calculator("10% of 200")
    assert "20" in result


# ── Datetime ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "what time is it?",
    "what day is today?",
    "what is today's date",
])
def test_needs_datetime_true(msg):
    assert needs_datetime(msg) is True


def test_run_datetime_returns_time():
    result = run_datetime("what time is it?")
    assert "Ghana" in result or "GMT" in result or ":" in result


# ── Currency ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "what is the exchange rate for GHS",
    "how many cedis is 100 dollars",
    "dollar to cedi today",
])
def test_needs_currency_true(msg):
    assert needs_currency(msg) is True


# ── Weather ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "what is the weather in Accra?",
    "weather today",
    "is it going to rain?",
])
def test_needs_weather_true(msg):
    assert needs_weather(msg) is True


# ── Wikipedia ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "who is Kwame Nkrumah?",
    "tell me about the University of Ghana",
    "what is the history of Ashanti",
])
def test_needs_wikipedia_true(msg):
    assert needs_wikipedia(msg) is True


# ── Bible ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("msg", [
    "read John 3:16",
    "read me Psalm 23",
    "Bible verse about love",
])
def test_needs_bible_true(msg):
    assert needs_bible(msg) is True
