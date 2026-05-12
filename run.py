#!/usr/bin/env python3
"""Minimal bootstrap — reads outline.md, Orchestrator self-organizes via sub-agents."""

import sys, os, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from anthropic import Anthropic

# ── Environment-aware client ──
CLIENT = Anthropic(
    api_key=os.environ.get("ANTHROPIC_AUTH_TOKEN", os.environ.get("ANTHROPIC_API_KEY")),
    base_url=os.environ.get("ANTHROPIC_BASE_URL"),
)
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def extract_section(md, heading):
    """Extract content after '## <heading>' until the next ## or end of file."""
    pattern = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s|\Z)"
    m = re.search(pattern, md, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


# ── Tool definitions ──
# Agents only get file I/O + spawn_agent. Skills are prompt-based, handled by the model.

FILE_TOOLS = [
    {"name": "read_file",
     "description": "读取指定路径的文件内容",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string", "description": "文件路径"}},
                      "required": ["path"]}},
    {"name": "write_file",
     "description": "将内容写入指定路径的文件",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string", "description": "文件路径"},
                                     "content": {"type": "string", "description": "写入内容"}},
                      "required": ["path", "content"]}},
    {"name": "list_files",
     "description": "列出指定目录下的文件",
     "input_schema": {"type": "object",
                      "properties": {"path": {"type": "string", "description": "目录路径"}},
                      "required": ["path"]}},
]

SPAWN_TOOL = {"name": "spawn_agent",
              "description": "创建一个 sub-Agent 执行任务。Agent 获得独立对话上下文和文件工具，完成后返回结果文本。",
              "input_schema": {"type": "object",
                               "properties": {"role": {"type": "string", "description": "Agent 角色名"},
                                              "prompt": {"type": "string", "description": "Agent 的系统提示词 (完整 prompt)"},
                                              "task": {"type": "string", "description": "给 Agent 的任务描述 (要读什么文件、输出到什么文件)"},
                                              "workspace": {"type": "string", "description": "工作目录路径"}},
                               "required": ["role", "prompt", "task"]}}


# ── Tool execution ──

def exec_file_tool(name, inp):
    p = inp.get("path", "")
    if name == "read_file":
        return open(p, encoding="utf-8").read() if os.path.exists(p) else f"File not found: {p}"
    if name == "write_file":
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(inp.get("content", ""))
        return f"Written: {p}"
    if name == "list_files":
        if os.path.isdir(p):
            return "\n".join(sorted(os.listdir(p)))
        return f"Dir not found: {p}"


# ── Agent conversation runner ──

ORCHESTRATOR_TOOLS = FILE_TOOLS + [SPAWN_TOOL]
SUB_AGENT_TOOLS = FILE_TOOLS


def run_agent(system_prompt, initial_msg, tools, max_tokens=8192):
    """Run a single agent conversation to completion. Returns final text output."""
    msgs = [{"role": "user", "content": initial_msg}]

    while True:
        resp = CLIENT.messages.create(
            model=MODEL, max_tokens=max_tokens,
            system=system_prompt, messages=msgs, tools=tools)

        has_tool = any(b.type == "tool_use" for b in resp.content)
        text = "".join(b.text for b in resp.content if b.type == "text")
        if text:
            print(text)

        if not has_tool:
            return text

        msgs.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                if b.name == "spawn_agent":
                    sub_prompt = b.input.get("prompt", "")
                    sub_task = b.input.get("task", "")
                    sub_ws = b.input.get("workspace", "")
                    initial = sub_task
                    if sub_ws:
                        initial += f"\n工作目录: {sub_ws}"
                    print(f"\n  [>>] spawn_agent: {b.input.get('role', '?')}")
                    result = run_agent(sub_prompt, initial, SUB_AGENT_TOOLS)
                    print(f"  [OK] {b.input.get('role', '?')} done\n")
                else:
                    result = exec_file_tool(b.name, b.input)
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": result})
        msgs.append({"role": "user", "content": results})


def main():
    workspace = sys.argv[1] if len(sys.argv) > 1 else "problems/001"
    outline = open("outline.md", encoding="utf-8").read()
    orchestrator_prompt = extract_section(outline, "System: Orchestrator")

    if not orchestrator_prompt:
        print("Error: cannot find '## System: Orchestrator' in outline.md")
        sys.exit(1)

    initial_msg = (
        f"请解决 {workspace}/problem.md 中的物理题目。\n"
        f"先读取 outline.md 了解工作流架构和各 Agent 定义，然后按照架构执行。\n"
        f"工作目录: {workspace}"
    )

    run_agent(orchestrator_prompt, initial_msg, ORCHESTRATOR_TOOLS)


if __name__ == "__main__":
    main()