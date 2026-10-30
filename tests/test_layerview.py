import http.client, json, os, tempfile, threading, time, unittest
from fit2print import layerview, project, server
from test_toolpath import plate as synthetic_plate

class Viewer(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "View Test")
        os.makedirs(os.path.join(self.f, "plates"))
        with open(os.path.join(self.f, "plates", "tee.gcode"), "w") as fh:
            fh.write("\n".join(synthetic_plate(28)))                                    # the overhanging-shelf plate from the toolpath tests
        self.srv = server.make_server(dict(projects=[self.f], new_projects_dir=os.path.join(self.d.name, "n")), "127.0.0.1", 0)
        self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def get(self, p):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20); c.request("GET", p); r = c.getresponse(); return r.status, r.read().decode()
    def test_plates_are_found_and_listed_on_the_project_page(self):
        self.assertIn("tee", layerview.discover(self.f, {}))
        self.assertIn("Layer preview", self.get("/p/view-test")[1])
    def test_meta_and_layers(self):
        s, t = self.get("/p/view-test/plate/tee/meta.json"); m = json.loads(t)
        self.assertEqual(s, 200); self.assertEqual(m["layers"], 6); self.assertEqual(m["bounds"][0], -0.0 if m["bounds"][0] == 0 else m["bounds"][0])
        s, t = self.get("/p/view-test/plate/tee/layer/5.json"); d = json.loads(t)
        self.assertEqual(s, 200); self.assertIn("Outer wall", d["features"]); self.assertGreater(len(d["features"]["Outer wall"][0]), 20)
    def test_the_hanging_shelf_is_marked_on_its_own_layer(self):      # the point of the overlay
        self.get("/p/view-test/plate/tee/meta.json")
        for _ in range(100):
            s, t = self.get("/p/view-test/plate/tee/problems.json"); pr = json.loads(t)
            if pr["state"] in ("done", "failed"): break
            time.sleep(0.1)
        self.assertEqual(pr["state"], "done")
        zs = {z: v for z, v in pr["by_z"].items() if v["cant"] or v["bridge"]}
        self.assertTrue(zs, "the shelf was not marked"); self.assertIn("1.2", zs)                    # the layer the shelf starts on
        self.assertFalse(pr["by_z"].get("0.6", {"cant": [], "bridge": []})["cant"])                 # and not the layers below it
    def test_unknown_plates_layers_and_odd_names_are_404(self):
        for p in ("/p/view-test/plate/nope/meta.json", "/p/view-test/plate/tee/layer/999.json", "/p/view-test/plate/..%2F..%2Fx/meta.json", "/p/view-test/plate/TEE"):
            self.assertEqual(self.get(p)[0], 404, p)
    def test_the_viewer_page_loads(self):
        s, t = self.get("/p/view-test/plate/tee"); self.assertEqual(s, 200); self.assertIn("<canvas", t); self.assertIn("hanging plastic", t)
    def test_a_plate_is_found_only_inside_known_places(self):          # NEGATIVE CONTROL: the page cannot name an arbitrary file
        open(os.path.join(self.d.name, "secret.gcode"), "w").write("G1 X1 Y1 E1")
        self.assertNotIn("secret", layerview.discover(self.f, {}))
        self.assertEqual(self.get("/p/view-test/plate/secret/meta.json")[0], 404)

if __name__ == "__main__":
    unittest.main()
