"""The 'Checks' card on a project's page (read-only): when each check was last run and how it came out, whether the model has changed since, and the splits the
project has made. Nothing here runs anything: it shows what records/checks.jsonl and the split files say, and the exact command for what has not been run."""
import datetime, html, json, os
from . import records

CHECKS = [("assembly-check", "checks.toml", "Virtual build (sweeps, screws, probes, driver runs, rings)", "fit2print assembly-check ."),
          ("selftest", "selftest.toml", "Self-test (is the checker still telling the truth?)", "fit2print selftest .")]
SKIP = {".git", ".f2p_cache", "__pycache__", "renders", "plates", "photos"}


def esc(s):
    return html.escape(str(s), quote=True)


def _when(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d %H:%M").timestamp()
    except (TypeError, ValueError):
        return None


def splits(folder, depth=3):
    """[(relative path, parsed split.json)] for every NAME_split.json under the project."""
    out = []
    base = os.path.abspath(folder)
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP]
        if root[len(base):].count(os.sep) >= depth:
            dirs[:] = []
        for f in files:
            if f.endswith("_split.json"):
                p = os.path.join(root, f)
                try:
                    out.append((os.path.relpath(p, base), json.load(open(p))))
                except (OSError, ValueError):
                    out.append((os.path.relpath(p, base), None))
    return sorted(out, key=lambda t: t[0])


def rows(folder, marker):
    """[dict(title, state, text, command)] where state is ok | fail | stale | never | na."""
    latest = records.latest(folder)
    model = marker.get("model")
    mt = os.path.getmtime(os.path.join(folder, model)) if isinstance(model, str) and os.path.exists(os.path.join(folder, model)) else None
    out = []
    for key, cfgfile, title, cmd in CHECKS:
        if not os.path.exists(os.path.join(folder, cfgfile)):
            continue
        r = latest.get(key)
        if r is None:
            out.append(dict(title=title, state="never", text="not run yet", command=cmd)); continue
        at = r.get("ts") or _when(r.get("at"))        # exact seconds when recorded: minute resolution flagged a run made in the same minute as a save as stale
        detail = ", ".join(f"{k} {v}" for k, v in r.items() if (k in ("cases", "passed", "skipped") and v != 0) or k == "failed")
        if not r["ok"]:
            out.append(dict(title=title, state="fail", text=f"FAILED on {r['at']}" + (f" ({detail})" if detail else ""), command=cmd))
        elif mt and at and mt > at + 1.0:          # a second of slack: file times and the clock do not agree to the millisecond
            out.append(dict(title=title, state="stale", text=f"passed on {r['at']}, but the model has changed since: run it again", command=cmd))
        else:
            out.append(dict(title=title, state="ok", text=f"clear on {r['at']}" + (f" ({detail})" if detail else ""), command=None))
    return out


def card(pid, folder, marker):
    rs = rows(folder, marker)
    sp = splits(folder)
    if not rs and not sp:
        return ""
    colour = {"ok": "var(--green)", "fail": "var(--red, #c0392b)", "stale": "var(--amber, #b9770e)", "never": "var(--mute)"}
    label = {"ok": "CLEAR", "fail": "FAILED", "stale": "STALE", "never": "NOT RUN"}
    body = ""
    for r in rs:
        cmd = f"<div class=small><code>{esc(r['command'])}</code></div>" if r["command"] else ""
        body += (f"<div style='padding:6px 0;border-top:1px solid var(--line)'><div class=row><b>{esc(r['title'])}</b>"
                 f"<span class=small style='color:{colour[r['state']]};font-weight:700'>{label[r['state']]}</span></div><div class=small>{esc(r['text'])}</div>{cmd}</div>")
    for path, d in sp:
        if d is None:
            body += f"<div style='padding:6px 0;border-top:1px solid var(--line)'><b>{esc(path)}</b> <span class=small style='color:{colour['fail']}'>unreadable</span></div>"; continue
        pins = (d.get("pins") or {}).get("count", 0)
        joints = sorted({c.get("joint", "pins") for c in d.get("cuts", [])})
        state = "ok" if d.get("ok") else "fail"
        body += (f"<div style='padding:6px 0;border-top:1px solid var(--line)'><div class=row><b>Split: {esc(d.get('base', path))}</b>"
                 f"<span class=small style='color:{colour[state]};font-weight:700'>{'OK' if d.get('ok') else 'FAILED'}</span></div>"
                 f"<div class=small>{esc(d.get('summary', ''))}" + (f" &middot; joints: {esc(', '.join(joints))}" if joints else "") + (f" &middot; {pins} loose pins" if pins else "") + "</div>"
                 + "".join(f"<div class=small style='color:{colour['stale']}'>{esc(w)}</div>" for w in d.get("warnings", [])[:4]) + "</div>")
    return f"<div class=card><h3>Checks</h3><div class=meta>When each check last ran. Nothing here runs anything: use the command shown.</div>{body}</div>"
