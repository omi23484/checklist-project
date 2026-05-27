"""Health check evaluation against a JSON snapshot."""

import re
from typing import Any


def evaluate_checks(snapshot: dict, checks: list[dict]) -> dict:
    """Run health checks against a snapshot. Returns a structured results dict."""
    commands = snapshot.get("commands", {})
    results = [_run_check(c, commands) for c in checks]

    passed  = sum(1 for r in results if r["status"] == "pass")
    failed  = sum(1 for r in results if r["status"] == "fail")
    errored = sum(1 for r in results if r["status"] == "error")

    return {
        "metadata": snapshot.get("metadata", {}),
        "summary": {
            "total":  len(results),
            "passed": passed,
            "failed": failed,
            "error":  errored,
        },
        "results": results,
    }


def _run_check(check: dict, commands: dict) -> dict:
    name      = check.get("name", "(unnamed)")
    cmd       = check.get("command", "")
    path      = check.get("path", "")
    condition = check.get("condition", "eq")
    expected  = check.get("value")

    if cmd not in commands:
        return _result_error(name, check, f"Command '{cmd}' not in snapshot")

    parsed = commands[cmd].get("parsed", {})

    try:
        values = _resolve_path(parsed, path)
    except (KeyError, IndexError, TypeError) as exc:
        return _result_error(name, check, f"Path resolution failed: {exc}")

    # [*] expanding an empty list is vacuously true — no items to violate the condition
    if not values:
        return {
            "name":   name,
            "status": "pass",
            "check":  check,
            "actual": [],
            "note":   f"Path '{path}' resolved to 0 items (vacuously true)",
        }

    match_mode = check.get("match", "all")
    failures, passes = [], []
    for resolved_path, actual in values:
        ok, msg = _apply_condition(actual, condition, expected)
        (passes if ok else failures).append({"path": resolved_path, "actual": actual, "message": msg})

    if match_mode == "any":
        if passes:
            return {"name": name, "status": "pass", "check": check,
                    "actual": [f["actual"] for f in passes]}
        return {"name": name, "status": "fail", "check": check, "failures": failures}
    else:  # all (default — preserves existing behaviour exactly)
        if failures:
            return {"name": name, "status": "fail", "check": check, "failures": failures}
        return {"name": name, "status": "pass", "check": check,
                "actual": [v for _, v in values]}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_path(data: Any, path: str) -> list[tuple[str, Any]]:
    """
    Resolve a dot-notation path with optional list indexing into (path, value) pairs.

    Syntax:
      [N]   — select index N from a list
      [*]   — expand all items in a list (each becomes a separate result)
      .key  — dict key access

    Examples:
      "[0].VERSION"                        -> list index 0, then VERSION field
      "[*].state_pfx"                      -> all items' state_pfx
      "vrfs[*].neighbors[*].state_pfx"     -> nested list expansion
      "vrfs.default.summary.total_groups"  -> nested dict access
    """
    return _resolve(data, _tokenize(path), "")


def _tokenize(path: str) -> list:
    tokens: list = []
    for part in path.split("."):
        if not part:
            continue
        m = re.match(r'^(.*?)\[(\*|\d+)\](.*)$', part)
        if m:
            key, idx, rest = m.group(1), m.group(2), m.group(3)
            if key:
                tokens.append(key)
            tokens.append("*" if idx == "*" else int(idx))
            if rest:
                tokens.extend(_tokenize(rest))
        else:
            tokens.append(part)
    return tokens


def _resolve(data: Any, tokens: list, current_path: str) -> list[tuple[str, Any]]:
    if not tokens:
        return [(current_path, data)]

    token = tokens[0]
    rest  = tokens[1:]

    if token == "*":
        if isinstance(data, list):
            results = []
            for i, item in enumerate(data):
                results.extend(_resolve(item, rest, f"{current_path}[{i}]"))
            return results
        if isinstance(data, dict):
            results = []
            for k, v in data.items():
                results.extend(_resolve(v, rest, f"{current_path}[{k}]"))
            return results
        raise TypeError(
            f"Expected list or dict at '{current_path}', got {type(data).__name__}"
        )

    if isinstance(token, int):
        if not isinstance(data, list):
            raise TypeError(
                f"Expected list at '{current_path}', got {type(data).__name__}"
            )
        return _resolve(data[token], rest, f"{current_path}[{token}]")

    # String key — dict lookup
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected dict at '{current_path}', got {type(data).__name__}"
        )
    child_path = f"{current_path}.{token}" if current_path else token
    return _resolve(data[token], rest, child_path)


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def _apply_condition(actual: Any, condition: str, expected: Any) -> tuple[bool, str]:
    try:
        if condition == "eq":
            ok = actual == expected
            return ok, f"{actual!r} != {expected!r}"
        if condition == "ne":
            ok = actual != expected
            return ok, f"{actual!r} == {expected!r} (expected not equal)"
        if condition in ("gt", "lt", "gte", "lte"):
            a, e = float(actual), float(expected)
            ops = {"gt": a > e, "lt": a < e, "gte": a >= e, "lte": a <= e}
            sym = {"gt": ">",   "lt": "<",   "gte": ">=",  "lte": "<="}
            ok  = ops[condition]
            return ok, f"{actual} not {sym[condition]} {expected}"
        if condition == "contains":
            ok = expected in str(actual)
            return ok, f"{actual!r} does not contain {expected!r}"
        if condition == "not_contains":
            ok = expected not in str(actual)
            return ok, f"{actual!r} contains {expected!r} (should not)"
        if condition == "matches":
            ok = bool(re.search(str(expected), str(actual)))
            return ok, f"{actual!r} does not match pattern {expected!r}"
        return False, f"Unknown condition: {condition!r}"
    except (ValueError, TypeError) as exc:
        return False, f"Condition error: {exc}"


def merge_checks(default: list[dict], override: list[dict]) -> list[dict]:
    """
    Union of two check lists; override wins on name clash.

    All checks from both lists are included. When the same `name` appears
    in both, the override version replaces the default.
    """
    merged = {c["name"]: c for c in default}
    merged.update({c["name"]: c for c in override})
    return list(merged.values())


def _result_error(name: str, check: dict, message: str) -> dict:
    return {"name": name, "status": "error", "check": check, "message": message}
