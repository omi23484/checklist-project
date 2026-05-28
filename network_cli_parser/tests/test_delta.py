from utils.delta import compute_delta


def _snap(hostname, commands):
    return {
        "metadata": {"hostname": hostname, "timestamp": "01-Jan-26"},
        "commands": commands,
    }


def _cmd(parsed, status="parsed"):
    return {"status": status, "raw": "", "parsed": parsed}


class TestComputeDelta:
    def test_identical_snapshots_no_changes(self):
        data   = {"show_version": _cmd({"version": "7.0"})}
        before = _snap("SW1", data)
        after  = _snap("SW1", data)
        result = compute_delta(before, after)
        assert result["summary"]["commands_changed"] == []
        assert "show_version" in result["summary"]["commands_unchanged"]

    def test_added_command(self):
        before = _snap("SW1", {})
        after  = _snap("SW1", {"show_version": _cmd({})})
        result = compute_delta(before, after)
        assert "show_version" in result["summary"]["commands_added"]

    def test_removed_command(self):
        before = _snap("SW1", {"show_version": _cmd({})})
        after  = _snap("SW1", {})
        result = compute_delta(before, after)
        assert "show_version" in result["summary"]["commands_removed"]

    def test_changed_scalar_value(self):
        before = _snap("SW1", {"show_version": _cmd({"version": "7.0"})})
        after  = _snap("SW1", {"show_version": _cmd({"version": "8.0"})})
        result = compute_delta(before, after)
        assert "show_version" in result["summary"]["commands_changed"]
        diffs = result["changes"]["show_version"]["diffs"]
        diff  = next(d for d in diffs if d["path"] == "parsed.version")
        assert diff["before"] == "7.0"
        assert diff["after"]  == "8.0"

    def test_status_change_detected(self):
        before = _snap("SW1", {"show_x": {"status": "parsed", "raw": "", "parsed": {}}})
        after  = _snap("SW1", {"show_x": {"status": "failed",  "raw": "", "parsed": {}}})
        result = compute_delta(before, after)
        assert "show_x" in result["summary"]["commands_changed"]

    def test_added_dict_key(self):
        before = _snap("SW1", {"show_iface": _cmd({"mtu": 1500})})
        after  = _snap("SW1", {"show_iface": _cmd({"mtu": 1500, "speed": "1G"})})
        result = compute_delta(before, after)
        assert "show_iface" in result["summary"]["commands_changed"]
        diffs = result["changes"]["show_iface"]["diffs"]
        added = next(d for d in diffs if "speed" in d["path"])
        assert added["before"] is None
        assert added["after"] == "1G"

    def test_removed_dict_key(self):
        before = _snap("SW1", {"show_iface": _cmd({"mtu": 1500, "speed": "1G"})})
        after  = _snap("SW1", {"show_iface": _cmd({"mtu": 1500})})
        result = compute_delta(before, after)
        diffs = result["changes"]["show_iface"]["diffs"]
        removed = next(d for d in diffs if "speed" in d["path"])
        assert removed["before"] == "1G"
        assert removed["after"]  is None

    def test_list_diff_by_natural_key(self):
        before = _snap("SW1", {"show_ifaces": _cmd([
            {"INTERFACE": "eth0", "STATUS": "up"},
            {"INTERFACE": "eth1", "STATUS": "up"},
        ])})
        after = _snap("SW1", {"show_ifaces": _cmd([
            {"INTERFACE": "eth0", "STATUS": "up"},
            {"INTERFACE": "eth1", "STATUS": "down"},
        ])})
        result = compute_delta(before, after)
        assert "show_ifaces" in result["summary"]["commands_changed"]
        diffs   = result["changes"]["show_ifaces"]["diffs"]
        changed = [d for d in diffs if "eth1" in d["path"] and "STATUS" in d["path"]]
        assert changed
        assert changed[0]["before"] == "up"
        assert changed[0]["after"]  == "down"

    def test_list_natural_key_new_row(self):
        before = _snap("SW1", {"show_ifaces": _cmd([
            {"INTERFACE": "eth0", "STATUS": "up"},
        ])})
        after = _snap("SW1", {"show_ifaces": _cmd([
            {"INTERFACE": "eth0", "STATUS": "up"},
            {"INTERFACE": "eth1", "STATUS": "up"},
        ])})
        result = compute_delta(before, after)
        assert "show_ifaces" in result["summary"]["commands_changed"]
        diffs = result["changes"]["show_ifaces"]["diffs"]
        added = [d for d in diffs if d["before"] is None]
        assert added

    def test_metadata_preserved(self):
        before = _snap("SW1", {})
        after  = _snap("SW2", {})
        result = compute_delta(before, after)
        assert result["metadata"]["before"]["hostname"] == "SW1"
        assert result["metadata"]["after"]["hostname"]  == "SW2"

    def test_empty_snapshots(self):
        before = _snap("SW1", {})
        after  = _snap("SW1", {})
        result = compute_delta(before, after)
        assert result["summary"]["commands_added"]     == []
        assert result["summary"]["commands_removed"]   == []
        assert result["summary"]["commands_changed"]   == []
        assert result["summary"]["commands_unchanged"] == []

    def test_list_diff_natural_key_integer_values(self):
        # Non-string natural key values must not crash (_diff_list_by_key KeyError fix)
        before = _snap("SW1", {"show_ports": _cmd([
            {"PORT": 1, "STATUS": "up"},
            {"PORT": 2, "STATUS": "up"},
        ])})
        after = _snap("SW1", {"show_ports": _cmd([
            {"PORT": 1, "STATUS": "up"},
            {"PORT": 2, "STATUS": "down"},
        ])})
        result = compute_delta(before, after)
        assert "show_ports" in result["summary"]["commands_changed"]

    def test_multiple_commands_mixed(self):
        before = _snap("SW1", {
            "show_version": _cmd({"version": "7.0"}),
            "show_bgp":     _cmd({"peers": 4}),
        })
        after = _snap("SW1", {
            "show_version": _cmd({"version": "8.0"}),
            "show_bgp":     _cmd({"peers": 4}),
            "show_ospf":    _cmd({"neighbors": 2}),
        })
        result = compute_delta(before, after)
        assert "show_version" in result["summary"]["commands_changed"]
        assert "show_bgp"     in result["summary"]["commands_unchanged"]
        assert "show_ospf"    in result["summary"]["commands_added"]
