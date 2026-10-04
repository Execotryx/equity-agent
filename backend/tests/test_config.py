import pytest

from equity_agent.config import AGENTS, ConfigError, load_settings

REQUIRED = {
    "ANTHROPIC_API_KEY": "sk-ant-test-0123456789",
    "TAVILY_API_KEY": "tvly-test-0123456789",
    "EDGAR_IDENTITY": "Test Person test@example.com",
}


def test_all_required_present_loads():
    settings = load_settings(REQUIRED)
    assert settings.edgar_identity == "Test Person test@example.com"
    assert settings.cors_origins == ("http://localhost:3000",)


@pytest.mark.parametrize("missing", list(REQUIRED))
def test_missing_required_setting_is_named(missing):
    env = {k: v for k, v in REQUIRED.items() if k != missing}
    with pytest.raises(ConfigError, match=missing):
        load_settings(env)


def test_blank_value_counts_as_missing():
    with pytest.raises(ConfigError, match="EDGAR_IDENTITY"):
        load_settings({**REQUIRED, "EDGAR_IDENTITY": "   "})


def test_all_missing_settings_reported_together():
    with pytest.raises(ConfigError) as error:
        load_settings({})
    for name in REQUIRED:
        assert name in str(error.value)


def test_defaults_per_agent():
    settings = load_settings(REQUIRED)
    for agent in ("comps", "risk", "analyst"):
        assert settings.agent(agent).model == "claude-opus-5-5"
        assert settings.agent(agent).effort == "low"
    assert settings.agent("writer").model == "claude-sonnet-5-5"
    assert settings.agent("writer").effort == "low"


def test_override_one_agent_keeps_other_defaults():
    settings = load_settings({**REQUIRED, "WRITER_MODEL": "claude-haiku-4-5"})
    assert settings.agent("writer").model == "claude-haiku-4-5"
    assert settings.agent("analyst").model == "claude-opus-5-5"
    assert settings.agent("comps").model == "claude-opus-5-5"


def test_effort_override_is_case_insensitive():
    assert load_settings({**REQUIRED, "ANALYST_EFFORT": "Medium"}).agent("analyst").effort == "medium"


def test_invalid_effort_names_the_setting():
    with pytest.raises(ConfigError, match="RISK_EFFORT"):
        load_settings({**REQUIRED, "RISK_EFFORT": "turbo"})


def test_every_agent_configured():
    assert set(load_settings(REQUIRED).agents) == set(AGENTS)


def test_cors_origins_override():
    settings = load_settings({**REQUIRED, "CORS_ORIGINS": "http://localhost:3000, http://127.0.0.1:3000"})
    assert settings.cors_origins == ("http://localhost:3000", "http://127.0.0.1:3000")


def test_env_file_is_used_and_process_env_wins(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "ANTHROPIC_API_KEY=from-file\nTAVILY_API_KEY=from-file\nEDGAR_IDENTITY=File Person file@example.com\n",
        encoding="utf-8",
    )
    for name in REQUIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EDGAR_IDENTITY", "Env Person env@example.com")
    settings = load_settings(env_file=env_file)
    assert settings.anthropic_api_key == "from-file"
    assert settings.edgar_identity == "Env Person env@example.com"
