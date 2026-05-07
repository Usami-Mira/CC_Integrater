from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Optional

from openai import AsyncOpenAI

from calc_solver.utils.logger import RunLogger


class QwenClient:
    def __init__(
        self,
        model_id: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key: Optional[str] = None,
        timeout_s: int = 60,
        max_concurrent: int = 16,
        logger: Optional[RunLogger] = None,
    ):
        self.model_id = model_id
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrent)
        self.logger = logger
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=base_url,
            timeout=timeout_s,
        )

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        json_mode: bool = False,
        max_retries: int = 3,
        agent_name: str = "unknown",
    ) -> str:
        kwargs: dict = {
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with self._sem:
                    t0 = time.monotonic()
                    resp = await self._client.chat.completions.create(**kwargs)
                    elapsed = time.monotonic() - t0
                    content = resp.choices[0].message.content or ""

                    if self.logger:
                        self.logger.log_llm({
                            "model": self.model_id,
                            "temperature": temperature,
                            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                            "elapsed_s": round(elapsed, 2),
                            "json_mode": json_mode,
                            "content": content,
                            "agent": agent_name,
                        })
                        # Verbose logging for debugging
                        self.logger.log_llm_verbose({
                            "model": self.model_id,
                            "temperature": temperature,
                            "json_mode": json_mode,
                            "prompt_tokens": resp.usage.prompt_tokens if resp.usage else 0,
                            "completion_tokens": resp.usage.completion_tokens if resp.usage else 0,
                            "elapsed_s": round(elapsed, 2),
                            "agent": agent_name,
                            "request": {"messages": messages},
                            "response": {"content": content},
                        })

                    if json_mode:
                        return self._extract_json(content)
                    return content

            except Exception as e:
                last_err = e
                wait = 2 ** attempt
                if self.logger:
                    self.logger.error("llm_retry", attempt=attempt, error=str(e), wait=wait)
                await asyncio.sleep(wait)

        raise RuntimeError(f"LLM call failed after {max_retries} retries: {last_err}")

    @staticmethod
    def _extract_json(text: str) -> str:
        """Robustly extract first {...} or [...] block from LLM output."""
        text = text.strip()
        # strip markdown code fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        # find first { ... }
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
        return text

