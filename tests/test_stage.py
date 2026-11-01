import http.client, json, os, tempfile, threading, unittest, urllib.parse
from fit2print import assistant, project, server, stage
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from test_assistant import FAKE, wait

class Stages(unittest.TestCase):
    def setUp(self): self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Stage Test")
    def tearDown(self): self.d.cleanup()
    def test_a_new_project_starts_in_scope(self): self.assertEqual(stage.current(self.f), "scope")
    def test_the_person_moves_it_one_stage_at_a_time_and_it_is_logged(self):
        stage.move(self.f, "concept"); stage.move(self.f, "model")
        self.assertEqual(stage.current(self.f), "model"); self.assertEqual([e["to"] for e in stage.history(self.f)], ["concept", "model"])
    def test_it_cannot_skip_a_stage(self):                      # NEGATIVE CONTROL: no jumping from scope straight to printing
        with self.assertRaises(ValueError): stage.move(self.f, "print")
        with self.assertRaises(ValueError): stage.move(self.f, "model")
        self.assertEqual(stage.current(self.f), "scope")
    def test_it_can_go_back_one_but_not_before_the_start(self):
        stage.move(self.f, "concept"); stage.move(self.f, "scope"); self.assertEqual(stage.current(self.f), "scope")
        with self.assertRaises(ValueError): stage.move(self.f, "plate")
    def test_an_established_project_with_prints_starts_in_print(self):
        os.makedirs(os.path.join(self.f, "records"), exist_ok=True)
        with open(os.path.join(self.f, "records", "prints.jsonl"), "w") as fh: fh.write(json.dumps(dict(plate="x", result="ok", what="y", date="d")) + "\n")
        self.assertEqual(stage.current(self.f), "print")
    def test_every_stage_has_work_instructions_and_every_gate_a_start_message(self):
        for k in stage.KEYS: self.assertIn(k, stage.WORK)
        for k in stage.KEYS[:-1]: self.assertIn(k, stage.GATE)
        for k in stage.KEYS[1:]: self.assertIn(k, stage.START)

class AssistantKnowsTheStage(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Assist Test")
        self.log = os.path.join(self.d.name, "a.log"); os.environ["FAKE_CLAUDE_LOG"] = self.log
        self.a = assistant.Assistant(command=FAKE, f2p="fit2print")
    def tearDown(self): os.environ.pop("FAKE_CLAUDE_LOG", None); self.d.cleanup()
    def prompt(self):
        with open(self.log) as fh: c = json.loads(fh.readline())
        return c[c.index("--append-system-prompt") + 1]
    def test_in_scope_it_is_told_not_to_design(self):
        wait(self.a, self.a.start("p", self.f, "Assist Test", "hello", "scope"))
        p = self.prompt(); self.assertIn("SCOPE STAGE", p); self.assertIn("Do NOT design", p); self.assertIn("press the button", p)
    def test_the_stage_is_also_in_the_message_so_a_resumed_conversation_cannot_miss_it(self):   # the dice-test-2 bug
        wait(self.a, self.a.start("p", self.f, "Assist Test", "go", "concept"))
        with open(self.log) as fh: c = json.loads(fh.readline())
        sent = c[c.index("-p") + 1]
        self.assertIn("CONCEPT stage RIGHT NOW", sent); self.assertIn("go", sent)
        self.assertEqual([h["text"] for h in self.a.history(self.f) if h["role"] == "you"], ["go"])       # the person's own words are what is remembered and shown
    def test_in_concept_it_is_told_to_draw(self):
        wait(self.a, self.a.start("p", self.f, "Assist Test", "hello", "concept"))
        p = self.prompt(); self.assertIn("CONCEPT STAGE", p); self.assertIn("model.scad", p)
    def test_the_assistant_cannot_change_who_the_project_is(self):        # NEGATIVE CONTROL
        ev = wait(self.a, self.a.start("p", self.f, "Assist Test", "TAMPER", "scope"))
        self.assertIn('id = "assist-test"', open(os.path.join(self.f, "fit2print.toml")).read())
        self.assertTrue(any("identity" in e["text"] for e in ev if e["kind"] == "error"))

class Button(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Button Test")
        self.srv = server.make_server(dict(projects=[self.f], new_projects_dir=os.path.join(self.d.name, "n")), "127.0.0.1", 0, None, assistant.Assistant(command=FAKE))
        self.port = self.srv.server_address[1]; threading.Thread(target=self.srv.serve_forever, daemon=True).start()
    def tearDown(self): self.srv.shutdown(); self.srv.server_close(); self.d.cleanup()
    def post(self, to):
        d = urllib.parse.urlencode(dict(to=to)).encode(); c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("POST", "/p/button-test/stage", d, {"Content-Type": "application/x-www-form-urlencoded", "Content-Length": str(len(d))}); r = c.getresponse(); return r.status, r.read().decode()
    def test_the_page_shows_the_stage_and_the_gate_button(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10); c.request("GET", "/p/button-test"); t = c.getresponse().read().decode()
        self.assertIn("Stage: Scope", t); self.assertIn("The brief is complete: start the design", t)
    def test_pressing_it_moves_to_concept_and_tells_the_assistant_to_start(self):
        s, t = self.post("concept"); d = json.loads(t)
        self.assertEqual((s, d["stage"]), (200, "concept")); self.assertIn("concept", d["start"].lower()); self.assertEqual(stage.current(self.f), "concept")
    def test_skipping_a_stage_is_refused(self):
        self.assertEqual(self.post("print")[0], 400); self.assertEqual(stage.current(self.f), "scope")

if __name__ == "__main__":
    unittest.main()
