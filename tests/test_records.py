import json, os
from fit2print import records


def test_lines_are_appended_never_rewritten_and_latest_is_the_newest(tmp_path):
    f = str(tmp_path)
    records.append(f, "assembly-check", False, cases=10, failed=2)
    records.append(f, "assembly-check", True, cases=10, failed=0)
    records.append(f, "selftest", True, passed=12)
    h = records.history(f)
    assert len(h) == 3 and h[0]["ok"] is False and h[1]["ok"] is True      # the earlier failure is still there
    assert records.latest(f)["assembly-check"]["failed"] == 0 and records.latest(f)["selftest"]["passed"] == 12
    assert records.history(f, "selftest")[0]["check"] == "selftest"


def test_a_torn_line_is_skipped_not_fatal(tmp_path):
    f = str(tmp_path); records.append(f, "x", True)
    with open(os.path.join(f, "records", "checks.jsonl"), "a") as fh:
        fh.write("{not json\n")
    records.append(f, "y", True)
    assert [r["check"] for r in records.history(f)] == ["x", "y"]


def test_no_file_is_an_empty_history(tmp_path):
    assert records.history(str(tmp_path)) == [] and records.latest(str(tmp_path)) == {}
