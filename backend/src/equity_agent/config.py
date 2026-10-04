"""Runtime settings: secrets, SEC identity and per-agent Claude model/effort, loaded once from backend/.env.

Every other module reads configuration from a `Settings` object; nothing else reads `os.environ` directly.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

from dotenv import dotenv_values

BACKEND_ROOT = Path(__file__).resolve().parents[2]  # backend/
DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"

Effort = Literal["low", "medium", "high", "xhigh", "max"]
EFFORTS: tuple[str, ...] = get_args(Effort)

AgentName = Literal["comps", "risk", "analyst", "writer"]
AGENTS: tuple[AgentName, ...] = get_args(AgentName)

DEFAULT_MODEL = "claude-opus-5-5"
# The Writer streams prose: Opus 5.5 always thinks first (~11 s to first text), Sonnet 5.5 starts in ~1 s.
DEFAULT_MODELS: dict[AgentName, str] = {
    "comps": DEFAULT_MODEL,
    "risk": DEFAULT_MODEL,
    "analyst": DEFAULT_MODEL,
    "writer": "claude-sonnet-5-5",
}
DEFAULT_EFFORT: Effort = "low"

# Environment variable names, kept in one place so .env.example can be checked against them.
REQUIRED_VARS = ("ANTHROPIC_API_KEY", "TAVILY_API_KEY", "EDGAR_IDENTITY")
OPTIONAL_VARS = tuple(f"{agent.upper()}_MODEL" for agent in AGENTS) + tuple(
    f"{agent.upper()}_EFFORT" for agent in AGENTS
) + ("CORS_ORIGINS", "DEMO_OFFLINE", "DEMO_REPLAY_SPEED")


@dataclass(frozen=True)
class ScoringConfig:
    """Scorecard thresholds (IMPLEMENTATION_PLAN.md §4.5). Fractions: 0.15 means 15 % / 15 percentage points."""

    valuation_band: float = 0.15
    growth_band: float = 0.05
    profitability_band: float = 0.05
    upside_band: float = 0.10
    buy_at: int = 2  # factor total at or above -> BUY
    sell_at: int = -2  # factor total at or below -> SELL
    min_peers: int = 3
    max_peers: int = 5
    momentum_window: int = 200  # trading days for the moving average


class ConfigError(ValueError):
    """Raised at startup when settings are missing or invalid. Messages name settings, never their values."""


@dataclass(frozen=True)
class AgentConfig:
    model: str
    effort: Effort


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(repr=False)
    tavily_api_key: str = field(repr=False)
    edgar_identity: str  # "Name email"; sent to SEC as the User-Agent, not a secret
    agents: dict[AgentName, AgentConfig]
    cors_origins: tuple[str, ...] = ("http://localhost:3000",)
    offline: bool = False  # DEMO_OFFLINE: replay the recording in backend/demo/ instead of calling any service
    replay_speed: float = 0.4  # DEMO_REPLAY_SPEED: offline model calls take this share of their recorded time

    def agent(self, name: AgentName) -> AgentConfig:
        return self.agents[name]

    def secret_values(self) -> tuple[str, ...]:
        """Values that must never appear in logs, errors or responses (used for redaction)."""
        return tuple(v for v in (self.anthropic_api_key, self.tavily_api_key) if v)

    def redact(self, text: str) -> str:
        for value in self.secret_values():
            text = text.replace(value, "***")
        return text


def load_settings(env: Mapping[str, str | None] | None = None, env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Build settings from `env` (tests) or from the process environment layered over `env_file`.

    Real environment variables win over the .env file. Raises ConfigError naming every problem at once.
    """
    if env is None:
        file_values = dotenv_values(env_file) if env_file is not None and env_file.exists() else {}
        merged: dict[str, str | None] = {**file_values, **os.environ}
    else:
        merged = dict(env)

    def get(name: str) -> str:
        return (merged.get(name) or "").strip()

    problems = [f"{name} is missing or empty" for name in REQUIRED_VARS if not get(name)]

    agents: dict[AgentName, AgentConfig] = {}
    for agent in AGENTS:
        model = get(f"{agent.upper()}_MODEL") or DEFAULT_MODELS[agent]
        effort = get(f"{agent.upper()}_EFFORT").lower() or DEFAULT_EFFORT
        if effort not in EFFORTS:
            problems.append(f"{agent.upper()}_EFFORT must be one of {', '.join(EFFORTS)}")
            continue
        agents[agent] = AgentConfig(model=model, effort=effort)  # type: ignore[arg-type]  # validated above

    if problems:
        raise ConfigError("Invalid configuration (see backend/.env.example): " + "; ".join(problems))

    origins = tuple(o.strip() for o in get("CORS_ORIGINS").split(",") if o.strip()) or ("http://localhost:3000",)
    try:
        replay_speed = float(get("DEMO_REPLAY_SPEED") or 0.4)
    except ValueError:
        replay_speed = -1.0
    if replay_speed < 0:
        raise ConfigError("Invalid configuration (see backend/.env.example): DEMO_REPLAY_SPEED must be a number >= 0")
    return Settings(
        anthropic_api_key=get("ANTHROPIC_API_KEY"),
        tavily_api_key=get("TAVILY_API_KEY"),
        edgar_identity=get("EDGAR_IDENTITY"),
        agents=agents,
        cors_origins=origins,
        offline=get("DEMO_OFFLINE").lower() in ("1", "true", "yes"),
        replay_speed=replay_speed,
    )
