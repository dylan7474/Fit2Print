"""The front door: a small local web app (standard library only). `fit2print serve` opens Home (your projects), a project's dashboard,
Log a print (with a photo), and New project. Every project is a folder with a fit2print.toml marker; the page never guesses.

Safety: it listens on 127.0.0.1 only unless you pass --host, and any other address REQUIRES --token (sent as ?t=TOKEN once, then a cookie).
Uploads: images only, 15 MB at most, saved under the project's own photos/ folder with a safe name. Project ids come from the marker, never from the URL path."""
import datetime, time, email.parser, email.policy, hashlib, html, http.server, json, os, re, secrets, socketserver, urllib.parse
from . import assistant as assistant_mod, dashboard, printer as printer_mod, project
from .adapters import generic, phonosphere
from .settings import ROOT

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

MAX_UPLOAD = 15 * 1024 * 1024
def esc(s): return html.escape(str(s), quote=True)

CSS = """
:root{--bg:#f5f3ee;--card:#fff;--ink:#1d1b18;--mute:#6b665d;--line:#e3ded3;--brand:#2b5c8a;--green:#2f855a;--amber:#b7791f;--violet:#6b46c1;--red:#c53030}
@media (prefers-color-scheme:dark){:root{--bg:#161512;--card:#1f1d19;--ink:#ece8df;--mute:#a39d90;--line:#36332c;--brand:#6aa7e0;--green:#5cc08a;--amber:#e0a23a;--violet:#a68bf0;--red:#ee7b7b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif}
header{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;border-bottom:1px solid var(--line);background:var(--card)}
.logo{font-weight:700;font-size:20px}.logo b{color:var(--brand)}.logo a{color:inherit;text-decoration:none}
a.btn,button.btn{display:inline-block;background:var(--brand);color:#fff;border:0;border-radius:10px;padding:10px 18px;font-size:16px;font-weight:600;text-decoration:none;cursor:pointer}a.ghost,button.ghost{background:transparent;color:var(--brand);border:1px solid var(--brand)}
.wrap{max-width:1180px;margin:0 auto;padding:22px 16px 40px}h1{font-size:26px;margin:4px 0 2px}.sub{color:var(--mute);margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:14px}.card h3{margin:0 0 2px;font-size:19px}.meta,.small{color:var(--mute);font-size:14px}
.row{display:flex;gap:10px;align-items:center;justify-content:space-between;flex-wrap:wrap}.bar{height:8px;background:var(--line);border-radius:8px;margin:10px 0 6px;overflow:hidden}.bar i{display:block;height:100%;background:var(--green)}
.needs{background:#fff7e6;border:1px solid #f1d9a6;border-radius:10px;padding:8px 12px;margin-top:10px;font-size:15px}@media (prefers-color-scheme:dark){.needs{background:#2d2616;border-color:#5a4a1f}}
.chip{display:inline-block;font-size:12px;font-weight:700;color:#fff;border-radius:99px;padding:1px 9px}.violet{background:var(--violet)}.green{background:var(--green)}.amber{background:var(--amber)}.blue{background:var(--brand)}.grey{background:var(--mute)}.red{background:var(--red)}
.actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}input,select,textarea{width:100%;border:1px solid var(--line);border-radius:10px;padding:10px 12px;font:inherit;background:var(--card);color:var(--ink)}
a{color:var(--brand)}label{display:block;font-weight:600;margin:14px 0 4px}.note{background:#eef0f4;border-radius:10px;padding:10px 12px;font-size:15px}@media (prefers-color-scheme:dark){.note{background:#2a2a30}}
.flash{background:#e6f4ea;border:1px solid #b7dfc2;border-radius:10px;padding:8px 12px;margin-bottom:14px}@media (prefers-color-scheme:dark){.flash{background:#1d2e23;border-color:#2f5a3c}}
"""

def page(title, body, token_note=""):
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>{esc(title)}</title><style>{CSS}</style></head><body>"
            f"<header><div class=logo><a href='/'>Fit<b>2</b>Print</a></div><div class=small>{token_note}</div></header><div class=wrap>{body}</div></body></html>")

def assistant_card(pid, folder, name, a, start=False, desc=""):
    """The assistant panel for a project page: past messages, a box, and a few lines of script that send a message and poll for the answer."""
    hist = a.history(folder) if a else []
    def bubble(role, text):
        cls = {"you": "me", "assistant": "ai", "error": "err"}.get(role, "ai")
        return f"<div class='bub {cls}'>{esc(text)}</div>"
    shown = "".join(bubble(h["role"], h["text"]) for h in hist)
    def peek(fn, title):
        p = os.path.join(folder, fn)
        if not os.path.exists(p): return ""
        with open(p) as fh: t = fh.read()
        return f"<details><summary>{title}</summary><pre class=file>{esc(t)}</pre></details>"
    if a is None:
        return ("<div class=card><h3>Assistant</h3><div class=note>Not set up on this machine (no <code>claude</code> command found). "
                "Everything else works without it.</div></div>")
    first = f"I want to make: {name}. {desc}".strip() + " Please start the scoping stage: read CLAUDE.md, PLAYBOOK.md and brief.md, then ask me what you need to know, a little at a time."
    auto = "true" if (start and not hist) else "false"
    return f"""<div class=card id=asst><div class=row><h3>Assistant</h3><span class=small>Claude, working inside this project's own folder</span></div>
<div id=chat>{shown or "<div class=small>Nothing said yet. Ask a question, or tell it what you want to do next.</div>"}</div>
<div id=working class=small style='display:none;margin:6px 0'></div>
<form id=askform style='display:flex;gap:8px;margin-top:10px'><textarea id=msg rows=2 placeholder="Ask or tell the assistant something..." style='flex:1'></textarea><button class=btn id=sendbtn type=submit>Send</button></form>
{peek("brief.md", "The brief so far")}{peek("NEXT.md", "Where it stands (NEXT.md)")}</div>
<style>.bub{{border-radius:12px;padding:9px 12px;margin:8px 0;font-size:15px;white-space:pre-wrap}}.ai{{background:#eef0f4;margin-right:34px}}.me{{background:var(--brand);color:#fff;margin-left:34px}}.err{{background:#fde8e8;color:#8a1c1c}}
@media (prefers-color-scheme:dark){{.ai{{background:#2a2a30}}.err{{background:#3a1d1d;color:#f5b5b5}}}}pre.file{{white-space:pre-wrap;font-size:13px;background:var(--bg);border-radius:8px;padding:10px;max-height:320px;overflow:auto}}details{{margin-top:8px}}</style>
<script>(function(){{const pid={json.dumps(pid)},chat=document.getElementById('chat'),w=document.getElementById('working'),btn=document.getElementById('sendbtn'),box=document.getElementById('msg');
const FIRST={json.dumps(first)};
function add(cls,t){{const d=document.createElement('div');d.className='bub '+cls;d.textContent=t;const e=chat.querySelector('.small');if(e&&!e.className.includes('bub'))e.remove();chat.appendChild(d);d.scrollIntoView({{block:'nearest'}})}}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function ask(msg){{add('me',msg);btn.disabled=true;w.style.display='block';w.textContent='thinking...';
 const r=await fetch('/p/'+pid+'/ask',{{method:'POST',headers:{{'Content-Type':'application/x-www-form-urlencoded'}},body:'message='+encodeURIComponent(msg)}});
 if(!r.ok){{add('err',await r.text());btn.disabled=false;w.style.display='none';return}}
 const {{job}}=await r.json();let n=0;
 for(;;){{const p=await (await fetch('/p/'+pid+'/ask/'+job+'?n='+n)).json();n=p.next;
  for(const e of p.events){{if(e.kind=='tool')w.textContent=e.text+'...';else if(e.kind=='text')add('ai',e.text);else if(e.kind=='error')add('err',e.text)}}
  if(p.done)break;await sleep(1000)}}
 w.style.display='none';btn.disabled=false;}}
document.getElementById('askform').addEventListener('submit',ev=>{{ev.preventDefault();const m=box.value.trim();if(!m)return;box.value='';ask(m)}});
if({auto})ask(FIRST);}})();</script>"""

def load_config(path=None):
    path = path or os.path.expanduser("~/.config/fit2print/config.toml")
    cfg = dict(projects=[], new_projects_dir=os.path.expanduser("~/fit2print-projects"), assistant={})
    if os.path.exists(path) and tomllib:
        with open(path, "rb") as f:
            d = tomllib.load(f)
        cfg["projects"] = [os.path.expanduser(p) for p in d.get("projects", [])]
        cfg["new_projects_dir"] = os.path.expanduser(d.get("new_projects_dir", cfg["new_projects_dir"]))
        cfg["assistant"] = d.get("assistant", {})
    return cfg

def read_marker(folder):
    p = os.path.join(folder, "fit2print.toml")
    if not os.path.exists(p) or tomllib is None:
        return None
    with open(p, "rb") as f:
        return tomllib.load(f)

class App:
    def __init__(self, cfg):
        self.cfg = cfg
    def projects(self):
        out = {}
        folders = list(self.cfg["projects"])
        nd = self.cfg["new_projects_dir"]
        if os.path.isdir(nd):
            folders += [os.path.join(nd, d) for d in sorted(os.listdir(nd))]
        for f in folders:
            m = read_marker(f)
            if m and m.get("id"):
                out[m["id"]] = (f, m)               # the id comes from the marker, so the URL can never name an arbitrary path
        return out
    def load(self, pid):
        folder, m = self.projects()[pid]
        data = phonosphere.load(folder) if m.get("adapter") == "phonosphere" else generic.load(folder, m)
        return folder, m, data

def summarise(data):
    cards = {}
    for p in data["parts"]:
        st = dashboard.part_state(p, data["runs"], data["prints"])[0]
        cards[st] = cards.get(st, 0) + 1
    total = len(data["parts"])
    if cards.get("onprinter"): chip = ("printing now", "violet")
    elif cards.get("bad"): chip = ("needs a fix", "red")
    elif cards.get("look"): chip = ("needs a look", "amber")
    elif cards.get("ready"): chip = ("ready to print", "blue")
    elif cards.get("printed") and cards["printed"] == total: chip = ("all printed", "green")
    else: chip = ("just started" if not total else "in progress", "grey")
    needs = []
    for p in data["parts"]:
        st, lp, lr, _ = dashboard.part_state(p, data["runs"], data["prints"])
        if st == "onprinter": needs.append(f"send a photo of {p['name']} when it finishes")
    looks = [p["name"] for p in data["parts"] if dashboard.part_state(p, data["runs"], data["prints"])[0] in ("look", "bad")]
    if looks: needs.append(f"{len(looks)} part(s) want a look ({', '.join(looks[:3])}{'...' if len(looks) > 3 else ''})")
    for t in data["open_items"][:2]:
        if not t.lstrip("*").lower().startswith("resolved"): needs.append(dashboard.short(t, 110))
    return dict(total=total, printed=cards.get("printed", 0), chip=chip, needs=needs[:3], minutes=0)

def printer_card(app, pr):
    """The printer panel for Home: the last status the background poller got (the page never waits for the printer), the camera, the job's project."""
    if pr is None:
        return ""
    st = pr.last
    age = int(time.time() - st["at"]) if st.get("at") else None
    state = st.get("state", "unknown")
    colour = {"printing": "violet", "idle": "grey", "finished": "green", "failed": "red", "paused": "amber", "offline": "red"}.get(state, "grey")
    if state in ("offline", "unknown"):
        return (f"<div class=card><div class=row><h3>Printer</h3><span class='chip {colour}'>{esc(state)}</span></div>"
                f"<div class=meta>{esc(st.get('error') or 'waiting for the first report')}</div></div>")
    job = st.get("job") or ""
    link = ""
    for pid, (folder, m) in app.projects().items():
        try:
            _, _, data = app.load(pid)
        except Exception:
            continue
        if any(job and dashboard.mentions(p["name"], job) for p in data["parts"]):
            link = f"<a href='/p/{esc(pid)}'>{esc(m.get('name', pid).split(' (')[0])}</a>"
            break
    pct = st.get("percent")
    left = st.get("minutes_left")
    def hm(m): return f"{int(m)} min" if m < 60 else f"{int(m) // 60} h {int(m) % 60:02d} min"
    def deg(x): return f"{round(x)}" if isinstance(x, (int, float)) else "-"
    left_s = "about " + hm(left) if isinstance(left, (int, float)) and state == "printing" else "-"
    rows = [("Job", esc(job or "-") + (f" &middot; {link}" if link else ""))]
    if state == "printing" and pct is not None:
        rows += [("Progress", f"{pct} % &middot; layer {st.get('layer')} of {st.get('layers')}"), ("Time left", left_s)]
    rows += [("Nozzle / bed", f"{deg(st.get('nozzle'))} &deg;C / {deg(st.get('bed'))} &deg;C"), ("Problems", "yes: look at the printer" if st.get("errors") else "none")]
    kv = "".join(f"<b style='color:var(--mute);font-weight:500'>{k}</b><span>{v}</span>" for k, v in rows)
    bar = f"<div class=bar><i style='width:{int(pct)}%'></i></div>" if state == "printing" and isinstance(pct, (int, float)) else ""
    return (f"<div class=card><div class=row><h3>Printer</h3><span class='chip {colour}'>{esc(state)}</span></div>{bar}"
            f"<img alt='printer camera' src='/printer/frame.jpg?n={int(time.time())}' style='width:100%;border-radius:10px;display:block;margin:8px 0' onerror=\"this.style.display='none'\">"
            f"<div style='display:grid;grid-template-columns:auto 1fr;gap:2px 12px;font-size:14px'>{kv}</div>"
            f"<div class=small style='margin-top:8px'>updated {age if age is not None else '?'} s ago &middot; <a href='/'>refresh</a></div></div>")

def home(app, flash="", pr=None):
    cards = []
    for pid, (folder, m) in app.projects().items():
        try:
            _, _, data = app.load(pid)
            s = summarise(data)
        except Exception as e:
            cards.append(f"<div class=card><h3>{esc(m.get('name', pid))}</h3><div class=meta>could not be read: {esc(e)}</div></div>"); continue
        pct = int(100 * s["printed"] / s["total"]) if s["total"] else 0
        needs = f"<div class=needs><b>Needs you:</b> {esc(' &middot; '.join(s['needs'])).replace('&amp;middot;', '&middot;')}</div>" if s["needs"] else ""
        kind = " <span class=small>sample</span>" if m.get("kind") == "sample" else ""
        cards.append(f"<div class=card><div class=row><div><h3>{esc(m.get('name', pid))}{kind}</h3><div class=meta>{s['total']} parts &middot; {s['printed']} printed</div></div>"
                     f"<span class='chip {s['chip'][1]}'>{s['chip'][0]}</span></div><div class=bar><i style='width:{pct}%'></i></div>{needs}"
                     f"<div class=actions><a class=btn href='/p/{esc(pid)}'>Open project</a><a class='btn ghost' href='/p/{esc(pid)}/log'>Log a print</a></div></div>")
    pc = printer_card(app, pr)
    body = (f"{('<div class=flash>' + esc(flash) + '</div>') if flash else ''}<div class=row><div><h1>Your projects</h1><p class=sub>From an idea to a print, checked before anything is wasted.</p></div>"
            f"<a class=btn href='/new'>+ New project</a></div>"
            + (f"<div style='display:grid;grid-template-columns:2fr 1fr;gap:18px' class=twocol><div>{''.join(cards) or '<div class=card>No projects yet. Start one.</div>'}</div><div>{pc}</div></div>"
               "<style>@media(max-width:850px){.twocol{grid-template-columns:1fr!important}}</style>" if pc else ("".join(cards) or "<div class=card>No projects yet. Start one.</div>")))
    return page("Fit2Print", body)

def new_form(err=""):
    return page("New project", f"""<h1>New project</h1><p class=sub>Describe it in a line. You can fill in the details with the assistant afterwards.</p>
{('<div class=needs>' + esc(err) + '</div>') if err else ''}
<form method=post action=/new class=card><label for=name>What do you want to make?</label><input id=name name=name placeholder="Pi Zero case" required maxlength=80>
<label for=desc>Anything else you already know? (optional)</label><textarea id=desc name=desc rows=4 placeholder="hangs on a wall, snap-fit lid, Pi Zero 2 W with header pins" maxlength=2000></textarea>
<div class=actions><button class=btn type=submit>Create the project</button><a class='btn ghost' href='/'>Cancel</a></div></form>
<div class=card><h3>Assistant</h3><div class=note>Not connected yet. When it is, it will ask the questions it needs, write the brief with you and draw the first concept. For now the project is created with your description in <code>brief.md</code>, ready for Claude Code to continue from.</div></div>""")

def log_form(app, pid, flash=""):
    folder, m, data = app.load(pid)
    names = "".join(f"<option>{esc(p['name'])}</option>" for p in data["parts"])
    return page("Log a print", f"""<h1>Log a print</h1><p class=sub>{esc(m.get('name', pid))}</p>{('<div class=flash>' + esc(flash) + '</div>') if flash else ''}
<form method=post enctype=multipart/form-data class=card><label for=part>Which part?</label><input id=part name=part list=parts required maxlength=120 placeholder="e.g. pod_L"><datalist id=parts>{names}</datalist>
<label for=result>How did it go?</label><select id=result name=result><option value=ok>ok</option><option value=partial>partly</option><option value=failed>failed</option><option value=printing>on the printer now</option></select>
<label for=what>What happened, in your own words</label><textarea id=what name=what rows=4 required maxlength=3000 placeholder="Printed fine; the left hole is a bit rough"></textarea>
<label for=photo>A photo (optional)</label><input id=photo name=photo type=file accept="image/*">
<div class=actions><button class=btn type=submit>Save</button><a class='btn ghost' href='/p/{esc(pid)}'>Cancel</a></div></form>""")

def parse_multipart(headers, body):
    ct = headers.get("Content-Type", "")
    msg = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(b"Content-Type: " + ct.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
    fields, files = {}, {}
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        fn = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if fn is not None:
            if data:
                files[name] = (fn, data)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files

def save_print(folder, marker, fields, files):
    part = fields.get("part", "").strip()
    what = fields.get("what", "").strip()
    result = fields.get("result", "ok")
    if not part or not what or result not in ("ok", "partial", "failed", "printing"):
        raise ValueError("a part, a result and a few words about what happened are needed")
    entry = dict(date=datetime.date.today().isoformat(), plate=part[:120], result=result, what=what[:3000], checks="")
    if "photo" in files:
        fn, data = files["photo"]
        if len(data) > MAX_UPLOAD:
            raise ValueError("that photo is over 15 MB")
        ext = os.path.splitext(fn)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png") or not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
            raise ValueError("the photo must be a jpg or png image")
        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", part)[:40] + "_" + datetime.date.today().isoformat() + "_" + hashlib.sha256(data).hexdigest()[:8] + (".png" if data[:4] == b"\x89PNG" else ".jpg")
        os.makedirs(os.path.join(folder, "photos"), exist_ok=True)
        with open(os.path.join(folder, "photos", safe), "wb") as fh:
            fh.write(data)
        entry["photo"] = os.path.join("photos", safe)
    path = os.path.join(folder, "PRINT_LOG.jsonl") if marker.get("adapter") == "phonosphere" else os.path.join(folder, "records", "prints.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry

class Handler(http.server.BaseHTTPRequestHandler):
    app = None; token = None; printer = None; assistant = None
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="text/html; charset=utf-8", headers=()):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("X-Content-Type-Options", "nosniff"); self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' data:")
        for k, v in headers: self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)
    def _redirect(self, to, headers=()):
        self.send_response(303); self.send_header("Location", to)
        for k, v in headers: self.send_header(k, v)
        self.end_headers()
    def _auth(self, qs):
        if not self.token:
            return True, ()
        cookie = self.headers.get("Cookie", "")
        if re.search(r"(?:^|;\s*)f2p=" + re.escape(self.token) + r"(?:;|$)", cookie):
            return True, ()
        if qs.get("t", [""])[0] == self.token:
            return True, (("Set-Cookie", f"f2p={self.token}; HttpOnly; SameSite=Strict; Path=/"),)
        return False, ()
    def _first_desc(self, folder):
        try:
            with open(os.path.join(folder, "brief.md")) as fh:
                m = re.search(r"## What it is for\s*\n(.*?)\n\n", fh.read(), re.S)
            t = m.group(1).strip() if m else ""
            return "" if t.startswith("(") else t[:400]
        except OSError:
            return ""
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); qs = urllib.parse.parse_qs(u.query)
        ok, hdr = self._auth(qs)
        if not ok:
            return self._send(401, page("Fit2Print", "<div class=card><h3>Locked</h3>Open the link with its token.</div>"))
        path = u.path
        try:
            if path == "/health": return self._send(200, "ok", "text/plain")
            if path == "/": return self._send(200, home(self.app, qs.get("msg", [""])[0], self.printer), headers=hdr)
            if path == "/printer/frame.jpg":
                if self.printer is None: return self._send(404, "no printer set up", "text/plain")
                try:
                    return self._send(200, self.printer.frame(), "image/jpeg", (("Cache-Control", "no-store"),))
                except Exception:
                    return self._send(503, "the camera is not available", "text/plain")
            if path == "/new": return self._send(200, new_form(), headers=hdr)
            m = re.fullmatch(r"/p/([a-z0-9-]+)(/log)?", path)
            ja = re.fullmatch(r"/p/([a-z0-9-]+)/ask/([0-9a-f]{12})", path)
            if ja:
                r = self.assistant.poll(ja.group(2), int(qs.get("n", ["0"])[0])) if self.assistant else None
                if r is None: return self._send(404, json.dumps(dict(error="no such job")), "application/json")
                return self._send(200, json.dumps(r), "application/json", (("Cache-Control", "no-store"),))
            if m:
                pid = m.group(1)
                if pid not in self.app.projects(): return self._send(404, page("Not found", "<div class=card>No such project.</div>"))
                if m.group(2): return self._send(200, log_form(self.app, pid, qs.get("msg", [""])[0]), headers=hdr)
                folder, mk, data = self.app.load(pid)
                doc = dashboard.render(data)
                bar = f"<div class=row style='margin-bottom:10px'><a class='btn ghost' href='/'>&larr; Your projects</a><a class=btn href='/p/{pid}/log'>Log a print</a></div>"
                asst = assistant_card(pid, folder, mk.get("name", pid), self.assistant, qs.get("start", [""])[0] == "1", self._first_desc(folder))
                return self._send(200, doc.replace("<div class='wrap'>", "<div class='wrap'>" + bar + asst, 1), headers=hdr)
            return self._send(404, page("Not found", "<div class=card>Nothing here.</div>"))
        except Exception as e:
            return self._send(500, page("Error", f"<div class=card><h3>Something went wrong</h3><div class=meta>{esc(e)}</div></div>"))
    def do_POST(self):
        u = urllib.parse.urlparse(self.path); qs = urllib.parse.parse_qs(u.query)
        ok, hdr = self._auth(qs)
        if not ok: return self._send(401, "locked", "text/plain")
        n = int(self.headers.get("Content-Length", "0"))
        if n > MAX_UPLOAD + 100000: return self._send(413, page("Too big", "<div class=card>That upload is too large.</div>"))
        body = self.rfile.read(n)
        try:
            if u.path == "/new":
                f = {k: v[0] for k, v in urllib.parse.parse_qs(body.decode()).items()}
                name = f.get("name", "").strip()
                if not name: return self._send(400, new_form("Please give it a name."))
                d = self.app.cfg["new_projects_dir"]; os.makedirs(d, exist_ok=True)
                pid = project.slug(name)
                if pid in self.app.projects(): return self._send(400, new_form(f"There is already a project called '{pid}'."))
                try:
                    pid, folder = project.init(os.path.join(d, pid), name)
                except SystemExit as e:
                    return self._send(400, new_form(str(e)))
                desc = f.get("desc", "").strip()
                if desc:
                    bp = os.path.join(folder, "brief.md")
                    with open(bp) as fh:
                        b = fh.read().replace("(one paragraph, in the person's words)", desc[:2000], 1)
                    with open(bp, "w") as fh:
                        fh.write(b)
                return self._redirect(f"/p/{pid}?start=1", hdr)
            ma = re.fullmatch(r"/p/([a-z0-9-]+)/ask", u.path)
            if ma and ma.group(1) in self.app.projects():
                if not self.assistant: return self._send(503, "the assistant is not set up on this machine", "text/plain")
                pid = ma.group(1); folder, mk = self.app.projects()[pid]
                msg = urllib.parse.parse_qs(body.decode()).get("message", [""])[0]
                try:
                    job = self.assistant.start(pid, folder, mk.get("name", pid), msg)
                except ValueError as e:
                    return self._send(400, str(e), "text/plain")
                except RuntimeError as e:
                    return self._send(409, str(e), "text/plain")
                return self._send(200, json.dumps(dict(job=job)), "application/json")
            m = re.fullmatch(r"/p/([a-z0-9-]+)/log", u.path)
            if m and m.group(1) in self.app.projects():
                pid = m.group(1); folder, mk = self.app.projects()[pid]
                fields, files = parse_multipart(self.headers, body)
                try:
                    save_print(folder, mk, fields, files)
                except ValueError as e:
                    return self._send(400, log_form(self.app, pid, str(e)))
                return self._redirect(f"/p/{pid}", hdr)
            return self._send(404, page("Not found", "<div class=card>Nothing here.</div>"))
        except Exception as e:
            return self._send(500, page("Error", f"<div class=card><h3>Something went wrong</h3><div class=meta>{esc(e)}</div></div>"))

class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def make_server(cfg, host="127.0.0.1", port=8750, token=None, printer=None, assistant=None):
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit("listening on a network address needs --token (the page can add files to your projects)")
    Handler.app = App(cfg); Handler.token = token; Handler.printer = printer; Handler.assistant = assistant
    return Server((host, port), Handler)
