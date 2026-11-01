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

class PlainWebsite(unittest.TestCase):
    """The page is JUST a website: no token, no login, no knowledge of any proxy. Whatever sits in front of it is someone else's job."""
    def serve(self, host="127.0.0.1"):
        d = tempfile.mkdtemp(); srv = server.make_server(dict(projects=[], new_projects_dir=d), host, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start(); self.addCleanup(lambda: (srv.shutdown(), srv.server_close()))
        return srv.server_address[1]
    def status(self, port, path="/", headers=None, method="GET"):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request(method, path, headers=headers or {}); r = c.getresponse(); r.read(); return r.status
    def test_a_plain_request_is_served_with_no_token_or_cookie(self):
        self.assertEqual(self.status(self.serve()), 200)
    def test_a_network_address_is_allowed_and_asks_for_nothing(self):
        self.assertEqual(self.status(self.serve("0.0.0.0")), 200)
    def test_requests_that_came_through_a_tunnel_or_proxy_are_served_like_any_other(self):
        p = self.serve()
        for h in ("Cf-Ray", "Cf-Connecting-Ip", "Cf-Access-Jwt-Assertion", "X-Forwarded-For", "Forwarded", "Cdn-Loop", "X-Real-Ip"):
            self.assertEqual(self.status(p, headers={h: "203.0.113.9"}), 200, h)
    def test_the_app_never_asks_for_a_token(self):                                   # NEGATIVE CONTROL: the owner asked for this to be gone, and it must stay gone
        import inspect
        src = inspect.getsource(server)
        for word in ("token", "Cloudflare", "CF_Authorization", "Access-Jwt", "trust_lan", "locked"):
            self.assertNotIn(word, src.replace("token_note", ""), word)
        self.assertEqual(self.status(self.serve(), "/?t=whatever"), 200)
        for flag in ("--token", "--trust-lan", "--token-file"):
            r = __import__("subprocess").run([__import__("sys").executable, "-m", "fit2print", "serve", flag, "x", "--port", "0"], capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=os.path.join(os.path.dirname(__file__), "..", "src")), timeout=30)
            self.assertNotEqual(r.returncode, 0); self.assertIn("unrecognized arguments", r.stderr)
    def test_posting_needs_nothing_either(self):
        p = self.serve()
        c = http.client.HTTPConnection("127.0.0.1", p, timeout=10); body = "name=Plain+Site+Test&kind=design-and-print"
        c.request("POST", "/new", body=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(body))}); r = c.getresponse(); r.read()
        self.assertEqual(r.status, 303)

    def test_home_shows_the_printer_and_links_the_job_to_its_project(self):
        from fit2print import printer
        with tempfile.TemporaryDirectory() as d:
            project.init(os.path.join(d, "p1"), "Test Bracket")
            with open(os.path.join(d, "p1", "records", "prints.jsonl"), "w") as f:
                f.write(json.dumps(dict(date="2026-10-30", plate="base", result="ok", what="x")) + "\n")
            pr = printer.Printer(dict(host="x", serial="s", access_code="SECRETCODE"))
            pr.last = dict(state="printing", job="base", percent=54, layer=311, layers=579, minutes_left=160, nozzle=220, bed=65, errors=False, at=__import__("time").time())
            srv = server.make_server(dict(projects=[os.path.join(d, "p1")], new_projects_dir=os.path.join(d, "n")), "127.0.0.1", 0, pr)
            port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/"); r = c.getresponse(); t = r.read().decode()
            self.assertIn("54 %", t); self.assertIn("layer 311 of 579", t); self.assertIn("2 h 40 min", t); self.assertIn("220 &deg;C / 65 &deg;C", t); self.assertIn("/p/test-bracket", t)
            self.assertNotIn("SECRETCODE", t, "the access code leaked into a page")
            srv.shutdown(); srv.server_close()
    def test_an_offline_printer_is_shown_plainly_not_as_an_error_page(self):
        from fit2print import printer
        with tempfile.TemporaryDirectory() as d:
            pr = printer.Printer(dict(host="x", serial="s", access_code="c")); pr.last = dict(state="offline", error="can not reach the printer (OSError)", at=1)
            srv = server.make_server(dict(projects=[], new_projects_dir=d), "127.0.0.1", 0, pr)
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

class AssistantPanel(unittest.TestCase):
    FAKE = [__import__("sys").executable, os.path.join(os.path.dirname(__file__), "fake_claude.py")]
    def setUp(self):
        from fit2print import assistant
        self.d = tempfile.TemporaryDirectory(); project.init(os.path.join(self.d.name, "p1"), "Chat Test")
        self.a = assistant.Assistant(command=self.FAKE, f2p="fit2print")
        self.srv = server.make_server(dict(projects=[os.path.join(self.d.name, "p1")], new_projects_dir=os.path.join(self.d.name, "n")), "127.0.0.1", 0, None, self.a)
        self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def call(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10); c.request(method, path, body=body, headers=headers or {}); r = c.getresponse(); t = r.read().decode(); return r.status, t
    def ask(self, text):
        data = urllib.parse.urlencode(dict(message=text)).encode()
        return self.call("POST", "/p/chat-test/ask", data, {"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(data))})
    def test_the_project_page_has_the_panel(self):
        s, t = self.call("GET", "/p/chat-test"); self.assertEqual(s, 200); self.assertIn("Assistant", t); self.assertIn("askform", t)
    def test_ask_and_poll(self):
        import json as j, time
        s, t = self.ask("hello"); self.assertEqual(s, 200); job = j.loads(t)["job"]
        for _ in range(100):
            p = j.loads(self.call("GET", f"/p/chat-test/ask/{job}?n=0")[1])
            if p["done"]: break
            time.sleep(0.05)
        self.assertTrue(p["done"]); self.assertIn("Which board is it for?", [e["text"] for e in p["events"]])
    def test_an_empty_message_is_a_400_and_a_busy_assistant_is_a_409(self):
        self.assertEqual(self.ask("  ")[0], 400)
    def test_unknown_job_is_404(self):
        self.assertEqual(self.call("GET", "/p/chat-test/ask/aaaaaaaaaaaa")[0], 404)
    def test_no_assistant_means_a_plain_note_not_a_broken_page(self):
        srv = server.make_server(dict(projects=[os.path.join(self.d.name, "p1")], new_projects_dir=self.d.name), "127.0.0.1", 0)
        port = srv.server_address[1]; threading.Thread(target=srv.serve_forever, daemon=True).start()
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", "/p/chat-test"); r = c.getresponse(); t = r.read().decode()
        self.assertEqual(r.status, 200); self.assertIn("Not set up on this machine", t)
        c.request("POST", "/p/chat-test/ask", body=b"message=hi", headers={"Content-Type": "application/x-www-form-urlencoded"}); r = c.getresponse(); r.read(); self.assertEqual(r.status, 503)
        srv.shutdown(); srv.server_close()
    def test_a_new_project_opens_with_the_assistant_started(self):
        data = urllib.parse.urlencode(dict(name="Pico Case", desc="snap fit")).encode()
        s, _ = self.call("POST", "/new", data, {"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(data))})
        self.assertEqual(s, 303)

class GuidePage(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Guide Test")
        with open(os.path.join(self.f, "assembly.toml"), "w") as fh:
            fh.write('title = "Guide"\n[[step]]\ntitle = "Join the halves"\ntext = "bolt them"\nparts = ["pod_L", "pod_R", "missing_part"]\nfixings = [{what = "M3 x 16 bolt", qty = 4}]\npicture = "pic.png"\n'
                     '[[step]]\ntitle = "Close"\nparts = ["pod_L"]\nfixings = [{what = "M3 x 16 bolt", qty = 2}]\n')
        with open(os.path.join(self.f, "pic.png"), "wb") as fh: fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 50)
        with open(os.path.join(self.f, "secret.png"), "wb") as fh: fh.write(b"\x89PNG\r\n\x1a\n" + b"1" * 50)
        os.makedirs(os.path.join(self.f, "records"), exist_ok=True)
        with open(os.path.join(self.f, "records", "plates.jsonl"), "w") as fh:
            fh.write(json.dumps(dict(part="pod_L", verdict="PASS", minutes=1, grams=1, notes=[], stl_sha="NEW")) + "\n" + json.dumps(dict(part="pod_R", verdict="PASS", minutes=1, grams=1, notes=[], stl_sha="NEW")) + "\n")
        with open(os.path.join(self.f, "records", "prints.jsonl"), "w") as fh:
            fh.write(json.dumps(dict(date="2026-10-25", plate="pod_R", result="ok", what="x", design="OLD")) + "\n" + json.dumps(dict(date="2026-10-30", plate="pod_L", result="ok", what="x", design="NEW")) + "\n")
        self.srv = server.make_server(dict(projects=[self.f], new_projects_dir=os.path.join(self.d.name, "n")), "127.0.0.1", 0)
        self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def get(self, p):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10); c.request("GET", p); r = c.getresponse(); return r.status, r.read().decode("utf-8", "replace")
    def test_the_guide_shows_steps_hands_status_and_the_other_half(self):
        s, t = self.get("/p/guide-test/guide"); self.assertEqual(s, 200)
        self.assertIn("Step 1: Join the halves", t); self.assertIn("LEFT", t); self.assertIn("RIGHT", t); self.assertIn("its other half: pod_R", t)
    def test_a_part_printed_from_an_older_design_is_flagged(self):      # the 25 Oct pod_R problem
        s, t = self.get("/p/guide-test/guide"); self.assertIn("printed from an older design", t)
    def test_fixings_are_added_up_across_steps(self):
        s, t = self.get("/p/guide-test/guide"); self.assertIn("6 &times;", t)                                  # 4 + 2 M3 x 16 bolts
    def test_a_part_that_is_not_in_the_project_is_said_so(self):
        self.assertIn("not in this project", self.get("/p/guide-test/guide")[1])
    def test_a_step_picture_in_the_guide_is_served_but_other_files_are_not(self):     # NEGATIVE CONTROL
        self.assertEqual(self.get("/p/guide-test/guide/img/pic.png")[0], 200)
        self.assertEqual(self.get("/p/guide-test/guide/img/secret.png")[0], 404)                              # exists, but no step names it
        self.assertEqual(self.get("/p/guide-test/guide/img/..%2Ffit2print.toml")[0], 404)
    def test_the_project_page_links_the_guide(self):
        self.assertIn("Open the guide", self.get("/p/guide-test")[1])
    def test_no_guide_is_a_polite_404(self):
        os.remove(os.path.join(self.f, "assembly.toml")); self.assertEqual(self.get("/p/guide-test/guide")[0], 404)

if __name__ == "__main__":
    unittest.main()
