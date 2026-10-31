"""The 3D model view: the project's own model (model.scad) as a mesh you can turn, zoom and take apart in the browser.

Each [[model3d]] table in the project marker names one piece of the model, drawn IN PLACE (not laid flat like an [[export]]), with a colour:

    [[model3d]]
    name = "display"             # the piece (letters, digits, - and _)
    label = "LED display"        # what the person sees
    part = "display"             # the model's `part` value that draws just that piece, where it sits in the finished thing
    colour = "#3A7BD5"
    scene = "assembled"          # "assembled" (the default) or "exploded" (the pulled-apart drawing)

With no [[model3d]] tables the view is the model's part = "assembly" (and part = "exploded" if the model has one), each in one colour.
The pieces are drawn with OpenSCAD like the pictures (same command setting) and kept in renders/3d/ as plain float32 triangles plus a meta.json; the page
draws them with WebGL (no library). Z is up, as in every model."""
import json, os, re, shutil, subprocess, time
import numpy as np
import trimesh

NAME = re.compile(r"[a-z0-9_-]{1,40}")
COLOUR = re.compile(r"#[0-9a-fA-F]{6}")
SCENES = [("assembled", "Assembled"), ("exploded", "Pulled apart")]
PALETTE = ["#7C9CC4", "#D9A441", "#7FB685", "#C4725A", "#9B86C2", "#5FB0B7"]
DEFAULT = [dict(name="assembly", label="Assembled", part="assembly", colour="#8FA3BF", scene="assembled"),
           dict(name="exploded", label="Pulled apart", part="exploded", colour="#8FA3BF", scene="exploded")]

def pieces(marker):
    out = []
    for i, e in enumerate(marker.get("model3d") or DEFAULT):
        n = str(e.get("name", ""))
        if not NAME.fullmatch(n):
            raise ValueError(f"a [[model3d]] needs a name of lower-case letters, digits, - or _ (got {e.get('name')!r})")
        c = str(e.get("colour") or PALETTE[i % len(PALETTE)])
        if not COLOUR.fullmatch(c):
            raise ValueError(f"the colour of [[model3d]] {n} must look like #3A7BD5 (got {c!r})")
        s = str(e.get("scene", "assembled"))
        if s not in dict(SCENES):
            raise ValueError(f"the scene of [[model3d]] {n} must be assembled or exploded (got {s!r})")
        out.append(dict(name=n, label=str(e.get("label", n))[:60], part=str(e.get("part", n)), colour=c.upper(), scene=s))
    return out

def dir3d(folder):
    return os.path.join(folder, "renders", "3d")

def triangles(mesh):
    """-> float32 array of shape (n * 3, 3): the three corners of every triangle, in order."""
    return np.asarray(mesh.vertices, dtype=np.float32)[np.asarray(mesh.faces)].reshape(-1, 3)

def build(folder, marker, command=None, timeout=300):
    """Draw every piece and write renders/3d/. -> list of dict(name, ok, error). A piece that cannot be drawn is left out and reported; the others still show."""
    folder = os.path.abspath(folder)
    model = marker.get("model")
    if not model or os.path.isabs(model) or ".." in model.split("/") or not os.path.exists(os.path.join(folder, model)):
        raise ValueError("the project's marker needs model = \"file.scad\" (a file inside the project) to build the 3D view")
    cmd = command or [shutil.which("openscad") or "openscad"]
    out = dir3d(folder); os.makedirs(out, exist_ok=True)
    res, kept = [], {}
    for p in pieces(marker):
        tmp = os.path.join(out, p["name"] + ".part.stl")
        try:
            r = subprocess.run(cmd + ["-q", "--backend=manifold", "-D", f'part="{p["part"]}"', "-o", tmp, os.path.join(folder, model)],
                               capture_output=True, text=True, timeout=timeout, cwd=folder)
            if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 200:
                res.append(dict(name=p["name"], ok=False, error=(r.stderr.strip().splitlines() or [f'OpenSCAD drew nothing for part = "{p["part"]}"'])[-1][:200]))
                continue
            try:
                m = trimesh.load(tmp, force="mesh")
                bad = len(m.faces) == 0
            except Exception:
                bad = True
            if bad:
                res.append(dict(name=p["name"], ok=False, error="OpenSCAD's drawing of the piece could not be read as a surface")); continue
            tri = triangles(m)
            tri.tofile(os.path.join(out, p["name"] + ".bin.part")); os.replace(os.path.join(out, p["name"] + ".bin.part"), os.path.join(out, p["name"] + ".bin"))
            kept[p["name"]] = dict(p, tris=len(tri) // 3, lo=[round(float(x), 2) for x in tri.min(0)], hi=[round(float(x), 2) for x in tri.max(0)])
            res.append(dict(name=p["name"], ok=True, error=""))
        except FileNotFoundError:
            res.append(dict(name=p["name"], ok=False, error="OpenSCAD is not installed on this machine"))
        except subprocess.TimeoutExpired:
            res.append(dict(name=p["name"], ok=False, error="drawing took too long"))
        finally:
            if os.path.exists(tmp): os.remove(tmp)
    scenes = [dict(name=s, label=lab, pieces=[v for v in kept.values() if v["scene"] == s]) for s, lab in SCENES]
    scenes = [s for s in scenes if s["pieces"]]
    meta = dict(stamp=int(time.time()), scenes=scenes)
    with open(os.path.join(out, "meta.json.part"), "w") as f: json.dump(meta, f)
    os.replace(os.path.join(out, "meta.json.part"), os.path.join(out, "meta.json"))
    for fn in os.listdir(out):                                   # drop the files of pieces that are no longer in the model
        if fn.endswith(".bin") and fn[:-4] not in kept: os.remove(os.path.join(out, fn))
    return res

def load_meta(folder):
    try:
        with open(os.path.join(dir3d(folder), "meta.json")) as f: return json.load(f)
    except (OSError, ValueError):
        return None

JS = r"""(async function(){const base="/p/%PID%/model3d",stamp=%STAMP%;const card=document.getElementById('m3d'),cv=document.getElementById('m3c'),note=document.getElementById('m3n');
const meta=await (await fetch(base+'/meta.json?n='+stamp)).json();const gl=cv.getContext('webgl2');if(!gl){note.textContent='This browser cannot draw 3D (it needs WebGL2).';return}
function prog(vs,fs){const p=gl.createProgram();for(const [t,src] of [[gl.VERTEX_SHADER,vs],[gl.FRAGMENT_SHADER,fs]]){const s=gl.createShader(t);gl.shaderSource(s,src);gl.compileShader(s);gl.attachShader(p,s)}gl.linkProgram(p);return p}
const P=prog(`#version 300 es
in vec3 p;uniform mat4 vp;out vec3 w;void main(){w=p;gl_Position=vp*vec4(p,1.);}`,`#version 300 es
precision highp float;in vec3 w;uniform vec3 col;out vec4 o;void main(){vec3 n=normalize(cross(dFdx(w),dFdy(w)));float l=.32+.68*abs(dot(n,normalize(vec3(.4,-.5,.8))));if(!gl_FrontFacing)l*=.7;o=vec4(col*l,1.);}`);
const hex=h=>[1,3,5].map(i=>parseInt(h.substr(i,2),16)/255);const items={};
for(const s of meta.scenes)for(const q of s.pieces){const b=new Float32Array(await (await fetch(base+'/'+q.name+'.bin?n='+stamp)).arrayBuffer());const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,b,gl.STATIC_DRAW);items[q.name]={vb,n:b.length/3,col:hex(q.colour),on:true,q}}
let scene=meta.scenes[0],th=-.6,ph=.5,dist=1,ctr=[0,0,0],size=1,draws=0;
function fit(){let lo=[1e9,1e9,1e9],hi=[-1e9,-1e9,-1e9];for(const q of scene.pieces)for(let k=0;k<3;k++){lo[k]=Math.min(lo[k],q.lo[k]);hi[k]=Math.max(hi[k],q.hi[k])}ctr=[0,1,2].map(k=>(lo[k]+hi[k])/2);size=Math.max(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2])||1;dist=size*1.9;th=-.6;ph=.5}
function mul(a,b){const o=new Float32Array(16);for(let i=0;i<4;i++)for(let j=0;j<4;j++){let s=0;for(let k=0;k<4;k++)s+=a[k*4+j]*b[i*4+k];o[i*4+j]=s}return o}
function persp(f,a,n,fa){const t=1/Math.tan(f/2),o=new Float32Array(16);o[0]=t/a;o[5]=t;o[10]=(fa+n)/(n-fa);o[11]=-1;o[14]=2*fa*n/(n-fa);return o}
function look(e,c,u){let z=[e[0]-c[0],e[1]-c[1],e[2]-c[2]],l=Math.hypot(...z);z=z.map(v=>v/l);let x=[u[1]*z[2]-u[2]*z[1],u[2]*z[0]-u[0]*z[2],u[0]*z[1]-u[1]*z[0]];l=Math.hypot(...x);x=x.map(v=>v/l);const y=[z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0]];
 return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-(x[0]*e[0]+x[1]*e[1]+x[2]*e[2]),-(y[0]*e[0]+y[1]*e[1]+y[2]*e[2]),-(z[0]*e[0]+z[1]*e[1]+z[2]*e[2]),1])}
function draw(){gl.viewport(0,0,cv.width,cv.height);gl.clearColor(.953,.945,.918,1);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);
 const e=[ctr[0]+dist*Math.cos(ph)*Math.sin(th),ctr[1]-dist*Math.cos(ph)*Math.cos(th),ctr[2]+dist*Math.sin(ph)];
 const vp=mul(persp(.7,cv.width/cv.height,size*.05,size*30),look(e,ctr,[0,0,1]));gl.useProgram(P);gl.uniformMatrix4fv(gl.getUniformLocation(P,'vp'),false,vp);const a=gl.getAttribLocation(P,'p'),cl=gl.getUniformLocation(P,'col');
 for(const q of scene.pieces){const it=items[q.name];if(!it.on)continue;gl.uniform3fv(cl,it.col);gl.bindBuffer(gl.ARRAY_BUFFER,it.vb);gl.enableVertexAttribArray(a);gl.vertexAttribPointer(a,3,gl.FLOAT,false,0,0);gl.drawArrays(gl.TRIANGLES,0,it.n)}
 draws++;window.__f2pView={th,ph,dist,draws,scene:scene.name,pieces:scene.pieces.length,shown:scene.pieces.filter(q=>items[q.name].on).length,tris:scene.pieces.reduce((s,q)=>s+q.tris,0)}}
function panel(){const sb=document.getElementById('m3s'),pl=document.getElementById('m3p');sb.innerHTML='';for(const s of meta.scenes){const b=document.createElement('button');b.type='button';b.className='btn'+(s===scene?'':' ghost');b.textContent=s.label;b.onclick=()=>{scene=s;fit();panel();draw()};sb.appendChild(b)}
 pl.innerHTML='';for(const q of scene.pieces){const l=document.createElement('label');l.style.cssText='display:inline-flex;gap:6px;align-items:center;margin:4px 14px 4px 0;font-size:15px';const c=document.createElement('input');c.type='checkbox';c.checked=items[q.name].on;c.style.width='auto';c.onchange=()=>{items[q.name].on=c.checked;draw()};
  const sw=document.createElement('span');sw.style.cssText='width:14px;height:14px;border-radius:3px;border:1px solid #0003;background:'+q.colour;l.append(c,sw,document.createTextNode(q.label));pl.appendChild(l)}}
let drag=null;cv.addEventListener('pointerdown',e=>{drag=[e.clientX,e.clientY];cv.setPointerCapture(e.pointerId);cv.style.cursor='grabbing'});cv.addEventListener('pointerup',()=>{drag=null;cv.style.cursor='grab'});
cv.addEventListener('pointermove',e=>{if(!drag)return;th-=(e.clientX-drag[0])*.008;ph=Math.max(-1.45,Math.min(1.5,ph+(e.clientY-drag[1])*.008));drag=[e.clientX,e.clientY];draw()});
cv.addEventListener('wheel',e=>{e.preventDefault();dist=Math.max(size*.4,Math.min(size*8,dist*(1+Math.sign(e.deltaY)*.1)));draw()},{passive:false});
document.getElementById('m3r').addEventListener('click',()=>{fit();draw()});note.textContent='Drag to turn it, scroll or pinch to zoom. Untick a part to hide it.';fit();panel();draw();})();"""

def card(pid, folder, esc=lambda s: s):
    """The card for the project page: '' until the 3D view has been built."""
    meta = load_meta(folder)
    if not meta or not meta.get("scenes"):
        return ""
    return (f"<div class=card id=m3d><div class=row><h3>The model in 3D</h3><span><span id=m3s></span> <button class='btn ghost' id=m3r type=button>Reset view</button></span></div>"
            "<canvas id=m3c width=1000 height=560 style='width:100%;background:#f3f1ea;border:1px solid var(--line);border-radius:10px;touch-action:none;cursor:grab;margin-top:8px'></canvas>"
            "<div id=m3p style='margin-top:6px'></div><div class=small id=m3n></div></div>"
            "<script>" + JS.replace("%PID%", pid).replace("%STAMP%", str(int(meta.get("stamp", 0)))) + "</script>")
