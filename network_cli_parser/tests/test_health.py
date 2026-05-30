import pytest
from utils.health import (
    _parse_duration, _apply_condition, _resolve_path,
    evaluate_checks, merge_checks, _format_print,
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


# ---------------------------------------------------------------------------
# Plan 10: Compound conditions
# ---------------------------------------------------------------------------

def _snap(cmd_key, parsed_data):
    return {
        "metadata": {"hostname": "TEST"},
        "commands": {cmd_key: {"parsed": parsed_data}},
    }


class TestOneOf:
    def test_value_in_list_passes(self):
        snap = _snap("show_interfaces", [{"status": "up"}])
        checks = [{"name": "c", "command": "show_interfaces",
                   "path": "[*].status", "condition": "one_of",
                   "value": ["up", "connected"]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_value_not_in_list_fails(self):
        snap = _snap("show_interfaces", [{"status": "down"}])
        checks = [{"name": "c", "command": "show_interfaces",
                   "path": "[*].status", "condition": "one_of",
                   "value": ["up", "connected"]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"

    def test_not_one_of_passes_when_absent(self):
        snap = _snap("show_interfaces", [{"desc": "ACCESS"}])
        checks = [{"name": "c", "command": "show_interfaces",
                   "path": "[*].desc", "condition": "not_one_of",
                   "value": ["DECOM", "DECOMMISSIONED"]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_not_one_of_fails_when_present(self):
        snap = _snap("show_interfaces", [{"desc": "DECOM"}])
        checks = [{"name": "c", "command": "show_interfaces",
                   "path": "[*].desc", "condition": "not_one_of",
                   "value": ["DECOM", "DECOMMISSIONED"]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"

    def test_non_list_value_returns_false(self):
        ok, msg = _apply_condition("up", "one_of", "up")
        assert ok is False
        assert "requires a list" in msg

    def test_not_one_of_non_list_returns_false(self):
        ok, msg = _apply_condition("up", "not_one_of", "up")
        assert ok is False
        assert "requires a list" in msg


class TestAndConditions:
    def test_both_pass(self):
        snap = _snap("show_bgp", [{"prefixes": 500}])
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].prefixes",
                   "conditions": [
                       {"condition": "gte", "value": 1},
                       {"condition": "lte", "value": 1000},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_first_fails(self):
        snap = _snap("show_bgp", [{"prefixes": 0}])
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].prefixes",
                   "conditions": [
                       {"condition": "gte", "value": 1},
                       {"condition": "lte", "value": 1000},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"
        assert len(r["results"][0]["failures"][0]["messages"]) == 1

    def test_second_fails(self):
        snap = _snap("show_bgp", [{"prefixes": 9999}])
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].prefixes",
                   "conditions": [
                       {"condition": "gte", "value": 1},
                       {"condition": "lte", "value": 1000},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"

    def test_both_fail_shows_both_messages(self):
        snap = _snap("show_bgp", [{"prefixes": -1}])
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].prefixes",
                   "conditions": [
                       {"condition": "gte", "value": 1},
                       {"condition": "lte", "value": -2},  # -1 is NOT <= -2
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"
        assert len(r["results"][0]["failures"][0]["messages"]) == 2

    def test_match_any_with_and_conditions(self):
        snap = _snap("show_bgp", [{"prefixes": 500}, {"prefixes": 0}])
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].prefixes",
                   "match": "any",
                   "conditions": [
                       {"condition": "gte", "value": 1},
                       {"condition": "lte", "value": 1000},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"


class TestBranches:
    def _make_snap(self, rows):
        return _snap("show_interfaces", rows)

    def test_when_match_then_applied_pass(self):
        snap = self._make_snap([{"type": "loopback", "mtu": 65535}])
        checks = [{"name": "c", "command": "show_interfaces", "path": "[*]",
                   "branches": [
                       {"when": {"field": "type", "condition": "eq", "value": "loopback"},
                        "then": {"field": "mtu", "condition": "eq", "value": 65535}},
                       {"default": {"field": "mtu", "condition": "eq", "value": 9216}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_when_match_then_applied_fail(self):
        snap = self._make_snap([{"type": "loopback", "mtu": 1500}])
        checks = [{"name": "c", "command": "show_interfaces", "path": "[*]",
                   "branches": [
                       {"when": {"field": "type", "condition": "eq", "value": "loopback"},
                        "then": {"field": "mtu", "condition": "eq", "value": 65535}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"

    def test_default_fires_when_no_when_matches(self):
        snap = self._make_snap([{"type": "ethernet", "mtu": 9216}])
        checks = [{"name": "c", "command": "show_interfaces", "path": "[*]",
                   "branches": [
                       {"when": {"field": "type", "condition": "eq", "value": "loopback"},
                        "then": {"field": "mtu", "condition": "eq", "value": 65535}},
                       {"default": {"field": "mtu", "condition": "eq", "value": 9216}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_no_match_no_default_vacuously_passes(self):
        snap = self._make_snap([{"type": "unknown", "mtu": 1}])
        checks = [{"name": "c", "command": "show_interfaces", "path": "[*]",
                   "branches": [
                       {"when": {"field": "type", "condition": "eq", "value": "loopback"},
                        "then": {"field": "mtu", "condition": "eq", "value": 65535}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_non_dict_row_fails(self):
        snap = _snap("show_bgp", ["scalar_not_dict"])
        checks = [{"name": "c", "command": "show_bgp", "path": "[*]",
                   "branches": [
                       {"when": {"field": "x", "condition": "eq", "value": 1},
                        "then": {"field": "y", "condition": "eq", "value": 1}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"

    def test_mixed_rows_multiple_when(self):
        snap = self._make_snap([
            {"type": "loopback", "mtu": 65535},
            {"type": "Ethernet", "mtu": 9216},
        ])
        checks = [{"name": "c", "command": "show_interfaces", "path": "[*]",
                   "branches": [
                       {"when": {"field": "type", "condition": "eq", "value": "loopback"},
                        "then": {"field": "mtu", "condition": "eq", "value": 65535}},
                       {"when": {"field": "type", "condition": "eq", "value": "Ethernet"},
                        "then": {"field": "mtu", "condition": "eq", "value": 9216}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"


class TestPrintField:
    def test_print_true_adds_printed_to_result(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version",
                   "path": "[*].version", "condition": "matches",
                   "value": "17\\..*", "print": True}]
        r = evaluate_checks(snap, checks)
        res = r["results"][0]
        assert res["status"] == "pass"
        assert "printed" in res
        assert "17.3.1" in res["printed"][0]

    def test_print_template_substitutes_value(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version",
                   "path": "[*].version", "condition": "eq",
                   "value": "17.3.1", "print": "OS version is {value}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["printed"][0] == "OS version is 17.3.1"

    def test_print_on_fail_also_present(self):
        snap = _snap("show_version", [{"version": "16.0"}])
        checks = [{"name": "c", "command": "show_version",
                   "path": "[*].version", "condition": "eq",
                   "value": "17.3.1", "print": "Got: {value}"}]
        r = evaluate_checks(snap, checks)
        res = r["results"][0]
        assert res["status"] == "fail"
        assert res["printed"][0] == "Got: 16.0"

    def test_print_with_and_conditions(self):
        snap = _snap("show_bgp", [{"prefixes": 500}])
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].prefixes",
                   "conditions": [{"condition": "gte", "value": 1}],
                   "print": "Prefixes: {value}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["printed"][0] == "Prefixes: 500"

    def test_print_with_branches(self):
        snap = _snap("show_interfaces", [{"type": "loopback", "mtu": 65535}])
        checks = [{"name": "c", "command": "show_interfaces", "path": "[*]",
                   "print": "MTU is {value}",
                   "branches": [
                       {"when": {"field": "type", "condition": "eq", "value": "loopback"},
                        "then": {"field": "mtu", "condition": "eq", "value": 65535}},
                   ]}]
        r = evaluate_checks(snap, checks)
        assert "MTU is 65535" in r["results"][0]["printed"][0]

    def test_no_print_field_no_printed_key(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version",
                   "path": "[*].version", "condition": "eq", "value": "17.3.1"}]
        r = evaluate_checks(snap, checks)
        assert "printed" not in r["results"][0]


class TestPrintTemplate:
    """Tests for {{[*]}} wildcard key capture and double-brace template syntax."""

    def _run(self, data, path, template):
        """Resolve path against data and format each result with the template."""
        results = _resolve_path(data, path)
        return [_format_print(template, rp, val) for rp, val in results]

    def test_single_wildcard_key(self):
        data = {"GETVPN-P2P": {"10.2.240.1": {"state": "REDUNDANT"}}}
        lines = self._run(data, "GETVPN-P2P[*].state", "Peer {{[*]}} has state {{value}}")
        assert lines == ["Peer 10.2.240.1 has state REDUNDANT"]

    def test_double_wildcard_indexed(self):
        data = {"vrfs": {"default": {"neighbors": {"10.0.0.1": {"prefix_count": 42}}}}}
        lines = self._run(
            data,
            "vrfs[*].neighbors[*].prefix_count",
            "VRF {{[*][0]}} neighbor {{[*][1]}} has {{value}} prefixes",
        )
        assert lines == ["VRF default neighbor 10.0.0.1 has 42 prefixes"]

    def test_double_brace_value_same_as_single(self):
        data = [{"version": "17.3.1"}]
        lines_double = self._run(data, "[0].version", "Version: {{value}}")
        lines_single = self._run(data, "[0].version", "Version: {value}")
        assert lines_double == lines_single == ["Version: 17.3.1"]

    def test_backward_compat_single_brace(self):
        data = [{"hostname": "N9K-1"}]
        lines = self._run(data, "[0].hostname", "Host is {value}")
        assert lines == ["Host is N9K-1"]

    def test_no_wildcard_key_empty_string(self):
        # Path with no bracket segments — {{[*]}} substitutes empty string
        data = {"version": "17.3"}
        lines = self._run(data, "version", "Node {{[*]}} ver {{value}}")
        assert lines == ["Node  ver 17.3"]

    def test_list_index_in_bracket(self):
        # [*] over a list → bracket key is the numeric index
        data = [{"version": "17.3"}]
        lines = self._run(data, "[*].version", "Item {{[*]}} ver {{value}}")
        assert lines == ["Item 0 ver 17.3"]

    def test_out_of_range_index_empty_string(self):
        # {{[*][5]}} when only one bracket key exists → empty string, no crash
        data = {"peers": {"10.0.0.1": {"uptime": "5d"}}}
        lines = self._run(data, "peers[*].uptime", "{{[*][5]}}")
        assert lines == [""]

    def test_print_true_fallback(self):
        data = [{"state": "up"}]
        lines = self._run(data, "[0].state", True)
        assert lines == ["[0].state -> 'up'"]

    def test_via_evaluate_checks_single_wildcard(self):
        snap = _snap("show_crypto", {"10.2.240.1": {"state": "REDUNDANT"}})
        checks = [{"name": "c", "command": "show_crypto",
                   "path": "[*].state",
                   "condition": "eq", "value": "REDUNDANT",
                   "print": "Peer {{[*]}} → {{value}}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"
        assert r["results"][0]["printed"] == ["Peer 10.2.240.1 → REDUNDANT"]
