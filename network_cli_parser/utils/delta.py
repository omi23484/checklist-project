"""Delta computation between two JSON snapshots."""

from typing import Any

_NATURAL_KEYS = (
    "INTERFACE", "NEIGHBOR", "NEIGHBOR_ID", "IP_ADDRESS", "VRF", "NAME", "PORT",
    "neighbor", "interface", "neighbor_id", "ip_address", "vrf", "name", "port",
)


def compute_delta(before: dict, after: dict) -> dict:
    b_cmds = before.get("commands", {})
    a_cmds = after.get("commands", {})

    all_keys = set(b_cmds) | set(a_cmds)
    added   = sorted(k for k in all_keys if k not in b_cmds)
    removed = sorted(k for k in all_keys if k not in a_cmds)
    common  = sorted(k for k in all_keys if k in b_cmds and k in a_cmds)

    changes: dict[str, dict] = {}
    unchanged: list[str] = []

    for key in common:
        diffs: list[dict] = []

        b_cmd = b_cmds[key]
        a_cmd = a_cmds[key]

        if b_cmd.get("status") != a_cmd.get("status"):
            diffs.append({
                "path":   "status",
                "before": b_cmd.get("status"),
                "after":  a_cmd.get("status"),
            })

        diffs.extend(_diff_value(
            b_cmd.get("parsed", {}),
            a_cmd.get("parsed", {}),
            path="parsed",
        ))

        if diffs:
            changes[key] = {"diffs": diffs}
        else:
            unchanged.append(key)

    return {
        "metadata": {
            "before": before.get("metadata", {}),
            "after":  after.get("metadata", {}),
        },
        "summary": {
            "commands_added":     added,
            "commands_removed":   removed,
            "commands_changed":   sorted(changes.keys()),
            "commands_unchanged": unchanged,
        },
        "changes": changes,
    }


def _diff_value(before: Any, after: Any, path: str) -> list[dict]:
    if before == after:
        return []
    if type(before) is not type(after):
        return [{"path": path, "before": before, "after": after}]
    if isinstance(before, dict):
        return _diff_dict(before, after, path)
    if isinstance(before, list):
        return _diff_list(before, after, path)
    return [{"path": path, "before": before, "after": after}]


def _diff_dict(before: dict, after: dict, path: str) -> list[dict]:
    diffs = []
    for k in sorted(set(before) | set(after)):
        child = f"{path}.{k}"
        if k not in before:
            diffs.append({"path": child, "before": None, "after": after[k]})
        elif k not in after:
            diffs.append({"path": child, "before": before[k], "after": None})
        else:
            diffs.extend(_diff_value(before[k], after[k], child))
    return diffs


def _diff_list(before: list, after: list, path: str) -> list[dict]:
    if before and after and isinstance(before[0], dict):
        key_field = _detect_key_field(before + after)
        if key_field:
            return _diff_list_by_key(before, after, path, key_field)

    diffs = []
    for i in range(max(len(before), len(after))):
        child = f"{path}[{i}]"
        if i >= len(before):
            diffs.append({"path": child, "before": None, "after": after[i]})
        elif i >= len(after):
            diffs.append({"path": child, "before": before[i], "after": None})
        else:
            diffs.extend(_diff_value(before[i], after[i], child))
    return diffs


def _diff_list_by_key(before: list, after: list, path: str, key_field: str) -> list[dict]:
    b_map = {str(row[key_field]): row for row in before if key_field in row}
    a_map = {str(row[key_field]): row for row in after  if key_field in row}
    if len(b_map) < sum(1 for r in before if key_field in r):
        print(f"[WARN] delta: duplicate '{key_field}' values in before '{path}' — last row wins")
    if len(a_map) < sum(1 for r in after if key_field in r):
        print(f"[WARN] delta: duplicate '{key_field}' values in after '{path}' — last row wins")
    diffs = []
    for k in sorted(set(b_map) | set(a_map)):
        child = f"{path}[{key_field}={k}]"
        if k not in b_map:
            diffs.append({"path": child, "before": None, "after": a_map[k]})
        elif k not in a_map:
            diffs.append({"path": child, "before": b_map[k], "after": None})
        else:
            diffs.extend(_diff_dict(b_map[k], a_map[k], child))
    return diffs


def _detect_key_field(rows: list[dict]):
    for field in _NATURAL_KEYS:
        if all(field in row for row in rows):
            return field
    return None
