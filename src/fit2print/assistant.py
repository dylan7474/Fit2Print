"""The assistant: Claude, run headlessly by the page, in the project's own folder.

How it works (and why it is built this way):
  * `claude -p` is started with the PROJECT FOLDER as its working directory, so it automatically reads that project's CLAUDE.md (the rules) and can
    be pointed at NEXT.md, brief.md and PLAYBOOK.md. The project's files are its memory, not the conversation.
  * Only a short list of tools is allowed (read, search, write/edit inside the project folder, and the Fit2Print command), and every other tool is
    DENIED without asking (permission mode dontAsk). It cannot browse the web, run arbitrary commands or write outside the project.
  * Every request has a spending cap and a turn cap. The conversation continues with the same Claude session id, kept per project.
  * The project folder always comes from the project's marker file, never from the page's request.
Used from the page (server.py): start a job, poll it for new events, show them as they arrive."""
import json, os, re, subprocess, threading, time, uuid

ALLOWED = ["Read", "Glob", "Grep", "Write", "Edit"]
SYSTEM = """You are the assistant inside Fit2Print, working in the folder of ONE project ({name}). Follow CLAUDE.md and PLAYBOOK.md in this folder.
The person is not an engineer: plain words, one question or one picture at a time, short answers. A question from them is not a go-ahead.
Never invent a dimension: mark unknown ones UNVERIFIED and ask them to measure. Never say a check has passed unless a Fit2Print command in this session said so.
Keep this project apart from every other: read and write only inside this folder.
When you change the state of the project, rewrite NEXT.md (state, next step, needs the person). Do the scoping stage by writing brief.md with the person, a little at a time.
To run Fit2Print commands use exactly: {f2p}"""

def tool_note(name, inp):
    p = inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
    base = os.path.basename(str(p)) if p else ""
    return {"Read": f"reading {base}", "Write": f"writing {base}", "Edit": f"editing {base}", "Glob": "looking through the project", "Grep": "searching the project",
            "Bash": "running: " + str(inp.get("command", ""))[:90]}.get(name, f"using {name}")

class Assistant:
    def __init__(self, command=None, model="sonnet", budget_usd=0.75, max_turns=14, f2p="fit2print"):
        self.command, self.model, self.budget, self.max_turns, self.f2p = command or ["claude"], model, budget_usd, max_turns, f2p
        self.jobs, self.running, self.lock = {}, {}, threading.Lock()
    # ---- history kept in the project
    def _paths(self, folder):
        return os.path.join(folder, "records", "assistant.jsonl"), os.path.join(folder, "records", "assistant_session.txt")
    def history(self, folder, n=12):
        p = self._paths(folder)[0]
        if not os.path.exists(p):
            return []
        with open(p) as f:
            return [json.loads(l) for l in f if l.strip()][-n:]
    def _remember(self, folder, role, text, cost=None):
        p = self._paths(folder)[0]
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(dict(at=time.strftime("%Y-%m-%d %H:%M"), role=role, text=text, cost=cost)) + "\n")
    def command_for(self, folder, name, message, session):
        sp = self._paths(folder)[1]
        cmd = list(self.command) + ["-p", message, "--output-format", "stream-json", "--verbose", "--model", self.model, "--permission-mode", "dontAsk",
               "--allowedTools", *ALLOWED, f"Bash({self.f2p}:*)", "--max-budget-usd", str(self.budget), "--max-turns", str(self.max_turns),
               "--append-system-prompt", SYSTEM.format(name=name, f2p=self.f2p)]
        cmd += ["--resume", session] if session else ["--session-id", str(uuid.uuid4())]
        return cmd
    # ---- jobs
    def start(self, pid, folder, name, message):
        message = message.strip()[:4000]
        if not message:
            raise ValueError("say something to the assistant first")
        with self.lock:
            if self.running.get(pid):
                raise RuntimeError("the assistant is still answering the last message")
            self.running[pid] = True
        job = uuid.uuid4().hex[:12]
        self.jobs[job] = dict(pid=pid, events=[], done=False)
        self._remember(folder, "you", message)
        threading.Thread(target=self._run, args=(job, pid, folder, name, message), daemon=True).start()
        return job
    def poll(self, job, since=0):
        j = self.jobs.get(job)
        if not j:
            return None
        return dict(events=j["events"][since:], next=len(j["events"]), done=j["done"])
    def _run(self, job, pid, folder, name, message):
        j = self.jobs[job]; ev = j["events"]
        sp = self._paths(folder)[1]
        session = open(sp).read().strip() if os.path.exists(sp) else ""
        final, cost, err = "", None, ""
        try:
            proc = subprocess.Popen(self.command_for(folder, name, message, session), cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, stdin=subprocess.DEVNULL)
            for line in proc.stdout:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") == "assistant":
                    for b in d.get("message", {}).get("content", []):
                        if b.get("type") == "text" and b.get("text", "").strip():
                            ev.append(dict(kind="text", text=b["text"]))
                        elif b.get("type") == "tool_use":
                            ev.append(dict(kind="tool", text=tool_note(b.get("name", ""), b.get("input", {}))))
                elif d.get("type") == "result":
                    final, cost = d.get("result", ""), d.get("total_cost_usd")
                    if d.get("session_id"):
                        os.makedirs(os.path.dirname(sp), exist_ok=True)
                        with open(sp, "w") as f:
                            f.write(d["session_id"])
                    if d.get("is_error"):
                        err = (final or "the assistant stopped with an error")[:300]
            proc.wait(timeout=30)
            if proc.returncode not in (0, None) and not final:
                err = (proc.stderr.read() or f"the assistant exited with code {proc.returncode}")[:300]
        except FileNotFoundError:
            err = "Claude is not installed on this machine (no `claude` command)"
        except Exception as e:
            err = f"the assistant could not run ({type(e).__name__})"
        if err:
            ev.append(dict(kind="error", text=err)); self._remember(folder, "error", err)
        else:
            self._remember(folder, "assistant", final, cost)
            ev.append(dict(kind="done", text=final, cost=cost))
        j["done"] = True
        with self.lock:
            self.running[pid] = False
