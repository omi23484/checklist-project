"""
Standalone SFTP log fetcher.

Downloads device CLI log files (.txt) from a remote SFTP server and saves
them under  data/raw/<date>/  where <date> is extracted from each filename.

Filename convention expected on the server:
    <HOSTNAME>_<DD-Mon-YY>.txt      e.g.  N9K-CAMA-WAN-1_03-May-26.txt

Usage:
    python fetch_logs.py \
        --host   10.0.0.100 \
        --user   admin \
        --remote /uploads/cli-logs \
        [--password secret]          # omit to be prompted
        [--local-root /some/path]    # default: data/raw/ beside this script
        [--pattern "*.txt"]          # optional filename filter
        [--dry-run]                  # list files without downloading

Dependencies (independent of the main project):
    pip install paramiko
"""

import argparse
import getpass
import os
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r'_(\d{2}-[A-Za-z]{3}-\d{2,4})\.')


def _date_from_filename(name: str) -> str:
    """Extract date string from filename, e.g. '03-May-26' from 'N9K_03-May-26.txt'."""
    m = _DATE_RE.search(name)
    return m.group(1) if m else "unknown"


# ---------------------------------------------------------------------------
# SFTP fetch
# ---------------------------------------------------------------------------

def fetch(host: str, port: int, username: str, password: str,
          remote_path: str, local_root: Path, pattern: str, dry_run: bool) -> None:
    try:
        import paramiko
    except ImportError:
        sys.exit("[ERROR] paramiko not installed — run: pip install paramiko")

    print(f"Connecting to {host}:{port} as {username} ...")
    transport = paramiko.Transport((host, port))
    try:
        transport.connect(username=username, password=password)
        sftp = paramiko.SFTPClient.from_transport(transport)
    except paramiko.AuthenticationException:
        sys.exit("[ERROR] Authentication failed — check username/password")
    except Exception as exc:
        sys.exit(f"[ERROR] Could not connect: {exc}")

    try:
        remote_files = sftp.listdir(remote_path)
    except Exception as exc:
        sys.exit(f"[ERROR] Cannot list remote path '{remote_path}': {exc}")

    # Filter by pattern (simple glob on extension / prefix)
    if pattern and pattern != "*":
        suffix = pattern.lstrip("*")
        remote_files = [f for f in remote_files if f.endswith(suffix)]

    remote_files = sorted(remote_files)
    print(f"Found {len(remote_files)} file(s) in {remote_path}")

    downloaded, skipped = 0, 0
    for name in remote_files:
        date_str  = _date_from_filename(name)
        local_dir = local_root / date_str
        local_path = local_dir / name
        remote_full = f"{remote_path.rstrip('/')}/{name}"

        if dry_run:
            print(f"  [DRY-RUN] {remote_full}  ->  {local_path}")
            continue

        local_dir.mkdir(parents=True, exist_ok=True)
        try:
            sftp.get(remote_full, str(local_path))
            print(f"  [OK] {name}  ->  {local_path}")
            downloaded += 1
        except Exception as exc:
            print(f"  [WARN] {name}: {exc}")
            skipped += 1

    sftp.close()
    transport.close()

    if not dry_run:
        print(f"\nDone — {downloaded} downloaded, {skipped} skipped")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    here = Path(__file__).parent

    parser = argparse.ArgumentParser(description="Fetch device CLI logs from SFTP server")
    parser.add_argument("--host",       required=True, help="SFTP server hostname or IP")
    parser.add_argument("--port",       type=int, default=22, help="SFTP port (default: 22)")
    parser.add_argument("--user",       required=True, help="SFTP username")
    parser.add_argument("--password",   default=None,  help="SFTP password (prompted if omitted)")
    parser.add_argument("--remote",     required=True, help="Remote directory path on SFTP server")
    parser.add_argument("--local-root", default=None,
                        help="Local root to save files under (default: data/raw/ beside this script)")
    parser.add_argument("--pattern",    default="*.txt", help="Filename filter (default: *.txt)")
    parser.add_argument("--dry-run",    action="store_true", help="List files without downloading")
    args = parser.parse_args()

    password   = args.password or getpass.getpass(f"Password for {args.user}@{args.host}: ")
    local_root = Path(args.local_root) if args.local_root else here / "data" / "raw"

    fetch(
        host        = args.host,
        port        = args.port,
        username    = args.user,
        password    = password,
        remote_path = args.remote,
        local_root  = local_root,
        pattern     = args.pattern,
        dry_run     = args.dry_run,
    )


if __name__ == "__main__":
    main()
