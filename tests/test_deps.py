import unittest
from fit2print import deps

class Deps(unittest.TestCase):
    def test_a_program_that_is_on_the_path_but_will_not_run_is_reported_missing(self):   # NEGATIVE CONTROL for the doctor
        spec = {"program": [{"name": "false", "verify": ["false"], "why": "always fails"}]}
        row = deps.probe(spec)[0]
        self.assertFalse(row["found"], "doctor said a broken tool was fine")
        self.assertIn("will not run", row["why"])
    def test_a_working_program_is_found(self):
        spec = {"program": [{"name": "true", "verify": ["true"], "why": "always works"}]}
        self.assertTrue(deps.probe(spec)[0]["found"])
    def test_an_absent_program_is_absent(self):
        self.assertFalse(deps.probe({"program": [{"name": "no-such-tool-xyz"}]})[0]["found"])

if __name__ == "__main__":
    unittest.main()
