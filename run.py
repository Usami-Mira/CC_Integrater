#!/usr/bin/env python3
"""Minimal bootstrap — launches Orchestrator Agent via Claude Code CLI."""

import sys, os, json, re, subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

CONFIG = json.loads(open(os.path.join(ROOT, "config.json"), encoding="utf-8").read())
MODEL = CONFIG.get("model", "sonnet")
TIMEOUT = CONFIG.get("timeout_seconds", 600)

SUMMARY_FILE = "problems/001/final_summary.md"


def extract_section(md, heading):
    """Extract content after '## <heading>' until the next ## or EOF."""
    pattern = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, md, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else "problems/001"

    outline = open(os.path.join(ROOT, "outline.md"), encoding="utf-8").read()
    orchestrator_prompt = extract_section(outline, "System: Orchestrator")

    if not orchestrator_prompt:
        print("Error: cannot find '## System: Orchestrator' in outline.md")
        sys.exit(1)

    agents_json = json.dumps({
        "Orchestrator": {
            "description": "Orchestrator — 编排多个Agent解决物理题目",
            "prompt": orchestrator_prompt,
        }
    })

    cmd = [
        "claude",
        "--print",
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--bare",
        "--agents", agents_json,
        "--agent", "Orchestrator",
        "--allowed-tools", "Bash,Read,Write",
        "--add-dir", workspace,
        "--model", MODEL,
        f"请解决 {workspace}/problem.md 中的物理题目。\n"
        f"先读取 outline.md 了解工作流架构和各 Agent 定义，然后按照架构执行。\n"
        f"创建子 Agent 的方法：Bash 调用 spawn.py <role> <workspace> <prompt_file> <task_file>\n"
        f"全部阶段完成后，将最终解题结果（包含轮次统计、用时、Token消耗等关键指标和解题内容）写入 {workspace}/final_summary.md 文件。\n"
        f"工作目录: {workspace}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Error: JSON parse failed\n{result.stdout[-500:]}")
        sys.exit(1)

    if data.get("is_error"):
        print(f"Error: {data.get('result', 'Unknown')[:300]}")
        sys.exit(1)

    # Print whatever Orchestrator wrote
    summary_path = os.path.join(workspace, "final_summary.md")
    if os.path.exists(summary_path):
        print(open(summary_path, encoding="utf-8").read())
    else:
        print("No summary file found.")


if __name__ == "__main__":
    main()
