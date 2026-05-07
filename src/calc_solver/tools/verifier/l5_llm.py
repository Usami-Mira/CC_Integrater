from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from calc_solver.llm.client import QwenClient
    from calc_solver.utils.logger import RunLogger

from calc_solver.tools.verifier.base import VerifyResult


def check_llm_arbitration(
    pred: str, gold: str, var: str, answer_type: str,
    question: str, pass_count: int, total_count: int,
    llm_client: "QwenClient",
    logger: Optional["RunLogger"] = None,
) -> VerifyResult:
    """L5: LLM arbitration for edge cases."""
    if not llm_client:
        return VerifyResult(is_eq=False, level_used="fail", confidence=0.0, evidence="no_llm_client")
    try:
        from calc_solver.llm.prompts import get, format_prompt
        try:
            system = get("equivalence_judge", "system")
        except (KeyError, TypeError):
            system = ""
        user = format_prompt(
            "equivalence_judge", "user_template",
            question=question,
            answer_type=answer_type,
            pred=pred,
            gold=gold,
            pass_rate=pass_count,
            total=total_count,
        )
        raw = llm_client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.0, json_mode=True, max_retries=1, agent_name="verifier"
        )
        import json
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                if isinstance(data, list) and len(data) > 0:
                    data = data[0] if isinstance(data[0], dict) else {}
                else:
                    data = {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        is_eq = data.get("equivalent", data.get("is_eq", data.get("equal", False)))
        reason = str(data.get("reason", data.get("explanation", "")))[:100]
        if logger:
            logger.info("verifier_L5_success", is_eq=is_eq, reason=reason)
        return VerifyResult(is_eq=is_eq, level_used="L5", confidence=0.6, evidence=f"llm_judge: {reason}")
    except Exception as e:
        if logger:
            logger.info("verifier_L5_error", error=str(e))
        return VerifyResult(is_eq=False, level_used="fail", confidence=0.0, evidence=f"L5_error: {type(e).__name__}: {str(e)[:50]}")
