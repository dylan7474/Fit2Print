import json, os, sys, tempfile, time, unittest
from fit2print import assistant, project

FAKE = [sys.executable, os.path.join(os.path.dirname(__file__), "fake_claude.py")]

def wait(a, job, timeout=10):
    n, events, end = 0, [], time.time() + timeout
    while time.time() < end:
        r = a.poll(job, n); events += r["events"]; n = r["next"]
        if r["done"]:
            return events
        time.sleep(0.05)
    raise AssertionError("the assistant never finished")

class Assist(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory(); self.f = os.path.join(self.d.name, "p"); project.init(self.f, "Assist Test")
        self.log = os.path.join(self.d.name, "args.log"); os.environ["FAKE_CLAUDE_LOG"] = self.log
        self.a = assistant.Assistant(command=FAKE, model="sonnet", budget_usd=0.5, f2p="fit2print")
    def tearDown(self):
        os.environ.pop("FAKE_CLAUDE_LOG", None); self.d.cleanup()
    def args(self):
        with open(self.log) as f:
            return [json.loads(l) for l in f]
    def test_a_message_gets_an_answer_and_is_remembered(self):
        ev = wait(self.a, self.a.start("p", self.f, "Assist Test", "hello"))
        self.assertEqual([e["kind"] for e in ev], ["tool", "text", "done"]); self.assertIn("reading brief.md", ev[0]["text"])
        h = self.a.history(self.f); self.assertEqual([x["role"] for x in h], ["you", "assistant"])
    def test_the_command_is_locked_down(self):                # the safety rules, checked on the real command line
        wait(self.a, self.a.start("p", self.f, "Assist Test", "hello"))
        c = self.args()[0]
        self.assertEqual(c[c.index("--permission-mode") + 1], "dontAsk")                     # anything not allowed is denied, never asked
        allowed = c[c.index("--allowedTools") + 1:c.index("--max-budget-usd")]
        self.assertEqual(allowed, ["Read", "Glob", "Grep", "Write", "Edit", "WebFetch", "WebSearch", "Bash(fit2print:*)"])     # the web to read, but no free Bash
        self.assertNotIn("Bash", allowed)                                                    # NEGATIVE CONTROL: a bare Bash would let it run anything
        self.assertFalse([x for x in allowed if x in ("Task", "Agent", "NotebookEdit", "mcp__")])
        self.assertIn("--max-budget-usd", c); self.assertIn("--max-turns", c)
    def test_it_runs_in_the_project_folder_and_can_write_there(self):
        wait(self.a, self.a.start("p", self.f, "Assist Test", "WRITE please"))
        self.assertIn("written by the fake assistant", open(os.path.join(self.f, "brief.md")).read())
    def test_the_conversation_continues_with_the_same_session(self):
        wait(self.a, self.a.start("p", self.f, "Assist Test", "one")); wait(self.a, self.a.start("p", self.f, "Assist Test", "two"))
        first, second = self.args()
        self.assertIn("--session-id", first); self.assertIn("--resume", second); self.assertEqual(second[second.index("--resume") + 1], "S1")
    def test_a_crash_is_reported_not_raised(self):            # NEGATIVE CONTROL
        ev = wait(self.a, self.a.start("p", self.f, "Assist Test", "CRASH"))
        self.assertEqual(ev[-1]["kind"], "error"); self.assertIn("boom", ev[-1]["text"])
    def test_an_error_result_is_reported(self):
        self.assertEqual(wait(self.a, self.a.start("p", self.f, "Assist Test", "ERRORRESULT"))[-1]["kind"], "error")
    def test_claude_not_installed_is_explained(self):
        a = assistant.Assistant(command=["/no/such/claude"])
        self.assertIn("not installed", wait(a, a.start("p", self.f, "Assist Test", "hi"))[-1]["text"])
    def test_only_one_question_at_a_time_per_project(self):
        job = self.a.start("p", self.f, "Assist Test", "hello")
        with self.assertRaises(RuntimeError):
            self.a.start("p", self.f, "Assist Test", "again")
        wait(self.a, job)
    def test_an_empty_message_is_refused(self):
        with self.assertRaises(ValueError):
            self.a.start("p", self.f, "Assist Test", "   ")
    def test_the_template_playbook_matches_the_docs(self):    # a project gets the same playbook the docs hold
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "PLAYBOOK.md")) as a, open(os.path.join(root, "templates", "project", "PLAYBOOK.md")) as b:
            self.assertEqual(a.read(), b.read())
        self.assertTrue(os.path.exists(os.path.join(self.f, "PLAYBOOK.md")))

if __name__ == "__main__":
    unittest.main()
