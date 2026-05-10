from magnus import submit_job, JobType, FileSecret
from typing import Annotated, Literal, Optional, List
def safe_quote(s: str) -> str:
    return "'" + str(s).replace("'", r"'\''") + "'"


# ── Calc Solver v2: 批量求解任务蓝图 ──────────────────────────────────────────
# 用 scripts/run_batch.py 跑 Planner → Builder → Evaluator 流水线。
# CPU + LLM API 调用型，不需要 GPU。

ParquetData = Annotated[FileSecret, {
    "label": "Parquet 数据集",
    "description": "微积分题目数据文件，需包含 question / answer 列。用 magnus send 上传后填入 magnus-secret:...",
    "placeholder": "magnus-secret:xxxx-xxxx-xxxx-xxxx",
}]

DashscopeKey = Annotated[FileSecret, {
    "label": "DashScope API Key",
    "description": "通过 magnus send 上传密钥，填入返回的 magnus-secret:...",
    "placeholder": "magnus-secret:xxxx-xxxx-xxxx-xxxx",
}]

# ── 核心参数 ────────────────────────────────────────────────────────────────
K = Annotated[int, {
    "label": "Planner 策略数",
    "description": "每道题生成的求解策略数量。3 = 默认；1 = 快速验证",
    "min": 1,
    "max": 5,
    "scope": "核心参数",
}]

MaxRows = Annotated[int, {
    "label": "题目截断数",
    "description": "0 = 全量；用于 smoke 烟测建议填 10-50",
    "min": 0,
    "max": 999,
    "scope": "核心参数",
}]

# ── 高级参数 ────────────────────────────────────────────────────────────────
MaxOuterLoops = Annotated[int, {
    "label": "Builder-Evaluator 重试轮数",
    "description": "Evaluator 拒绝后最多 replan 几轮",
    "min": 1,
    "max": 3,
    "scope": "高级参数",
}]

MaxConcurrentLLM = Annotated[int, {
    "label": "LLM 并发调用数",
    "description": "全局 LLM 调用并发上限",
    "min": 1,
    "max": 32,
    "scope": "高级参数",
}]

MaxLLMSteps = Annotated[int, {
    "label": "Builder 最大推理步数",
    "description": "单个 Builder 最多调用 LLM 的轮数",
    "min": 4,
    "max": 20,
    "scope": "高级参数",
}]

ProblemConcurrency = Annotated[int, {
    "label": "题目并行度",
    "description": "同时处理的题目数量。值越大吞吐越高但 LLM QPS 也越高",
    "min": 1,
    "max": 16,
    "scope": "高级参数",
}]

Priority = Annotated[Literal["A1", "A2", "B1", "B2"], {
    "label": "优先级",
    "scope": "高级参数",
    "options": {
        "A1": {"label": "A1", "description": "最高优先级，不可被抢占"},
        "A2": {"label": "A2", "description": "高优先级，不可被抢占"},
        "B1": {"label": "B1", "description": "低优先级，可被 A 类抢占"},
        "B2": {"label": "B2", "description": "最低优先级"},
    },
}]


def blueprint(
    parquet_data: ParquetData,
    dashscope_key: DashscopeKey,
    k: K = 3,
    max_rows: MaxRows = 0,
    max_outer_loops: MaxOuterLoops = 2,
    max_concurrent_llm: MaxConcurrentLLM = 16,
    max_llm_steps: MaxLLMSteps = 12,
    problem_concurrency: ProblemConcurrency = 4,
    priority: Priority = "B1",
):
    """批量求解微积分题：scripts/run_batch.py 的 wrapper.

    任何参数变体都通过这里走，不再建临时蓝图。
    smoke 场景设 max_rows=20 即可快速验证。
    """
    solver_args = [
        "--parquet /tmp/input.parquet",
        f"--K {k}",
    ]
    if max_rows > 0:
        solver_args.append(f"--max-rows {max_rows}")

    env_parts = []
    if max_outer_loops != 2:
        env_parts.append(f"SOLVER_MAX_LOOPS={max_outer_loops}")
    if max_concurrent_llm != 16:
        env_parts.append(f"SOLVER_MAX_CONCURRENT={max_concurrent_llm}")
    if max_llm_steps != 12:
        env_parts.append(f"SOLVER_MAX_STEPS={max_llm_steps}")
    if problem_concurrency != 4:
        env_parts.append(f"SOLVER_PROBLEM_CONCURRENCY={problem_concurrency}")

    env_setup = " ".join(env_parts)
    solver_cmd = " ".join(solver_args)

    label_parts = [f"k{k}"]
    if max_rows > 0:
        label_parts.append(f"rows{max_rows}")
    label = "-".join(label_parts)

    description = f"""\
## Calc Solver 批量求解

- 策略数: {k}, 重试轮数: {max_outer_loops}
- 截断: {max_rows if max_rows > 0 else '全量'}
- LLM 并发: {max_concurrent_llm}, Builder 步数: {max_llm_steps}
- 题目并行: {problem_concurrency}
"""

    # entry_command 直接在仓库根目录执行（Magnus 已自动 cd 到 repo）
    entry_command = f"""\
python -c "from magnus import download_file; download_file({safe_quote(parquet_data)}, '/tmp/input.parquet')" && \\
python -c "from magnus import download_file; download_file({safe_quote(dashscope_key)}, '/tmp/.dashscope_key')" && \\
export DASHSCOPE_API_KEY=$(cat /tmp/.dashscope_key) && \\
{env_setup} python scripts/run_batch.py {solver_cmd} && \\
rm -f /tmp/input.parquet /tmp/.dashscope_key\
"""

    submit_job(
        task_name=f"calc-solver-{label}",
        entry_command=entry_command,
        repo_name="CC_Integrater",
        namespace="Usami-Mira",
        branch="planner",
        description=description,
        cpu_count=8,
        memory_demand="32G",
        job_type=getattr(JobType, priority),
        container_image="docker://ghcr.io/xwdun/cc_integrater:latest",
    )