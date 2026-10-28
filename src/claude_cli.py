"""Ask Claude through the logged-in claude CLI (the user's claude.ai account) in a clean context.

Each conversation runs in its own empty working directory, with no tools (--tools ""), no MCP servers, no settings
files, and no CLAUDE.md, skills, hooks or plugins of the user (--safe-mode); our text replaces the system prompt.
The process environment holds only HOME, PATH, USER and LANG, so no API key or Claude Code session variable is
inherited.  The full stream-json event log of every call is kept; a call whose init event lists a tool or an MCP
server, or whose answer contains a tool use, raises.  A follow-up turn resumes the same session.
"""
import json
import os
import subprocess

CLAUDE_MODEL = "opus"
CALL_TIMEOUT = 3600
MCP_NONE = json.dumps({"mcpServers": {}})


def clean_env():
    return {k: os.environ[k] for k in ("HOME", "PATH", "USER", "LANG") if k in os.environ}


def command(system, session_id, resume):
    args = ["claude", "-p", "--model", CLAUDE_MODEL, "--tools", "", "--safe-mode", "--setting-sources", "",
            "--strict-mcp-config", "--mcp-config", MCP_NONE, "--output-format", "stream-json", "--verbose",
            "--system-prompt", system]
    return args + (["--resume", session_id] if resume else ["--session-id", session_id])


def parse_events(lines):
    """Return the init event, the answer text, the served model ids and the result event; raise on any tool."""
    events = [json.loads(line) for line in lines if line.strip()]
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"), None)
    result = next((e for e in events if e.get("type") == "result"), None)
    if init is None or result is None:
        raise RuntimeError("claude stream has no init or result event")
    if init.get("tools") or init.get("mcp_servers"):
        raise RuntimeError("claude session has tools {} and MCP servers {}".format(init.get("tools"),
                                                                                  init.get("mcp_servers")))
    texts, models = [], []
    for e in events:
        if e.get("type") != "assistant":
            continue
        message = e["message"]
        models.append(message.get("model"))
        for block in message.get("content", []):
            if block.get("type") in ("tool_use", "server_tool_use"):
                raise RuntimeError("claude answer uses tool {}".format(block.get("name")))
            if block.get("type") == "text":
                texts.append(block["text"])
    if result.get("is_error") or result.get("subtype") != "success":
        raise RuntimeError("claude call failed: {:s}".format(json.dumps(result)[:1000]))
    if result.get("num_turns") != 1:
        raise RuntimeError("claude call took {} turns".format(result.get("num_turns")))
    return init, "".join(texts), sorted(set(models)), result


def call_claude(system, message, workdir, session_id, log_path, resume=False):
    """Send one user message; return {"answer", "init", "models", "result"}.  workdir must be empty for a new
    conversation and the same directory for a resumed one."""
    os.makedirs(workdir, exist_ok=True)
    if not resume and os.listdir(workdir):
        raise RuntimeError("working directory {:s} is not empty".format(workdir))
    proc = subprocess.run(command(system, session_id, resume), input=message, capture_output=True, text=True,
                          cwd=workdir, env=clean_env(), timeout=CALL_TIMEOUT)
    with open(log_path, "w") as f:
        f.write(proc.stdout)
    if proc.returncode != 0:
        raise RuntimeError("claude exited with {:d}: {:s} {:s}".format(proc.returncode, proc.stderr[-1000:],
                                                                      proc.stdout[-1000:]))
    init, answer, models, result = parse_events(proc.stdout.splitlines())
    return {"answer": answer, "init": init, "models": models, "result": result}
