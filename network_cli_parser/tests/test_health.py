import pytest
from utils.health import (
    _parse_duration, _apply_condition, _resolve_path,
    evaluate_checks, merge_checks,
)


class TestParseDuration:
    def test_hh_mm_ss(self):
        assert _parse_duration("00:03:42") == 222.0

    def test_hh_mm(self):
        assert _parse_duration("10:30") == 630.0

    def test_weeks_and_days(self):
        assert _parse_duration("5w2d") == 5 * 604800 + 2 * 86400

    def test_days_and_hours(self):
        assert _parse_duration("2d03h") == 2 * 86400 + 3 * 3600

    def test_all_units(self):
        result = _parse_duration("1y3w2d4h5m6s")
        expected = (365 * 86400) + (3 * 7 * 86400) + (2 * 86400) + (4 * 3600) + (5 * 60) + 6
        assert result == expected

    def test_never_keyword(self):
        assert _parse_duration("never") == 0.0

    def test_na_keyword(self):
        assert _parse_duration("n/a") == 0.0

    def test_dash_keyword(self):
        assert _parse_duration("-") == 0.0

    def test_empty_string(self):
        assert _parse_duration("") == 0.0

    def test_bare_integer(self):
        assert _parse_duration("42") == 42.0

    def test_typo_tolerant(self):
        # extra chars between units are ignored
        assert _parse_duration("2dsay03hour") == 2 * 86400 + 3 * 3600

    def test_long_unit_names(self):
        assert _parse_duration("5week2dday") == 5 * 604800 + 2 * 86400

    def test_case_insensitive(self):
        assert _parse_duration("2D3H") == 2 * 86400 + 3 * 3600

    def test_whitespace_trimmed(self):
        assert _parse_duration("  1h  ") == 3600.0


class TestApplyCondition:
    def test_eq_pass(self):
        ok, _ = _apply_condition("up", "eq", "up")
        assert ok

    def test_eq_fail(self):
        ok, _ = _apply_condition("down", "eq", "up")
        assert not ok

    def test_ne_pass(self):
        ok, _ = _apply_condition("down", "ne", "up")
        assert ok

    def test_ne_fail(self):
        ok, _ = _apply_condition("up", "ne", "up")
        assert not ok

    def test_gt_pass(self):
        ok, _ = _apply_condition(10, "gt", 5)
        assert ok

    def test_gt_fail(self):
        ok, _ = _apply_condition(3, "gt", 5)
        assert not ok

    def test_gte_pass_equal(self):
        ok, _ = _apply_condition(5, "gte", 5)
        assert ok

    def test_lt_pass(self):
        ok, _ = _apply_condition(3, "lt", 5)
        assert ok

    def test_lte_pass(self):
        ok, _ = _apply_condition(5, "lte", 5)
        assert ok

    def test_lte_fail(self):
        ok, _ = _apply_condition(6, "lte", 5)
        assert not ok

    def test_contains_pass(self):
        ok, _ = _apply_condition("hello world", "contains", "world")
        assert ok

    def test_contains_fail(self):
        ok, _ = _apply_condition("hello", "contains", "world")
        assert not ok

    def test_not_contains_pass(self):
        ok, _ = _apply_condition("hello", "not_contains", "world")
        assert ok

    def test_not_contains_fail(self):
        ok, _ = _apply_condition("hello world", "not_contains", "world")
        assert not ok

    def test_matches_pass(self):
        ok, _ = _apply_condition("10.0.0.1", "matches", r"\d+\.\d+\.\d+\.\d+")
        assert ok

    def test_matches_fail(self):
        ok, _ = _apply_condition("not-an-ip", "matches", r"^\d+\.\d+\.\d+\.\d+$")
        assert not ok

    def test_duration_gte_pass(self):
        ok, _ = _apply_condition("3d", "duration_gte", "2d")
        assert ok

    def test_duration_gte_fail(self):
        ok, _ = _apply_condition("1d", "duration_gte", "2d")
        assert not ok

    def test_duration_gt_fail_on_equal(self):
        ok, _ = _apply_condition("2d", "duration_gt", "2d")
        assert not ok

    def test_duration_lte_hh_mm_ss(self):
        # 00:03:42 = 222s <= 600s (10m)
        ok, _ = _apply_condition("00:03:42", "duration_lte", "10m")
        assert ok

    def test_duration_never_vs_gt_zero(self):
        # "never" = 0, not > 0
        ok, _ = _apply_condition("never", "duration_gt", "0s")
        assert not ok

    def test_duration_lt_pass(self):
        ok, _ = _apply_condition("1h", "duration_lt", "1d")
        assert ok

    def test_unknown_condition(self):
        ok, msg = _apply_condition("x", "invalid_op", "y")
        assert not ok
        assert "Unknown condition" in msg

    def test_bad_numeric_value(self):
        ok, msg = _apply_condition("not-a-number", "gt", 5)
        assert not ok
        assert "Condition error" in msg

    def test_invalid_regex_returns_error_not_crash(self):
        ok, msg = _apply_condition("hello", "matches", "[invalid")
        assert not ok
        assert "Condition error" in msg


class TestResolvePath:
    def test_simple_key(self):
        data = {"status": "up"}
        result = _resolve_path(data, "status")
        assert result == [("status", "up")]

    def test_nested_key(self):
        data = {"iface": {"mtu": 9216}}
        result = _resolve_path(data, "iface.mtu")
        assert result == [("iface.mtu", 9216)]

    def test_list_index(self):
        data = [{"name": "eth0"}, {"name": "eth1"}]
        result = _resolve_path(data, "[0].name")
        assert result == [("[0].name", "eth0")]

    def test_wildcard_list(self):
        data = [{"state": "up"}, {"state": "down"}]
        result = _resolve_path(data, "[*].state")
        assert len(result) == 2
        values = [v for _, v in result]
        assert "up" in values
        assert "down" in values

    def test_wildcard_dict(self):
        data = {"vrf1": {"rd": "1:1"}, "vrf2": {"rd": "2:2"}}
        result = _resolve_path(data, "[*].rd")
        assert len(result) == 2
        values = [v for _, v in result]
        assert "1:1" in values
        assert "2:2" in values

    def test_empty_path(self):
        data = {"x": 1}
        result = _resolve_path(data, "")
        assert result == [("", {"x": 1})]

    def test_missing_key_raises(self):
        data = {"a": 1}
        with pytest.raises(KeyError):
            _resolve_path(data, "b")

    def test_type_mismatch_raises(self):
        data = "just a string"
        with pytest.raises(TypeError):
            _resolve_path(data, "key")


class TestEvaluateChecks:
    def _snap(self, cmd_key, parsed, status="parsed"):
        return {
            "metadata": {"hostname": "test-sw"},
            "commands": {
                cmd_key: {"status": status, "raw": "", "parsed": parsed}
            },
        }

    def test_pass_check(self):
        snap = self._snap("show_version", [{"hostname": "SW1"}])
        checks = [{"name": "hn", "command": "show_version", "path": "[0].hostname",
                   "condition": "eq", "value": "SW1"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["passed"] == 1
        assert r["summary"]["failed"] == 0

    def test_fail_check(self):
        snap = self._snap("show_version", [{"hostname": "SW2"}])
        checks = [{"name": "hn", "command": "show_version", "path": "[0].hostname",
                   "condition": "eq", "value": "SW1"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed"] == 1

    def test_missing_command_is_error(self):
        snap = self._snap("show_version", [])
        checks = [{"name": "x", "command": "show_nonexistent", "path": "[0].x",
                   "condition": "eq", "value": "y"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["error"] == 1

    def test_match_any_pass(self):
        snap = self._snap("show_peers", [{"status": "down"}, {"status": "up"}])
        checks = [{"name": "any_up", "command": "show_peers", "path": "[*].status",
                   "condition": "eq", "value": "up", "match": "any"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["passed"] == 1

    def test_match_any_fail_when_none_match(self):
        snap = self._snap("show_peers", [{"status": "down"}, {"status": "down"}])
        checks = [{"name": "any_up", "command": "show_peers", "path": "[*].status",
                   "condition": "eq", "value": "up", "match": "any"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed"] == 1

    def test_match_all_fail_on_one_bad(self):
        snap = self._snap("show_peers", [{"status": "up"}, {"status": "down"}])
        checks = [{"name": "all_up", "command": "show_peers", "path": "[*].status",
                   "condition": "eq", "value": "up"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed"] == 1

    def test_severity_warn_counted_separately(self):
        snap = self._snap("show_version", [{"version": "7.0"}])
        checks = [{"name": "ver", "command": "show_version", "path": "[0].version",
                   "condition": "eq", "value": "8.0", "severity": "warn"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed_warn"] == 1
        assert r["summary"]["failed_critical"] == 0

    def test_severity_critical_default(self):
        snap = self._snap("show_version", [{"version": "7.0"}])
        checks = [{"name": "ver", "command": "show_version", "path": "[0].version",
                   "condition": "eq", "value": "8.0"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed_critical"] == 1

    def test_vacuously_true_empty_list(self):
        snap = self._snap("show_ifaces", [])
        checks = [{"name": "mtu", "command": "show_ifaces", "path": "[*].mtu",
                   "condition": "eq", "value": 9216}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["passed"] == 1

    def test_duration_check_pass(self):
        snap = self._snap("show_bgp", [{"updown": "3d"}])
        checks = [{"name": "bgp_up", "command": "show_bgp", "path": "[0].updown",
                   "condition": "duration_gte", "value": "2d"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["passed"] == 1

    def test_total_count(self):
        snap = self._snap("show_version", [{"x": "a"}])
        checks = [
            {"name": "c1", "command": "show_version", "path": "[0].x", "condition": "eq", "value": "a"},
            {"name": "c2", "command": "show_version", "path": "[0].x", "condition": "eq", "value": "b"},
        ]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["total"] == 2
        assert r["summary"]["passed"] == 1
        assert r["summary"]["failed"] == 1


class TestMergeChecks:
    def test_override_wins_on_name_clash(self):
        default  = [{"name": "check_a", "value": "old"}, {"name": "check_b", "value": "b"}]
        override = [{"name": "check_a", "value": "new"}]
        merged   = merge_checks(default, override)
        by_name  = {c["name"]: c for c in merged}
        assert by_name["check_a"]["value"] == "new"
        assert by_name["check_b"]["value"] == "b"
        assert len(merged) == 2

    def test_additive_when_no_clash(self):
        default  = [{"name": "a"}]
        override = [{"name": "b"}]
        merged   = merge_checks(default, override)
        assert len(merged) == 2

    def test_empty_override(self):
        default = [{"name": "x"}]
        merged  = merge_checks(default, [])
        assert merged == default

    def test_empty_default(self):
        override = [{"name": "x"}]
        merged   = merge_checks([], override)
        assert merged == override

    def test_missing_name_raises(self):
        import pytest
        with pytest.raises(ValueError, match="missing required 'name'"):
            merge_checks([{"value": "x"}], [])
