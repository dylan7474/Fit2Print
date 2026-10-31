"""The dashboard: one self-contained HTML page made from a project's records (no server, no scripts to load).

A part's state is never typed in: it is worked out from the records, newest wins:
  a real print marked superseded (made from an older design) -> Reprint needed, until a LATER print of that same part is logged |
  a real print marked failed -> Failed, reprint | printing -> On the printer | ok / partial -> Printed |
  (a log line marked pending means "plate prepared, not printed yet" and does not change the state) |
  otherwise the last virtual check: BLOCK -> Blocked | CHECK -> Look first | PASS -> Ready to print | none -> Not checked yet.
"""
import base64, datetime, html, io, os, re
from PIL import Image

STATES = [  # key, label, colour class, one line of meaning
    ("none", "Not checked yet", "grey", "no virtual check has been run on this part"),
    ("ready", "Ready to print", "blue", "the checks pass"),
    ("look", "Look first", "amber", "a check wants a person to look before this is printed"),
    ("onprinter", "On the printer", "violet", "sent to the printer, result not reported yet"),
    ("printed", "Printed", "green", "printed and logged"),
    ("reprint", "Reprint needed", "orange", "printed, but from an older design: it no longer matches the model"),
    ("bad", "Failed or blocked", "red", "a print failed, or a check blocks it"),
]

def esc(s): return html.escape(str(s), quote=True)

def thumb(path, w=440):
    try:
        im = Image.open(path).convert("RGB"); im.thumbnail((w, w))
        b = io.BytesIO(); im.save(b, "JPEG", quality=72)
        return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()
    except Exception:
        return None

def short(text, n=200):
    """The first sentence or so, cut at a word, never mid-word."""
    t = re.sub(r"\s+", " ", re.sub(r"\*\*|`", "", str(text))).strip()
    if len(t) <= n:
        return t
    cut = t[:n].rsplit(" ", 1)[0]
    m = re.search(r"^(.*?[.;])\s", t[:n + 40])
    return (m.group(1) if m and len(m.group(1)) > 40 else cut.rstrip(" :;,") + "...")

def mentions(name, text):
    return re.search(r"(?<![a-z_])" + re.escape(name) + r"(?![a-z_])", text) is not None

def part_state(p, runs, prints):
    hist = [e for e in prints if mentions(p["name"], e["plate"])]
    last_print = hist[-1] if hist else None
    mine = [r for r in runs if r.get("part") == p["name"]]
    last_run = mine[-1] if mine else None
    sup = [i for i, e in enumerate(hist) if e["result"] == "superseded"]
    if sup:
        # only a later entry that is ABOUT this part (its plate starts with the name) clears it: a dry-fit note that merely mentions it does not
        later = [e for e in hist[sup[-1] + 1:] if e["plate"].lstrip("`").startswith(p["name"]) and e["result"] in ("ok", "pass", "partial", "failed", "printing")]
        if not later:
            return "reprint", hist[sup[-1]], last_run, hist
    if last_print and last_print["result"] == "failed":
        return "bad", last_print, last_run, hist
    if last_print and last_print["result"] == "printing":
        return "onprinter", last_print, last_run, hist
    if last_print and last_print["result"] in ("ok", "pass", "partial"):
        return "printed", last_print, last_run, hist
    if last_run:
        v = last_run.get("verdict")
        return {"BLOCK": "bad", "CHECK": "look", "PASS": "ready"}.get(v, "none"), last_print, last_run, hist
    return "none", last_print, last_run, hist

def render(project, today=None):
    today = today or datetime.date.today().isoformat()
    parts, runs, prints = project["parts"], project["runs"], project["prints"]
    cards = {k: [] for k, *_ in STATES}
    rem_min = rem_g = 0
    n_printed = 0
    needs = []
    for p in parts:
        st, lp, lr, hist = part_state(p, runs, prints)
        p["_state"] = st
        cards[st].append((p, lp, lr, hist))
        if st == "printed": n_printed += 1
        elif lr and lr.get("minutes"):
            rem_min += lr["minutes"] * p["qty"]; rem_g += lr.get("grams", 0) * p["qty"]
        if st == "look":
            flags = [re.sub(r"^\[CHECK\]\s*", "", n) for n in (lr or {}).get("notes", []) if n.startswith("[CHECK]")]
            needs.append(("Look at", p["name"], "the checks flag: " + short("; ".join(flags), 170) if flags else "a check wants a person to look"))
        if st == "onprinter": needs.append(("Send a photo of", p["name"], "it is on the printer now."))
        if st == "reprint": needs.append(("Reprint", p["name"], short((lp or {}).get("what", ""), 170)))
        if st == "bad": needs.append(("Fix", p["name"], short((lp or lr or {}).get("what", "") or "; ".join((lr or {}).get("notes", [])), 170)))
    for t in project["open_items"]:
        if t.lstrip("*").lower().startswith("resolved"):
            continue                                   # done items are history, not requests
        needs.append(("Open", "", short(t, 230)))
    css = """
:root{--bg:#f6f4ef;--card:#fff;--ink:#1d1b18;--mute:#6b665d;--line:#e3ded3;--grey:#8a857b;--blue:#2b6cb0;--amber:#b7791f;--orange:#c05621;--violet:#6b46c1;--green:#2f855a;--red:#c53030}
@media (prefers-color-scheme:dark){:root{--bg:#161512;--card:#1f1d19;--ink:#ece8df;--mute:#a39d90;--line:#36332c;--grey:#9a9488;--blue:#63a4e8;--amber:#e0a23a;--orange:#f08a4b;--violet:#a68bf0;--green:#5cc08a;--red:#ee7b7b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.45 system-ui,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:20px 16px 60px}h1{margin:0;font-size:28px}h2{margin:34px 0 10px;font-size:19px}
.sub{color:var(--mute);margin:2px 0 16px}.stats{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px 14px;min-width:130px}.stat b{display:block;font-size:24px}.stat span{color:var(--mute);font-size:13px}
.needs{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--amber);border-radius:12px;padding:6px 16px}
.needs li{margin:9px 0;list-style:none}.needs ul{margin:0;padding:0}.tag{display:inline-block;font-size:12px;font-weight:600;border-radius:99px;padding:1px 9px;color:#fff;background:var(--amber);margin-right:6px}
.board{display:grid;grid-template-columns:repeat(7,minmax(170px,1fr));gap:12px;align-items:start;overflow-x:auto}
.col h3{font-size:14px;margin:0 0 8px;display:flex;justify-content:space-between}.col h3 i{font-style:normal;color:var(--mute)}
.col{min-width:180px}.bar{height:4px;border-radius:4px;margin-bottom:8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;margin-bottom:8px;padding:8px 10px}
.card summary{cursor:pointer;list-style:none}.card summary::-webkit-details-marker{display:none}.card code{font-weight:600}
.card .what{font-size:13px;color:var(--mute)}.card .more{font-size:13px;margin-top:8px;border-top:1px solid var(--line);padding-top:6px}.more dt{font-weight:600;margin-top:5px}.more dd{margin:0;color:var(--mute)}
.timeline{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.entry{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}.entry img{width:100%;display:block}
.entry div{padding:10px 12px}.entry .d{color:var(--mute);font-size:13px}.chip{font-size:12px;font-weight:600;border-radius:99px;padding:1px 9px;color:#fff}
.grey{background:var(--grey)}.blue{background:var(--blue)}.amber{background:var(--amber)}.orange{background:var(--orange)}.violet{background:var(--violet)}.green{background:var(--green)}.red{background:var(--red)}
.bg-grey{background:var(--grey)}.bg-blue{background:var(--blue)}.bg-amber{background:var(--amber)}.bg-orange{background:var(--orange)}.bg-violet{background:var(--violet)}.bg-green{background:var(--green)}.bg-red{background:var(--red)}
.gallery{display:flex;flex-wrap:wrap;gap:10px}.gallery img{height:150px;border-radius:8px;border:1px solid var(--line)}
footer{color:var(--mute);font-size:13px;margin-top:40px}
@media(max-width:900px){.board{grid-template-columns:1fr}}
"""
    o = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(project['name'])} dashboard</title><style>{css}</style></head><body><div class='wrap'>"]
    o.append(f"<h1>{esc(project['name'])}</h1><p class='sub'>{esc(project['subtitle'])} &middot; made by Fit2Print on {today}</p>")
    ready = len(cards["ready"])
    o.append("<div class='stats'>" + "".join(f"<div class='stat'><b>{a}</b><span>{b}</span></div>" for a, b in [
        (len(parts), project.get("parts_label", "parts in this project")), (n_printed, "printed"), (ready, "ready to print"), (len(cards["look"]) + len(cards["bad"]) + len(cards["reprint"]), "need a look, a fix or a reprint"),
        (f"{rem_min / 60:.0f} h", "print time still to go"), (f"{rem_g / 1000:.1f} kg", "filament still to go")]) + "</div>")
    o.append("<h2>What I need from you</h2><div class='needs'><ul>" + "".join(
        f"<li><span class='tag'>{esc(k)}</span>{('<code>' + esc(n) + '</code> ' if n else '')}{esc(t)}</li>" for k, n, t in needs) + "</ul></div>")
    o.append("<h2>The parts</h2><div class='board'>")
    for key, label, colour, meaning in STATES:
        o.append(f"<div class='col'><div class='bar bg-{colour}'></div><h3><span title='{esc(meaning)}'>{label}</span><i>{len(cards[key])}</i></h3>")
        for p, lp, lr, hist in cards[key]:
            sub = f"{p['qty']}x " if p["qty"] > 1 else ""
            line = (f"{lr['verdict']}, {lr['minutes']} min, {lr['grams']} g" if lr and lr.get("minutes") else "")
            o.append(f"<details class='card'><summary><code>{esc(p['name'])}</code><div class='what'>{sub}{esc(p['what'])}</div></summary><dl class='more'>"
                     f"<dt>Group</dt><dd>{esc(p['group'])}</dd><dt>Colour</dt><dd>{esc(p['colour'])}</dd>"
                     + (f"<dt>Virtual check</dt><dd>{esc(line)}</dd>" if line else "")
                     + (f"<dt>Fixings</dt><dd>{esc(p['fixings'])}</dd>" if p["fixings"] else "")
                     + (f"<dt>Open issues</dt><dd>{esc(p['issues'])}</dd>" if p["issues"] else "")
                     + "".join(f"<dt>{esc(h['date'])} &middot; {esc(h['result'])}</dt><dd>{esc(h['what'][:300])}</dd>" for h in hist[-2:])
                     + "</dl></details>")
        o.append("</div>")
    o.append("</div><h2>Print log, newest first</h2><div class='timeline'>")
    shown = set()
    for e in reversed(prints):
        colour = {"ok": "green", "pass": "green", "partial": "amber", "failed": "red", "pending": "violet"}.get(e["result"], "grey")
        img = thumb(e["photo"]) if e.get("photo") else None
        if e.get("photo"): shown.add(os.path.basename(e["photo"]))
        o.append(f"<div class='entry'>{('<img alt=\"photo of the print\" src=\"' + img + '\">') if img else ''}<div><span class='chip {colour}'>{esc({'pending': 'prepared, not printed', 'printing': 'on the printer'}.get(e['result'], e['result']))}</span> <b>{esc(e['plate'])}</b>"
                 f"<div class='d'>{esc(e['date'])}" + (f" &middot; checks said: {esc(short(e['checks'], 110))}" if e.get("checks") else "") + "</div>"
                 + (f"<p>{esc(short(e['what'], 260))}</p>" + (f"<details><summary>the whole entry</summary><p>{esc(e['what'])}</p></details>" if len(e['what']) > 270 else "") ) + "</div></div>")
    o.append("</div>")
    extra = [p for p in project.get("photos", []) if os.path.basename(p) not in shown]
    if extra:
        o.append("<h2>Other photos</h2><div class='gallery'>" + "".join(f"<img alt='{esc(os.path.basename(p))}' title='{esc(os.path.basename(p))}' src='{thumb(p, 520)}'>" for p in extra if thumb(p)) + "</div>")
    o.append("<footer>State is worked out from the records, never typed in: the virtual-check results, the real print log and the parts register. "
             "A CHECK is not a pass. This page is a snapshot; run <code>fit2print dashboard</code> again to refresh it.</footer></div></body></html>")
    return "".join(o)
