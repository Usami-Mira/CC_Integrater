#!/usr/bin/env python3
"""Helper script — spawn a sub-Agent via Claude Code CLI.
Called by the Orchestrator through Bash tool use.

Usage: spawn.py <role> <workspace> <prompt_file> <task_file> [--tools Read,Write]
"""

import sys, os, json, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = json.loads(open(os.path.join(ROOT, "config.json"), encoding="utf-8").read())
MODEL = CONFIG.get("model", "sonnet")
TIMEOUT = CONFIG.get("timeout_seconds", 600)


def main():
    if len(sys.argv) < 5:
        print("Usage: spawn.py <role> <workspace> <prompt_file> <task_file> [--tools Read,Write]")
        sys.exit(1)

    role = sys.argv[1]
    workspace = sys.argv[2]
    prompt_file = sys.argv[3]
    task_file = sys.argv[4]

    # Parse optional --tools
    allowed_tools = "Read,Write"
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
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--bare",
        "--agents", agents_json,
        "--agent", role,
        "--allowed-tools", allowed_tools,
        "--add-dir", workspace,
        "--model", MODEL,
        task,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[spawn:{role}] error: JSON parse failed — {result.stdout[-300:]}")
        sys.exit(1)

    if data.get("is_error"):
        print(f"[spawn:{role}] error: {data.get('result', 'Unknown')[:300]}")
        sys.exit(1)

    # Write result text for Orchestrator
    result_path = os.path.join(workspace, f".{role}.result")
    with open(result_path, "w", encoding="utf-8") as f:
        f.write(data.get("result", ""))

    # Write metrics for Orchestrator to collect
    metrics = {
        "role": role,
        "duration_ms": data.get("duration_ms", 0),
        "duration_api_ms": data.get("duration_api_ms", 0),
        "usage": data.get("usage", {}),
    }
    metrics_path = os.path.join(workspace, f".{role}.metrics")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False)

    print(f"[spawn:{role}] done → {result_path}")


if __name__ == "__main__":
    main()
