"""3D shapes of library components: expressions are safe, status follows what has been measured, the drawing is real (OpenSCAD, skipped without it), the page
route works, and a REAL-BROWSER check that the component page shows a viewer you can turn (skipped without Chrome + websockets)."""
import asyncio, http.client, json, os, shutil, subprocess, tempfile, threading, time, unittest, urllib.request
from fit2print import hardware, componentview, server
try:
    import websockets
except ImportError:
    websockets = None
OPENSCAD = shutil.which("openscad"); CHROME = shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")

ENTRY = dict(id="t-board", name="T", dim=dict(
    length=dict(value=60.0, basis="official", source="drawing", unit="mm"), width=dict(value=30.0, basis="official", source="drawing", unit="mm"),
    thick=dict(value=1.5, basis="estimate", source="guess", unit="mm"), inset=dict(value=3.0, basis="official", source="drawing", unit="mm")),
    shape=dict(note="outline", part=[dict(name="pcb", label="Board", colour="#2E7D32", type="box", at=[0, 0, 0], size=["length", "width", "thick"], holes=[["inset", "inset", 2.5], ["length-inset", "width-inset", 2.5]]),
                                     dict(name="flat", label="Flat", colour="#FFFFFF", type="box", at=[0, 0, "thick"], size=["length/2", "width/2", 1])]))

class Shapes(unittest.TestCase):
    def test_numbers_expressions_and_status(self):
        ps = {p["name"]: p for p in hardware.shape_parts(ENTRY)}
        self.assertEqual(ps["pcb"]["size"], [60.0, 30.0, 1.5]); self.assertEqual(ps["pcb"]["holes"][1], [57.0, 27.0, 2.5])
        self.assertEqual(ps["pcb"]["status"], "unverified")                      # it rests on the estimated thickness
        self.assertEqual(ps["flat"]["size"], [30.0, 15.0, 1.0])
    def test_measuring_makes_it_measured_and_changes_the_cache_key(self):
        before = componentview.key(ENTRY)
        e = json.loads(json.dumps(ENTRY)); e["dim"]["thick"]["measured"] = dict(value=1.6, on="2026-10-31", how="callipers")
        for k in ("length", "width", "inset"): e["dim"][k]["measured"] = dict(value=e["dim"][k]["value"], on="2026-10-31", how="callipers")
        ps = {p["name"]: p for p in hardware.shape_parts(e)}
        self.assertEqual(ps["pcb"]["status"], "measured"); self.assertEqual(ps["pcb"]["size"][2], 1.6); self.assertNotEqual(componentview.key(e), before)
    def test_unsafe_or_unknown_expressions_are_refused(self):              # NEGATIVE CONTROLS
        for bad in ("__import__('os')", "length.real", "nope", "length**2", "open('x')"):
            e = json.loads(json.dumps(ENTRY)); e["shape"]["part"][0]["size"] = [bad, 1, 1]
            with self.assertRaises(ValueError, msg=bad): hardware.shape_parts(e)
    def test_the_shipped_components_all_resolve(self):
        for k, e in hardware.load_all().items():
            self.assertTrue(hardware.shape_parts(e), f"{k} has no shape")

@unittest.skipUnless(OPENSCAD, "needs OpenSCAD")
class Draw(unittest.TestCase):
    def test_draws_the_pieces_and_reuses_them(self):
        with tempfile.TemporaryDirectory() as c:
            d = componentview.ensure(ENTRY, cache=c); meta = json.load(open(os.path.join(d, "meta.json")))
            pcb = [q for q in meta["scenes"][0]["pieces"] if q["name"] == "pcb"][0]
            self.assertEqual((pcb["lo"], pcb["hi"]), ([0, 0, 0], [60, 30, 1.5])); self.assertGreater(pcb["tris"], 12)     # holes make it more than a plain box
            t = os.path.getmtime(os.path.join(d, "meta.json")); self.assertEqual(componentview.ensure(ENTRY, cache=c), d); self.assertEqual(os.path.getmtime(os.path.join(d, "meta.json")), t)

@unittest.skipUnless(OPENSCAD and CHROME and websockets, "needs OpenSCAD, Chrome and websockets")
class Browser(unittest.TestCase):
    def test_component_page_shows_a_viewer_you_can_turn(self):
        d = tempfile.mkdtemp(); componentview.CACHE = os.path.join(d, "cache")
        srv = server.make_server(dict(projects=[], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        out = {}
        async def main():
            cport = 9380; prof = tempfile.mkdtemp()
            p = subprocess.Popen([CHROME, "--headless=new", "--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", f"--remote-debugging-port={cport}", f"--user-data-dir={prof}", "--window-size=1200,1500", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try: tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{cport}/json")); break
                    except Exception: time.sleep(0.2)
                async with websockets.connect([t for t in tabs if t["type"] == "page"][0]["webSocketDebuggerUrl"], max_size=50_000_000) as ws:
                    n = 0
                    async def call(m, **pr):
                        nonlocal n; n += 1; await ws.send(json.dumps({"id": n, "method": m, "params": pr}))
                        while True:
                            x = json.loads(await ws.recv())
                            if x.get("id") == n: return x.get("result", x)
                    async def js(e):
                        r = await call("Runtime.evaluate", expression=e, awaitPromise=True, returnByValue=True); return r.get("result", {}).get("value")
                    await call("Runtime.enable"); await call("Page.enable")
                    await call("Page.navigate", url=f"http://127.0.0.1:{port}/hardware/pi-zero-2-w"); await asyncio.sleep(6)
                    out["v0"] = await js("window.__f2pView||null")
                    out["text"] = await js("document.getElementById('m3p').innerText")
                    x, y = await js("(()=>{const b=document.getElementById('m3c').getBoundingClientRect();document.getElementById('m3c').scrollIntoView({block:'center'});const c=document.getElementById('m3c').getBoundingClientRect();return [c.x+c.width/2,c.y+c.height/2]})()")
                    await call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
                    for k in range(1, 8): await call("Input.dispatchMouseEvent", type="mouseMoved", x=x + k * 12, y=y + k * 4, button="left", buttons=1)
                    await call("Input.dispatchMouseEvent", type="mouseReleased", x=x + 90, y=y + 30, button="left", clickCount=1)
                    out["v1"] = await js("window.__f2pView")
            finally:
                p.terminate()
        asyncio.run(main()); srv.shutdown()
        self.assertEqual(out["v0"]["pieces"], 8)
        self.assertNotAlmostEqual(out["v1"]["th"], out["v0"]["th"], places=2)
        self.assertIn("unverified", out["text"])

if __name__ == "__main__":
    unittest.main()
