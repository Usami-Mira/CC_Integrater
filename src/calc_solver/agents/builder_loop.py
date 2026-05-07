from __future__ import annotations

import json
from typing import Optional

from calc_solver.llm.prompts import format_prompt, get
from calc_solver.schema import SolvingProblem, StepTrace, Strategy
from calc_solver.tools.sympy_tool import call_tool


async def run_react_loop(
    problem: SolvingProblem,
    strategy: Strategy,
    client,
    temperature: float,
    max_steps: int,
    logger=None,
    prior_steps: list[StepTrace] | None = None,
    prior_error: Optional[str] = None,
) -> tuple[Optional[dict], list[StepTrace], Optional[str]]:
    """Execute the Builder's ReAct loop: think → tool → finish."""
    system = get("builder", "system")
    steps_outline = "\n".join(f"{i+1}. {s}" for i, s in enumerate(strategy.steps_outline))
    first_step = strategy.steps_outline[0] if strategy.steps_outline else ""

    user_init = format_prompt(
        "builder", "user_template",
        question=problem.question,
        variable=problem.variable,
        strategy_name=strategy.name,
        strategy_rationale=strategy.rationale,
        steps_outline=steps_outline,
        first_step=first_step,
    )
    if prior_error:
        hint = format_prompt("builder", "retry_hint",
                             reason=prior_error,
                             weak_step="???")
        user_init = user_init + "\n\n" + hint

    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_init},
    ]

    steps: list[StepTrace] = list(prior_steps or [])
    json_fail_count = 0
    final_result: Optional[dict] = None

    for step_no in range(1, max_steps + 1):
        if step_no >= max_steps:
            messages.append({
                "role": "user",
                "content": "请使用 action=finish 给出最终答案",
            })

        messages = compact_messages(messages, steps)

        raw = await client.chat(
            messages, json_mode=True, temperature=temperature, agent_name="builder",
        )
        action_dict, parse_err = parse_action(raw)

        if parse_err:
            json_fail_count += 1
            if json_fail_count >= 2:
                return final_result, steps, f"json_parse_failed: {parse_err}"
            messages.append({"role": "assistant", "content": raw})
            messages.append({
                "role": "user",
                "content": f"JSON解析错误：{parse_err}。请重新输出有效的 JSON。",
            })
            continue

        json_fail_count = 0
        action = action_dict.get("action", "think")
        thought = action_dict.get("thought", "")
        state = action_dict.get("current_state", "")

        step = StepTrace(step_no=step_no, thought=thought, state=state)

        if action == "finish":
            step.tool_call = None
            steps.append(step)
            final_result = action_dict
            return final_result, steps, None

        elif action == "tool":
            tool_name = action_dict.get("tool", "")
            tool_args = action_dict.get("args", {})
            step.tool_call = {"name": tool_name, "args": tool_args}

            tool_res = call_tool(tool_name, tool_args)
            step.tool_result = tool_res.get("result") or tool_res.get("error")
            steps.append(step)

            messages.append({"role": "assistant", "content": raw})
            if tool_res["ok"]:
                feedback = format_prompt("builder", "tool_result_template",
                                         tool_name=tool_name,
                                         result=tool_res["result"])
            else:
                feedback = (
                    f"工具 {tool_name} 返回错误：{tool_res['error']}。\n"
                    "请检查参数或换一种方法。"
                )
            messages.append({"role": "user", "content": feedback})

        else:  # think
            steps.append(step)
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "请继续下一步"})

    return final_result, steps, "max_steps_exceeded"


def compact_messages(messages: list[dict], steps: list[StepTrace],
                     keep_recent: int = 6, threshold: int = 14) -> list[dict]:
    """Rolling summary: when messages exceed threshold, replace middle with a step digest."""
    if len(messages) <= threshold:
        return messages
    head = messages[:2]
    tail = messages[-keep_recent:]
    n_summarised_steps = max(0, len(steps) - keep_recent // 2)
    digest_lines = []
    for s in steps[:n_summarised_steps]:
        tc = s.tool_call.get("name") if s.tool_call else "?"
        tr = (s.tool_result or "")[:80]
        digest_lines.append(f"step{s.step_no}: tool={tc} state={s.state[:40] if s.state else ''} result={tr}")
    digest = "历史步骤摘要\n" + "\n".join(digest_lines) if digest_lines else ""
    if digest:
        head = head + [{"role": "user", "content": digest}]
    return head + tail


def parse_action(raw: str) -> tuple[dict, Optional[str]]:
    """Parse LLM response into action dict."""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data, None
    except json.JSONDecodeError:
        pass
    m = __import__("re").search(r"\{.*\}", raw, __import__("re").DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data, None
        except Exception:
            pass
    return {}, f"Cannot parse JSON from: {raw[:100]}"
