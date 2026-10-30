import http.client, json, os, tempfile, threading, unittest, urllib.parse
from fit2print import project, server

def multipart(fields, files):
    b = "----f2ptest"; out = b""
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    for k, (fn, data) in files.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode() + data + b"\r\n"
    return out + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 200

class Front(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); root = self.d.name
        os.makedirs(os.path.join(root, "stray_folder"))                          # no marker: must not be listed
        project.init(os.path.join(root, "p1"), "Test Bracket")
        self.cfg = dict(projects=[os.path.join(root, "p1"), os.path.join(root, "stray_folder")], new_projects_dir=os.path.join(root, "new"))
        self.srv = server.make_server(self.cfg, "127.0.0.1", 0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse(); data = r.read().decode("utf-8", "replace"); c.close()
        return r.status, data, r
    def test_home_lists_only_marked_projects(self):
        s, t, _ = self.req("GET", "/")
        self.assertEqual(s, 200); self.assertIn("Test Bracket", t); self.assertNotIn("stray_folder", t)
    def test_unknown_or_odd_project_ids_are_404(self):
        for p in ("/p/nope", "/p/..%2F..%2Fetc", "/p/test-bracket/../../x"):
            self.assertIn(self.req("GET", p)[0], (404,))
    def test_project_page_and_log_form(self):
        self.assertEqual(self.req("GET", "/p/test-bracket")[0], 200)
        self.assertEqual(self.req("GET", "/p/test-bracket/log")[0], 200)
    def test_log_a_print_with_a_photo(self):
        body, ct = multipart(dict(part="base", result="ok", what="printed fine"), dict(photo=("x.jpg", JPEG)))
        s, _, r = self.req("POST", "/p/test-bracket/log", body, {"Content-Type": ct, "Content-Length": str(len(body))})
        self.assertEqual(s, 303)
        folder = self.cfg["projects"][0]
        rec = [json.loads(l) for l in open(os.path.join(folder, "records", "prints.jsonl"))]
        self.assertEqual(rec[0]["plate"], "base"); self.assertTrue(os.path.exists(os.path.join(folder, rec[0]["photo"])))
        self.assertIn("base", self.req("GET", "/p/test-bracket")[1])
    def test_a_non_image_upload_is_refused(self):   # NEGATIVE CONTROL: only images may be saved
        body, ct = multipart(dict(part="base", result="ok", what="x"), dict(photo=("evil.jpg", b"#!/bin/sh\nrm -rf ~\n")))
        s, t, _ = self.req("POST", "/p/test-bracket/log", body, {"Content-Type": ct, "Content-Length": str(len(body))})
        self.assertEqual(s, 400); self.assertFalse(os.path.exists(os.path.join(self.cfg["projects"][0], "photos")))
    def test_a_photo_cannot_name_its_own_path(self):
        body, ct = multipart(dict(part="../../escape", result="ok", what="x"), dict(photo=("../../evil.jpg", JPEG)))
        self.req("POST", "/p/test-bracket/log", body, {"Content-Type": ct, "Content-Length": str(len(body))})
        self.assertFalse(os.path.exists(os.path.join(self.d.name, "evil.jpg")))
        saved = os.listdir(os.path.join(self.cfg["projects"][0], "photos"))
        self.assertEqual(len(saved), 1); self.assertNotIn("..", saved[0]); self.assertNotIn("/", saved[0])
    def test_new_project_from_the_form(self):
        data = urllib.parse.urlencode(dict(name="Pico Case", desc="snap fit, desk")).encode()
        s, _, r = self.req("POST", "/new", data, {"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(data))})
        self.assertEqual(s, 303)
        self.assertIn("snap fit, desk", open(os.path.join(self.cfg["new_projects_dir"], "pico-case", "brief.md")).read())
        self.assertIn("Pico Case", self.req("GET", "/")[1])
    def test_a_duplicate_project_name_is_refused(self):
        data = urllib.parse.urlencode(dict(name="Test Bracket")).encode()
        s, _, _ = self.req("POST", "/new", data, {"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(data))})
        self.assertEqual(s, 400)

class Access(unittest.TestCase):
    def test_a_network_address_needs_a_token(self):    # NEGATIVE CONTROL: the page can add files, so it must not be open on the network
        with self.assertRaises(SystemExit):
            server.make_server(dict(projects=[], new_projects_dir="/tmp/none"), "0.0.0.0", 0)
    def test_token_is_required_and_then_remembered(self):
        with tempfile.TemporaryDirectory() as d:
            srv = server.make_server(dict(projects=[], new_projects_dir=d), "127.0.0.1", 0, token="s3cret")
            port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
            def get(path, headers=None):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", path, headers=headers or {}); r = c.getresponse(); r.read(); return r
            self.assertEqual(get("/").status, 401)
            r = get("/?t=s3cret"); self.assertEqual(r.status, 200)
            self.assertEqual(get("/", {"Cookie": "f2p=s3cret"}).status, 200)
            self.assertEqual(get("/", {"Cookie": "f2p=wrong"}).status, 401)
            srv.shutdown(); srv.server_close()

class PrinterPanel(unittest.TestCase):
    def test_home_shows_the_printer_and_links_the_job_to_its_project(self):
        from fit2print import printer
        with tempfile.TemporaryDirectory() as d:
            project.init(os.path.join(d, "p1"), "Test Bracket")
            with open(os.path.join(d, "p1", "records", "prints.jsonl"), "w") as f:
                f.write(json.dumps(dict(date="2026-10-30", plate="base", result="ok", what="x")) + "\n")
            pr = printer.Printer(dict(host="x", serial="s", access_code="SECRETCODE"))
            pr.last = dict(state="printing", job="base", percent=54, layer=311, layers=579, minutes_left=160, nozzle=220, bed=65, errors=False, at=__import__("time").time())
            srv = server.make_server(dict(projects=[os.path.join(d, "p1")], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0, None, pr)
            port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/"); r = c.getresponse(); t = r.read().decode()
            self.assertIn("54 %", t); self.assertIn("layer 311 of 579", t); self.assertIn("2 h 40 min", t); self.assertIn("220 &deg;C / 65 &deg;C", t); self.assertIn("/p/test-bracket", t)
            self.assertNotIn("SECRETCODE", t, "the access code leaked into a page")
            srv.shutdown(); srv.server_close()
    def test_an_offline_printer_is_shown_plainly_not_as_an_error_page(self):
        from fit2print import printer
        with tempfile.TemporaryDirectory() as d:
            pr = printer.Printer(dict(host="x", serial="s", access_code="c")); pr.last = dict(state="offline", error="can not reach the printer (OSError)", at=1)
            srv = server.make_server(dict(projects=[], new_projects_dir=d), "127.0.0.1", 0, None, pr)
            port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/"); r = c.getresponse(); t = r.read().decode()
            self.assertEqual(r.status, 200); self.assertIn("can not reach the printer", t)
            srv.shutdown(); srv.server_close()
    def test_the_frame_route_is_404_when_no_printer_is_set_up(self):
        with tempfile.TemporaryDirectory() as d:
            srv = server.make_server(dict(projects=[], new_projects_dir=d), "127.0.0.1", 0)
            port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/printer/frame.jpg"); r = c.getresponse(); r.read()
            self.assertEqual(r.status, 404); srv.shutdown(); srv.server_close()

if __name__ == "__main__":
    unittest.main()
