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

import zipfile, numpy as np

def make_3mf(path, item_tf="1 0 0 0 1 0 0 0 1 100 50 0", comp_tf="1 0 0 0 1 0 0 0 1 5 5 2"):
    """A minimal sliced-plate 3MF: one cube-ish tetrahedron object placed by a component transform and a build-item transform."""
    ns = 'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
    main = f'<?xml version="1.0"?><model {ns}><resources><object id="2"><components><component p:path="/3D/Objects/o1.model" objectid="1" transform="{comp_tf}"/></components></object></resources><build><item objectid="2" transform="{item_tf}" printable="1"/></build></model>'
    obj = f'<?xml version="1.0"?><model {ns}><resources><object id="1"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="10" y="0" z="0"/><vertex x="0" y="10" z="0"/><vertex x="0" y="0" z="10"/></vertices><triangles><triangle v1="0" v2="2" v3="1"/><triangle v1="0" v2="1" v3="3"/><triangle v1="0" v2="3" v3="2"/><triangle v1="1" v2="2" v3="3"/></triangles></mesh></object></resources></model>'
    layers = "\n".join(synthetic_plate(20))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3D/3dmodel.model", main); z.writestr("3D/Objects/o1.model", obj); z.writestr("Metadata/plate_1.gcode", layers)

class Mesh(unittest.TestCase):
    def test_the_mesh_is_placed_by_both_transforms_in_bed_coordinates(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.3mf"); make_3mf(p)
            t = layerview.mesh_triangles(p).reshape(-1, 3)
            self.assertEqual(list(t.min(0)), [105, 55, 2]); self.assertEqual(list(t.max(0)), [115, 65, 12])
    def test_a_rotated_item_is_rotated(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.3mf"); make_3mf(p, item_tf="0 1 0 -1 0 0 0 0 1 0 0 0", comp_tf="1 0 0 0 1 0 0 0 1 0 0 0")   # 90 degrees about z
            t = layerview.mesh_triangles(p).reshape(-1, 3)
            self.assertEqual(sorted(t.min(0)), sorted([-10, 0, 0])); self.assertEqual(list(t.max(0)), [0, 10, 10])
    def test_a_gcode_file_has_no_mesh(self):                # NEGATIVE CONTROL
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.gcode"); open(p, "w").write("G1 X1 Y1 E1")
            self.assertIsNone(layerview.mesh_triangles(p))
    def test_the_page_serves_the_mesh_as_float32_triangles_only_when_there_is_one(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "p"); project.init(f, "Mesh Test"); os.makedirs(os.path.join(f, "plates"))
            make_3mf(os.path.join(f, "plates", "tet.3mf")); open(os.path.join(f, "plates", "g.gcode"), "w").write("\n".join(synthetic_plate(20)))
            srv = server.make_server(dict(projects=[f], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0); port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            def get(p):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=20); c.request("GET", p); r = c.getresponse(); return r.status, r.read()
            s, b = get("/p/mesh-test/plate/tet/mesh.bin"); self.assertEqual((s, len(b)), (200, 4 * 3 * 3 * 4))      # 4 triangles x 3 corners x 3 floats x 4 bytes
            self.assertEqual(json.loads(get("/p/mesh-test/plate/tet/meta.json")[1])["mesh"], 4)
            self.assertEqual(get("/p/mesh-test/plate/g/mesh.bin")[0], 404); self.assertEqual(json.loads(get("/p/mesh-test/plate/g/meta.json")[1])["mesh"], 0)
            srv.shutdown(); srv.server_close()

if __name__ == "__main__":
    unittest.main()
