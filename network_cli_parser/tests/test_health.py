import pytest
from datetime import datetime
from utils.health import (
    _parse_duration, _apply_condition, _resolve_path,
    evaluate_checks, merge_checks, _format_print, _parse_date,
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
        results = _resolve_path(data, path)
        return [_format_print(template, p, v) for p, v in results]

    def test_single_wildcard_key(self):
        data = {
            "GETVPN-P2P": {
                "group_id": "65010",
                "10.2.240.1": {"state": "REDUNDANT"},
                "10.2.240.2": {"state": "LOCAL"},
            }
        }
        lines = self._run(data, "GETVPN-P2P[*].state", "Peer {{[*]}} has state {{value}}")
        assert "Peer 10.2.240.1 has state REDUNDANT" in lines
        assert "Peer 10.2.240.2 has state LOCAL" in lines

    def test_double_wildcard_indexed(self):
        data = {
            "vrfs": {
                "default": {"neighbors": {"10.0.1.2": {"prefixes": 1500}}},
            }
        }
        lines = self._run(
            data,
            "vrfs[*].neighbors[*].prefixes",
            "VRF {{[*][0]}} neighbor {{[*][1]}} has {{value}} prefixes",
        )
        assert lines == ["VRF default neighbor 10.0.1.2 has 1500 prefixes"]

    def test_double_brace_value_synonym(self):
        data = {"peers": {"10.0.0.1": {"uptime": "5w2d"}}}
        lines = self._run(data, "peers[*].uptime", "{{value}}")
        assert lines == ["5w2d"]

    def test_backward_compat_single_brace(self):
        data = {"peers": {"10.0.0.1": {"uptime": "5w2d"}}}
        lines = self._run(data, "peers[*].uptime", "{value}")
        assert lines == ["5w2d"]

    def test_no_wildcard_key_in_path(self):
        # Path resolved without any [key] segment — {{[*]}} becomes empty string
        data = {"version": "17.3.1"}
        lines = self._run(data, "version", "Node {{[*]}} ver {{value}}")
        assert lines == ["Node  ver 17.3.1"]

    def test_out_of_range_index_graceful(self):
        data = {"peers": {"10.0.0.1": {"uptime": "1d"}}}
        lines = self._run(data, "peers[*].uptime", "{{[*][5]}}")
        assert lines == [""]

    def test_sibling_field_list_of_dicts(self):
        """{{.field}} fetches another field from the same dict row."""
        data = [
            {"prefix": "10.0.0.0/8", "bgp_neig": "10.2.240.1", "state": "up"},
            {"prefix": "192.168.0.0/16", "bgp_neig": "10.2.240.2", "state": "up"},
        ]
        results = _resolve_path(data, "[*].prefix")
        lines = [_format_print("neig={{.bgp_neig}} prefix={{value}}", p, v, data) for p, v in results]
        assert lines[0] == "neig=10.2.240.1 prefix=10.0.0.0/8"
        assert lines[1] == "neig=10.2.240.2 prefix=192.168.0.0/16"

    def test_sibling_field_via_evaluate_checks(self):
        snap = _snap("show_bgp", [
            {"prefix": "10.0.0.0/8", "bgp_neig": "10.2.240.1"},
            {"prefix": "192.168.0.0/16", "bgp_neig": "10.2.240.2"},
        ])
        checks = [{"name": "c", "command": "show_bgp", "path": "[*].prefix",
                   "condition": "contains", "value": "10",
                   "print": "neig={{.bgp_neig}} prefix={{value}}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["printed"][0] == "neig=10.2.240.1 prefix=10.0.0.0/8"


class TestPrintOnly:
    """Checks with no condition/value/conditions/branches — display-only, always pass."""

    def test_no_condition_is_print_only(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version"}]
        r = evaluate_checks(snap, checks)
        result = r["results"][0]
        assert result["status"] == "pass"
        assert result["print_only"] is True

    def test_print_only_surfaces_values_with_template(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version",
                   "path": "[0].version",
                   "print": "Running version {{value}}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["printed"] == ["Running version 17.3.1"]

    def test_print_only_auto_template_when_no_print_field(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version"}]
        r = evaluate_checks(snap, checks)
        assert "17.3.1" in r["results"][0]["printed"][0]

    def test_print_only_never_fails(self):
        snap = _snap("show_version", [{"version": "UNEXPECTED"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version",
                   "print": "Version: {{value}}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"
        assert r["summary"]["failed"] == 0

    def test_print_only_wildcard_expand(self):
        snap = _snap("show_bgp", {"10.0.0.1": {"pfx": 100}, "10.0.0.2": {"pfx": 200}})
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].pfx",
                   "print": "Peer {{[*]}} has {{value}} prefixes"}]
        r = evaluate_checks(snap, checks)
        printed = r["results"][0]["printed"]
        assert len(printed) == 2
        assert any("10.0.0.1" in l and "100" in l for l in printed)
        assert any("10.0.0.2" in l and "200" in l for l in printed)

    def test_print_only_does_not_affect_exit_code(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed_critical"] == 0
        assert result["print_only"] is True

    def test_print_only_surfaces_values_with_template(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version",
                   "path": "[0].version",
                   "print": "Running version {{value}}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["printed"] == ["Running version 17.3.1"]

    def test_print_only_auto_template_when_no_print_field(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version"}]
        r = evaluate_checks(snap, checks)
        # auto-formats as "{path} -> {value!r}"
        assert "17.3.1" in r["results"][0]["printed"][0]

    def test_print_only_never_fails(self):
        snap = _snap("show_version", [{"version": "UNEXPECTED"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version",
                   "print": "Version: {{value}}"}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"
        assert r["summary"]["failed"] == 0

    def test_print_only_wildcard_expand(self):
        snap = _snap("show_bgp", {"10.0.0.1": {"pfx": 100}, "10.0.0.2": {"pfx": 200}})
        checks = [{"name": "c", "command": "show_bgp",
                   "path": "[*].pfx",
                   "print": "Peer {{[*]}} has {{value}} prefixes"}]
        r = evaluate_checks(snap, checks)
        printed = r["results"][0]["printed"]
        assert len(printed) == 2
        assert any("10.0.0.1" in l and "100" in l for l in printed)
        assert any("10.0.0.2" in l and "200" in l for l in printed)

    def test_print_only_does_not_affect_exit_code(self):
        snap = _snap("show_version", [{"version": "17.3.1"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].version"}]
        r = evaluate_checks(snap, checks)
        assert r["summary"]["failed_critical"] == 0


def _two_cmd_snap(intf_rows=None, brief_rows=None):
    intf_rows  = intf_rows  or [
        {"interface": "Gi1/1/0",    "description": "PR-link", "status": "up"},
        {"interface": "Loopback10", "description": "",         "status": "up"},
    ]
    brief_rows = brief_rows or [{"intf": "Lo10", "status": "up"}]
    return {
        "metadata": {"hostname": "TEST"},
        "commands": {
            "show_interfaces":   {"parsed": intf_rows},
            "show_ip_int_brief": {"parsed": brief_rows},
        },
    }


class TestCrossCheck:
    def _check(self, **kwargs):
        base = {
            "name": "c",
            "command": "show_interfaces",
            "cross_check": {
                "if": {
                    "path": "[*]",
                    "field": "description",
                    "condition": "contains",
                    "value": "PR",
                },
                "then": {
                    "path": "[*]",
                    "filter": {"field": "interface", "condition": "eq", "value": "Loopback10"},
                    "assert": {"field": "status", "condition": "eq", "value": "up"},
                },
            },
        }
        base.update(kwargs)
        return base

    def test_if_matches_then_passes(self):
        r = evaluate_checks(_two_cmd_snap(), [self._check()])
        assert r["results"][0]["status"] == "pass"

    def test_if_matches_then_fails(self):
        snap = _two_cmd_snap(intf_rows=[
            {"interface": "Gi1/1/0",    "description": "PR-link", "status": "up"},
            {"interface": "Loopback10", "description": "",         "status": "down"},
        ])
        r = evaluate_checks(snap, [self._check()])
        assert r["results"][0]["status"] == "fail"
        assert r["results"][0]["failures"][0]["actual"] == "down"

    def test_if_no_match_vacuously_passes(self):
        snap = _two_cmd_snap(intf_rows=[
            {"interface": "Gi1/1/0",    "description": "normal-link", "status": "up"},
            {"interface": "Loopback10", "description": "",             "status": "down"},
        ])
        r = evaluate_checks(snap, [self._check()])
        result = r["results"][0]
        assert result["status"] == "pass"
        assert "0 rows" in result.get("note", "")

    def test_then_target_not_found(self):
        snap = _two_cmd_snap(intf_rows=[
            {"interface": "Gi1/1/0", "description": "PR-link", "status": "up"},
        ])
        r = evaluate_checks(snap, [self._check()])
        assert r["results"][0]["status"] == "error"

    def test_different_commands(self):
        snap = _two_cmd_snap()
        check = {
            "name": "cross-cmd",
            "cross_check": {
                "if": {
                    "command": "show_interfaces",
                    "path": "[*]",
                    "field": "description",
                    "condition": "contains",
                    "value": "PR",
                },
                "then": {
                    "command": "show_ip_int_brief",
                    "path": "[*]",
                    "filter": {"field": "intf", "condition": "eq", "value": "Lo10"},
                    "assert": {"field": "status", "condition": "eq", "value": "up"},
                },
            },
        }
        r = evaluate_checks(snap, [check])
        assert r["results"][0]["status"] == "pass"


# ---------------------------------------------------------------------------
# TestCountCheck
# ---------------------------------------------------------------------------

class TestCountCheck:
    def _check(self, cond, val):
        return {"name": "c", "command": "show_bgp", "path": "neighbors[*]",
                "count": {"condition": cond, "value": val}}

    def _snap(self, n):
        return _snap("show_bgp", {"neighbors": [{"ip": f"10.0.0.{i}"} for i in range(n)]})

    def test_count_gte_pass(self):
        r = evaluate_checks(self._snap(4), [self._check("gte", 4)])
        assert r["results"][0]["status"] == "pass"
        assert r["results"][0]["actual"] == [4]

    def test_count_gte_fail(self):
        r = evaluate_checks(self._snap(2), [self._check("gte", 4)])
        assert r["results"][0]["status"] == "fail"

    def test_count_eq_pass(self):
        r = evaluate_checks(self._snap(3), [self._check("eq", 3)])
        assert r["results"][0]["status"] == "pass"

    def test_count_zero(self):
        r = evaluate_checks(self._snap(0), [self._check("eq", 0)])
        assert r["results"][0]["status"] == "pass"


# ---------------------------------------------------------------------------
# TestLenConditions
# ---------------------------------------------------------------------------

class TestLenConditions:
    def test_len_gte_string_pass(self):
        snap = _snap("show_version", [{"hostname": "N9K-WAN-1"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].hostname",
                   "condition": "len_gte", "value": 5}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"

    def test_len_gte_string_fail(self):
        snap = _snap("show_version", [{"hostname": "hi"}])
        checks = [{"name": "c", "command": "show_version", "path": "[0].hostname",
                   "condition": "len_gte", "value": 5}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "fail"

    def test_len_eq_list(self):
        snap = _snap("show_bgp", {"items": [1, 2, 3]})
        checks = [{"name": "c", "command": "show_bgp", "path": "items",
                   "condition": "len_eq", "value": 3}]
        r = evaluate_checks(snap, checks)
        assert r["results"][0]["status"] == "pass"


# ---------------------------------------------------------------------------
# TestDateConditions
# ---------------------------------------------------------------------------

class TestDateConditions:
    def _snap_date(self, val):
        return _snap("show_cert", [{"expiry": val}])

    def test_date_before_pass(self):
        r = evaluate_checks(self._snap_date("03-May-2030"),
                            [{"name": "c", "command": "show_cert", "path": "[0].expiry",
                              "condition": "date_before", "value": "01-Jan-2031"}])
        assert r["results"][0]["status"] == "pass"

    def test_date_before_fail(self):
        r = evaluate_checks(self._snap_date("03-May-2030"),
                            [{"name": "c", "command": "show_cert", "path": "[0].expiry",
                              "condition": "date_before", "value": "01-Jan-2025"}])
        assert r["results"][0]["status"] == "fail"

    def test_date_within_days_pass(self):
        from datetime import timedelta
        future = (datetime.now() + timedelta(days=5)).strftime("%d-%b-%Y")
        # a date 5 days in the future is -5 days old → date_within_days checks age <= N
        # actually date is in the future so age_days < 0 which is <= 30 → passes
        r = evaluate_checks(self._snap_date(future),
                            [{"name": "c", "command": "show_cert", "path": "[0].expiry",
                              "condition": "date_within_days", "value": 30}])
        assert r["results"][0]["status"] == "pass"

    def test_date_older_than_days_pass(self):
        r = evaluate_checks(self._snap_date("01-Jan-2020"),
                            [{"name": "c", "command": "show_cert", "path": "[0].expiry",
                              "condition": "date_older_than_days", "value": 100}])
        assert r["results"][0]["status"] == "pass"

    def test_multiple_date_formats(self):
        from utils.health import _parse_date
        assert _parse_date("03-May-2026") is not None
        assert _parse_date("03/05/2026") is not None
        assert _parse_date("2026-05-03") is not None
        assert _parse_date("03-05-2026") is not None
        assert _parse_date("03-May-26") is not None
        assert _parse_date("not-a-date") is None


# ---------------------------------------------------------------------------
# TestBaselineCheck
# ---------------------------------------------------------------------------

class TestBaselineCheck:
    def _make_snap(self, prefix_count):
        return _snap("show_bgp", {"neighbors": [{"ip": "10.0.0.1", "pfx": prefix_count}]})

    def _check(self, cond, val=None):
        c = {"name": "c", "command": "show_bgp", "path": "neighbors[*].pfx",
             "compare_baseline": {"condition": cond}}
        if val is not None:
            c["compare_baseline"]["value"] = val
        return c

    def test_gte_passes_when_not_lower(self):
        current  = self._make_snap(100)
        baseline = self._make_snap(90)
        r = evaluate_checks(current, [self._check("gte")], baseline=baseline)
        assert r["results"][0]["status"] == "pass"

    def test_gte_fails_when_lower(self):
        current  = self._make_snap(50)
        baseline = self._make_snap(100)
        r = evaluate_checks(current, [self._check("gte")], baseline=baseline)
        assert r["results"][0]["status"] == "fail"

    def test_diff_lte_pass(self):
        current  = self._make_snap(95)
        baseline = self._make_snap(100)
        r = evaluate_checks(current, [self._check("diff_lte", 10)], baseline=baseline)
        assert r["results"][0]["status"] == "pass"

    def test_diff_lte_fail(self):
        current  = self._make_snap(80)
        baseline = self._make_snap(100)
        r = evaluate_checks(current, [self._check("diff_lte", 10)], baseline=baseline)
        assert r["results"][0]["status"] == "fail"

    def test_no_baseline_errors(self):
        r = evaluate_checks(self._make_snap(100), [self._check("gte")])
        assert r["results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# TestMetadataCheck
# ---------------------------------------------------------------------------

class TestMetadataCheck:
    def _meta_snap(self, hostname="N9K-WAN-1", platform="cisco_nxos",
                   collection_time="01-Jan-2020"):
        return {"metadata": {"hostname": hostname, "platform": platform,
                              "collection_time": collection_time},
                "commands": {}}

    def test_hostname_matches_pass(self):
        r = evaluate_checks(self._meta_snap(),
                            [{"name": "c", "metadata": "hostname",
                              "condition": "matches", "value": "^N9K-"}])
        assert r["results"][0]["status"] == "pass"

    def test_hostname_matches_fail(self):
        r = evaluate_checks(self._meta_snap(hostname="IOS-RTR-1"),
                            [{"name": "c", "metadata": "hostname",
                              "condition": "matches", "value": "^N9K-"}])
        assert r["results"][0]["status"] == "fail"

    def test_platform_eq_pass(self):
        r = evaluate_checks(self._meta_snap(),
                            [{"name": "c", "metadata": "platform",
                              "condition": "eq", "value": "cisco_nxos"}])
        assert r["results"][0]["status"] == "pass"

    def test_missing_field_errors(self):
        r = evaluate_checks(self._meta_snap(),
                            [{"name": "c", "metadata": "serial_number",
                              "condition": "eq", "value": "ABC123"}])
        assert r["results"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# Plan 17: skip_if
# ---------------------------------------------------------------------------

class TestSkipIf:
    def _snap(self, hostname="WAN-1"):
        return {"metadata": {"hostname": hostname}, "commands": {
            "show_version": {"parsed": [{"version": "17.0"}]}
        }}

    def _check(self, skip_if_spec):
        return {"name": "c", "command": "show_version", "path": "[0].version",
                "condition": "eq", "value": "17.0", "skip_if": skip_if_spec}

    def test_skip_when_condition_matches(self):
        """Check is skipped when skip_if metadata condition is true."""
        r = evaluate_checks(self._snap("IOS-RTR-1"),
                            [self._check({"metadata": "hostname",
                                          "condition": "matches", "value": "^IOS-"})])
        assert r["results"][0]["status"] == "skip"

    def test_not_skipped_when_condition_does_not_match(self):
        """Check runs normally when skip_if condition is false."""
        r = evaluate_checks(self._snap("WAN-1"),
                            [self._check({"metadata": "hostname",
                                          "condition": "matches", "value": "^IOS-"})])
        assert r["results"][0]["status"] == "pass"

    def test_skipped_count_in_summary(self):
        """Skipped checks are counted in summary.skipped, not failed."""
        r = evaluate_checks(self._snap("IOS-RTR-1"),
                            [self._check({"metadata": "hostname",
                                          "condition": "matches", "value": "^IOS-"})])
        assert r["summary"]["skipped"] == 1
        assert r["summary"]["failed"] == 0
        assert r["summary"]["failed_critical"] == 0


# ---------------------------------------------------------------------------
# Plan 17: tags filter
# ---------------------------------------------------------------------------

class TestTags:
    def _snap(self):
        return {"metadata": {"hostname": "TEST"}, "commands": {
            "show_bgp": {"parsed": [{"prefixes": 10}]},
            "show_ospf": {"parsed": [{"state": "FULL"}]},
        }}

    def test_tags_filter_selects_matching_checks(self):
        """Only checks with the specified tag are run."""
        checks = [
            {"name": "bgp_check", "command": "show_bgp", "path": "[0].prefixes",
             "condition": "gte", "value": 1, "tags": ["bgp", "routing"]},
            {"name": "ospf_check", "command": "show_ospf", "path": "[0].state",
             "condition": "eq", "value": "FULL", "tags": ["ospf", "routing"]},
        ]
        r = evaluate_checks(self._snap(), checks, tags=["bgp"])
        assert r["summary"]["total"] == 1
        assert r["results"][0]["name"] == "bgp_check"

    def test_tags_or_logic(self):
        """A check with any matching tag is included (OR logic)."""
        checks = [
            {"name": "bgp_check", "command": "show_bgp", "path": "[0].prefixes",
             "condition": "gte", "value": 1, "tags": ["bgp"]},
            {"name": "ospf_check", "command": "show_ospf", "path": "[0].state",
             "condition": "eq", "value": "FULL", "tags": ["ospf"]},
        ]
        r = evaluate_checks(self._snap(), checks, tags=["bgp", "ospf"])
        assert r["summary"]["total"] == 2

    def test_no_tags_runs_all_checks(self):
        """When tags=None, all checks run regardless of their tags field."""
        checks = [
            {"name": "bgp_check", "command": "show_bgp", "path": "[0].prefixes",
             "condition": "gte", "value": 1, "tags": ["bgp"]},
            {"name": "ospf_check", "command": "show_ospf", "path": "[0].state",
             "condition": "eq", "value": "FULL", "tags": ["ospf"]},
        ]
        r = evaluate_checks(self._snap(), checks)
        assert r["summary"]["total"] == 2


# ---------------------------------------------------------------------------
# Simple dashboard renderer + skip_if validation
# ---------------------------------------------------------------------------

class TestSkipIfValidation:
    def _base(self, skip_if):
        return [{"name": "x", "command": "c", "path": "p",
                 "condition": "eq", "value": 1, "skip_if": skip_if}]

    def test_unknown_skip_condition_warns(self):
        from utils.health import validate_checks
        warns = validate_checks(self._base(
            {"metadata": "hostname", "condition": "not_matches", "value": "^WAN-"}))
        assert any("skip_if" in w and "not_matches" in w for w in warns)

    def test_missing_metadata_field_warns(self):
        from utils.health import validate_checks
        warns = validate_checks(self._base({"condition": "eq", "value": "z"}))
        assert any("no 'metadata'" in w for w in warns)

    def test_valid_skip_if_no_warning(self):
        from utils.health import validate_checks
        warns = validate_checks(self._base(
            {"metadata": "hostname", "condition": "contains", "value": "WAN"}))
        assert not any("skip_if" in w for w in warns)


class TestSimpleDashboard:
    def _snapshot(self):
        return {
            "metadata": {"hostname": "EDGE-RTR-1", "collection_time": "09-Jun-26"},
            "commands": {
                "show_ip_bgp_summary": {
                    "status": "parsed",
                    "raw": "SECRET-RAW neighbor 10.99.88.77",
                    "parsed": {"neighbors": [
                        {"ip": "10.99.88.77", "prefixes_received": 0},
                        {"ip": "10.99.88.78", "prefixes_received": 500},
                    ]},
                },
                "show_version": {
                    "status": "parsed",
                    "raw": "serial FDO12345XYZ",
                    "parsed": [{"version": "9.3(8)", "serial": "FDO12345XYZ"}],
                },
            },
        }

    def _checks(self):
        return [
            {"name": "BGP prefixes > 0", "command": "show_ip_bgp_summary",
             "path": "neighbors[*].prefixes_received", "condition": "gt", "value": 0},
            {"name": "OSPF check", "command": "show_ip_ospf_neighbors",
             "path": "[*].state", "condition": "eq", "value": "FULL"},
            {"name": "Skipped check", "command": "show_version", "path": "[0].version",
             "condition": "eq", "value": "9.3(8)",
             "skip_if": {"metadata": "hostname", "condition": "contains", "value": "EDGE"}},
            {"name": "Display serial", "command": "show_version",
             "path": "[0].serial", "print": True},
        ]

    def test_no_sensitive_data_in_simple_html(self):
        from utils import html_report
        report = evaluate_checks(self._snapshot(), self._checks())
        html = html_report.render_health_simple(report)
        for secret in ("10.99.88.77", "10.99.88.78", "SECRET-RAW", "FDO12345XYZ", "9.3(8)"):
            assert secret not in html

    def test_all_status_badges_render(self):
        from utils import html_report
        report = evaluate_checks(self._snapshot(), self._checks())
        html = html_report.render_health_simple(report)
        for token in (">FAIL<", ">ERROR<", ">SKIP<", ">DISPLAY<"):
            assert token in html

    def test_fail_count_without_values(self):
        from utils import html_report
        report = evaluate_checks(self._snapshot(), self._checks())
        html = html_report.render_health_simple(report)
        assert "1 value(s) failed" in html

    def test_multi_device_simple_no_links_no_leaks(self):
        from utils import html_report
        snap = self._snapshot()
        report = evaluate_checks(snap, self._checks())
        html = html_report.render_health_all_simple(
            [{"hostname": "EDGE-RTR-1", "report": report, "snapshot": snap}])
        assert 'href="#device-' not in html
        assert ">SKIP<" in html
        assert "10.99.88.77" not in html

    def test_detailed_matrix_shows_skip_not_err(self):
        from utils import html_report
        snap = self._snapshot()
        report = evaluate_checks(snap, self._checks())
        html = html_report.render_health_all(
            [{"hostname": "EDGE-RTR-1", "report": report, "snapshot": snap}], "base.yaml")
        assert ">SKIP</a>" in html

    def test_empty_report(self):
        from utils import html_report
        empty = {"metadata": {}, "summary": {"total": 0, "passed": 0,
                                             "failed": 0, "error": 0}, "results": []}
        assert "No checks defined" in html_report.render_health_simple(empty)
        assert "No checks found" in html_report.render_health_all_simple([])
