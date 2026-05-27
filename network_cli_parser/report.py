"""
Network CLI Report Generator

Usage:
    python report.py delta      --before <old.json> --after <new.json> [--output out.html]
    python report.py delta-all  --before-dir <dir> --after-dir <dir> [--output-dir out/] [--format html|json|both]
    python report.py health     --snapshot <snap.json> --checks <checks.yaml> [--device-checks <dev.yaml>] [--output out.html]
    python report.py health-all --dir <dir> --default-checks <checks.yaml> [--device-checks-dir <dir>] [--output-dir out/] [--format html|json|both]

Output format is inferred from the --output extension (.html or .json).
When --output is omitted, JSON is printed to stdout.
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from utils.delta import compute_delta
from utils.health import evaluate_checks, merge_checks
from utils import html_report


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_checks(path: str) -> list:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if isinstance(data, list):
        return data
    return data.get("checks", [])


def _write_output(data: dict, output: str | None) -> None:
    text = json.dumps(data, indent=2)
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"  -> {output}")
    else:
        print(text)


def _is_html(path: str | None) -> bool:
    return bool(path and path.lower().endswith(".html"))


def _write_report(report: dict, snap: dict, output: str | None, before_snap: dict | None = None, after_snap: dict | None = None) -> None:
    """Write a health or delta report to file or stdout."""
    if _is_html(output):
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        if before_snap is not None:
            html = html_report.render_delta(report, before_snap, after_snap)
        else:
            html = html_report.render_health(report, snap)
        out.write_text(html, encoding="utf-8")
        print(f"  -> {output}")
    else:
        _write_output(report, output)


def _load_dir_snapshots(d: Path) -> dict[str, tuple[Path, dict]]:
    """Glob *.json in a directory; return {hostname: (path, snap)} map."""
    mapping: dict[str, tuple[Path, dict]] = {}
    for p in sorted(d.glob("*.json")):
        try:
            snap = _load_json(str(p))
            hostname = snap.get("metadata", {}).get("hostname")
            if not hostname:
                print(f"  [WARN] {p.name}: missing metadata.hostname — skipping")
                continue
            if hostname in mapping:
                print(f"  [WARN] {p.name}: duplicate hostname '{hostname}' in {d} — skipping")
                continue
            mapping[hostname] = (p, snap)
        except Exception as exc:
            print(f"  [WARN] {p.name}: failed to load ({exc}) — skipping")
    return mapping


# ---------------------------------------------------------------------------
# delta subcommand
# ---------------------------------------------------------------------------

def cmd_delta(args: argparse.Namespace) -> None:
    before = _load_json(args.before)
    after  = _load_json(args.after)
    report = compute_delta(before, after)

    b = report["metadata"]["before"]
    a = report["metadata"]["after"]
    s = report["summary"]

    print(f"\nDelta report")
    print(f"  host:   {b.get('hostname', '?')}")
    print(f"  before: {b.get('collection_time', '?')}  ({args.before})")
    print(f"  after:  {a.get('collection_time', '?')}  ({args.after})")
    print(f"\n  added:     {len(s['commands_added'])}")
    print(f"  removed:   {len(s['commands_removed'])}")
    print(f"  changed:   {len(s['commands_changed'])}")
    print(f"  unchanged: {len(s['commands_unchanged'])}")

    if s["commands_added"]:
        for cmd in s["commands_added"]:
            print(f"    [+] {cmd}")
    if s["commands_removed"]:
        for cmd in s["commands_removed"]:
            print(f"    [-] {cmd}")
    if s["commands_changed"]:
        for cmd in s["commands_changed"]:
            n = len(report["changes"][cmd]["diffs"])
            print(f"    [~] {cmd}  ({n} diff(s))")
            for diff in report["changes"][cmd]["diffs"]:
                print(f"          {diff['path']}")
                print(f"            before: {diff['before']}")
                print(f"            after:  {diff['after']}")

    print()
    if _is_html(args.output):
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_report.render_delta(report, before, after), encoding="utf-8")
        print(f"  -> {args.output}")
    else:
        _write_output(report, args.output)


# ---------------------------------------------------------------------------
# delta-all subcommand
# ---------------------------------------------------------------------------

def cmd_delta_all(args: argparse.Namespace) -> None:
    before_dir = Path(args.before_dir)
    after_dir  = Path(args.after_dir)
    output_dir = Path(args.output_dir)
    fmt        = args.format

    output_dir.mkdir(parents=True, exist_ok=True)

    before_map = _load_dir_snapshots(before_dir)
    after_map  = _load_dir_snapshots(after_dir)
    all_hosts  = sorted(set(before_map) | set(after_map))

    print(f"\nDelta-all: {before_dir} → {after_dir}")
    print(f"  devices in before: {len(before_map)}  after: {len(after_map)}\n")

    results = []
    for hostname in all_hosts:
        has_before = hostname in before_map
        has_after  = hostname in after_map

        if not has_before or not has_after:
            side = "after-only" if not has_before else "before-only"
            print(f"  [WARN] '{hostname}': found in {side.replace('-', ' ')} — skipping")
            results.append({"hostname": hostname, "status": "unmatched", "side": side,
                            "report_path": None, "summary": None})
            continue

        _, before_snap = before_map[hostname]
        _, after_snap  = after_map[hostname]
        report = compute_delta(before_snap, after_snap)
        s = report["summary"]

        report_path = None
        if fmt in ("html", "both"):
            html_path = output_dir / f"{hostname}_delta.html"
            html_path.write_text(
                html_report.render_delta(report, before_snap, after_snap),
                encoding="utf-8"
            )
            report_path = f"{hostname}_delta.html"
        if fmt in ("json", "both"):
            json_path = output_dir / f"{hostname}_delta.json"
            _write_output(report, str(json_path))
            if report_path is None:
                report_path = f"{hostname}_delta.json"

        results.append({"hostname": hostname, "status": "matched", "side": "both",
                        "report_path": report_path, "summary": s})

    _print_delta_all_summary(results)

    index_path = output_dir / "index.html"
    index_path.write_text(
        html_report.render_delta_index(results, str(before_dir), str(after_dir)),
        encoding="utf-8"
    )
    print(f"  -> {index_path}")


def _print_delta_all_summary(results: list) -> None:
    header = f"  {'Device':<32} {'Status':<10} {'Added':>6} {'Removed':>8} {'Changed':>8} {'Unchanged':>10}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        if r["status"] == "unmatched":
            print(f"  {r['hostname']:<32} {'UNMATCHED':<10} {'—':>6} {'—':>8} {'—':>8} {'—':>10}")
        else:
            s = r["summary"]
            print(
                f"  {r['hostname']:<32} {'matched':<10}"
                f" {len(s['commands_added']):>6}"
                f" {len(s['commands_removed']):>8}"
                f" {len(s['commands_changed']):>8}"
                f" {len(s['commands_unchanged']):>10}"
            )
    print()


# ---------------------------------------------------------------------------
# health subcommand
# ---------------------------------------------------------------------------

def cmd_health(args: argparse.Namespace) -> None:
    snapshot = _load_json(args.snapshot)
    checks   = _load_checks(args.checks)

    if getattr(args, "device_checks", None):
        device_checks = _load_checks(args.device_checks)
        checks = merge_checks(checks, device_checks)

    report = evaluate_checks(snapshot, checks)
    _print_health_summary(report)

    if _is_html(args.output):
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_report.render_health(report, snapshot), encoding="utf-8")
        print(f"  -> {args.output}")
    else:
        _write_output(report, args.output)

    s = report["summary"]
    if s["failed"] > 0 or s["error"] > 0:
        sys.exit(1)


def _print_health_summary(report: dict) -> None:
    s    = report["summary"]
    meta = report["metadata"]
    print(f"\nHealth report")
    print(f"  host:      {meta.get('hostname', '?')}")
    print(f"  timestamp: {meta.get('collection_time', '?')}")
    print(f"  checks:    {s['total']}  passed: {s['passed']}  failed: {s['failed']}  error: {s['error']}")
    print()
    for r in report["results"]:
        status = r["status"].upper()
        print(f"  [{status:5s}] {r['name']}")
        if r["status"] == "fail":
            for f in r.get("failures", []):
                print(f"          path:    {f['path']}")
                print(f"          actual:  {f['actual']}")
                print(f"          reason:  {f['message']}")
        elif r["status"] == "error":
            print(f"          {r.get('message')}")
        elif r["status"] == "pass" and r.get("note"):
            print(f"          note: {r['note']}")
    print()


# ---------------------------------------------------------------------------
# health-all subcommand
# ---------------------------------------------------------------------------

def cmd_health_all(args: argparse.Namespace) -> None:
    snap_dir   = Path(args.dir)
    output_dir = Path(args.output_dir)
    fmt        = args.format
    dev_dir    = Path(args.device_checks_dir) if args.device_checks_dir else None

    output_dir.mkdir(parents=True, exist_ok=True)

    default_checks = _load_checks(args.default_checks)
    snap_map       = _load_dir_snapshots(snap_dir)

    print(f"\nHealth-all: {snap_dir}  ({len(snap_map)} device(s))\n")

    results = []
    any_failure = False

    for hostname, (_, snap) in sorted(snap_map.items()):
        checks = default_checks
        dev_file = dev_dir / f"{hostname}.yaml" if dev_dir else None
        if dev_file and dev_file.exists():
            checks = merge_checks(default_checks, _load_checks(str(dev_file)))

        report = evaluate_checks(snap, checks)
        s      = report["summary"]

        if s["failed"] > 0 or s["error"] > 0:
            any_failure = True

        report_path = None
        if fmt in ("html", "both"):
            html_path = output_dir / f"{hostname}_health.html"
            html_path.write_text(html_report.render_health(report, snap), encoding="utf-8")
            report_path = f"{hostname}_health.html"
        if fmt in ("json", "both"):
            json_path = output_dir / f"{hostname}_health.json"
            _write_output(report, str(json_path))
            if report_path is None:
                report_path = f"{hostname}_health.json"

        ts = snap.get("metadata", {}).get("collection_time", "?")
        results.append({
            "hostname":    hostname,
            "timestamp":   ts,
            "summary":     s,
            "report_path": report_path,
        })

    _print_health_all_summary(results)

    index_path = output_dir / "index.html"
    index_path.write_text(
        html_report.render_health_index(results, str(snap_dir)),
        encoding="utf-8"
    )
    print(f"  -> {index_path}")

    if any_failure:
        sys.exit(1)


def _print_health_all_summary(results: list) -> None:
    header = f"  {'Device':<32} {'Timestamp':<14} {'Total':>6} {'Pass':>6} {'Fail':>6} {'Error':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        s = r["summary"]
        print(
            f"  {r['hostname']:<32} {r['timestamp']:<14}"
            f" {s['total']:>6} {s['passed']:>6} {s['failed']:>6} {s['error']:>6}"
        )
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Network CLI Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # delta
    p_delta = sub.add_parser("delta", help="Compare two JSON snapshots")
    p_delta.add_argument("--before", required=True, help="Older snapshot JSON")
    p_delta.add_argument("--after",  required=True, help="Newer snapshot JSON")
    p_delta.add_argument("--output", default=None,  help="Output file (.json or .html); default: stdout")
    p_delta.set_defaults(func=cmd_delta)

    # delta-all
    p_dall = sub.add_parser("delta-all", help="Per-device delta across two snapshot directories")
    p_dall.add_argument("--before-dir", required=True, help="Directory of 'before' snapshots")
    p_dall.add_argument("--after-dir",  required=True, help="Directory of 'after' snapshots")
    p_dall.add_argument("--output-dir", default="delta-reports", help="Output directory (default: delta-reports/)")
    p_dall.add_argument("--format", choices=["html", "json", "both"], default="html",
                        help="Per-device report format (default: html)")
    p_dall.set_defaults(func=cmd_delta_all)

    # health
    p_health = sub.add_parser("health", help="Run health checks against a snapshot")
    p_health.add_argument("--snapshot",      required=True, help="Snapshot JSON file")
    p_health.add_argument("--checks",        required=True, help="Default health checks YAML")
    p_health.add_argument("--device-checks", default=None,  help="Device-specific checks YAML (overrides on name clash)")
    p_health.add_argument("--output",        default=None,  help="Output file (.json or .html); default: stdout")
    p_health.set_defaults(func=cmd_health)

    # health-all
    p_hall = sub.add_parser("health-all", help="Run health checks across a directory of snapshots")
    p_hall.add_argument("--dir",              required=True, help="Directory of JSON snapshots")
    p_hall.add_argument("--default-checks",   required=True, help="Default health checks YAML (applies to all devices)")
    p_hall.add_argument("--device-checks-dir", default=None, help="Directory of per-device YAML files named {hostname}.yaml")
    p_hall.add_argument("--output-dir",       default="health-reports", help="Output directory (default: health-reports/)")
    p_hall.add_argument("--format", choices=["html", "json", "both"], default="html",
                        help="Per-device report format (default: html)")
    p_hall.set_defaults(func=cmd_health_all)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
