import http.client, json, os, stat, sys, tempfile, threading, time, unittest
from fit2print import project, render, server

FAKE = """#!{py}
import sys
a = sys.argv
out = a[a.index("-o") + 1]
if "BREAK" in " ".join(a): sys.exit(2)
import os
from PIL import Image
Image.frombytes("RGB", (60, 40), os.urandom(60 * 40 * 3)).save(out, "PNG")      # noise, so the file is a realistic size
"""

class Render(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Render Test")
        open(os.path.join(self.f, "model.scad"), "w").write("cube(1);")
        self.fake = os.path.join(self.d.name, "openscad"); open(self.fake, "w").write(FAKE.format(py=sys.executable)); os.chmod(self.fake, 0o755)
    def tearDown(self): self.d.cleanup()
    def test_views_default_and_validation(self):
        self.assertEqual(render.views({})[0]["part"], "assembly")
        with self.assertRaises(ValueError): render.views({"render": [{"name": "../x"}]})            # NEGATIVE CONTROL: no path tricks in a name
        with self.assertRaises(ValueError): render.views({"render": [{"name": "ok", "angle": [1, 2]}]})
    def test_named_views_look_from_different_places(self):
        v = {x["name"]: x["angle"] for x in render.views({"render": [dict(name="f", view="front"), dict(name="s", view="right"), dict(name="i", view="iso"), dict(name="t", view="top")]})}
        self.assertEqual(v["f"], [90.0, 0.0, 0.0]); self.assertEqual(len({tuple(a) for a in v.values()}), 4)          # all four differ
    def test_the_bug_of_2026_10_31_unknown_fields_are_refused(self):        # NEGATIVE CONTROL: `view = "front"` used to be ignored, so two pictures came out identical
        with self.assertRaises(ValueError) as c: render.views({"render": [dict(name="a", vue="front")]})
        self.assertIn("unknown field", str(c.exception))
        with self.assertRaises(ValueError): render.views({"render": [dict(name="a", view="sideways")]})
        with self.assertRaises(ValueError): render.views({"render": [dict(name="a", view="front", angle=[1, 2, 3])]})
    def test_two_views_of_the_same_thing_are_reported(self):
        m = dict(model="model.scad", render=[dict(name="a", part="assembly"), dict(name="b", part="assembly"), dict(name="c", part="assembly", view="front")])
        r = {x["name"]: x for x in render.render(self.f, m, [self.fake])}
        self.assertEqual((r["a"]["same_as"], r["b"]["same_as"], r["c"]["same_as"]), ("", "a", ""))
    def test_it_draws_every_view_into_renders(self):
        m = dict(model="model.scad", render=[dict(name="a", part="assembly"), dict(name="b", part="exploded", angle=[1, 2, 3])])
        r = render.render(self.f, m, [self.fake])
        self.assertTrue(all(x["ok"] for x in r)); self.assertEqual(sorted(os.listdir(os.path.join(self.f, "renders"))), ["a.png", "b.png"])
        self.assertEqual([t for t, _ in render.list_renders(self.f, m)], ["a", "b"])
    def test_a_failed_drawing_keeps_the_old_picture(self):
        m = dict(model="model.scad", render=[dict(name="a", part="assembly")]); render.render(self.f, m, [self.fake])
        before = open(os.path.join(self.f, "renders", "a.png"), "rb").read()
        r = render.render(self.f, dict(m, render=[dict(name="a", part="BREAK")]), [self.fake])
        self.assertFalse(r[0]["ok"]); self.assertEqual(open(os.path.join(self.f, "renders", "a.png"), "rb").read(), before)
        self.assertFalse(any(n.endswith(".part.png") for n in os.listdir(os.path.join(self.f, "renders"))))
    def test_a_model_outside_the_project_is_refused(self):
        for bad in ("/etc/passwd", "../x.scad"):
            with self.assertRaises(ValueError): render.render(self.f, dict(model=bad), [self.fake])
    def test_missing_openscad_is_explained(self):
        r = render.render(self.f, dict(model="model.scad"), ["/no/such/openscad"])
        self.assertFalse(r[0]["ok"]); self.assertIn("not installed", r[0]["error"])

class Pages(unittest.TestCase):
    def test_gallery_route_and_draw_again(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "p"); project.init(f, "Pic Test"); open(os.path.join(f, "model.scad"), "w").write("cube(1);")
            with open(os.path.join(f, "fit2print.toml"), "a") as fh: fh.write('model = "model.scad"\n')
            fake = os.path.join(d, "openscad"); open(fake, "w").write(FAKE.format(py=sys.executable)); os.chmod(fake, 0o755)
            srv = server.make_server(dict(projects=[f], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0, render_command=[fake]); port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            def call(m, p, body=None, h=None):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request(m, p, body=body, headers=h or {}); r = c.getresponse(); return r.status, r.read()
            self.assertIn(b"What it should look like", call("GET", "/p/pic-test")[1])
            self.assertEqual(call("POST", "/p/pic-test/render", b"go=1", {"Content-Type": "application/x-www-form-urlencoded"})[0], 200)
            for _ in range(100):
                st = json.loads(call("GET", "/p/pic-test/render/status")[1])
                if not st["running"]: break
                time.sleep(0.1)
            self.assertEqual(st["error"], "")
            s, img = call("GET", "/p/pic-test/renders/assembled.png"); self.assertEqual((s, img[:4]), (200, b"\x89PNG"))
            for bad in ("/p/pic-test/renders/..%2Ffit2print.toml", "/p/pic-test/renders/x.txt", "/p/pic-test/renders/nope.png"):
                self.assertEqual(call("GET", bad)[0], 404, bad)
            srv.shutdown(); srv.server_close()

if __name__ == "__main__":
    unittest.main()
