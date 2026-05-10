from __future__ import annotations

import asyncio
import re
import time
from typing import Optional

from vllm import AsyncEngineArgs, AsyncLLMEngine, SamplingParams

from calc_solver.utils.logger import RunLogger


class VLLMClient:
    """vLLM async client with the same interface as QwenClient."""

    def __init__(
        self,
        model_id: str,
        timeout_s: int = 120,
        max_concurrent: int = 16,
        logger: Optional[RunLogger] = None,
    ):
        self.model_id = model_id
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrent)
        self.logger = logger

        engine_args = AsyncEngineArgs(
            model=model_id,
            tensor_parallel_size=1,
            dtype="auto",
            max_model_len=8192,
            gpu_memory_utilization=0.9,
            disable_log_requests=True,
        )
        self._engine = AsyncLLMEngine.from_engine_args(engine_args)

    async def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        json_mode: bool = False,
        max_retries: int = 3,
        agent_name: str = "unknown",
    ) -> str:
        prompt = self._messages_to_prompt(messages)
        sampling = SamplingParams(
            temperature=temperature,
            max_tokens=4096,
            top_p=0.95,
        )

        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with self._sem:
                    t0 = time.monotonic()
                    result = await self._engine.generate(
                        prompt,
                        request_id=f"{agent_name}_{time.monotonic()}",
                        sampling_params=sampling,
                    )
                    elapsed = time.monotonic() - t0
                    content = result.outputs[0].text.strip()
                    prompt_tokens = len(result.prompt_token_ids) if result.prompt_token_ids else 0
                    completion_tokens = len(result.outputs[0].token_ids) if result.outputs[0].token_ids else 0

                    if self.logger:
                        self.logger.log_llm({
                            "model": self.model_id,
                            "temperature": temperature,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "elapsed_s": round(elapsed, 2),
                            "json_mode": json_mode,
                            "content": content,
                            "agent": agent_name,
                        })
                        self.logger.log_llm_verbose({
                            "model": self.model_id,
                            "temperature": temperature,
                            "json_mode": json_mode,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
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
    def _messages_to_prompt(messages: list[dict]) -> str:
        """Convert OpenAI-style messages to chat template prompt."""
        parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"<|im_start|>system\n{content}<|im_end|>")
            elif role == "user":
                parts.append(f"<|im_start|>user\n{content}<|im_end|>")
            elif role == "assistant":
                parts.append(f"<|im_start|>assistant\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    @staticmethod
    def _extract_json(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return m.group(0)
        return text
