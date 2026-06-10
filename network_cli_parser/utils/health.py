"""Health check evaluation against a JSON snapshot."""

import re
import sys
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Check validation
# ---------------------------------------------------------------------------

_VALID_CONDITIONS = {
    "eq", "ne", "gt", "gte", "lt", "lte",
    "contains", "not_contains", "matches",
    "one_of", "not_one_of",
    "duration_gt", "duration_gte", "duration_lt", "duration_lte",
    "len_eq", "len_ne", "len_gt", "len_gte", "len_lt", "len_lte",
    "date_before", "date_after", "date_within_days", "date_older_than_days",
    "diff_eq", "diff_ne", "diff_gt", "diff_gte", "diff_lt", "diff_lte",
    "diff_pct_gt", "diff_pct_gte", "diff_pct_lt", "diff_pct_lte",
}
_VALID_SEVERITIES = {"critical", "warn", "info"}
_VALID_MATCH      = {"all", "any"}


def validate_checks(checks: list, source: str = "") -> list[str]:
    """
    Validate a list of health check dicts.

    Prints [ERROR] lines to stderr and raises ValueError for fatal structural
    problems (missing required fields, unknown values).  Returns a list of
    non-fatal [WARN] strings (duplicate names, unrecognised condition names)
    that the caller may print.

    Args:
        checks: list of check dicts (output of _load_checks)
        source: label for error messages — e.g. the file path

    Returns:
        list of warning strings (empty when all checks are clean)

    Raises:
        ValueError: if any fatal validation errors are found
    """
    label  = f" in {source!r}" if source else ""
    seen: dict[str, int] = {}
    warnings: list[str] = []
    errors:   list[str] = []

    for i, check in enumerate(checks):
        pos = f"check[{i}]{label}"

        if not isinstance(check, dict):
            errors.append(f"{pos}: expected a dict, got {type(check).__name__}")
            continue

        name = check.get("name", "")
        if not name:
            errors.append(f"{pos}: missing required field 'name'")
        else:
            pos = f"'{name}'{label}"
            if name in seen:
                warnings.append(f"[WARN] duplicate check name {name!r} "
                                 f"(check[{i}] shadows check[{seen[name]}]){label}")
            seen[name] = i

        is_metadata_check     = "metadata"          in check
        is_cross_check        = "cross_check"        in check
        is_count_check        = "count"              in check
        is_baseline_check     = "compare_baseline"   in check

        if not is_metadata_check and not is_cross_check:
            if not check.get("command"):
                errors.append(f"{pos}: missing required field 'command'")
            if not is_count_check and not check.get("path"):
                errors.append(f"{pos}: missing required field 'path'")

        has_cond       = "condition" in check
        has_conditions = "conditions" in check
        has_branches   = "branches"  in check
        is_print_only  = (
            not has_cond and not has_conditions and not has_branches
            and "value" not in check
            and not is_count_check and not is_baseline_check and not is_metadata_check
        )

        if not is_print_only and not is_count_check and not is_baseline_check \
                and not is_metadata_check and not is_cross_check:
            if not has_cond and not has_conditions and not has_branches:
                errors.append(f"{pos}: must have 'condition', 'conditions', or 'branches'")

            if has_cond:
                cond = check.get("condition")
                if cond not in _VALID_CONDITIONS:
                    warnings.append(
                        f"[WARN] {pos}: unknown condition {cond!r} "
                        f"(known: {', '.join(sorted(_VALID_CONDITIONS))})"
                    )
                if "value" not in check:
                    errors.append(f"{pos}: condition {cond!r} requires a 'value' field")
                elif cond in ("one_of", "not_one_of") and not isinstance(check.get("value"), list):
                    errors.append(f"{pos}: condition {cond!r} requires 'value' to be a list")

            if has_conditions:
                for j, spec in enumerate(check.get("conditions", [])):
                    if not isinstance(spec, dict):
                        errors.append(f"{pos}: conditions[{j}]: expected a dict")
                        continue
                    c = spec.get("condition")
                    if c not in _VALID_CONDITIONS:
                        warnings.append(
                            f"[WARN] {pos}: conditions[{j}]: unknown condition {c!r}"
                        )
                    if "value" not in spec:
                        errors.append(f"{pos}: conditions[{j}]: missing 'value'")

        if is_cross_check:
            cc = check.get("cross_check")
            if not isinstance(cc, dict):
                errors.append(f"{pos}: cross_check must be a dict with 'if' and 'then'")
            else:
                if not isinstance(cc.get("if"), dict):
                    errors.append(f"{pos}: cross_check missing 'if' dict")
                then_spec = cc.get("then")
                if not isinstance(then_spec, dict):
                    errors.append(f"{pos}: cross_check missing 'then' dict")
                elif not isinstance(then_spec.get("assert"), dict):
                    errors.append(f"{pos}: cross_check 'then' missing 'assert' dict")

        if "branches" in check:
            branches = check.get("branches")
            if not isinstance(branches, list):
                errors.append(f"{pos}: branches must be a list")
            else:
                for j, b in enumerate(branches):
                    if not isinstance(b, dict):
                        errors.append(f"{pos}: branches[{j}]: expected a dict")
                    elif "when" in b and not isinstance(b.get("then"), dict):
                        errors.append(f"{pos}: branches[{j}]: 'when' without a 'then' dict")
                    elif "when" not in b and "default" not in b:
                        errors.append(f"{pos}: branches[{j}]: needs 'when'+'then' or 'default'")

        skip_spec = check.get("skip_if")
        if skip_spec is not None:
            if not isinstance(skip_spec, dict):
                errors.append(f"{pos}: skip_if must be a dict")
            else:
                if "metadata" not in skip_spec:
                    warnings.append(
                        f"[WARN] {pos}: skip_if has no 'metadata' field — "
                        f"the check will never be skipped"
                    )
                sc = skip_spec.get("condition", "eq")
                if sc not in _VALID_CONDITIONS:
                    warnings.append(
                        f"[WARN] {pos}: skip_if: unknown condition {sc!r} — "
                        f"the check will never be skipped"
                    )

        sev = check.get("severity")
        if sev and sev not in _VALID_SEVERITIES:
            warnings.append(
                f"[WARN] {pos}: unknown severity {sev!r} "
                f"(valid: {', '.join(sorted(_VALID_SEVERITIES))})"
            )

        match = check.get("match")
        if match and match not in _VALID_MATCH:
            warnings.append(
                f"[WARN] {pos}: unknown match value {match!r} (valid: all, any)"
            )

    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        raise ValueError(
            f"{len(errors)} validation error(s){label} — fix and retry"
        )

    return warnings


def evaluate_checks(snapshot: dict, checks: list[dict],
                    baseline: dict = None, tags: list = None) -> dict:
    commands          = snapshot.get("commands", {})
    metadata          = snapshot.get("metadata", {})
    baseline_commands = baseline.get("commands", {}) if baseline else {}

    # Filter by tags if provided (OR logic: check passes filter if it has any requested tag)
    if tags:
        tag_set = set(tags)
        checks = [c for c in checks if set(c.get("tags", [])) & tag_set]

    results = [_safe_run_check(c, commands, metadata, baseline_commands) for c in checks]

    passed  = sum(1 for r in results if r["status"] == "pass")
    failed  = sum(1 for r in results if r["status"] == "fail")
    errored = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skip")

    def _sev(r):
        s = r.get("severity", "critical")
        # unknown severities gate the exit code like critical rather than vanishing
        return s if s in ("critical", "warn", "info") else "critical"

    return {
        "metadata": snapshot.get("metadata", {}),
        "summary": {
            "total":   len(results),
            "passed":  passed,
            "failed":  failed,
            "error":   errored,
            "skipped": skipped,
            "failed_critical": sum(1 for r in results if r["status"] == "fail" and _sev(r) == "critical"),
            "failed_warn":     sum(1 for r in results if r["status"] == "fail" and _sev(r) == "warn"),
            "failed_info":     sum(1 for r in results if r["status"] == "fail" and _sev(r) == "info"),
        },
        "results": results,
    }


def _safe_run_check(check, commands: dict, metadata: dict, baseline_commands: dict) -> dict:
    """One malformed check must not abort the whole run — degrade to an error result."""
    try:
        return _run_check(check, commands, metadata, baseline_commands)
    except Exception as exc:
        name = check.get("name", "(unnamed)") if isinstance(check, dict) else "(invalid)"
        sev  = check.get("severity", "critical") if isinstance(check, dict) else "critical"
        return _result_error(name, check if isinstance(check, dict) else {},
                             f"Check crashed: {type(exc).__name__}: {exc}", sev)


def _eval_skip_if(skip_spec: dict, metadata: dict) -> bool:
    """Return True if the check should be skipped (skip condition is satisfied)."""
    if not isinstance(skip_spec, dict):
        return False
    condition = skip_spec.get("condition", "eq")
    expected  = skip_spec.get("value")
    if "metadata" in skip_spec:
        actual = (metadata or {}).get(skip_spec["metadata"])
        ok, _ = _apply_condition(actual, condition, expected)
        return ok
    return False


def _run_check(check: dict, commands: dict,
               metadata: dict = None, baseline_commands: dict = None) -> dict:
    name      = check.get("name", "(unnamed)")
    cmd       = check.get("command", "")
    path      = check.get("path", "")
    condition = check.get("condition", "eq")
    expected  = check.get("value")
    severity  = check.get("severity", "critical")
    print_tpl = check.get("print")

    # skip_if: evaluate before everything else
    if "skip_if" in check and _eval_skip_if(check["skip_if"], metadata or {}):
        return {"name": name, "status": "skip", "severity": severity, "check": check,
                "note": "skip_if condition matched"}

    if "metadata" in check:
        return _run_metadata_check(check, metadata or {})

    if "cross_check" in check:
        return _run_cross_check(check, commands, metadata or {})

    if cmd not in commands:
        return _result_error(name, check, f"Command '{cmd}' not in snapshot", severity)

    parsed = commands[cmd].get("parsed", {})

    try:
        values = _resolve_path(parsed, path)
    except (KeyError, IndexError, TypeError) as exc:
        return _result_error(name, check, f"Path resolution failed: {exc}", severity)

    # count: — must run even when the path expands to 0 items ("at least N
    # neighbors" has to FAIL when all neighbors are gone, not vacuously pass)
    if "count" in check:
        return _run_check_count(check, name, severity, values)

    # [*] expanding an empty list is vacuously true for match: all — but an
    # existential check (match: any) over 0 items has nothing to satisfy it,
    # and a baseline comparison over 0 items means the values disappeared.
    if not values:
        if check.get("match") == "any":
            return {"name": name, "status": "fail", "severity": severity, "check": check,
                    "failures": [{"path": path, "actual": None,
                                  "message": f"Path '{path}' resolved to 0 items — "
                                             f"no value can satisfy a match: any check"}]}
        if "compare_baseline" in check:
            return _result_error(name, check,
                                 f"Path '{path}' resolved to 0 items in current snapshot — "
                                 f"cannot compare against baseline", severity)
        return {
            "name":     name,
            "status":   "pass",
            "severity": severity,
            "check":    check,
            "actual":   [],
            "note":     f"Path '{path}' resolved to 0 items (vacuously true)",
        }

    # compare_baseline: — delta check against a previous snapshot
    if "compare_baseline" in check:
        return _run_compare_baseline(check, name, severity, cmd, path, values, baseline_commands)

    # Print-only: no condition/value/conditions/branches — just surface the resolved values
    is_print_only = (
        "condition" not in check
        and "value"      not in check
        and "conditions" not in check
        and "branches"   not in check
    )
    if is_print_only:
        tpl = print_tpl if print_tpl is not None else True
        printed = [_format_print(tpl, rp, act, parsed) for rp, act in values]
        return {
            "name":       name,
            "status":     "pass",
            "severity":   severity,
            "check":      check,
            "printed":    printed,
            "print_only": True,
            "note":       f"{len(values)} value(s) resolved",
        }

    match_mode = check.get("match", "all")
    if match_mode not in ("all", "any"):
        print(f"[WARN] check '{name}': unknown match mode '{match_mode}' — treating as 'all'")
        match_mode = "all"

    if "branches" in check:
        return _run_check_branches(check, name, severity, match_mode, values, print_tpl, parsed,
                                   metadata or {})
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


def _run_metadata_check(check: dict, metadata: dict) -> dict:
    """Check a field from snapshot metadata."""
    name      = check.get("name", "(unnamed)")
    severity  = check.get("severity", "critical")
    field     = check["metadata"]
    condition = check.get("condition", "eq")
    expected  = check.get("value")

    actual = metadata.get(field)
    if actual is None:
        return _result_error(name, check, f"metadata field '{field}' not found in snapshot", severity)

    ok, msg = _apply_condition(actual, condition, expected)
    if ok:
        return {"name": name, "status": "pass", "severity": severity, "check": check, "actual": [actual]}
    return {"name": name, "status": "fail", "severity": severity, "check": check,
            "failures": [{"path": f"metadata.{field}", "actual": actual, "message": msg}]}


def _run_check_count(check: dict, name: str, severity: str, values: list) -> dict:
    """Assert the number of items resolved by the path."""
    count_spec = check["count"]
    if not isinstance(count_spec, dict):
        return _result_error(name, check, "count must be a dict with condition/value", severity)
    condition  = count_spec.get("condition", "eq")
    expected   = count_spec.get("value")
    # A path-less count over a parsed list counts the rows, not "1 blob"
    if len(values) == 1 and values[0][0] == "" and isinstance(values[0][1], (list, dict)):
        actual_cnt = len(values[0][1])
    else:
        actual_cnt = len(values)

    ok, msg = _apply_condition(actual_cnt, condition, expected)
    if ok:
        return {"name": name, "status": "pass", "severity": severity, "check": check,
                "actual": [actual_cnt], "note": f"{actual_cnt} item(s) resolved"}
    return {"name": name, "status": "fail", "severity": severity, "check": check,
            "failures": [{"path": "count", "actual": actual_cnt, "message": msg}]}


def _run_compare_baseline(check: dict, name: str, severity: str,
                          cmd: str, path: str, values: list,
                          baseline_commands: dict) -> dict:
    """Compare current values against the same path in the baseline snapshot."""
    if not baseline_commands:
        return _result_error(name, check, "compare_baseline requires --baseline snapshot", severity)

    cb_spec   = check["compare_baseline"]
    condition = cb_spec.get("condition", "eq")
    cb_value  = cb_spec.get("value")    # only used for diff_* conditions

    if cmd not in baseline_commands:
        return _result_error(name, check, f"Command '{cmd}' not found in baseline snapshot", severity)

    baseline_parsed = baseline_commands[cmd].get("parsed", {})
    try:
        baseline_vals = _resolve_path(baseline_parsed, path)
    except Exception as exc:
        return _result_error(name, check, f"Baseline path resolution failed: {exc}", severity)

    baseline_map = {rp: v for rp, v in baseline_vals}

    failures, passes = [], []
    for resolved_path, actual in values:
        if resolved_path not in baseline_map:
            failures.append({"path": resolved_path, "actual": actual,
                             "message": f"path not found in baseline snapshot"})
            continue
        baseline_val = baseline_map[resolved_path]

        if condition.startswith("diff"):
            try:
                a, b = float(actual), float(baseline_val)
                diff = abs(a - b)
                if condition.endswith("pct_lte") or condition.endswith("pct_gte") \
                        or condition.endswith("pct_lt") or condition.endswith("pct_gt"):
                    if b == 0:
                        # baseline 0: no change → 0%, any change → infinite %
                        pct = 0.0 if a == 0 else float("inf")
                        ops = {"diff_pct_lte": pct <= float(cb_value),
                               "diff_pct_gte": pct >= float(cb_value),
                               "diff_pct_lt":  pct <  float(cb_value),
                               "diff_pct_gt":  pct >  float(cb_value)}
                        ok  = ops.get(condition, False)
                        msg = (f"baseline is 0 — change treated as "
                               f"{'0%' if a == 0 else 'infinite %'}, not "
                               f"{condition.split('_', 1)[1]} {cb_value}%")
                    else:
                        pct = diff / abs(b) * 100
                        ops = {"diff_pct_lte": pct <= float(cb_value),
                               "diff_pct_gte": pct >= float(cb_value),
                               "diff_pct_lt":  pct <  float(cb_value),
                               "diff_pct_gt":  pct >  float(cb_value)}
                        ok  = ops.get(condition, False)
                        msg = f"|{actual} - {baseline_val}| / {baseline_val} * 100 = {pct:.1f}% not {condition.split('_',1)[1]} {cb_value}%"
                else:
                    ops = {"diff_lte": diff <= float(cb_value),
                           "diff_gte": diff >= float(cb_value),
                           "diff_lt":  diff <  float(cb_value),
                           "diff_gt":  diff >  float(cb_value),
                           "diff_eq":  diff == float(cb_value),
                           "diff_ne":  diff != float(cb_value)}
                    ok  = ops.get(condition, False)
                    msg = f"|{actual} - {baseline_val}| = {diff} not {condition.split('_',1)[1]} {cb_value}"
            except (ValueError, TypeError) as exc:
                ok, msg = False, f"Diff condition error: {exc}"
        else:
            ok, msg = _apply_condition(actual, condition, baseline_val)

        (passes if ok else failures).append({"path": resolved_path, "actual": actual,
                                              "baseline": baseline_val, "message": msg})

    if failures:
        return {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
    return {"name": name, "status": "pass", "severity": severity, "check": check,
            "actual": [p["actual"] for p in passes]}


def _run_cross_check(check: dict, commands: dict, metadata: dict = None) -> dict:
    """Cross-row check: IF rows matching one condition exist, THEN assert on different rows."""
    name        = check.get("name", "(unnamed)")
    severity    = check.get("severity", "critical")
    cc          = check["cross_check"]
    default_cmd = check.get("command", "")
    metadata    = metadata or {}

    if_spec   = cc["if"]
    then_spec = cc["then"]

    # IF side — may use metadata instead of a command path
    if_cond  = if_spec.get("condition", "eq")
    if_value = if_spec.get("value")

    if "metadata" in if_spec:
        meta_field = if_spec["metadata"]
        actual = metadata.get(meta_field)
        ok, _ = _apply_condition(actual, if_cond, if_value)
        if_matches = [("metadata." + meta_field, actual)] if ok else []
    else:
        if_cmd   = if_spec.get("command", default_cmd)
        if_field = if_spec.get("field", "")
        if if_cmd not in commands:
            return _result_error(name, check, f"Command '{if_cmd}' not in snapshot", severity)
        if_parsed = commands[if_cmd].get("parsed", {})
        try:
            if_rows = _resolve_path(if_parsed, if_spec.get("path", ""))
        except Exception as exc:
            return _result_error(name, check, f"IF path resolution failed: {exc}", severity)
        if_matches = []
        for rp, row in if_rows:
            actual = row.get(if_field) if isinstance(row, dict) else row
            ok, _ = _apply_condition(actual, if_cond, if_value)
            if ok:
                if_matches.append((rp, row))

    if not if_matches:
        return {"name": name, "status": "pass", "severity": severity, "check": check,
                "actual": [], "note": "IF condition matched 0 rows — check not applicable"}

    # THEN side
    then_cmd    = then_spec.get("command", default_cmd)
    then_filter = then_spec.get("filter", {})
    then_assert = then_spec["assert"]
    then_field  = then_assert.get("field", "")
    then_cond   = then_assert.get("condition", "eq")
    then_value  = then_assert.get("value")

    if then_cmd not in commands:
        return _result_error(name, check, f"Command '{then_cmd}' not in snapshot", severity)
    then_parsed = commands[then_cmd].get("parsed", {})
    try:
        then_rows = _resolve_path(then_parsed, then_spec.get("path", ""))
    except Exception as exc:
        return _result_error(name, check, f"THEN path resolution failed: {exc}", severity)

    if then_filter:
        f_field = then_filter.get("field", "")
        f_cond  = then_filter.get("condition", "eq")
        f_value = then_filter.get("value")
        then_rows = [
            (rp, row) for rp, row in then_rows
            if isinstance(row, dict) and _apply_condition(row.get(f_field), f_cond, f_value)[0]
        ]

    if not then_rows:
        return _result_error(name, check, "THEN target resolved to 0 rows after filter", severity)

    failures, passes = [], []
    for rp, row in then_rows:
        actual    = row.get(then_field) if isinstance(row, dict) else row
        item_path = f"{rp}.{then_field}" if then_field else rp
        ok, msg   = _apply_condition(actual, then_cond, then_value)
        (passes if ok else failures).append({"path": item_path, "actual": actual, "message": msg})

    if failures:
        return {"name": name, "status": "fail", "severity": severity, "check": check, "failures": failures}
    return {"name": name, "status": "pass", "severity": severity, "check": check,
            "actual": [p["actual"] for p in passes]}


def _run_check_branches(check: dict, name: str, severity: str, match_mode: str,
                     values: list, print_tpl, parsed, metadata: dict = None) -> dict:
    """IF/ELIF/ELSE logic: for each resolved dict row, find the first matching branch."""
    branches     = check.get("branches", [])
    default_spec = next((b["default"] for b in branches if "default" in b), None)
    when_specs   = [b for b in branches if "when" in b]
    metadata     = metadata or {}

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
            # when: can match a metadata field instead of a row field
            if "metadata" in when:
                field_val = metadata.get(when["metadata"])
            else:
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
    # Split on dots that are not inside [brackets] — dict keys may contain
    # dots (e.g. peers[10.2.240.1].state from a resolved wildcard path)
    for part in re.split(r'\.(?![^\[]*\])', path):
        if not part:
            continue
        m = re.match(r'^(.*?)\[([^\]]+)\](.*)$', part)
        if m:
            key, idx, rest = m.group(1), m.group(2), m.group(3)
            if key:
                tokens.append(key)
            if idx == "*":
                tokens.append("*")
            elif idx.isdigit():
                tokens.append(int(idx))
            else:
                tokens.append(idx)   # literal dict key, e.g. [10.2.240.1] or [default]
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


_DATE_FORMATS = [
    "%d-%b-%Y",   # 03-May-2026
    "%d-%b-%y",   # 03-May-26
    "%d-%m-%Y",   # 03-05-2026
    "%d/%m/%Y",   # 03/05/2026
    "%Y-%m-%d",   # 2026-05-03
    "%Y/%m/%d",   # 2026/05/03
    "%b %d %Y",   # May 03 2026
    "%d %b %Y",   # 03 May 2026
    "%b %d, %Y",  # May 3, 2026
    "%Y-%m-%dT%H:%M:%S",  # ISO with time
    "%Y-%m-%d %H:%M:%S",  # ISO with space
    "%d-%b-%Y %H:%M:%S",  # 03-May-2026 10:00:00
]


def _parse_date(s: str):
    """Parse a calendar date string. Returns datetime or None if unrecognised."""
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_duration(s: str) -> float:
    s = s.strip()
    # Try calendar date first — convert to age in seconds (positive = past, negative = future)
    dt = _parse_date(s)
    if dt is not None:
        return (datetime.now() - dt).total_seconds()
    s = s.lower()
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
        if condition in ("len_eq", "len_ne", "len_gt", "len_gte", "len_lt", "len_lte"):
            n = len(actual)
            e = int(expected)
            base = condition[4:]  # strip "len_"
            ops = {"eq": n == e, "ne": n != e, "gt": n > e, "gte": n >= e, "lt": n < e, "lte": n <= e}
            sym = {"eq": "==", "ne": "!=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            ok  = ops[base]
            return ok, f"len({actual!r}) = {n}, not {sym[base]} {e}"
        if condition in ("date_before", "date_after"):
            dt_actual   = _parse_date(str(actual))
            dt_expected = _parse_date(str(expected))
            if dt_actual is None:
                return False, f"Cannot parse date from {actual!r}"
            if dt_expected is None:
                return False, f"Cannot parse expected date from {expected!r}"
            ok = (dt_actual < dt_expected) if condition == "date_before" else (dt_actual > dt_expected)
            sym = "<" if condition == "date_before" else ">"
            return ok, f"{actual!r} is not {sym} {expected!r}"
        if condition in ("date_within_days", "date_older_than_days"):
            dt_actual = _parse_date(str(actual))
            if dt_actual is None:
                return False, f"Cannot parse date from {actual!r}"
            age_days = (datetime.now() - dt_actual).total_seconds() / 86400
            e_days   = float(expected)
            ok = (age_days <= e_days) if condition == "date_within_days" else (age_days > e_days)
            sym = "<=" if condition == "date_within_days" else ">"
            return ok, f"date {actual!r} is {age_days:.1f} days old, not {sym} {e_days} days"
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
