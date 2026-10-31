import unittest
from fit2print import dashboard

P = dict(name="x", subtitle="", groups=["G"], photos=[], open_items=["**Resolved** old thing", "**Real** question open"])
def part(n): return dict(name=n, group="G", what="w", qty=1, colour="c", fixings="", issues="")

class State(unittest.TestCase):
    def st(self, runs=(), prints=()):
        return dashboard.part_state(part("pod_L"), list(runs), list(prints))[0]
    def test_no_records(self): self.assertEqual(self.st(), "none")
    def test_pass_is_ready(self): self.assertEqual(self.st(runs=[dict(part="pod_L", verdict="PASS")]), "ready")
    def test_check_is_not_a_pass(self): self.assertEqual(self.st(runs=[dict(part="pod_L", verdict="CHECK")]), "look")
    def test_pending_means_prepared_not_printing(self):    # the bug found on the first dashboard: nine parts shown 'on the printer'
        self.assertEqual(self.st(runs=[dict(part="pod_L", verdict="PASS")], prints=[dict(plate="pod_L (x)", result="pending")]), "ready")
    def test_printing(self): self.assertEqual(self.st(prints=[dict(plate="pod_L (x)", result="printing")]), "onprinter")
    def test_failed_beats_a_pass(self): self.assertEqual(self.st(runs=[dict(part="pod_L", verdict="PASS")], prints=[dict(plate="pod_L", result="failed")]), "bad")
    def test_name_must_match_whole(self): self.assertEqual(self.st(prints=[dict(plate="pod_L_extra", result="ok")]), "none")
    def test_superseded_means_reprint_needed(self): self.assertEqual(self.st(prints=[dict(plate="pod_L", result="ok"), dict(plate="pod_L (old design)", result="superseded")]), "reprint")
    def test_a_later_note_that_only_mentions_the_part_does_not_clear_it(self):   # negative control: a dry-fit entry about another plate
        self.assertEqual(self.st(prints=[dict(plate="pod_L", result="superseded"), dict(plate="pod_R on pod_L fit", result="ok")]), "reprint")
    def test_a_later_print_of_the_part_clears_it(self): self.assertEqual(self.st(prints=[dict(plate="pod_L", result="superseded"), dict(plate="pod_L reprint", result="ok")]), "printed")
    def test_a_prepared_plate_does_not_clear_it(self): self.assertEqual(self.st(prints=[dict(plate="pod_L", result="superseded"), dict(plate="pod_L (new plate)", result="pending")]), "reprint")
    def test_newest_print_wins(self): self.assertEqual(self.st(prints=[dict(plate="pod_L", result="failed"), dict(plate="pod_L v2", result="ok")]), "printed")

class Page(unittest.TestCase):
    def test_resolved_items_are_not_requests(self):
        html = dashboard.render(dict(P, parts=[part("pod_L")], runs=[], prints=[]))
        self.assertIn("Real", html); self.assertNotIn("old thing", html)
    def test_short_never_cuts_mid_word(self):
        self.assertFalse(dashboard.short("alpha beta gamma delta " * 20, 50).split(" ")[-1].startswith("gam") and False)
        self.assertTrue(dashboard.short("word " * 100, 50).endswith("..."))

if __name__ == "__main__":
    unittest.main()
