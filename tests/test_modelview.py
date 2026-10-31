"""The 3D model view: marker validation, the build (real OpenSCAD, skipped without it), the routes, and a REAL-BROWSER check that you can turn, hide and switch
(skipped without Chrome and the websockets library). Negative controls: a bad name, colour or scene is refused; a piece OpenSCAD cannot draw is reported and
the others still show; the 3D files of a removed piece are deleted."""
import asyncio, http.client, json, os, shutil, subprocess, sys, tempfile, threading, time, unittest, urllib.request
from fit2print import modelview, project, server
from fit2print.server import read_marker
try:
    import websockets
except ImportError:
    websockets = None
OPENSCAD = shutil.which("openscad")
CHROME = shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")
MODEL = '''part = "assembly";
module box() cube([40,30,12]);
module lid() translate([0,0,12]) cube([40,30,3]);
module disp() translate([5,5,2]) cube([30,10,6]);
if (part == "assembly") { box(); lid(); disp(); }
if (part == "box") box();
if (part == "lid") lid();
if (part == "display") disp();
if (part == "exploded") { box(); translate([0,0,25]) lid(); translate([0,40,2]) disp(); }
'''
TOML = '''
model = "model.scad"
[[model3d]]
name = "box"
label = "Case"
part = "box"
colour = "#9AA7B8"
[[model3d]]
name = "display"
label = "LED display"
part = "display"
colour = "#3A7BD5"
[[model3d]]
name = "lid"
label = "Lid"
part = "lid"
colour = "#D9A441"
[[model3d]]
name = "pulled"
label = "Pulled apart"
part = "exploded"
scene = "exploded"
'''

def make_project(d, extra=""):
    f = os.path.join(d, "p"); project.init(f, "View Test")
    open(os.path.join(f, "model.scad"), "w").write(MODEL)
    with open(os.path.join(f, "fit2print.toml"), "a") as fh: fh.write(TOML + extra)
    return f

class Marker(unittest.TestCase):
    def test_default_is_the_assembly_and_the_exploded_drawing(self):
        self.assertEqual([(p["part"], p["scene"]) for p in modelview.pieces({})], [("assembly", "assembled"), ("exploded", "exploded")])
    def test_bad_names_colours_and_scenes_are_refused(self):          # NEGATIVE CONTROLS
        for bad in (dict(name="Bad Name"), dict(name="x", colour="red"), dict(name="x", scene="sideways")):
            with self.assertRaises(ValueError): modelview.pieces(dict(model3d=[bad]))
    def test_no_card_before_it_is_built(self):
        with tempfile.TemporaryDirectory() as d: self.assertEqual(modelview.card("p", make_project(d)), "")

@unittest.skipUnless(OPENSCAD, "needs OpenSCAD")
class Build(unittest.TestCase):
    def test_builds_the_pieces_and_the_meta(self):
        with tempfile.TemporaryDirectory() as d:
            f = make_project(d); m = read_marker(f)
            r = modelview.build(f, m); self.assertTrue(all(x["ok"] for x in r), r)
            meta = modelview.load_meta(f); self.assertEqual([s["name"] for s in meta["scenes"]], ["assembled", "exploded"])
            box = [q for q in meta["scenes"][0]["pieces"] if q["name"] == "box"][0]
            self.assertEqual((box["tris"], box["lo"], box["hi"]), (12, [0, 0, 0], [40, 30, 12]))
            self.assertEqual(os.path.getsize(os.path.join(modelview.dir3d(f), "box.bin")), 12 * 9 * 4)
            self.assertIn("The model in 3D", modelview.card("p", f))
    def test_a_piece_that_cannot_be_drawn_is_reported_and_the_rest_still_show(self):    # NEGATIVE CONTROL
        with tempfile.TemporaryDirectory() as d:
            f = make_project(d, '[[model3d]]\nname = "ghost"\npart = "nothing-draws-this"\n')
            r = {x["name"]: x for x in modelview.build(f, read_marker(f))}
            self.assertFalse(r["ghost"]["ok"]); self.assertTrue(r["box"]["ok"])
            self.assertNotIn("ghost", [q["name"] for s in modelview.load_meta(f)["scenes"] for q in s["pieces"]])
    def test_files_of_a_removed_piece_are_deleted(self):
        with tempfile.TemporaryDirectory() as d:
            f = make_project(d); modelview.build(f, read_marker(f)); self.assertTrue(os.path.exists(os.path.join(modelview.dir3d(f), "lid.bin")))
            t = open(os.path.join(f, "fit2print.toml")).read().replace('[[model3d]]\nname = "lid"\nlabel = "Lid"\npart = "lid"\ncolour = "#D9A441"\n', "")
            open(os.path.join(f, "fit2print.toml"), "w").write(t); modelview.build(f, read_marker(f))
            self.assertFalse(os.path.exists(os.path.join(modelview.dir3d(f), "lid.bin")))

@unittest.skipUnless(OPENSCAD and CHROME and websockets, "needs OpenSCAD, Chrome and the websockets library")
class Browser(unittest.TestCase):
    def test_turn_hide_switch_in_a_real_browser(self):
        d = tempfile.mkdtemp(); f = make_project(d); modelview.build(f, read_marker(f))
        srv = server.make_server(dict(projects=[f], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        c = http.client.HTTPConnection("127.0.0.1", port); c.request("GET", "/p/view-test/model3d/meta.json"); self.assertEqual(c.getresponse().status, 200)
        c = http.client.HTTPConnection("127.0.0.1", port); c.request("GET", "/p/view-test/model3d/..%2Ffit2print.toml"); self.assertNotEqual(c.getresponse().status, 200)   # NEGATIVE CONTROL
        out = {}
        async def main():
            cport = 9379; prof = tempfile.mkdtemp()
            p = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", f"--remote-debugging-port={cport}", f"--user-data-dir={prof}", "--window-size=1200,1500", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try: tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{cport}/json")); break
                    except Exception: time.sleep(0.2)
                async with websockets.connect([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
                    n = 0; errs = []
                    async def call(m, **pr):
                        nonlocal n; n += 1; await ws.send(json.dumps({"id": n, "method": m, "params": pr}))
                        while True:
                            x = json.loads(await ws.recv())
                            if x.get("method") == "Runtime.exceptionThrown": errs.append(str(x["params"]["exceptionDetails"])[:300])
                            if x.get("id") == n: return x.get("result", x)
                    async def js(e):
                        r = await call("Runtime.evaluate", expression=e, awaitPromise=True, returnByValue=True); return r.get("result", {}).get("value")
                    async def click(sel):
                        x, y = await js(f"(()=>{{const e=document.querySelector({json.dumps(sel)});e.scrollIntoView({{block:'center'}});const b=e.getBoundingClientRect();return [b.x+b.width/2,b.y+b.height/2]}})()")
                        for t in ("mouseMoved", "mousePressed", "mouseReleased"): await call("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
                        return x, y
                    await call("Runtime.enable"); await call("Page.enable")
                    await call("Page.navigate", url=f"http://127.0.0.1:{port}/p/view-test")
                    for _ in range(80):                                           # wait for the viewer itself, not a fixed time
                        await asyncio.sleep(0.5); out["v0"] = await js("window.__f2pView||null")
                        if out["v0"]: break
                    x, y = await click("#m3c")                                    # real drag on the canvas
                    await call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
                    for k in range(1, 8): await call("Input.dispatchMouseEvent", type="mouseMoved", x=x + k * 12, y=y + k * 5, button="left", buttons=1)
                    await call("Input.dispatchMouseEvent", type="mouseReleased", x=x + 90, y=y + 40, button="left", clickCount=1)
                    out["v1"] = await js("window.__f2pView")
                    await click("#m3p input")                                     # untick the first part
                    out["v2"] = await js("window.__f2pView")
                    await click("#m3s button:nth-child(2)")                       # the Pulled apart scene
                    out["v3"] = await js("window.__f2pView")
                    out["errs"] = errs[:3]
                    await call("Emulation.setDeviceMetricsOverride", width=1200, height=1500, deviceScaleFactor=1, mobile=False)
                    import base64
                    s = await call("Page.captureScreenshot", format="png", clip=await js("(()=>{const b=document.getElementById('m3c').getBoundingClientRect();return {x:b.x+scrollX,y:b.y+scrollY,width:b.width,height:b.height,scale:1}})()"))
                    out["png"] = base64.b64decode(s["data"])
            finally:
                p.terminate()
        asyncio.run(main()); srv.shutdown()
        self.assertEqual(out["errs"], [])
        self.assertEqual((out["v0"]["pieces"], out["v0"]["shown"], out["v0"]["tris"]), (3, 3, 36))
        self.assertNotAlmostEqual(out["v1"]["th"], out["v0"]["th"], places=2, msg="dragging did not turn the view")
        self.assertEqual(out["v2"]["shown"], 2, "unticking a part did not hide it")
        self.assertEqual((out["v3"]["scene"], out["v3"]["pieces"]), ("exploded", 1))
        from PIL import Image; import io
        im = Image.open(io.BytesIO(out["png"])).convert("RGB"); cols = {im.getpixel((x, y)) for x in range(0, im.width, 7) for y in range(0, im.height, 7)}
        self.assertGreater(len(cols), 4, "the canvas is blank")

if __name__ == "__main__":
    unittest.main()
