#!/usr/bin/env python3
"""Helper script — spawn a sub-Agent via Claude Code CLI with streaming log.

Usage: spawn.py <role> <workspace> <prompt_file> <task_file> [--tools Read,Write,Edit,Bash]
"""

import sys, os, json, subprocess, time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))
from stream_parser import parse_stream_event

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
MODEL = CONFIG.get("model", "sonnet")
TIMEOUT = CONFIG.get("timeout_seconds", 600)

# Per-agent permission profiles
# Format: Claude Code --allowed-tools values
# Bash(pattern) restricts Bash to commands matching the pattern
AGENT_PROFILES = {
    "Planner": (
        "Read,"
        "Write,"
        "Edit,"
        "Bash(python3 *),"
        "Bash(source * && python3 *),"
        "Bash(git status*),"
        "Bash(git diff*),"
        "Bash(git log*),"
        "Bash(git add *)"
    ),
    "Builder": (
        "Read,"
        "Write,"
        "Edit,"
        "Bash(python3 *),"
        "Bash(source * && python3 *),"
        "Bash(git status*),"
        "Bash(git diff*),"
        "Bash(git log*),"
        "Bash(git add *)"
    ),
    "Evaluator": (
        "Read,"
        "Write,"
        "Edit,"
        "Bash(python3 *),"
        "Bash(source * && python3 *),"
        "Bash(git status*),"
        "Bash(git diff*),"
        "Bash(git log*),"
        "Bash(git add *)"
    ),
}


def main():
    if len(sys.argv) < 5:
        print("Usage: spawn.py <role> <workspace> <prompt_file> <task_file> [--tools Read,Write,Edit,Bash]")
        sys.exit(1)

    role = sys.argv[1]
    workspace = sys.argv[2]
    prompt_file = sys.argv[3]
    task_file = sys.argv[4]

    # Determine allowed tools: CLI override > profile > generic default
    allowed_tools = "Read,Write,Edit,Bash"  # fallback default
    if role in AGENT_PROFILES:
        allowed_tools = AGENT_PROFILES[role]
    for i, arg in enumerate(sys.argv):
        if arg == "--tools" and i + 1 < len(sys.argv):
            allowed_tools = sys.argv[i + 1]

    system_prompt = open(prompt_file, encoding="utf-8").read()
    task = open(task_file, encoding="utf-8").read()
    if workspace:
        task += f"\n工作目录: {workspace}"

    agents_json = json.dumps({role: {"description": f"{role} Agent", "prompt": system_prompt}})

    cmd = [
        "claude",
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--bare",
        "--agents", agents_json,
        "--agent", role,
        "--allowed-tools", allowed_tools,
        "--add-dir", workspace,
        "--model", MODEL,
        task,
    ]

    log_path = os.path.join(workspace, f".{role}.log")
    start_time = time.time()

    with open(log_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"[start] {role} | {time.strftime('%H:%M:%S')}\n")
        log_file.flush()

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

        result_event = None

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            etype, summary, event = parse_stream_event(line)
            if summary:
                log_file.write(f"[{etype}] {summary}\n")
                log_file.flush()
            if etype == "result" and event:
                result_event = event

        proc.wait(timeout=TIMEOUT)
        elapsed = time.time() - start_time

        if proc.returncode != 0:
            stderr_output = proc.stderr.read() if proc.stderr else ""
            log_file.write(f"[error] returncode={proc.returncode} stderr={stderr_output[:500]}\n")
            log_file.flush()
            print(f"[spawn:{role}] error: exit code {proc.returncode}")
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
