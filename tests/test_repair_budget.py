from mind3.core.driver import REPAIR_MAX_CHANGED_LINE_RATIO, _repair_diff_stats, _rtl_identity_hash


def test_repair_diff_stats_is_deterministic() -> None:
    before = "module x;\n  assign y = a;\nendmodule\n"
    after = "module x;\n  assign y = b;\nendmodule\n"
    stats = _repair_diff_stats(before, after)
    assert stats["changed_lines"] == 2
    assert stats["before_lines"] == 3
    assert stats["after_lines"] == 3
    assert stats["changed_line_ratio"] == 2 / 3
    assert REPAIR_MAX_CHANGED_LINE_RATIO < 1.0


def test_rtl_identity_hash_ignores_only_line_endings_and_trailing_whitespace() -> None:
    source = "module x;\r\n  assign y = a;   \r\nendmodule\r\n"
    equivalent_formatting = "module x;\n  assign y = a;\nendmodule"
    changed_behavior = "module x;\n  assign y = ~a;\nendmodule"

    assert _rtl_identity_hash(source) == _rtl_identity_hash(equivalent_formatting)
    assert _rtl_identity_hash(source) != _rtl_identity_hash(changed_behavior)
