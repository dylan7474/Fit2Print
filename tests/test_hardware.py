import http.client, os, tempfile, threading, unittest, urllib.parse
from fit2print import hardware, project, server

class Library(unittest.TestCase):
    def test_the_shipped_entries_load_and_every_number_has_a_basis_and_a_source(self):
        lib = hardware.load_all([hardware.shipped_dir()])
        self.assertIn("pi-zero-2-w", lib)
        for e in lib.values():
            for k, d in e["dim"].items():
                self.assertIn(d["basis"], hardware.BASES, k)
                if d["basis"] != "derived": self.assertTrue(d.get("source"), f"{e['id']}.{k} has no source")
    def test_a_dimension_with_no_source_is_refused(self):     # NEGATIVE CONTROL: never an unsourced number
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "x.toml"), "w").write('id = "x"\n[dim.a]\nvalue = 5\nunit = "mm"\nbasis = "official"\n')
            with self.assertRaises(ValueError): hardware.load_all([d])
    def test_a_basis_must_be_one_of_the_known_ones(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "x.toml"), "w").write('id = "x"\n[dim.a]\nvalue = 5\nbasis = "memory"\nsource = "I remember"\n')
            with self.assertRaises(ValueError): hardware.load_all([d])
    def test_the_official_pi_numbers_are_the_drawings(self):
        e = hardware.load_all([hardware.shipped_dir()])["pi-zero-2-w"]["dim"]
        self.assertEqual((e["length"]["value"], e["width"]["value"], e["hole_inset"]["value"]), (65.0, 30.0, 3.5))
        self.assertEqual((e["port_hdmi_x"]["value"], e["port_usb_data_x"]["value"], e["port_usb_power_x"]["value"]), (12.4, 41.4, 54.0))
        self.assertEqual(e["board_thickness"]["basis"], "estimate")            # the numbers the drawing does NOT give are honestly labelled
    def test_a_measurement_goes_in_the_users_folder_and_beats_the_published_value(self):
        with tempfile.TemporaryDirectory() as u:
            lib = hardware.load_all([hardware.shipped_dir()])
            hardware.verify("pi-zero-2-w", "header_height_above_board", 8.7, "callipers", user_dir=u, library=lib)
            merged = hardware.load_all([hardware.shipped_dir(), u])["pi-zero-2-w"]["dim"]["header_height_above_board"]
            self.assertEqual(hardware.value(merged), 8.7); self.assertTrue(hardware.is_verified(merged))
            self.assertEqual(lib["pi-zero-2-w"]["dim"]["header_height_above_board"]["value"], 9.0)      # the shipped library is untouched
            self.assertNotIn("header_height_above_board", hardware.unverified(hardware.load_all([hardware.shipped_dir(), u])["pi-zero-2-w"]))
    def test_a_silly_measurement_is_refused(self):
        with tempfile.TemporaryDirectory() as u, self.assertRaises(ValueError):
            hardware.verify("pi-zero-2-w", "length", -5, user_dir=u, library=hardware.load_all([hardware.shipped_dir()]))
    def test_openscad_export_uses_the_measurement_and_says_what_is_unverified(self):
        with tempfile.TemporaryDirectory() as u:
            lib = hardware.load_all([hardware.shipped_dir()])
            hardware.verify("pi-zero-2-w", "length", 65.2, user_dir=u, library=lib)
            t = hardware.openscad(hardware.load_all([hardware.shipped_dir(), u])["pi-zero-2-w"])
            self.assertIn("pi_zero_2_w_length = 65.2;", t); self.assertIn("MEASURED by you", t); self.assertIn("UNVERIFIED (estimate)", t)

class Pages(unittest.TestCase):
    def test_components_pages_and_the_measure_form(self):
        with tempfile.TemporaryDirectory() as d:
            srv = server.make_server(dict(projects=[], new_projects_dir=d), "127.0.0.1", 0); port = srv.server_address[1]
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            def get(p):
                c = http.client.HTTPConnection("127.0.0.1", port, timeout=10); c.request("GET", p); r = c.getresponse(); return r.status, r.read().decode()
            s, t = get("/hardware"); self.assertEqual(s, 200); self.assertIn("Raspberry Pi Zero 2 W", t)
            s, t = get("/hardware/pi-zero-2-w"); self.assertEqual(s, 200); self.assertIn("I measured it", t); self.assertIn("official mechanical drawing", t)
            self.assertEqual(get("/hardware/nope")[0], 404); self.assertEqual(get("/hardware/..%2Fetc")[0], 404)
            srv.shutdown(); srv.server_close()

class NeedsYou(unittest.TestCase):
    def test_a_project_that_uses_a_component_asks_you_to_measure_it(self):
        from fit2print.adapters import generic
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "p"); project.init(f, "Hw Test")
            need = generic.load(f, dict(name="Hw Test", hardware=["pi-zero-2-w", "not-in-the-library"]))["open_items"]
            self.assertTrue(any("measure the Raspberry Pi Zero 2 W" in n for n in need)); self.assertTrue(any("not in the component library" in n for n in need))

if __name__ == "__main__":
    unittest.main()
