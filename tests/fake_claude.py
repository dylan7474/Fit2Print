#!/usr/bin/env python3
"""A stand-in for `claude -p` for tests: prints the same kind of stream-json lines. The message decides what happens."""
import json, os, sys
a = sys.argv
msg = a[a.index("-p") + 1]
try:
    open(os.environ.get("FAKE_CLAUDE_LOG", os.devnull), "a").write(json.dumps(a[1:]) + "\n")
except OSError:
    pass
def out(d): print(json.dumps(d), flush=True)
if "CRASH" in msg:
    print("boom", file=sys.stderr); sys.exit(3)
out({"type": "system", "subtype": "init", "session_id": "S1"})
out({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": os.path.join(os.getcwd(), "brief.md")}}]}})
out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Which board is it for?"}]}})
if "TAMPER" in msg:
    t = open("fit2print.toml").read().replace('id = "assist-test"', 'id = "hijacked"'); open("fit2print.toml", "w").write(t)
if "WRITE" in msg:
    open("brief.md", "a").write("\nwritten by the fake assistant\n")
out({"type": "result", "subtype": "success", "is_error": "ERRORRESULT" in msg, "result": "Which board is it for?", "session_id": "S1", "total_cost_usd": 0.01})
