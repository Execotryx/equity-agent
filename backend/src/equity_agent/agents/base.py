"""ClaudeAgent: one structured call, application validation, at most one re-ask."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from equity_agent.agents.payloads import compact_json
from equity_agent.config import AgentName
from equity_agent.llm import LlmClient, LlmError
from equity_agent.models import LlmUsage

PROMPTS_DIR = Path(__file__).parent / "prompts"

In = TypeVar("In")
Out = TypeVar("Out", bound=BaseModel)


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


def word_count(text: str | None) -> int:
    return len((text or "").split())


class StageFailed(Exception):
    """An agent stage that could not produce valid output; carries the usage of every attempt."""

    def __init__(self, message: str, usages: list[LlmUsage]) -> None:
        super().__init__(message)
        self.usages = usages


@dataclass
class AgentRun(Generic[Out]):
    output: Out
    usages: list[LlmUsage] = field(default_factory=list)


class ClaudeAgent(Generic[In, Out]):
    name: ClassVar[AgentName]  # selects the configured model and effort
    prompt_name: ClassVar[str | None] = None  # defaults to `name`; set when one agent makes two kinds of call
    output_model: ClassVar[type[BaseModel]]

    def __init__(self) -> None:
        self.system = load_prompt(self.prompt_name or self.name)

    def payload(self, data: In) -> dict[str, Any]:
        raise NotImplementedError

    def build_user(self, data: In) -> str:
        """The exact user message the model receives (also used by the evaluation to rebuild contexts)."""
        return compact_json(self.payload(data))

    def validate(self, out: Out, data: In) -> list[str]:
        return []

    async def _call(self, llm: LlmClient, user: str, record: Callable[[LlmUsage], None]) -> Out:
        try:
            out, usage = await llm.parse(self.name, self.output_model, self.system, user)  # type: ignore[arg-type]
        except LlmError as error:
            if error.usage:
                record(error.usage)
            raise StageFailed(str(error), []) from error
        record(usage)
        return out  # type: ignore[return-value]

    async def run(self, llm: LlmClient, data: In, on_usage: Callable[[LlmUsage], None] | None = None) -> AgentRun[Out]:
        """Call, validate, re-ask once if needed. Each call's usage goes to `on_usage` as it happens and is also
        kept on the result (or on the StageFailed)."""
        usages: list[LlmUsage] = []

        def record(usage: LlmUsage) -> None:
            usages.append(usage)
            if on_usage is not None:
                on_usage(usage)

        user = self.build_user(data)
        try:
            return await self._attempts(llm, data, user, record, usages)
        except StageFailed as error:
            error.usages = usages
            raise

    async def _attempts(
        self, llm: LlmClient, data: In, user: str, record: Callable[[LlmUsage], None], usages: list[LlmUsage]
    ) -> AgentRun[Out]:
        out = await self._call(llm, user, record)
        problems = self.validate(out, data)
        if not problems:
            return AgentRun(out, usages)
        retry = (
            f"{user}\n\nYour previous answer broke these rules:\n"
            + "\n".join(f"- {p}" for p in problems)
            + "\nReturn a corrected answer that follows every rule."
        )
        out = await self._call(llm, retry, record)
        problems = self.validate(out, data)
        if problems:
            raise StageFailed("invalid output after re-ask: " + "; ".join(problems), usages)
        return AgentRun(out, usages)
