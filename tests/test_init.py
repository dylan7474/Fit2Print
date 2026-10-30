import os, tempfile, unittest
from fit2print import cli, project

class Init(unittest.TestCase):
    def test_creates_a_project_the_tool_accepts(self):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "case")
            pid, _ = project.init(f, "Pi Zero Case")
            self.assertEqual(pid, "pi-zero-case")
            m = cli.read_marker(f)
            self.assertEqual(m["id"], "pi-zero-case")
            for name in ("brief.md", "NEXT.md", "CLAUDE.md"):
                self.assertTrue(os.path.exists(os.path.join(f, name)), name)
            self.assertIn("Pi Zero Case", open(os.path.join(f, "brief.md")).read())
    def test_refuses_a_folder_with_files_in_it(self):   # NEGATIVE CONTROL: projects are never mixed with other files
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "something.txt"), "w").write("x")
            with self.assertRaises(SystemExit):
                project.init(d, "Anything")
            self.assertEqual(os.listdir(d), ["something.txt"])
    def test_a_name_with_no_letters_is_refused(self):
        with self.assertRaises(SystemExit):
            project.slug("!!!")

if __name__ == "__main__":
    unittest.main()
