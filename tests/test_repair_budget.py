from mind3.core.driver import REPAIR_MAX_CHANGED_LINE_RATIO, _repair_diff_stats


def test_repair_diff_stats_is_deterministic() -> None:
    before = "module x;\n  assign y = a;\nendmodule\n"
    after = "module x;\n  assign y = b;\nendmodule\n"
    stats = _repair_diff_stats(before, after)
    assert stats["changed_lines"] == 2
    assert stats["before_lines"] == 3
    assert stats["after_lines"] == 3
    assert stats["changed_line_ratio"] == 2 / 3
    assert REPAIR_MAX_CHANGED_LINE_RATIO < 1.0
