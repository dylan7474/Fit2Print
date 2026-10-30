"""The layer preview: step through a sliced plate (a Bambu .3mf or a .gcode) layer by layer in the browser, exactly as the printer will lay it down,
with the places the checks worry about (plastic with nothing under it) marked on the layer where they occur.

  * Plates are found, never named by the page: a project's records (plates.jsonl, or PLATE_RESULTS.jsonl for Phonosphere) and its plates/ folder.
  * A plate is parsed once and kept in memory (the last few); a layer is drawn from it on request as polylines per feature (outer wall, infill, ...).
  * The hanging-plastic overlay comes from the same toolpath check as the verdict, computed in the background (a big plate takes a while)."""
import json, os, re, struct, threading, zipfile
import xml.etree.ElementTree as ET
import numpy as np
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


def _tf(txt):
    """A 3MF transform (12 numbers, row-vector convention) as a 4x4 matrix acting on column vectors."""
    v = [float(x) for x in txt.split()] if txt else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]
    return np.array([[v[0], v[3], v[6], v[9]], [v[1], v[4], v[7], v[10]], [v[2], v[5], v[8], v[11]], [0, 0, 0, 1]], float)

def mesh_triangles(path, limit=400_000):
    """The part(s) of a sliced .3mf as triangles in the BED's coordinates (the same as the G-code's): float array (n, 3, 3). None for a plain .gcode."""
    if not path.endswith(".3mf"):
        return None
    z = zipfile.ZipFile(path)
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02", "p": "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"}
    def parse(name):
        return ET.fromstring(z.read(name.lstrip("/")))
    def meshes_of(root):
        out = {}
        for o in root.findall(".//m:object", ns):
            mesh = o.find("m:mesh", ns)
            if mesh is not None:
                v = np.array([[float(x.get(a)) for a in "xyz"] for x in mesh.findall("m:vertices/m:vertex", ns)])
                t = np.array([[int(x.get(a)) for a in ("v1", "v2", "v3")] for x in mesh.findall("m:triangles/m:triangle", ns)])
                out[o.get("id")] = ("mesh", v[t] if len(t) else np.zeros((0, 3, 3)))
            else:
                out[o.get("id")] = ("components", [(c.get("{%s}path" % ns["p"]), c.get("objectid"), _tf(c.get("transform"))) for c in o.findall("m:components/m:component", ns)])
        return out
    main = parse("3D/3dmodel.model"); objs = meshes_of(main); tris = []
    cache = {}
    def resolve(oid, mat, extra=None):
        kind, data = (extra or objs)[oid]
        if kind == "mesh":
            tris.append(np.einsum("ij,nkj->nki", mat[:3, :3], data) + mat[:3, 3])
        else:
            for path, cid, cm in data:
                if path:
                    if path not in cache: cache[path] = meshes_of(parse(path))
                    resolve(cid, mat @ cm, cache[path])
                else:
                    resolve(cid, mat @ cm, extra)
    for item in main.findall(".//m:build/m:item", ns):
        if item.get("printable", "1") != "0" and item.get("objectid") in objs:
            resolve(item.get("objectid"), _tf(item.get("transform")))
    if not tris:
        return None
    t = np.concatenate(tris)
    return t[:limit] if len(t) > limit else t

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
        try:
            self.tris = mesh_triangles(path)
        except Exception:
            self.tris = None
    def meta(self):
        return dict(layers=len(self.zs), zs=[round(z, 2) for z in self.zs], bounds=[round(b, 2) for b in self.bounds], colours=COLOURS, problems=self.problems_state, mesh=0 if self.tris is None else len(self.tris))
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
    def mesh_bytes(self):
        return np.ascontiguousarray(self.tris, dtype='<f4').tobytes()
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

CARD3 = '''<div class=card id=card3 style='display:none'><div class=row><h3>The part in 3D</h3><span><label class=small style='margin:0;font-weight:400'><input type=checkbox id=clip checked style='width:auto'> only what is printed so far</label> <button class='btn ghost' id=reset3 type=button>Reset view</button></span></div>
<canvas id=c3 width=1000 height=560 style='width:100%;background:#f3f1ea;border:1px solid var(--line);border-radius:10px;touch-action:none;cursor:grab'></canvas>
<div class=small>Drag to turn it, scroll or pinch to zoom. Orange inside = the cut where the print has got to. Red and amber dots = plastic with little or nothing under it.</div></div>
<script>(async function(){const base="/p/%PID%/plate/%NAME%";const meta=await (await fetch(base+'/meta.json')).json();if(!meta.mesh)return;
const card=document.getElementById('card3'),cv=document.getElementById('c3'),gl=cv.getContext('webgl2');if(!gl){card.style.display='block';card.querySelector('.small').textContent='This browser cannot draw 3D (WebGL2).';return}card.style.display='block';
function prog(vs,fs){const p=gl.createProgram();for(const [t,src] of [[gl.VERTEX_SHADER,vs],[gl.FRAGMENT_SHADER,fs]]){const s=gl.createShader(t);gl.shaderSource(s,src);gl.compileShader(s);gl.attachShader(p,s)}gl.linkProgram(p);return p}
const P=prog(`#version 300 es
in vec3 p;uniform mat4 vp;out vec3 w;void main(){w=p;gl_Position=vp*vec4(p,1.);}`,`#version 300 es
precision highp float;in vec3 w;uniform float clipz;out vec4 o;void main(){if(w.z>clipz)discard;if(!gl_FrontFacing){o=vec4(.93,.6,.25,1.);return;}
vec3 n=normalize(cross(dFdx(w),dFdy(w)));float l=.30+.70*abs(dot(n,normalize(vec3(.4,-.5,.8))));vec3 c=mix(vec3(.55,.64,.78),vec3(.75,.82,.92),clamp(w.z/40.,0.,1.));o=vec4(c*l,1.);}`);
const Q=prog(`#version 300 es
in vec3 p;uniform mat4 vp;out vec3 w;void main(){w=p;gl_Position=vp*vec4(p,1.);gl_PointSize=6.;}`,`#version 300 es
precision highp float;in vec3 w;uniform float clipz;uniform vec3 col;out vec4 o;void main(){if(w.z>clipz)discard;o=vec4(col,1.);}`);
const buf=new Float32Array(await (await fetch(base+'/mesh.bin')).arrayBuffer());const nv=buf.length/3;
const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,buf,gl.STATIC_DRAW);
let lo=[1e9,1e9,1e9],hi=[-1e9,-1e9,-1e9];for(let i=0;i<buf.length;i+=3)for(let k=0;k<3;k++){lo[k]=Math.min(lo[k],buf[i+k]);hi[k]=Math.max(hi[k],buf[i+k])}
const ctr=[0,1,2].map(k=>(lo[k]+hi[k])/2),size=Math.max(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2]);
let th=-.6,ph=.55,dist=size*1.9,clipz=1e9,pts={bridge:null,cant:null};
function mul(a,b){const o=new Float32Array(16);for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];o[i*4+j]=s}return o}
function persp(f,a,n,fa){const t=1/Math.tan(f/2),o=new Float32Array(16);o[0]=t/a;o[5]=t;o[10]=(fa+n)/(n-fa);o[11]=-1;o[14]=2*fa*n/(n-fa);return o}
function look(e,c,u){let z=[e[0]-c[0],e[1]-c[1],e[2]-c[2]],l=Math.hypot(...z);z=z.map(v=>v/l);let x=[u[1]*z[2]-u[2]*z[1],u[2]*z[0]-u[0]*z[2],u[0]*z[1]-u[1]*z[0]];l=Math.hypot(...x);x=x.map(v=>v/l);const y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]];
 return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-(x[0]*e[0]+x[1]*e[1]+x[2]*e[2]),-(y[0]*e[0]+y[1]*e[1]+y[2]*e[2]),-(z[0]*e[0]+z[1]*e[1]+z[2]*e[2]),1])}
function draw(){gl.viewport(0,0,cv.width,cv.height);gl.clearColor(.953,.945,.918,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
 const e=[ctr[0]+dist*Math.cos(ph)*Math.sin(th),ctr[1]-dist*Math.cos(ph)*Math.cos(th),ctr[2]+dist*Math.sin(ph)];
 const vp=mul(persp(.7,cv.width/cv.height,size*.05,size*20),look(e,ctr,[0,0,1]));const cz=document.getElementById('clip').checked?clipz:1e9;
 gl.useProgram(P);gl.uniformMatrix4fv(gl.getUniformLocation(P,'vp'),false,vp);gl.uniform1f(gl.getUniformLocation(P,'clipz'),cz);
 gl.bindBuffer(gl.ARRAY_BUFFER,vb);let a=gl.getAttribLocation(P,'p');gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.TRIANGLES,0,nv);
 gl.useProgram(Q);gl.uniformMatrix4fv(gl.getUniformLocation(Q,'vp'),false,vp);gl.uniform1f(gl.getUniformLocation(Q,'clipz'),cz);a=gl.getAttribLocation(Q,'p');
 for(const [k,col] of [['bridge',[.91,.64,.1]],['cant',[.84,.16,.16]]])if(pts[k]){gl.uniform3fv(gl.getUniformLocation(Q,'col'),col);gl.bindBuffer(gl.ARRAY_BUFFER,pts[k].b);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.POINTS,0,pts[k].n)}}
window.f2pSet=z=>{clipz=z+0.05;draw()};
window.f2pProb=pr=>{for(const k of ['bridge','cant']){const a=[];for(const z in pr)for(const c of pr[z][k]||[])a.push(c[0],c[1],parseFloat(z)-0.1);if(a.length){const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(a),gl.STATIC_DRAW);pts[k]={b,n:a.length/3}}}draw()};
let drag=null;cv.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId);cv.style.cursor='grabbing'});cv.addEventListener('pointerup',()=>{drag=null;cv.style.cursor='grab'});
cv.addEventListener('pointermove',e=>{if(!drag)return;th-=(e.clientX-drag[0])*.008;ph=Math.max(-1.4,Math.min(1.5,ph+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];draw()});
cv.addEventListener('wheel',e=>{e.preventDefault();dist=Math.max(size*.4,Math.min(size*6,dist*(1+Math.sign(e.deltaY)*.1)));draw()},{passive:false});
document.getElementById('clip').addEventListener('change',draw);document.getElementById('reset3').addEventListener('click',()=>{th=-.6;ph=.55;dist=size*1.9;draw()});
if(window.__lastZ!==undefined)clipz=window.__lastZ+.05;draw();})();</script>'''

def viewer_html(pid, name, title, info):
    """The body of the viewer page: a canvas, a slider, play, a legend and the problem overlay."""
    return f"""<p><a href='/p/{pid}'>&larr; Back to the project</a></p><h1>{title}</h1><p class=sub>{info}</p>
<div class=card><div id=hud class=row><b id=lz>loading...</b><span class=small id=lstat></span></div>
<canvas id=cv width=1000 height=640 style='width:100%;background:#fbfaf6;border:1px solid var(--line);border-radius:10px;touch-action:none'></canvas>
<div style='display:flex;gap:10px;align-items:center;margin-top:10px'><button class=btn id=play type=button>Play</button><input type=range id=sl min=0 max=0 value=0 style='flex:1'>
<label class=small style='margin:0;font-weight:400'><input type=checkbox id=prob checked style='width:auto'> hanging plastic</label></div>
<div id=legend class=small style='margin-top:10px'></div></div>
{CARD3.replace('%PID%', pid).replace('%NAME%', name)}
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
 prev=d;window.__lastZ=d.z;if(window.f2pSet)window.f2pSet(d.z);busy=false;if(want>=0&&want!==k)show(want)}}
async function loadProblems(){{for(let i=0;i<400;i++){{const r=await (await fetch(base+'/problems.json')).json();probs=r.by_z||{{}};if(r.state==='done'||r.state==='failed'){{if(r.state==='failed')st.textContent='(the hanging-plastic check could not run)';else if(window.f2pProb)window.f2pProb(probs);show(cur);return}}await sleep(2000)}}}}
(async()=>{{meta=await (await fetch(base+'/meta.json')).json();sl.max=meta.layers-1;
 const lg=document.getElementById('legend');lg.innerHTML=Object.entries(meta.colours).filter(([k])=>k!=='Custom').map(([k,c])=>`<span style="margin-right:12px"><i style="display:inline-block;width:12px;height:3px;background:${{c}};vertical-align:middle"></i> ${{k}}</span>`).join('');
 sl.addEventListener('input',()=>show(+sl.value));pc.addEventListener('change',()=>show(cur));
 pl.addEventListener('click',()=>{{if(timer){{clearInterval(timer);timer=null;pl.textContent='Play'}}else{{pl.textContent='Pause';timer=setInterval(()=>{{if(cur>=meta.layers-1){{clearInterval(timer);timer=null;pl.textContent='Play';return}}show(cur+1)}},90)}}}});
 document.addEventListener('keydown',e=>{{if(e.key==='ArrowRight')show(Math.min(cur+1,meta.layers-1));if(e.key==='ArrowLeft')show(Math.max(cur-1,0))}});
 const q=new URLSearchParams(location.search).get('l');show(Math.max(0,Math.min(q?(+q)-1:5,meta.layers-1)));loadProblems()}})();}})();</script>"""
