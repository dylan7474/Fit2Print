import http.client, json, os, tempfile, threading, time, unittest
from fit2print import checkview, project, records, server


class Rows(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "View Test")
        open(os.path.join(self.f, "model.scad"), "w").write("cube(1);")
        self.m = dict(model="model.scad")
    def tearDown(self): self.d.cleanup()
    def touch(self, name): open(os.path.join(self.f, name), "w").write("")
    def test_no_config_files_means_no_card(self):
        self.assertEqual(checkview.card("p", self.f, self.m), "")
    def test_a_configured_check_that_never_ran_says_so_and_shows_the_command(self):
        self.touch("checks.toml")
        r = checkview.rows(self.f, self.m)
        self.assertEqual(r[0]["state"], "never"); self.assertEqual(r[0]["command"], "fit2print assembly-check .")
        self.assertIn("NOT RUN", checkview.card("p", self.f, self.m))
    def test_a_passing_run_is_clear_and_a_failing_one_is_not(self):
        self.touch("checks.toml"); self.touch("selftest.toml")
        records.append(self.f, "assembly-check", True, cases=10, failed=0)
        records.append(self.f, "selftest", False, passed=11, failed=1, skipped=0)
        by = {x["title"].split(" (")[0]: x for x in checkview.rows(self.f, self.m)}
        self.assertEqual(by["Virtual build"]["state"], "ok"); self.assertEqual(by["Self-test"]["state"], "fail")
        self.assertIn("FAILED", by["Self-test"]["text"]); self.assertIsNotNone(by["Self-test"]["command"])
    def test_a_pass_older_than_the_model_is_stale_not_clear(self):          # NEGATIVE CONTROL: a green tick for a design that has changed is a lie
        self.touch("checks.toml")
        records.append(self.f, "assembly-check", True, cases=3)
        later = time.time() + 3600
        os.utime(os.path.join(self.f, "model.scad"), (later, later))
        r = checkview.rows(self.f, self.m)[0]
        self.assertEqual(r["state"], "stale"); self.assertIn("run it again", r["text"])
    def test_an_old_record_without_exact_seconds_still_reads(self):
        self.touch("checks.toml")
        with open(os.path.join(self.f, "records", "checks.jsonl"), "a") as fh:
            fh.write(json.dumps(dict(at="2020-01-01 10:00", check="assembly-check", ok=True, cases=2)) + "\n")
        self.assertEqual(checkview.rows(self.f, self.m)[0]["state"], "stale")           # the model is newer than a 2020 record
    def test_the_newest_run_wins_so_a_later_failure_shows(self):
        self.touch("checks.toml")
        records.append(self.f, "assembly-check", True, cases=3)
        records.append(self.f, "assembly-check", False, cases=3, failed=1)
        self.assertEqual(checkview.rows(self.f, self.m)[0]["state"], "fail")
    def test_splits_are_listed_with_their_warnings_and_html_is_escaped(self):
        os.makedirs(os.path.join(self.f, "sections"))
        json.dump(dict(base="<b>front</b>", ok=False, summary="4 sections", cuts=[dict(joint="keys")], pins=dict(count=0), warnings=["<script>x</script> thin walls"]),
                  open(os.path.join(self.f, "sections", "front_split.json"), "w"))
        open(os.path.join(self.f, "sections", "bad_split.json"), "w").write("{nope")
        h = checkview.card("p", self.f, self.m)
        self.assertIn("FAILED", h); self.assertIn("joints: keys", h); self.assertIn("unreadable", h)
        self.assertNotIn("<script>", h); self.assertNotIn("<b>front</b>", h)


class Page(unittest.TestCase):
    def test_the_project_page_shows_the_card(self):
        with tempfile.TemporaryDirectory() as root:
            f = os.path.join(root, "p1"); project.init(f, "Card Test"); open(os.path.join(f, "checks.toml"), "w").write("")
            records.append(f, "assembly-check", True, cases=5)
            srv = server.make_server(dict(projects=[f], new_projects_dir=os.path.join(root, "new")), "127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                c = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=10); c.request("GET", "/p/card-test")
                r = c.getresponse(); t = r.read().decode()
                self.assertEqual(r.status, 200); self.assertIn("<h3>Checks</h3>", t); self.assertIn("Virtual build", t)
            finally:
                srv.shutdown(); srv.server_close()
