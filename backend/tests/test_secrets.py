import logging

from equity_agent.config import load_settings

ANTHROPIC_KEY = "sk-ant-test-secret-value-123"
TAVILY_KEY = "tvly-test-secret-value-456"
ENV = {"ANTHROPIC_API_KEY": ANTHROPIC_KEY, "TAVILY_API_KEY": TAVILY_KEY, "EDGAR_IDENTITY": "Test Person t@example.com"}


def test_str_and_repr_hide_keys():
    settings = load_settings(ENV)
    for text in (str(settings), repr(settings), f"{settings}"):
        assert ANTHROPIC_KEY not in text
        assert TAVILY_KEY not in text
    assert "Test Person" in str(settings)  # non-secret fields stay visible for debugging


def test_logged_settings_hide_keys(caplog):
    with caplog.at_level(logging.INFO):
        logging.getLogger("equity_agent").info("settings loaded: %s", load_settings(ENV))
    assert ANTHROPIC_KEY not in caplog.text
    assert TAVILY_KEY not in caplog.text


def test_redact_replaces_every_secret():
    settings = load_settings(ENV)
    message = f"401 for key {ANTHROPIC_KEY}; search key {TAVILY_KEY}"
    redacted = settings.redact(message)
    assert ANTHROPIC_KEY not in redacted and TAVILY_KEY not in redacted
    assert redacted.count("***") == 2
