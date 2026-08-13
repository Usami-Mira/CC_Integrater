#!/usr/bin/env python3
"""Shared stream-json parser for Claude Code CLI output."""

import json


def parse_stream_event(line):
    """Parse a stream-json event line. Returns (event_type, summary, full_event) tuple.

    event_type: 'init', 'thinking', 'text', 'tool_use', 'tool_result', 'result', 'other'
    summary: human-readable one-liner
    full_event: parsed dict (or None)
    """
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return ("other", None, None)

    etype = event.get("type", "")

    if etype == "system" and event.get("subtype") == "init":
        return ("init", f"model={event.get('model')}", event)

    elif etype == "assistant":
        content = event.get("message", {}).get("content", [])
        for block in content:
            bt = block.get("type", "")
            if bt == "thinking":
                t = block.get("thinking", "")
                if t:
                    return ("thinking", t[:300], event)
            elif bt == "text":
                t = block.get("text", "")
                if t:
                    return ("text", t[:500], event)
            elif bt == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})
                if name == "Bash":
                    cmd = inp.get("command", "")[:200]
                    return ("tool_use", f"Bash: {cmd}", event)
                elif name in ("Read", "Write", "Edit"):
                    return ("tool_use", f"{name}: {inp.get('file_path', '')}", event)
                else:
                    return ("tool_use", f"{name}", event)

    elif etype == "tool_result":
        content = event.get("content", "")
        if isinstance(content, list):
            content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        return ("tool_result", str(content)[:300], event)

    elif etype == "result":
        summary = (f"duration={event.get('duration_ms', 0)}ms "
                   f"turns={event.get('num_turns', 0)} "
                   f"cost=${event.get('total_cost_usd', 0):.4f}")
        return ("result", summary, event)

    return ("other", None, event)
