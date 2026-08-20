#!/usr/bin/env python3
"""Helper script — spawn a sub-Agent via Claude Code CLI with streaming log.

Usage: spawn.py <role> <workspace> <prompt_file> <task_file>
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))
from stream_parser import parse_stream_event
from process_runner import run_streaming_process

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
MODEL = CONFIG.get("model", "sonnet")
TIMEOUT = CONFIG.get("timeout_seconds", 600)

# Per-agent pre-approved permission rules. ``--tools`` separately limits which
# built-in tool categories exist, while deny rules take precedence over these.
AGENT_PROFILES = {
    "Planner": (
        "Read", "Write", "Edit",
        "Bash(python3 *)", "Bash(python *)",
        "Bash(git status*)", "Bash(git diff*)", "Bash(git log *)",
    ),
    "Builder": (
        "Read", "Write", "Edit",
        "Bash(python3 *)", "Bash(python *)",
        "Bash(git status*)", "Bash(git diff*)", "Bash(git log *)",
    ),
    "Evaluator": (
        "Read", "Write",
        "Bash(python3 *)", "Bash(python *)",
        "Bash(git status*)", "Bash(git diff*)", "Bash(git log *)",
    ),
}

AGENT_TOOL_SETS = {
    "Planner": "Bash,Read,Write,Edit",
    "Builder": "Bash,Read,Write,Edit",
    "Evaluator": "Bash,Read,Write",
}

AGENT_DISALLOWED_TOOLS = (
    "Bash(git add *)",
    "Bash(git commit *)",
    "Bash(git reset *)",
    "Bash(git clean *)",
    "Bash(git checkout *)",
    "Bash(git switch *)",
    "Bash(git branch *)",
    "Bash(git merge *)",
    "Bash(git rebase *)",
    "Bash(git push *)",
    "Bash(curl *)",
    "Bash(wget *)",
    "mcp__*",
)


def main():
    if len(sys.argv) < 5:
        print("Usage: spawn.py <role> <workspace> <prompt_file> <task_file>")
        sys.exit(1)

    role = sys.argv[1]
    if role not in AGENT_PROFILES:
        print(f"Unknown role: {role}")
        sys.exit(1)

    workspace = str(Path(sys.argv[2]).resolve())
    prompt_file = Path(sys.argv[3]).resolve()
    task_file = Path(sys.argv[4]).resolve()
    allowed_tools = AGENT_PROFILES[role]
    available_tools = AGENT_TOOL_SETS[role]

    system_prompt = prompt_file.read_text(encoding="utf-8")
    task = task_file.read_text(encoding="utf-8")
    if workspace:
        task += f"\n工作目录: {workspace}"

    agents_json = json.dumps({role: {"description": f"{role} Agent", "prompt": system_prompt}})

    cmd = [
        "claude",
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "default",
        "--bare",
        "--agents", agents_json,
        "--agent", role,
        "--tools", available_tools,
        "--allowed-tools", *allowed_tools,
        "--disallowed-tools", *AGENT_DISALLOWED_TOOLS,
        "--add-dir", workspace,
        "--model", MODEL,
        task,
    ]

    log_path = os.path.join(workspace, f".{role}.log")
    start_time = time.time()

    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"[start] {role} | {time.strftime('%H:%M:%S')}\n")
        log_file.flush()

        result_event = None

        def handle_stdout(line):
            nonlocal result_event
            line = line.strip()
            if not line:
                return
            etype, summary, event = parse_stream_event(line)
            if summary:
                log_file.write(f"[{etype}] {summary}\n")
                log_file.flush()
            if etype == "result" and event:
                result_event = event

        try:
            process_result = run_streaming_process(
                cmd,
                timeout=TIMEOUT,
                on_stdout_line=handle_stdout,
                cwd=workspace,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.time() - start_time
            stderr_output = exc.stderr or ""
            log_file.write(
                f"[error] timeout={TIMEOUT}s stderr={stderr_output[-500:]}\n"
            )
            log_file.flush()
            print(f"[spawn:{role}] error: timed out after {TIMEOUT}s")
            sys.exit(1)

        elapsed = time.time() - start_time

        if process_result.returncode != 0:
            stderr_output = process_result.stderr
            log_file.write(f"[error] returncode={process_result.returncode} stderr={stderr_output[:500]}\n")
            log_file.flush()
            print(f"[spawn:{role}] error: exit code {process_result.returncode}")
            sys.exit(1)

        if not result_event:
            log_file.write(f"[error] no result event received\n")
            log_file.flush()
            print(f"[spawn:{role}] error: no result event")
            sys.exit(1)

        if result_event.get("is_error"):
            err_msg = result_event.get("result", "Unknown")[:300]
            log_file.write(f"[error] {err_msg}\n")
            log_file.flush()
            print(f"[spawn:{role}] error: {err_msg}")
            sys.exit(1)

        log_file.write(f"[done] {role} | {time.strftime('%H:%M:%S')} | elapsed={elapsed:.1f}s\n")

    # Write result text for Orchestrator
    result_path = os.path.join(workspace, f".{role}.result")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(result_event.get("result", ""))

    # Write metrics for Orchestrator to collect
    metrics = {
        "role": role,
        "duration_ms": result_event.get("duration_ms", 0),
        "duration_api_ms": result_event.get("duration_api_ms", 0),
        "usage": result_event.get("usage", {}),
    }
    metrics_path = os.path.join(workspace, f".{role}.metrics")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False)

    print(f"[spawn:{role}] done ({elapsed:.0f}s, log: .{role}.log)")


if __name__ == "__main__":
    main()
