import os, tempfile, unittest
from fit2print import cli

class Marker(unittest.TestCase):
    def test_folder_without_marker_is_refused(self):     # NEGATIVE CONTROL: the tool must not guess the project
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as e:
                cli.read_marker(d)
            self.assertIn("refusing to guess", str(e.exception))
    def test_marker_is_read(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "fit2print.toml"), "w").write('id = "x"\nadapter = "generic"\n')
            self.assertEqual(cli.read_marker(d)["id"], "x")

if __name__ == "__main__":
    unittest.main()
