"""
Network CLI Report Generator

Usage:
    python report.py delta  --before <old.json> --after <new.json> [--output delta.json]
    python report.py health --snapshot <snap.json> --checks <checks.yaml> [--output health.json]
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

from utils.delta import compute_delta
from utils.health import evaluate_checks


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_output(data: dict, output: str | None) -> None:
    text = json.dumps(data, indent=2)
    if output:
        out = Path(output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"  -> {output}")
    else:
        print(text)


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
    _write_output(report, args.output)


# ---------------------------------------------------------------------------
# health subcommand
# ---------------------------------------------------------------------------

def cmd_health(args: argparse.Namespace) -> None:
    snapshot = _load_json(args.snapshot)
    with open(args.checks, encoding="utf-8") as fh:
        checks_doc = yaml.safe_load(fh)
    checks = checks_doc.get("checks", [])

    report = evaluate_checks(snapshot, checks)
    s      = report["summary"]
    meta   = report["metadata"]

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
    _write_output(report, args.output)

    if s["failed"] > 0 or s["error"] > 0:
        sys.exit(1)


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

    p_delta = sub.add_parser("delta", help="Compare two JSON snapshots")
    p_delta.add_argument("--before", required=True, help="Older snapshot JSON")
    p_delta.add_argument("--after",  required=True, help="Newer snapshot JSON")
    p_delta.add_argument("--output", default=None,  help="Output JSON file (default: stdout)")
    p_delta.set_defaults(func=cmd_delta)

    p_health = sub.add_parser("health", help="Run health checks against a snapshot")
    p_health.add_argument("--snapshot", required=True, help="Snapshot JSON file")
    p_health.add_argument("--checks",   required=True, help="Health checks YAML file")
    p_health.add_argument("--output",   default=None,  help="Output JSON file (default: stdout)")
    p_health.set_defaults(func=cmd_health)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
