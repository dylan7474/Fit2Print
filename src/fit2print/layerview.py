"""The layer preview: step through a sliced plate (a Bambu .3mf or a .gcode) layer by layer in the browser, exactly as the printer will lay it down,
with the places the checks worry about (plastic with nothing under it) marked on the layer where they occur.

  * Plates are found, never named by the page: a project's records (plates.jsonl, or PLATE_RESULTS.jsonl for Phonosphere) and its plates/ folder.
  * A plate is parsed once and kept in memory (the last few); a layer is drawn from it on request as polylines per feature (outer wall, infill, ...).
  * The hanging-plastic overlay comes from the same toolpath check as the verdict, computed in the background (a big plate takes a while)."""
import json, os, re, threading
from . import gcode, toolpath
from .settings import Settings

COLOURS = {"Outer wall": "#2b6cb0", "Inner wall": "#63a4e8", "Overhang wall": "#dd8a1a", "Bridge": "#c05621", "Internal bridge": "#c05621",
           "Sparse infill": "#9aa0a6", "Internal solid infill": "#7d8590", "Solid infill": "#7d8590", "Top surface": "#2f9e63", "Bottom surface": "#1f7a4a",
           "Gap infill": "#bdbdbd", "Floating vertical shell": "#e05d5d", "Support": "#a371f7", "Support interface": "#8250df", "Custom": "#cccccc"}
SLUG = re.compile(r"[a-z0-9_-]{1,60}")

def slug(s):
    return re.sub(r"[^a-z0-9_-]+", "-", os.path.splitext(os.path.basename(str(s)))[0].lower()).strip("-")[:60]

def _jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def discover(folder, marker):
    """{name: dict(path, part, verdict, minutes, grams)} for the plates this project has on this machine."""
    found = {}
    recs = _jsonl(os.path.join(folder, "PLATE_RESULTS.jsonl" if marker.get("adapter") == "phonosphere" else os.path.join("records", "plates.jsonl")))
    for r in recs:
        p = os.path.expanduser(str(r.get("file", "")))
        if p.endswith((".3mf", ".gcode")) and os.path.isfile(p):
            found[slug(p)] = dict(path=p, part=r.get("part", slug(p)), verdict=r.get("verdict", ""), minutes=r.get("minutes"), grams=r.get("grams"))
    d = os.path.join(folder, "plates")
    if os.path.isdir(d):
        for fn in sorted(os.listdir(d)):
            if fn.endswith((".3mf", ".gcode")):
                n = slug(fn)
                found.setdefault(n, dict(path=os.path.join(d, fn), part=n, verdict="", minutes=None, grams=None))
    return {k: v for k, v in found.items() if SLUG.fullmatch(k)}

class Plate:
    def __init__(self, path, cfg=None):
        self.path, self.cfg = path, cfg or Settings()
        lines = gcode.read_gcode(path)
        self.layers, _, _ = gcode.parse(lines, self.cfg.filament_area)
        self.zs = [z for z in sorted(self.layers) if sum(gcode.seg_points(s, 1e9)[1] for f, s, _ in self.layers[z] if f != "Custom") >= 3.0]
        xs, ys = [], []
        for z in self.zs:
            for f, s, _ in self.layers[z]:
                if f != "Custom":
                    xs += [s[1], s[3]]; ys += [s[2], s[4]]
        self.bounds = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 1, 1]
        self.problems, self.problems_state = {}, "waiting"
        self._lock = threading.Lock()
    def meta(self):
        return dict(layers=len(self.zs), zs=[round(z, 2) for z in self.zs], bounds=[round(b, 2) for b in self.bounds], colours=COLOURS, problems=self.problems_state)
    def layer(self, k):
        z = self.zs[k]
        feats, cur, last = {}, None, None
        for f, s, contiguous in self.layers[z]:
            if f == "Custom":
                continue
            pts = gcode.seg_points(s, 0.6)[0]
            if cur is None or f != last or not contiguous:
                cur = []; feats.setdefault(f, []).append(cur)
            for x, y in pts:
                cur += [round(float(x), 2), round(float(y), 2)]
            last = f
        return dict(z=round(z, 2), features=feats)
    def compute_problems(self):
        with self._lock:
            if self.problems_state in ("running", "done"):
                return
            self.problems_state = "running"
        def run():
            try:
                col = {}
                toolpath.analyse(self.layers, self.cfg, collect=col)
                self.problems = {round(z, 2): dict(cant=v["cant"][:4000], bridge=v["bridge"][:4000]) for z, v in col.items()}
                self.problems_state = "done"
            except Exception:
                self.problems_state = "failed"
        threading.Thread(target=run, daemon=True).start()
    def problems_json(self):
        return dict(state=self.problems_state, by_z={str(z): v for z, v in self.problems.items()})

class Cache:
    """The last few parsed plates, keyed by path + modification time (so a re-sliced plate is re-read)."""
    def __init__(self, keep=3):
        self.keep, self.items, self.lock = keep, [], threading.Lock()
    def get(self, path):
        key = (path, os.path.getmtime(path))
        with self.lock:
            for k, p in self.items:
                if k == key:
                    return p
        p = Plate(path)
        with self.lock:
            self.items = [(k, q) for k, q in self.items if k[0] != path] + [(key, p)]
            self.items = self.items[-self.keep:]
        return p

def viewer_html(pid, name, title, info):
    """The body of the viewer page: a canvas, a slider, play, a legend and the problem overlay."""
    return f"""<p><a href='/p/{pid}'>&larr; Back to the project</a></p><h1>{title}</h1><p class=sub>{info}</p>
<div class=card><div id=hud class=row><b id=lz>loading...</b><span class=small id=lstat></span></div>
<canvas id=cv width=1000 height=640 style='width:100%;background:#fbfaf6;border:1px solid var(--line);border-radius:10px;touch-action:none'></canvas>
<div style='display:flex;gap:10px;align-items:center;margin-top:10px'><button class=btn id=play type=button>Play</button><input type=range id=sl min=0 max=0 value=0 style='flex:1'>
<label class=small style='margin:0;font-weight:400'><input type=checkbox id=prob checked style='width:auto'> hanging plastic</label></div>
<div id=legend class=small style='margin-top:10px'></div></div>
<script>(function(){{const base="/p/{pid}/plate/{name}",cv=document.getElementById('cv'),cx=cv.getContext('2d'),sl=document.getElementById('sl'),lz=document.getElementById('lz'),st=document.getElementById('lstat'),pl=document.getElementById('play'),pc=document.getElementById('prob');
let meta=null,prev=null,probs={{}},timer=null,cur=0,busy=false,want=-1;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function tx(x){{const b=meta.bounds,s=Math.min((cv.width-40)/(b[2]-b[0]),(cv.height-40)/(b[3]-b[1]));return [20+(x[0]-b[0])*s+( (cv.width-40)-(b[2]-b[0])*s)/2, cv.height-20-(x[1]-b[1])*s-((cv.height-40)-(b[3]-b[1])*s)/2, s]}}
function draw(poly,col,w,alpha){{cx.strokeStyle=col;cx.lineWidth=w;cx.globalAlpha=alpha;cx.beginPath();for(const p of poly){{for(let i=0;i<p.length;i+=2){{const t=tx([p[i],p[i+1]]);i?cx.lineTo(t[0],t[1]):cx.moveTo(t[0],t[1])}}}}cx.stroke()}}
async function show(k){{if(busy){{want=k;return}}busy=true;want=-1;cur=k;sl.value=k;
 const d=await (await fetch(base+'/layer/'+k+'.json')).json();cx.globalAlpha=1;cx.clearRect(0,0,cv.width,cv.height);
 if(prev)for(const f in prev.features)draw(prev.features[f],'#c9c9c9',1,.5);
 let counts=[];for(const f in d.features){{draw(d.features[f],meta.colours[f]||(f.startsWith('Support')?meta.colours['Support']:'#888'),1.6,1);counts.push(f)}}
 if(pc.checked&&probs[String(d.z)]){{const pz=probs[String(d.z)],b=meta.bounds,t0=tx([0,0]),s=t0[2];cx.globalAlpha=.55;
  for(const [kind,col] of [['bridge','#e8a21a'],['cant','#d62828']])for(const c of pz[kind]||[]){{const t=tx(c);cx.fillStyle=col;cx.fillRect(t[0]-s*.5,t[1]-s*.5,s*1.1,s*1.1)}}}}
 lz.textContent='Layer '+(k+1)+' of '+meta.layers+'  ·  height '+d.z.toFixed(2)+' mm';
 const hasP=probs[String(d.z)]&&((probs[String(d.z)].cant||[]).length||(probs[String(d.z)].bridge||[]).length);
 st.textContent=(hasP?'⚠ plastic with little or nothing under it on this layer (orange = bridge, red = hanging). ':'')+counts.join(', ');
 prev=d;busy=false;if(want>=0&&want!==k)show(want)}}
async function loadProblems(){{for(let i=0;i<400;i++){{const r=await (await fetch(base+'/problems.json')).json();probs=r.by_z||{{}};if(r.state==='done'||r.state==='failed'){{if(r.state==='failed')st.textContent='(the hanging-plastic check could not run)';show(cur);return}}await sleep(2000)}}}}
(async()=>{{meta=await (await fetch(base+'/meta.json')).json();sl.max=meta.layers-1;
 const lg=document.getElementById('legend');lg.innerHTML=Object.entries(meta.colours).filter(([k])=>k!=='Custom').map(([k,c])=>`<span style="margin-right:12px"><i style="display:inline-block;width:12px;height:3px;background:${{c}};vertical-align:middle"></i> ${{k}}</span>`).join('');
 sl.addEventListener('input',()=>show(+sl.value));pc.addEventListener('change',()=>show(cur));
 pl.addEventListener('click',()=>{{if(timer){{clearInterval(timer);timer=null;pl.textContent='Play'}}else{{pl.textContent='Pause';timer=setInterval(()=>{{if(cur>=meta.layers-1){{clearInterval(timer);timer=null;pl.textContent='Play';return}}show(cur+1)}},90)}}}});
 document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight')show(Math.min(cur+1,meta.layers-1));if(e.key==='ArrowLeft')show(Math.max(cur-1,0))}});
 const q=new URLSearchParams(location.search).get('l');show(Math.max(0,Math.min(q?(+q)-1:5,meta.layers-1)));loadProblems()}})();}})();</script>"""
