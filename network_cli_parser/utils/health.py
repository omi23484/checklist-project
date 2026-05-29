"""Health check evaluation against a JSON snapshot."""

import re
from typing import Any


def evaluate_checks(snapshot: dict, checks: list[dict]) -> dict:
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
            "failed_critical": sum(1 for r in results if r["status"] == "fail" and r.get("severity", "critical") == "critical"),
            "failed_warn":     sum(1 for r in results if r["status"] == "fail" and r.get("severity", "critical") == "warn"),
            "failed_info":     sum(1 for r in results if r["status"] == "fail" and r.get("severity", "critical") == "info"),
        },
        "results": results,
    }


def _run_check(check: dict, commands: dict) -> dict:
    name      = check.get("name", "(unnamed)")
    cmd       = check.get("command", "")
    path      = check.get("path", "")
    condition = check.get("condition", "eq")
    expected  = check.get("value")
    severity  = check.get("severity", "critical")
    print_tpl = check.get("print")

    if cmd not in commands:
        return _result_error(name, check, f"Command '{cmd}' not in snapshot", severity)

    parsed = commands[cmd].get("parsed", {})

    try:
        values = _resolve_path(parsed, path)
    except (KeyError, IndexError, TypeError) as exc:
        return _result_error(name, check, f"Path resolution failed: {exc}", severity)

    # [*] expanding an empty list is vacuously true — no items to violate the condition
    if not values:
        return {
            "name":     name,
            "status":   "pass",
            "severity": severity,
            "check":    check,
            "actual":   [],
            "note":     f"Path '{path}' resolved to 0 items (vacuously true)",
        }

    match_mode = check.get("match", "all")
    if match_mode not in ("all", "any"):
        print(f"[WARN] check '{name}': unknown match mode '{match_mode}' — treating as 'all'")
        match_mode = "all"

    if "branches" in check:
        return _run_check_branches(check, name, severity, match_mode, values, print_tpl, parsed)
    if "conditions" in check:
        return _run_check_multi(check, name, severity, match_mode, values, print_tpl, parsed)

    # Single condition/value — existing logic
    failures, passes = [], []
    for resolved_path, actual in values:
        ok, msg = _apply_condition(actual, condition, expected)
        (passes if ok else failures).append({"path": resolved_path, "actual": actual, "message": msg})

    printed = [_format_print(print_tpl, rp, act, parsed) for rp, act in values] if print_tpl is not None else None

    if match_mode == "any":
        if passes:
            r = {"name": name, "status": "pass", "severity": severity, "check": check,
                 "actual": [f["actual"] for f in passes]}
        else:
            r = {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
    else:
        if failures:
            r = {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
        else:
            r = {"name": name, "status": "pass", "severity": severity, "check": check,
                 "actual": [v for _, v in values]}
    if printed is not None:
        r["printed"] = printed
    return r


def _run_check_multi(check: dict, name: str, severity: str, match_mode: str,
                     values: list, print_tpl, parsed) -> dict:
    """AND logic: every condition in `conditions` must pass for an item to pass."""
    cond_specs = check.get("conditions", [])
    failures, passes = [], []
    for resolved_path, actual in values:
        item_msgs = []
        for spec in cond_specs:
            ok, msg = _apply_condition(actual, spec.get("condition", "eq"), spec.get("value"))
            if not ok:
                item_msgs.append(msg)
        if item_msgs:
            failures.append({"path": resolved_path, "actual": actual, "messages": item_msgs})
        else:
            passes.append({"path": resolved_path, "actual": actual})

    printed = [_format_print(print_tpl, rp, act, parsed) for rp, act in values] if print_tpl is not None else None

    if match_mode == "any":
        if passes:
            r = {"name": name, "status": "pass", "severity": severity, "check": check,
                 "actual": [p["actual"] for p in passes]}
        else:
            r = {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
    else:
        if failures:
            r = {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
        else:
            r = {"name": name, "status": "pass", "severity": severity, "check": check,
                 "actual": [p["actual"] for p in passes]}
    if printed is not None:
        r["printed"] = printed
    return r


def _run_check_branches(check: dict, name: str, severity: str, match_mode: str,
                        values: list, print_tpl, parsed) -> dict:
    """IF/ELIF/ELSE logic: for each resolved dict row, find the first matching branch."""
    branches     = check.get("branches", [])
    default_spec = next((b["default"] for b in branches if "default" in b), None)
    when_specs   = [b for b in branches if "when" in b]

    failures, passes, printed_lines = [], [], []
    for resolved_path, row in values:
        if not isinstance(row, dict):
            msg = f"branches requires dict rows; got {type(row).__name__}"
            failures.append({"path": resolved_path, "actual": row, "message": msg})
            if print_tpl is not None:
                printed_lines.append(_format_print(print_tpl, resolved_path, row, parsed))
            continue

        then_spec = None
        for b in when_specs:
            when = b["when"]
            field_val = row.get(when.get("field", ""))
            ok, _ = _apply_condition(field_val, when.get("condition", "eq"), when.get("value"))
            if ok:
                then_spec = b["then"]
                break

        if then_spec is None:
            then_spec = default_spec

        if then_spec is None:
            # No branch matched and no default → vacuously pass this row
            passes.append({"path": resolved_path, "actual": None, "note": "no branch matched"})
            if print_tpl is not None:
                printed_lines.append(_format_print(print_tpl, resolved_path, "(no branch matched)", parsed))
            continue

        then_field = then_spec.get("field", "")
        check_val  = row.get(then_field)
        item_path  = f"{resolved_path}.{then_field}" if then_field else resolved_path
        ok, msg    = _apply_condition(check_val, then_spec.get("condition", "eq"), then_spec.get("value"))
        (passes if ok else failures).append({"path": item_path, "actual": check_val, "message": msg})
        if print_tpl is not None:
            printed_lines.append(_format_print(print_tpl, item_path, check_val, parsed))

    printed = printed_lines if print_tpl is not None else None

    if match_mode == "any":
        if passes:
            r = {"name": name, "status": "pass", "severity": severity, "check": check,
                 "actual": [p["actual"] for p in passes]}
        else:
            r = {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
    else:
        if failures:
            r = {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
        else:
            r = {"name": name, "status": "pass", "severity": severity, "check": check,
                 "actual": [p["actual"] for p in passes]}
    if printed is not None:
        r["printed"] = printed
    return r


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _resolve_path(data: Any, path: str) -> list[tuple[str, Any]]:
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
                if rest and not isinstance(v, (dict, list)):
                    continue  # skip flat scalars when more path tokens remain
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

_DURATION_UNITS = [
    (re.compile(r'(\d+)\s*y(?:ear)?s?',           re.IGNORECASE), 365 * 86400),
    (re.compile(r'(\d+)\s*w(?:eek)?s?',           re.IGNORECASE), 7   * 86400),
    (re.compile(r'(\d+)\s*d(?:ay)?s?',            re.IGNORECASE), 86400),
    (re.compile(r'(\d+)\s*h(?:our)?s?',           re.IGNORECASE), 3600),
    (re.compile(r'(\d+)\s*m(?:in(?:ute)?)?s?',    re.IGNORECASE), 60),
    (re.compile(r'(\d+)\s*s(?:ec(?:ond)?)?s?',    re.IGNORECASE), 1),
]
_HH_MM_SS = re.compile(r'^(\d+):(\d+):(\d+)$')
_HH_MM    = re.compile(r'^(\d+):(\d+)$')
_ZERO_KEYWORDS = {"never", "n/a", "unknown", "-", ""}


def _parse_duration(s: str) -> float:
    s = s.strip().lower()
    if s in _ZERO_KEYWORDS:
        return 0.0
    m = _HH_MM_SS.match(s)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = _HH_MM.match(s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    total = 0.0
    for pattern, mult in _DURATION_UNITS:
        for n in pattern.findall(s):
            total += int(n) * mult
    if total == 0.0:
        try:
            total = float(s)
        except (ValueError, TypeError):
            pass
    return total


def _format_print(template, path: str, value, data=None) -> str:
    if template is True:
        return f"{path} -> {value!r}"
    s = str(template)
    wildcard_keys = re.findall(r'\[([^\]]+)\]', path)
    s = s.replace('{{[*]}}', wildcard_keys[0] if wildcard_keys else '')
    s = re.sub(
        r'\{\{\[\*\]\[(\d+)\]\}\}',
        lambda m: wildcard_keys[int(m.group(1))] if int(m.group(1)) < len(wildcard_keys) else '',
        s,
    )
    if data is not None:
        parent = re.sub(r'\.[^.\[]+$', '', path)
        def _sibling(m):
            field = m.group(1)
            sibling_path = f"{parent}.{field}" if parent else field
            try:
                results = _resolve_path(data, sibling_path)
                return str(results[0][1]) if results else ''
            except Exception:
                return ''
        s = re.sub(r'\{\{\.(\w+)\}\}', _sibling, s)
    s = s.replace('{{value}}', str(value)).replace('{{path}}', str(path))
    s = s.replace('{value}', str(value)).replace('{path}', str(path))
    return s


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
        if condition in ("duration_gt", "duration_gte", "duration_lt", "duration_lte"):
            a_s = _parse_duration(str(actual))
            e_s = _parse_duration(str(expected))
            ops = {"duration_gt": a_s > e_s, "duration_gte": a_s >= e_s,
                   "duration_lt": a_s < e_s, "duration_lte": a_s <= e_s}
            sym = {"duration_gt": ">", "duration_gte": ">=",
                   "duration_lt": "<",  "duration_lte": "<="}
            ok = ops[condition]
            return ok, (f"duration({actual!r}) = {a_s:.0f}s, "
                        f"not {sym[condition]} {e_s:.0f}s ({expected!r})")
        if condition == "one_of":
            if not isinstance(expected, list):
                return False, f"one_of requires a list value, got {type(expected).__name__}"
            ok = actual in expected
            return ok, f"{actual!r} not in {expected!r}"
        if condition == "not_one_of":
            if not isinstance(expected, list):
                return False, f"not_one_of requires a list value, got {type(expected).__name__}"
            ok = actual not in expected
            return ok, f"{actual!r} is in {expected!r} (should not be)"
        return False, f"Unknown condition: {condition!r}"
    except (ValueError, TypeError, re.error) as exc:
        return False, f"Condition error: {exc}"


def merge_checks(default: list[dict], override: list[dict]) -> list[dict]:
    merged = {}
    for c in default:
        if "name" not in c:
            raise ValueError(f"check entry is missing required 'name' field: {c}")
        merged[c["name"]] = c
    for c in override:
        if "name" not in c:
            raise ValueError(f"check entry is missing required 'name' field: {c}")
        merged[c["name"]] = c
    return list(merged.values())


def _result_error(name: str, check: dict, message: str, severity: str = "critical") -> dict:
    return {"name": name, "status": "error", "severity": severity, "check": check, "message": message}
