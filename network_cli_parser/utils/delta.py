"""Delta computation between two JSON snapshots."""

from typing import Any

# Identity fields first (neighbor/address are unique per row); interface/vrf
# repeat on multi-access segments, so they only win if actually unique.
_NATURAL_KEYS = (
    "NEIGHBOR_ID", "NEIGHBOR", "IP_ADDRESS", "ADDRESS", "PEER_ADDRESS", "MAC",
    "neighbor_id", "neighbor", "ip_address", "address", "peer_address", "mac",
    "INTERFACE", "VRF", "NAME", "PORT",
    "interface", "vrf", "name", "port",
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
        key_fields = _detect_key_fields(before, after)
        if key_fields:
            return _diff_list_by_key(before, after, path, key_fields)

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


def _diff_list_by_key(before: list, after: list, path: str, key_fields: tuple) -> list[dict]:
    def key(row):
        return "/".join(str(row[f]) for f in key_fields)
    b_map = {key(row): row for row in before}
    a_map = {key(row): row for row in after}
    label = "+".join(key_fields)
    diffs = []
    for k in sorted(set(b_map) | set(a_map)):
        child = f"{path}[{label}={k}]"
        if k not in b_map:
            diffs.append({"path": child, "before": None, "after": a_map[k]})
        elif k not in a_map:
            diffs.append({"path": child, "before": b_map[k], "after": None})
        else:
            diffs.extend(_diff_dict(b_map[k], a_map[k], child))
    return diffs


def _detect_key_fields(before: list, after: list):
    """Smallest set of natural-key fields that uniquely identifies rows on both
    sides: one field if any is unique, else all present natural keys combined.
    None -> caller falls back to positional diff."""
    rows = before + after
    # Mixed lists (None / str rows from partial parses) fall back to positional diff
    if not all(isinstance(row, dict) for row in rows):
        return None
    present = [f for f in _NATURAL_KEYS if all(f in row for row in rows)]

    def unique(fields):
        return all(
            len({tuple(str(r[f]) for f in fields) for r in side}) == len(side)
            for side in (before, after)
        )

    for f in present:
        if unique((f,)):
            return (f,)
    if len(present) > 1 and unique(tuple(present)):
        return tuple(present)
    return None
