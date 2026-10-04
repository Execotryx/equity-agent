from dotenv import dotenv_values

from equity_agent.config import BACKEND_ROOT, OPTIONAL_VARS, REQUIRED_VARS, load_settings


def test_env_example_documents_every_setting():
    documented = set(dotenv_values(BACKEND_ROOT / ".env.example"))
    missing = set(REQUIRED_VARS + OPTIONAL_VARS) - documented
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_env_example_sets_utf8_mode():
    assert dotenv_values(BACKEND_ROOT / ".env.example").get("PYTHONUTF8") == "1"


def test_env_example_optional_values_are_valid():
    """The example's model/effort lines must load as-is once the required keys are filled in."""
    values = {k: v for k, v in dotenv_values(BACKEND_ROOT / ".env.example").items() if k in OPTIONAL_VARS}
    settings = load_settings({**values, "ANTHROPIC_API_KEY": "x", "TAVILY_API_KEY": "y", "EDGAR_IDENTITY": "A a@b.c"})
    assert settings.agent("writer").model == "claude-sonnet-5-5"
