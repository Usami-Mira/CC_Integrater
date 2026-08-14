#!/usr/bin/env python3
"""Bootstrap — assembles Orchestrator prompt from prompts/ directory and launches via Claude Code CLI.
Streams Orchestrator output to terminal and log file in real-time.
"""

import sys, os, json, subprocess, time
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(ROOT))
from stream_parser import parse_stream_event

PROMPTS_DIR = ROOT / "prompts"
SKILLS_DIR = PROMPTS_DIR / "skills"

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
MODEL = CONFIG.get("model", "sonnet")
TIMEOUT = CONFIG.get("timeout_seconds", 600)
MAX_CONCURRENT = CONFIG.get("max_concurrent_problems", 3)


def read_prompt(name):
    """Read a prompt file from prompts/ directory."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        print(f"Error: {path} not found")
        sys.exit(1)
    return path.read_text(encoding="utf-8").strip()


def read_skills():
    """Read all skill files from prompts/skills/ and concatenate."""
    if not SKILLS_DIR.exists():
        return ""
    parts = []
    for f in sorted(SKILLS_DIR.glob("*.md")):
        parts.append(f.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)


def assemble_orchestrator_prompt():
    """Assemble the complete orchestrator system prompt from components."""
    template = read_prompt("orchestrator")

    architecture = read_prompt("architecture")
    planner = read_prompt("planner")
    builder = read_prompt("builder")
    evaluator = read_prompt("evaluator")
    skills = read_skills()

    # Step 1: Insert all sections into template
    prompt = template
    prompt = prompt.replace("{architecture}", architecture)
    prompt = prompt.replace("{planner_prompt}", planner)
    prompt = prompt.replace("{builder_prompt}", builder)
    prompt = prompt.replace("{evaluator_prompt}", evaluator)
    prompt = prompt.replace("{skills}", skills)
    # Step 2: Replace config variables globally (including inside skills)
    # Runtime placeholders like {workspace} and {role} are preserved as-is
    prompt = prompt.replace("{project_root}", str(ROOT))
    prompt = prompt.replace("{max_concurrent_problems}", str(MAX_CONCURRENT))
    return prompt


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else "problems/001"

    # Copy RAG query script into workspace so agents can run it locally
    query_script = ROOT / "textbook" / "rag_build" / "query_rag.py"
    if query_script.exists():
        import shutil
        shutil.copy2(str(query_script), os.path.join(workspace, "query_rag.py"))

    # Set env vars so query_rag.py knows where model and data are
    os.environ["RAG_MODEL_DIR"] = str(ROOT / "textbook" / "models" / "bge-m3")
    os.environ["RAG_DATA_DIR"] = str(ROOT / "textbook" / "weaviate_data")

    orchestrator_prompt = assemble_orchestrator_prompt()

    agents_json = json.dumps({
        "Orchestrator": {
            "description": "Orchestrator — 编排多个 Agent 解决物理题目",
            "prompt": orchestrator_prompt,
        }
    })

    cmd = [
        "claude",
        "--print",
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--bare",
        "--agents", agents_json,
        "--agent", "Orchestrator",
        "--allowed-tools", "Bash,Read,Write",
        "--add-dir", workspace,
        "--model", MODEL,
        f"请解决 {workspace} 中的物理题目。\n"
        f"按照你的 system prompt 中的工作方式和 Architecture 执行。\n"
        f"创建子 Agent 的方法：Bash 调用 spawn.py <role> <workspace> <prompt_file> <task_file>\n"
        f"全部阶段完成后，将最终结果写入 {workspace}/final_summary.md。\n"
        f"工作目录: {workspace}",
    ]

    # Stream output to terminal and log file
    log_path = os.path.join(workspace, ".orchestrator.log")
    start_time = time.time()

    with open(log_path, "w", encoding="utf-8") as log_file:
        print(f"[Orchestrator] started at {time.strftime('%H:%M:%S')}", flush=True)
        log_file.write(f"[start] Orchestrator | {time.strftime('%H:%M:%S')}\n")
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
                # Print concise progress to terminal
                if etype == "tool_use":
                    print(f"  → {summary}", flush=True)
                elif etype == "text":
                    # Only print first 100 chars of text to avoid spam
                    print(f"  [{etype}] {summary[:100]}{'...' if len(summary) > 100 else ''}", flush=True)
                elif etype == "init":
                    print(f"  [{etype}] {summary}", flush=True)
                elif etype == "result":
                    print(f"  [{etype}] {summary}", flush=True)
                # Write full summary to log
                log_file.write(f"[{etype}] {summary}\n")
                log_file.flush()
            if etype == "result" and event:
                result_event = event

        proc.wait(timeout=TIMEOUT)
        elapsed = time.time() - start_time

        if proc.returncode != 0:
            stderr_output = proc.stderr.read() if proc.stderr else ""
            print(f"[Orchestrator] error: exit code {proc.returncode}")
            print(stderr_output[:500])
            sys.exit(1)

        if not result_event:
            print("[Orchestrator] error: no result event received")
            sys.exit(1)

        if result_event.get("is_error"):
            print(f"[Orchestrator] error: {result_event.get('result', 'Unknown')[:300]}")
            sys.exit(1)

        log_file.write(f"[done] Orchestrator | {time.strftime('%H:%M:%S')} | elapsed={elapsed:.1f}s\n")

    print(f"\n[Orchestrator] done ({elapsed:.0f}s)")

    # Print summary
    summary_path = os.path.join(workspace, "final_summary.md")
    if os.path.exists(summary_path):
        print("\n" + "=" * 60)
        print(open(summary_path, encoding="utf-8").read())
    else:
        print("No summary file found.")


if __name__ == "__main__":
    main()
