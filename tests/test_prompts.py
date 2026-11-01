import re, unittest
from fit2print import cli, stage


def subcommands():
    import argparse
    p = argparse.ArgumentParser()
    # build the real parser the way main() does by asking it for help of an unknown command: parse_known_args on --help is awkward, so read the choices
    parser = cli.build_parser() if hasattr(cli, "build_parser") else None
    if parser is None:
        import inspect
        src = inspect.getsource(cli)
        return set(re.findall(r's\.add_parser\("([a-z-]+)"', src))
    return {a for act in parser._actions if hasattr(act, "choices") and act.choices for a in act.choices}


class Prompts(unittest.TestCase):
    def test_every_command_the_assistant_is_told_to_run_exists(self):        # a prompt naming a command that is gone wastes the person's money
        cmds = subcommands()
        named = set()
        for stage_name, text in stage.WORK.items():
            for m in re.finditer(r"`\{f2p\} ([a-z-]+)", text):
                named.add(m.group(1))
                self.assertIn(m.group(1), cmds, f"stage {stage_name} tells the assistant to run '{m.group(1)}' which is not a command")
        self.assertTrue({"export", "split", "assembly-check", "selftest", "register", "plate", "coupon", "calibrate", "gate", "render"} <= named,
                        f"the stage prompts no longer mention: {sorted({'export','split','assembly-check','selftest','register','plate','coupon','calibrate','gate','render'} - named)}")
    def test_the_playbook_covers_every_workflow_command(self):
        for path in ("docs/PLAYBOOK.md", "templates/project/PLAYBOOK.md"):
            text = open(path).read()
            for c in ("export", "split", "assembly-check", "selftest", "register", "plate", "coupon", "calibrate", "gate", "report"):
                self.assertIn(f"fit2print {c}" if c != "report" else "--report", text, f"{path} does not teach '{c}'")
    def test_gate_is_the_last_thing_the_plate_stage_asks_for(self):
        self.assertTrue(stage.WORK["plate"].rstrip().endswith("is never a pass."))
    def test_the_pronoun_and_ask_first_rules_are_untouched_by_the_edit(self):
        self.assertIn("Do not run the checks or slice yet.", stage.WORK["model"]); self.assertIn("wait for the person to say the plates look right", stage.WORK["plate"])
