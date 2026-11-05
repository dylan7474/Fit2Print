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
        self.assertIn("href='#archived'", t); self.assertIn("id=archived", t)      # a visible link at the top that opens the list
        self.assertEqual(self.act("restore"), 303); self.assertNotIn("Archived projects", self.call("GET", "/")[1]); self.assertNotIn("#archived", self.call("GET", "/")[1])
    def test_the_project_page_has_an_archive_button_until_it_is_archived(self):
        self.assertIn("value=archive", self.call("GET", "/p/arch-test")[1])                  # the button on an active project
        self.act("archive"); t = self.call("GET", "/p/arch-test")[1]; self.assertNotIn("value=archive>", t); self.assertIn("value=restore", t)
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

class Delete(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.nd = os.path.join(self.d.name, "n"); os.makedirs(self.nd)
        self.f = os.path.join(self.nd, "gone-test"); project.init(self.f, "Gone Test")
        self.other = os.path.join(self.nd, "keeper"); project.init(self.other, "Keeper")
        self.laptop = os.path.join(self.d.name, "laptop-proj"); project.init(self.laptop, "Laptop Proj")
        self.srv = server.make_server(dict(projects=[self.laptop], new_projects_dir=self.nd), "127.0.0.1", 0); self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def call(self, m, p, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(m, p, body=body, headers={"Content-Type": "application/x-www-form-urlencoded"} if body else {}); r = c.getresponse(); return r.status, r.read().decode()
    def arch(self, pid="gone-test"): self.call("POST", f"/p/{pid}/archive", b"action=archive")
    def rm(self, pid, typed): return self.call("POST", f"/p/{pid}/delete", urllib.parse.urlencode(dict(confirm=typed)).encode())
    def test_an_archived_project_is_deleted_after_typing_its_name_and_only_it(self):
        self.arch(); self.assertIn("Delete for good", self.call("GET", "/")[1]); self.assertIn("Delete for good", self.call("GET", "/p/gone-test")[1])
        s, t = self.call("GET", "/p/gone-test/delete"); self.assertEqual(s, 200); self.assertIn("cannot be undone", t)
        s, _ = self.rm("gone-test", "Gone Test"); self.assertEqual(s, 303)
        self.assertFalse(os.path.exists(self.f)); self.assertTrue(os.path.exists(self.other)); self.assertEqual(self.call("GET", "/p/gone-test")[0], 404)
        self.assertNotIn("/p/gone-test", self.call("GET", "/")[1])
    def test_a_wrong_name_deletes_nothing(self):                    # NEGATIVE CONTROL
        self.arch()
        for typed in ("", "gone", "Keeper", " "):
            self.assertEqual(self.rm("gone-test", typed)[0], 400); self.assertTrue(os.path.exists(self.f))
    def test_an_active_project_cannot_be_deleted(self):             # NEGATIVE CONTROL
        self.assertEqual(self.rm("gone-test", "Gone Test")[0], 400); self.assertTrue(os.path.exists(self.f))
        self.assertEqual(self.call("GET", "/p/gone-test/delete")[0], 403); self.assertNotIn("Delete for good", self.call("GET", "/p/gone-test")[1])
    def test_a_project_outside_the_projects_folder_cannot_be_deleted(self):     # NEGATIVE CONTROL: the laptop's own folders
        self.arch("laptop-proj"); self.assertEqual(self.rm("laptop-proj", "Laptop Proj")[0], 400); self.assertTrue(os.path.exists(self.laptop))
        self.assertNotIn("Delete for good", self.call("GET", "/p/laptop-proj")[1])
    def test_the_radio_and_samples_cannot_be_deleted(self):          # NEGATIVE CONTROL
        for kind, key, val in (("radio", "adapter", "phonosphere"), ("smp", "kind", "sample")):
            f = os.path.join(self.nd, kind); project.init(f, kind.title()); fp = os.path.join(f, "fit2print.toml"); m = open(fp).read()
            m = m.replace('adapter = "generic"', 'adapter = "phonosphere"') if key == "adapter" else m.replace('kind = "design-and-print"', 'kind = "sample"')
            open(fp, "w").write(m); archive.record(f, "archive")
            self.assertEqual(self.rm(kind, kind.title())[0], 400); self.assertTrue(os.path.exists(f), kind)
    def test_a_symlinked_project_is_not_followed(self):               # NEGATIVE CONTROL: never delete what a link points at
        real = os.path.join(self.d.name, "real"); project.init(real, "Linked"); link = os.path.join(self.nd, "linked"); os.symlink(real, link); archive.record(real, "archive")
        self.assertTrue(archive.why_not_deletable(link, dict(id="linked", name="Linked"), self.nd)); self.assertTrue(os.path.exists(real))

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
