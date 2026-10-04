import pytest
from fastapi.testclient import TestClient

from equity_agent.api import create_app
from equity_agent.config import ConfigError, load_settings

ANTHROPIC_KEY = "sk-ant-test-secret-value-123"
TAVILY_KEY = "tvly-test-secret-value-456"
ENV = {"ANTHROPIC_API_KEY": ANTHROPIC_KEY, "TAVILY_API_KEY": TAVILY_KEY, "EDGAR_IDENTITY": "Test Person t@example.com"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(load_settings(ENV)), raise_server_exceptions=False)


def test_health_reports_agents_and_boolean_credentials(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["agents"]["analyst"] == {"model": "claude-opus-5-5", "effort": "low"}
    assert body["agents"]["writer"] == {"model": "claude-sonnet-5-5", "effort": "low"}
    assert body["credentials"] == {"anthropic": True, "tavily": True, "edgar_identity": True}


def test_health_never_contains_key_values(client):
    text = client.get("/api/health").text
    assert ANTHROPIC_KEY not in text
    assert TAVILY_KEY not in text


def test_cors_allows_local_frontend(client):
    response = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_cors_rejects_other_origins(client):
    response = client.get("/api/health", headers={"Origin": "http://evil.example.com"})
    assert "access-control-allow-origin" not in response.headers


def test_unhandled_error_returns_json_without_secrets(client, caplog):
    app = client.app

    @app.get("/api/boom")  # type: ignore[attr-defined]
    async def boom():
        raise RuntimeError(f"upstream rejected key {ANTHROPIC_KEY}")

    response = client.get("/api/boom")
    assert response.status_code == 500
    assert response.json() == {"message": "Internal server error"}
    assert ANTHROPIC_KEY not in response.text
    assert ANTHROPIC_KEY not in caplog.text
    assert "***" in caplog.text


def test_startup_fails_without_required_settings(monkeypatch, tmp_path):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match="EDGAR_IDENTITY"):
        create_app(load_settings(env_file=tmp_path / "absent.env"))
