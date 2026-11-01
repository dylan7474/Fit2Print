import http.client, io, json, os, tempfile, threading, unittest, urllib.parse, zipfile
from fit2print import downloads, project, server


class Downloads(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); root = self.d.name
        self.f = os.path.join(root, "p1"); project.init(self.f, "Down Test")
        for rel, data in (("plates/part_a.3mf", b"3MFDATA-A"), ("plates/part_b.3mf", b"3MFDATA-B"), ("plates/part_a_report.html", b"<html><script>alert(1)</script>REPORT</html>"),
                          ("stl/body.stl", b"solid body"), ("stl/body.part.stl", b"half-written"), ("coupons/c1.stl", b"solid c"), ("sections/front_s01.stl", b"solid s"),
                          ("GATE.md", b"# gate"), ("brief.md", b"SECRET BRIEF"), ("records/plates.jsonl", b"{}\n"), (".env", b"TOKEN=nope"), ("plates/bad$name.3mf", b"x"),
                          ("plates/notes.txt", b"not listed")):
            p = os.path.join(self.f, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(data)
        outside = os.path.join(root, "outside.3mf"); open(outside, "wb").write(b"OUTSIDE SECRET")
        os.symlink(outside, os.path.join(self.f, "plates", "link.3mf"))
        open(os.path.join(self.f, "records", "plates.jsonl"), "w").write(json.dumps(dict(file="plates/part_a.3mf", part="part_a", verdict="PASS", minutes=61, grams=40)) + "\n")
        self.srv = server.make_server(dict(projects=[self.f], new_projects_dir=os.path.join(root, "n")), "127.0.0.1", 0)
        self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def get(self, path):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10); c.request("GET", path); r = c.getresponse(); data = r.read(); c.close(); return r, data
    def test_the_list_has_the_right_files_and_nothing_else(self):
        names = {e["rel"] for e in downloads.collect(self.f, project_marker(self.f))}
        self.assertEqual(names, {"plates/part_a.3mf", "plates/part_b.3mf", "plates/part_a_report.html", "stl/body.stl", "coupons/c1.stl", "sections/front_s01.stl", "GATE.md"})
    def test_a_print_file_downloads_as_an_attachment_with_its_bytes(self):
        r, data = self.get("/p/down-test/dl/plates/part_a.3mf")
        self.assertEqual(r.status, 200); self.assertEqual(data, b"3MFDATA-A")
        self.assertIn('attachment; filename="part_a.3mf"', r.getheader("Content-Disposition")); self.assertIn("3dmodel", r.getheader("Content-Type"))
    def test_nothing_unlisted_can_be_fetched_whatever_the_url_says(self):           # NEGATIVE CONTROLS
        for bad in ("/p/down-test/dl/brief.md", "/p/down-test/dl/fit2print.toml", "/p/down-test/dl/records/plates.jsonl", "/p/down-test/dl/.env", "/p/down-test/dl/plates/notes.txt",
                    "/p/down-test/dl/stl/body.part.stl", "/p/down-test/dl/plates/bad$name.3mf", "/p/down-test/dl/plates/link.3mf",
                    "/p/down-test/dl/../brief.md", "/p/down-test/dl/plates/../brief.md", "/p/down-test/dl/%2e%2e/brief.md", "/p/down-test/dl/plates%2f..%2f..%2fbrief.md",
                    "/p/down-test/dl//etc/passwd", "/p/down-test/dl/%2Fetc%2Fpasswd", "/p/down-test/dl/plates/", "/p/down-test/dl/"):
            r, data = self.get(bad)
            self.assertIn(r.status, (404, 400), bad); self.assertNotIn(b"SECRET", data, bad); self.assertNotIn(b"TOKEN=", data, bad); self.assertNotIn(b"root:", data, bad)
    def test_a_symlink_that_leaves_the_project_is_never_listed_or_served(self):
        self.assertNotIn("plates/link.3mf", {e["rel"] for e in downloads.collect(self.f, project_marker(self.f))})
        r, data = self.get("/p/down-test/dl/plates/link.3mf"); self.assertEqual(r.status, 404); self.assertNotIn(b"OUTSIDE", data)
    def test_an_unknown_project_is_a_404(self):
        self.assertEqual(self.get("/p/nope/dl/plates/part_a.3mf")[0].status, 404); self.assertEqual(self.get("/p/nope/files")[0].status, 404)
    def test_the_files_page_lists_and_labels_them_and_links_the_zips(self):
        r, data = self.get("/p/down-test/files"); t = data.decode()
        self.assertEqual(r.status, 200)
        for s in ("part_a.3mf", "part_b.3mf", "body.stl", "c1.stl", "front_s01.stl", "GATE.md", "PASS 61 min 40 g", "download.zip?set=print", "download.zip?set=all"):
            self.assertIn(s, t)
        for s in ("brief.md", "bad$name", "notes.txt", "link.3mf", "body.part"):
            self.assertNotIn(s, t)
    def test_the_project_page_has_a_downloads_card_even_with_no_files(self):
        r, data = self.get("/p/down-test"); self.assertEqual(r.status, 200); self.assertIn("<h3>Downloads</h3>", data.decode()); self.assertIn("All print files (zip)", data.decode())
        g = tempfile.mkdtemp(); project.init(os.path.join(g, "q"), "Empty Down")
        srv = server.make_server(dict(projects=[os.path.join(g, "q")], new_projects_dir=g), "127.0.0.1", 0); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10); c.request("GET", "/p/empty-down"); t = c.getresponse().read().decode()
            self.assertIn("Nothing to download yet", t)
        finally:
            srv.shutdown(); srv.server_close()
    def test_zips_hold_the_right_set_and_nothing_else(self):
        def names(q):
            r, data = self.get(q); self.assertEqual(r.status, 200); self.assertEqual(r.getheader("Content-Type"), "application/zip")
            return sorted(zipfile.ZipFile(io.BytesIO(data)).namelist()), data
        n, data = names("/p/down-test/download.zip?set=print"); self.assertEqual(n, ["plates/part_a.3mf", "plates/part_b.3mf"])
        self.assertEqual(zipfile.ZipFile(io.BytesIO(data)).read("plates/part_a.3mf"), b"3MFDATA-A")
        n, _ = names("/p/down-test/download.zip?set=all"); self.assertNotIn("brief.md", n); self.assertNotIn("records/plates.jsonl", n); self.assertNotIn("plates/link.3mf", n); self.assertEqual(len(n), 7)
        self.assertEqual(self.get("/p/down-test/download.zip?set=bogus")[0].status, 404)
    def test_a_zip_over_the_limit_is_refused_with_the_reason(self):
        old = downloads.MAX_ZIP; downloads.MAX_ZIP = 5
        try:
            r, data = self.get("/p/down-test/download.zip?set=print"); self.assertEqual(r.status, 413); self.assertIn(b"too big", data)
        finally:
            downloads.MAX_ZIP = old
    def test_a_report_can_be_viewed_but_only_locked_down_and_is_otherwise_a_download(self):
        r, data = self.get("/p/down-test/dl/plates/part_a_report.html?view=1")
        self.assertEqual(r.status, 200); self.assertIn(b"REPORT", data)
        csp = [v for k, v in r.getheaders() if k.lower() == "content-security-policy"]
        self.assertTrue(any("sandbox" in c and "default-src 'none'" in c for c in csp))
        r2, _ = self.get("/p/down-test/dl/plates/part_a_report.html"); self.assertIn("attachment", r2.getheader("Content-Disposition"))


def project_marker(folder):
    from fit2print.cli import read_marker
    return read_marker(folder)
