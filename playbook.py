#!/usr/bin/env python3
"""
Playbook runner for the Network CLI Structured Parser toolchain.

Reads a CSV file and executes each enabled row in step order.  Each row runs
one script from the toolchain — fetch logs, parse CLI dumps, run health
checks, compare snapshots, or generate any report.py subcommand output.

━━━ CSV columns (header row required) ────────────────────────────────────────

  step              Integer — execution order.  Rows with equal step numbers
                    run in the order they appear in the file.
  name              Human-readable label shown in the job log.
  enabled           'yes' or 'no' — skip a step without deleting its row.
  type              Which script/subcommand to invoke (see list below).
  args              CLI arguments, space-separated, exactly as you would type
                    them after the script name.  Supports variable substitution
                    (see below).
  continue_on_error 'yes' to continue the playbook even if this step exits
                    non-zero.  Default: 'no' (abort on failure).
  description       Free-form notes — ignored by the runner.

━━━ Step types ───────────────────────────────────────────────────────────────

  fetch       →  python fetch_logs.py <args>
  parse       →  python network_cli_parser/main.py <args>
  health      →  python network_cli_parser/report.py health <args>
  health-all  →  python network_cli_parser/report.py health-all <args>
  health-diff →  python network_cli_parser/report.py health-diff <args>
  coverage    →  python network_cli_parser/report.py coverage <args>
  delta       →  python network_cli_parser/report.py delta <args>
  delta-all   →  python network_cli_parser/report.py delta-all <args>
  baseline    →  python network_cli_parser/report.py baseline <args>
  collect     →  python network_cli_parser/report.py collect <args>

━━━ Variable substitution in 'args' ─────────────────────────────────────────

  {date}        Today in filename format:   03-May-26
  {today}       Today in ISO format:        2026-05-30
  {timestamp}   Current datetime:           20260530_143000
  {yesterday}   Yesterday in ISO format:    2026-05-29

━━━ Usage ────────────────────────────────────────────────────────────────────

  python playbook.py --playbook network_cli_parser/playbooks/daily.csv
  python playbook.py --playbook network_cli_parser/playbooks/daily.csv --dry-run
  python playbook.py --playbook network_cli_parser/playbooks/daily.csv --list
  python playbook.py --playbook network_cli_parser/playbooks/daily.csv --step 3
  python playbook.py --playbook network_cli_parser/playbooks/daily.csv --from-step 2
  python playbook.py --playbook network_cli_parser/playbooks/daily.csv --only-type fetch,parse
"""

import argparse
import csv
import shlex
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
PARSER_DIR = SCRIPT_DIR / "network_cli_parser"

_TYPE_TO_CMD: dict[str, list[str]] = {
    "fetch":       [sys.executable, str(SCRIPT_DIR / "fetch_logs.py")],
    "parse":       [sys.executable, str(PARSER_DIR / "main.py")],
    "health":      [sys.executable, str(PARSER_DIR / "report.py"), "health"],
    "health-all":  [sys.executable, str(PARSER_DIR / "report.py"), "health-all"],
    "health-diff": [sys.executable, str(PARSER_DIR / "report.py"), "health-diff"],
    "coverage":    [sys.executable, str(PARSER_DIR / "report.py"), "coverage"],
    "delta":       [sys.executable, str(PARSER_DIR / "report.py"), "delta"],
    "delta-all":   [sys.executable, str(PARSER_DIR / "report.py"), "delta-all"],
    "baseline":    [sys.executable, str(PARSER_DIR / "report.py"), "baseline"],
    "collect":     [sys.executable, str(PARSER_DIR / "report.py"), "collect"],
}

_REQUIRED_COLS = {"step", "name", "enabled", "type", "args"}


# ---------------------------------------------------------------------------
# Variable substitution
# ---------------------------------------------------------------------------

def _build_vars() -> dict[str, str]:
    now = datetime.now()
    return {
        "{date}":      now.strftime("%d-%b-%y"),
        "{today}":     now.strftime("%Y-%m-%d"),
        "{timestamp}": now.strftime("%Y%m%d_%H%M%S"),
        "{yesterday}": (now - timedelta(days=1)).strftime("%Y-%m-%d"),
    }


def _resolve(s: str, vars_: dict[str, str]) -> str:
    for k, v in vars_.items():
        s = s.replace(k, v)
    return s


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def _load_playbook(path: str) -> list[dict]:
    """Load and validate a playbook CSV.  Raises ValueError on structural errors."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"{path}: file is empty or has no header row")

        headers = {f.strip() for f in reader.fieldnames}
        missing = _REQUIRED_COLS - headers
        if missing:
            raise ValueError(
                f"{path}: missing required column(s): {', '.join(sorted(missing))}\n"
                f"  Required: {', '.join(sorted(_REQUIRED_COLS))}"
            )

        rows = []
        for lineno, raw_row in enumerate(reader, start=2):
            row = {k.strip(): (v or "").strip() for k, v in raw_row.items() if k}
            try:
                row["_step_num"] = int(row["step"])
            except ValueError:
                raise ValueError(
                    f"{path}: line {lineno}: 'step' must be an integer, "
                    f"got {row['step']!r}"
                )
            rows.append(row)

    if not rows:
        raise ValueError(f"{path}: playbook has no data rows")

    return sorted(rows, key=lambda r: r["_step_num"])


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------

def _run_step(row: dict, vars_: dict[str, str], dry_run: bool = False) -> int:
    """Execute one playbook step.  Returns the process exit code."""
    step_type = row["type"].strip().lower()

    if step_type not in _TYPE_TO_CMD:
        print(
            f"  [ERROR] unknown type {step_type!r}\n"
            f"          valid types: {', '.join(sorted(_TYPE_TO_CMD))}"
        )
        return 1

    raw_args = _resolve(row.get("args", ""), vars_)
    try:
        extra = shlex.split(raw_args)
    except ValueError as exc:
        print(f"  [ERROR] could not parse args string: {exc}")
        return 1

    cmd = _TYPE_TO_CMD[step_type] + extra
    print(f"  $ {' '.join(cmd)}")

    if dry_run:
        return 0

    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    return result.returncode


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Playbook runner for the Network CLI Parser toolchain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--playbook", required=True, metavar="FILE",
        help="Path to the CSV playbook file",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the commands that would run but do not execute them",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all steps in the playbook without running any",
    )
    parser.add_argument(
        "--step", type=int, default=None, metavar="N",
        help="Run only the step with this number",
    )
    parser.add_argument(
        "--from-step", type=int, default=None, metavar="N",
        help="Start from step N — skip all earlier steps",
    )
    parser.add_argument(
        "--only-type", default=None, metavar="TYPES",
        help="Comma-separated type filter, e.g. 'fetch,parse'",
    )
    args = parser.parse_args()

    try:
        steps = _load_playbook(args.playbook)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    type_filter: set[str] | None = None
    if args.only_type:
        type_filter = {t.strip().lower() for t in args.only_type.split(",")}

    # ── List mode ──────────────────────────────────────────────────────────
    if args.list:
        print(f"\nPlaybook: {args.playbook}  ({len(steps)} step(s))\n")
        print(f"  {'STEP':>4}  {'TYPE':<12}  {'EN':>2}  {'COE':>3}  NAME")
        print(f"  {'─'*4}  {'─'*12}  {'─'*2}  {'─'*3}  {'─'*36}")
        for row in steps:
            en  = "Y" if row.get("enabled", "yes").lower() == "yes" else "N"
            coe = "Y" if row.get("continue_on_error", "no").lower() == "yes" else "N"
            print(f"  {row['step']:>4}  {row['type']:<12}  {en:>2}  {coe:>3}  {row['name']}")
        return

    # ── Run mode ───────────────────────────────────────────────────────────
    vars_ = _build_vars()
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\nPlaybook : {args.playbook}")
    print(f"Started  : {ts}")
    if args.dry_run:
        print("Mode     : DRY-RUN (no commands will be executed)")
    print(f"Variables: date={vars_['{date}']}  today={vars_['{today}']}  "
          f"timestamp={vars_['{timestamp}']}")
    print()

    ran = skipped = failed = 0

    for row in steps:
        num  = row["_step_num"]
        name = row["name"]
        typ  = row["type"].strip().lower()
        en   = row.get("enabled", "yes").strip().lower()
        coe  = row.get("continue_on_error", "no").strip().lower() == "yes"

        # Apply filters
        if args.step is not None and num != args.step:
            continue
        if args.from_step is not None and num < args.from_step:
            continue
        if type_filter and typ not in type_filter:
            continue

        if en == "no":
            print(f"[STEP {num:>3}]  {name}  — SKIPPED (enabled=no)")
            skipped += 1
            continue

        print(f"[STEP {num:>3}]  {name}")
        t0   = datetime.now()
        code = _run_step(row, vars_, dry_run=args.dry_run)
        elapsed = (datetime.now() - t0).total_seconds()

        if code == 0:
            ran += 1
            print(f"  ✓ OK  ({elapsed:.1f}s)\n")
        else:
            failed += 1
            print(f"  ✗ FAILED  exit={code}  ({elapsed:.1f}s)\n")
            if not coe:
                print(
                    f"Aborting — step {num} failed and continue_on_error=no\n"
                    f"Summary: {ran} OK  {skipped} skipped  {failed} failed"
                )
                sys.exit(code)

    print(f"Playbook complete: {ran} OK  {skipped} skipped  {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
