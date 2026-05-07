from __future__ import annotations

from typing import Optional

from calc_solver.llm.client import QwenClient
from calc_solver.utils.logger import RunLogger


class BaseAgent:
    name: str = "base"

    def __init__(
        self,
        client: QwenClient,
        temperature: float,
        logger: Optional[RunLogger] = None,
    ):
        self.client = client
        self.temperature = temperature
        self.logger = logger

    async def _call(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        temperature: Optional[float] = None,
        agent_name: str = "unknown",
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return await self.client.chat(
            messages,
            temperature=temperature if temperature is not None else self.temperature,
            json_mode=json_mode,
            agent_name=agent_name,
        )

    async def _call_messages(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: Optional[float] = None,
        agent_name: str = "unknown",
    ) -> str:
        return await self.client.chat(
            messages,
            temperature=temperature if temperature is not None else self.temperature,
            json_mode=json_mode,
            agent_name=agent_name,
        )
