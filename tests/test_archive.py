import http.client, os, tempfile, threading, unittest, urllib.parse
from fit2print import archive, dashboard, project, server

class Archive(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Arch Test")
        self.srv = server.make_server(dict(projects=[self.f], new_projects_dir=os.path.join(self.d.name, "n")), "127.0.0.1", 0); self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def call(self, m, p, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(m, p, body=body, headers={"Content-Type": "application/x-www-form-urlencoded"} if body else {}); r = c.getresponse(); return r.status, r.read().decode()
    def act(self, a): return self.call("POST", "/p/arch-test/archive", urllib.parse.urlencode(dict(action=a)).encode())[0]
    def test_archiving_hides_it_from_home_and_restore_brings_it_back(self):
        self.assertIn("Arch Test", self.call("GET", "/")[1]); self.assertEqual(self.act("archive"), 303)
        t = self.call("GET", "/")[1]; self.assertIn("Archived projects (1)", t); self.assertIn("Restore", t)
        self.assertEqual(self.act("restore"), 303); self.assertNotIn("Archived projects", self.call("GET", "/")[1])
    def test_nothing_is_deleted(self):
        self.act("archive"); self.assertTrue(os.path.exists(os.path.join(self.f, "brief.md"))); self.assertEqual(self.call("GET", "/p/arch-test")[0], 200)
        self.assertIn("This project is archived", self.call("GET", "/p/arch-test")[1])
    def test_a_silly_action_is_refused(self):                  # NEGATIVE CONTROL
        self.assertEqual(self.act("delete"), 400); self.assertFalse(archive.is_archived(self.f))
    def test_the_newest_event_decides(self):
        archive.record(self.f, "archive"); archive.record(self.f, "restore"); self.assertFalse(archive.is_archived(self.f))
    def test_the_radio_cannot_be_archived_from_the_page(self):        # NEGATIVE CONTROL
        rf = os.path.join(self.d.name, "radio"); project.init(rf, "Radio")
        with open(os.path.join(rf, "fit2print.toml")) as fh: m = fh.read().replace('adapter = "generic"', 'adapter = "phonosphere"')
        with open(os.path.join(rf, "fit2print.toml"), "w") as fh: fh.write(m)
        srv = server.make_server(dict(projects=[rf], new_projects_dir=os.path.join(self.d.name, "n2")), "127.0.0.1", 0); port = srv.server_address[1]
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("POST", "/p/radio/archive", body=b"action=archive", headers={"Content-Type": "application/x-www-form-urlencoded"})
        r = c.getresponse(); r.read(); self.assertEqual(r.status, 400); self.assertFalse(archive.is_archived(rf)); srv.shutdown(); srv.server_close()

class Labels(unittest.TestCase):
    def test_a_generic_project_does_not_say_the_radio(self):
        proj = dict(name="Dice", subtitle="", parts=[], groups=[], runs=[], prints=[], open_items=[], photos=[])
        self.assertNotIn("in the radio", dashboard.render(proj)); self.assertIn("parts in this project", dashboard.render(proj))

class Sketches(unittest.TestCase):
    def test_concept_sketches_are_shown_and_served_safely(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "p"); project.init(f, "Sketch Test"); os.makedirs(os.path.join(f, "concept"))
            open(os.path.join(f, "concept", "c1.svg"), "w").write("<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"); open(os.path.join(f, "secret.txt"), "w").write("s")
            srv = server.make_server(dict(projects=[f], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0); port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
            def get(p):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", p); r = c.getresponse(); return r.status, r.getheader("Content-Security-Policy"), r.read().decode()
            self.assertIn("sketch: c1.svg", get("/p/sketch-test")[2])
            s, csp, _ = get("/p/sketch-test/concept/c1.svg"); self.assertEqual(s, 200); self.assertIn("sandbox", csp)                 # an SVG cannot run scripts from our page
            for bad in ("/p/sketch-test/concept/..%2Fsecret.txt", "/p/sketch-test/concept/secret.txt", "/p/sketch-test/concept/x.html"): self.assertEqual(get(bad)[0], 404, bad)
            srv.shutdown(); srv.server_close()

if __name__ == "__main__":
    unittest.main()
