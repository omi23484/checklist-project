"""Regression tests for the correctness-audit fixes (one test per reproduced bug)."""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ttp import ttp

import main
import report
from parsers import splitter
from parsers.command_mapper import get_strategy
from utils.delta import compute_delta
from utils.health import _apply_condition, evaluate_checks
from utils.normalization import normalize_command

ROOT = Path(__file__).parent.parent


def _snap(cmd, parsed, status="parsed"):
    return {"metadata": {"hostname": "X"}, "commands": {cmd: {"status": status, "parsed": parsed}}}


def _ttp(template, raw):
    p = ttp(data=raw, template=template)
    p.parse()
    return p.result(format="raw")[0][0]


def test_delta_reports_lost_neighbor_sharing_an_interface():
    before = [{"NEIGHBOR_ID": "1.1.1.1", "INTERFACE": "Vlan10"},
              {"NEIGHBOR_ID": "2.2.2.2", "INTERFACE": "Vlan10"}]
    d = compute_delta(_snap("ospf", before), _snap("ospf", before[1:]))
    assert d["summary"]["commands_changed"] == ["ospf"]
    assert d["changes"]["ospf"]["diffs"][0]["path"] == "parsed[NEIGHBOR_ID=1.1.1.1]"


def test_check_on_failed_parse_is_error_not_vacuous_pass():
    check = [{"name": "c", "command": "bgp", "path": "[*].state", "condition": "eq", "value": "Established"}]
    r = evaluate_checks(_snap("bgp", {}, status="failed"), check)["results"][0]
    assert r["status"] == "error"


def test_eq_ne_one_of_compare_numbers_numerically():
    assert _apply_condition("10", "eq", 10)[0]
    assert not _apply_condition("0", "ne", 0)[0]
    assert _apply_condition("1", "one_of", [1, 2])[0]
    assert not _apply_condition("true", "eq", True)[0]


def test_baseline_matches_rows_by_identity_and_reports_vanished_rows():
    check = [{"name": "c", "command": "bgp", "path": "neighbors[*].pfx",
              "compare_baseline": {"condition": "diff_pct_lte", "value": 20}}]
    base = _snap("bgp", {"neighbors": [{"neighbor": "A", "pfx": "100"}, {"neighbor": "B", "pfx": "200"}]})
    reordered = _snap("bgp", {"neighbors": [{"neighbor": "B", "pfx": "200"}, {"neighbor": "A", "pfx": "100"}]})
    only_b = _snap("bgp", {"neighbors": [{"neighbor": "B", "pfx": "200"}]})
    assert evaluate_checks(reordered, check, baseline=base)["results"][0]["status"] == "pass"
    r = evaluate_checks(only_b, check, baseline=base)["results"][0]
    assert r["status"] == "fail"
    assert [f["message"] for f in r["failures"]] == ["present in baseline, missing from current snapshot"]


def test_wildcard_matches_exactly_one_token():
    def tmpl(cmd):
        return get_strategy("cisco_nxos", normalize_command(cmd)).get("template")
    assert tmpl("show ip msdp peer 172.16.253.19") == "cisco_nxos_show_ip_msdp_peer"
    assert tmpl("show ip bgp neighbors 10.0.0.1 routes") == "cisco_nxos_show_ip_bgp_neighbors_routes"
    for cmd in ("show ip msdp peer vrf all", "show ip msdp peer 1.1.1.1 advertised-sa",
                "show ip msdp peer 1.1.1.1 | include State"):
        assert tmpl(cmd) is None, cmd


def test_splitter_keeps_ipv6_command_and_parses_repeat_captures():
    dump = ("R1# show ip bgp summary\nBGP router identifier 1.1.1.1\n"
            "R1# show ipv6 route 2001:db8::/32\nIPv6 Routing Table\n"
            "R1# show bgp sessions\nx\nR1# show bgp sessions\ny\n")
    segs = splitter.split_commands(dump)
    assert segs["show_ip_bgp_summary"] == "BGP router identifier 1.1.1.1"
    assert "show_ipv6_route_2001:db8::/32" in segs
    assert "show_bgp_sessions__2" in segs
    # the repeat goes through the same parser as the first capture
    assert main._parse_command("cisco_nxos", "show_bgp_sessions__2", "x")[1] == \
           main._parse_command("cisco_nxos", "show_bgp_sessions", "x")[1] != "no_template"


def test_playbook_enabled_accepts_common_false_values():
    import playbook
    assert not any(playbook._is_yes(v) for v in ("no", "false", "0", "n", "off", "disabled"))
    assert all(playbook._is_yes(v) for v in ("yes", "Y", "true", "1", "on"))


def test_malformed_checks_do_not_crash_report():
    from utils import html_report
    snap = _snap("c", [{"v": "1"}])
    rep = evaluate_checks(snap, [
        {"name": "a", "command": "c", "path": "[*]", "count": 3},
        {"name": "b", "command": "c", "path": "[*].v", "condition": "eq", "value": 2, "severity": None},
        {"name": "c", "command": "c", "path": "[*].v", "condition": "eq", "value": 2, "severity": 1},
    ])
    assert {r["severity"] for r in rep["results"]} == {"critical"}
    html_report.render_health(rep, snap)
    html_report.render_health_simple(rep)


def test_find_baseline_does_not_match_hostname_prefix(tmp_path):
    json.dump({"who": "SW1"}, open(tmp_path / "SW1_05-May-26.json", "w"))
    time.sleep(0.01)
    json.dump({"who": "SW1_A"}, open(tmp_path / "SW1_A_06-May-26.json", "w"))
    assert report._find_baseline(tmp_path, "SW1") == {"who": "SW1"}


def test_single_ospf_neighbor_is_a_list_so_checks_can_fail():
    raw = ("Neighbor ID     Pri State            Up Time  Address         Interface\n"
           "10.0.2.2          1 INIT/DROTHER    00:00:04  10.0.2.2        Eth1/1\n")
    parsed = _ttp((ROOT / "templates/ttp/routing/cisco_nxos_show_ip_ospf_neighbors.ttp").read_text(), raw)
    assert isinstance(parsed["neighbors"], list)
    check = [{"name": "c", "command": "o", "path": "neighbors[*].state", "condition": "matches", "value": "^FULL"}]
    assert evaluate_checks(_snap("o", parsed), check)["results"][0]["status"] == "fail"


def test_nxos_mroute_templates_parse_real_device_output():
    segs = splitter.split_commands((ROOT / "data/raw/N9K-WAN-1_03-May-26.txt").read_text())
    mr = _ttp((ROOT / "templates/ttp/multicast/cisco_nxos_show_ip_mroute.ttp").read_text(), segs["show_ip_mroute"])
    assert [e["group"] for e in mr["vrfs"]["default"]["entries"]] == \
           ["239.255.0.1/32", "239.255.0.1/32", "232.0.0.0/8"]
    sm = _ttp((ROOT / "templates/ttp/multicast/cisco_nxos_show_ip_mroute_summary.ttp").read_text(),
              segs["show_ip_mroute_summary"])
    assert sm["vrfs"]["MCAST-VRF"]["summary"]["total_routes"] == 2


def test_ospf_database_summary_keeps_process_rows_out_of_areas():
    base = "templates/ttp/eigrp_ospf/cisco_ios_show_ip_ospf_database_database-summary"
    raw = (ROOT / f"data/reference/eigrp_ospf/cisco_ios_show_ip_ospf_database_database-summary.txt").read_text()
    r = _ttp((ROOT / f"{base}.ttp").read_text(), raw)
    assert [len(a["lsa_types"]) for a in r["areas"]] == [7]
    assert len(r["process_summary"]["lsa_types"]) == 9
