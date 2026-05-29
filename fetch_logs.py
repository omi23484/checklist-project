"""
Standalone SFTP log fetcher — full legacy + modern support.

Downloads device CLI log files from a remote SFTP server and saves them
under  data/raw/<date>/  where <date> is extracted from each filename.

Filename convention expected on the server:
    <HOSTNAME>_<DD-Mon-YY>.txt      e.g.  N9K-CAMA-WAN-1_03-May-26.txt

Quick start:
    pip install paramiko
    python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs

Authentication (pick one):
    --password secret
    --key ~/.ssh/id_rsa
    --key ~/.ssh/id_rsa --key-passphrase secret
    (omit both → tries SSH agent, then ~/.ssh/id_rsa/ed25519/ecdsa, then prompts)

Legacy device support (old Cisco / network gear):
    --legacy            shortcut: enables all legacy algorithms at once
    --kex diffie-hellman-group1-sha1
    --cipher aes128-cbc
    --mac hmac-sha1
    --host-key ssh-rsa

If-exists behaviour:
    --if-exists overwrite   (default) download and replace
    --if-exists skip        skip files already present locally
    --if-exists resume      re-download only if remote is larger than local
"""

import argparse
import fnmatch
import getpass
import os
import re
import socket
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants — legacy algorithm sets used by old network gear
# ---------------------------------------------------------------------------

_LEGACY_KEX = [
    "diffie-hellman-group1-sha1",
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group-exchange-sha1",
]
_LEGACY_CIPHERS = [
    "aes128-cbc", "aes192-cbc", "aes256-cbc",
    "3des-cbc", "blowfish-cbc", "arcfour128", "arcfour256",
]
_LEGACY_MACS = [
    "hmac-sha1", "hmac-sha1-96", "hmac-md5", "hmac-md5-96",
]
_LEGACY_HOST_KEYS = [
    "ssh-rsa", "ssh-dss",
]

# ---------------------------------------------------------------------------
# Date extraction
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r'_(\d{2}-[A-Za-z]{3}-\d{2,4})[._]')


def _date_from_filename(name: str) -> str:
    """'N9K-WAN-1_03-May-26.txt' → '03-May-26', fallback 'unknown'."""
    m = _DATE_RE.search(name)
    return m.group(1) if m else "unknown"


# ---------------------------------------------------------------------------
# Connection builder
# ---------------------------------------------------------------------------

def _build_transport(args):
    """
    Create and authenticate a paramiko Transport, honouring every CLI option.
    Returns an authenticated Transport ready for SFTPClient.
    """
    try:
        import paramiko
    except ImportError:
        sys.exit("[ERROR] paramiko not installed — run: pip install paramiko")

    # ── Timeout / TCP options ───────────────────────────────────────────────
    sock = socket.create_connection(
        (args.host, args.port),
        timeout=args.timeout,
    )
    if args.tcp_keepalive:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    transport = paramiko.Transport(sock)

    # ── Compression ─────────────────────────────────────────────────────────
    if args.compress:
        transport.use_compression(True)

    # ── Banner / auth timeouts ───────────────────────────────────────────────
    transport.banner_timeout = args.banner_timeout
    transport.auth_timeout   = args.auth_timeout
    transport.handshake_timeout = args.timeout

    # ── Legacy / custom algorithms ───────────────────────────────────────────
    #
    # paramiko's preferred_* lists are set on the Transport *before* the
    # handshake. Adding legacy entries makes them available for negotiation
    # with old servers that don't support modern algorithms.
    #
    if args.legacy:
        _prepend(transport, "preferred_kex",     _LEGACY_KEX)
        _prepend(transport, "preferred_ciphers", _LEGACY_CIPHERS)
        _prepend(transport, "preferred_macs",    _LEGACY_MACS)
        _prepend(transport, "preferred_keys",    _LEGACY_HOST_KEYS)

    if args.kex:
        _prepend(transport, "preferred_kex", args.kex)
    if args.cipher:
        _prepend(transport, "preferred_ciphers", args.cipher)
    if args.mac:
        _prepend(transport, "preferred_macs", args.mac)
    if args.host_key_alg:
        _prepend(transport, "preferred_keys", args.host_key_alg)

    # ── Start SFTP subsystem handshake ───────────────────────────────────────
    transport.start_client()

    # ── Host key verification ────────────────────────────────────────────────
    server_key = transport.get_remote_server_key()
    _verify_host_key(args, server_key, paramiko)

    # ── Authentication ───────────────────────────────────────────────────────
    _authenticate(args, transport, paramiko)

    return transport


def _prepend(transport, attr: str, values: list) -> None:
    """Prepend values to a transport preferred-algorithm list (dedup, preserve order)."""
    current = list(getattr(transport, attr, []))
    for v in reversed(values):
        if v in current:
            current.remove(v)
        current.insert(0, v)
    setattr(transport, attr, current)


def _verify_host_key(args, server_key, paramiko) -> None:
    mode = args.host_key_check

    if mode == "ignore":
        return

    if mode == "auto-add":
        known = paramiko.HostKeys()
        kf = Path(args.known_hosts).expanduser()
        if kf.exists():
            known.load(str(kf))
        entry = known.lookup(args.host)
        if entry is None:
            known.add(args.host, server_key.get_name(), server_key)
            kf.parent.mkdir(parents=True, exist_ok=True)
            known.save(str(kf))
            print(f"  [HOST KEY] Auto-added {args.host} to {kf}")
        return

    # strict (default)
    known = paramiko.HostKeys()
    kf = Path(args.known_hosts).expanduser()
    if not kf.exists():
        sys.exit(
            f"[ERROR] known_hosts file not found: {kf}\n"
            f"        Use --host-key-check auto-add to add it, or --host-key-check ignore to skip."
        )
    known.load(str(kf))
    entry = known.lookup(args.host)
    if entry is None or server_key not in entry.values():
        sys.exit(
            f"[ERROR] Host key verification failed for {args.host}.\n"
            f"        Run with --host-key-check auto-add once to trust this host."
        )


def _authenticate(args, transport, paramiko) -> None:
    username = args.user

    # ── 1. Explicit private key file ─────────────────────────────────────────
    if args.key:
        key_path = Path(args.key).expanduser()
        passphrase = args.key_passphrase
        pkey = _load_key(key_path, passphrase, paramiko)
        transport.auth_publickey(username, pkey)
        if transport.is_authenticated():
            return
        sys.exit(f"[ERROR] Key authentication failed for {username} using {key_path}")

    # ── 2. SSH agent ─────────────────────────────────────────────────────────
    if not args.no_agent:
        try:
            agent = paramiko.Agent()
            agent_keys = agent.get_keys()
            for akey in agent_keys:
                try:
                    transport.auth_publickey(username, akey)
                    if transport.is_authenticated():
                        if args.verbose:
                            print(f"  [AUTH] SSH agent key accepted")
                        return
                except paramiko.SSHException:
                    continue
        except Exception:
            pass

    # ── 3. Default key file locations ────────────────────────────────────────
    if not args.no_keys:
        for name in ("id_ed25519", "id_ecdsa", "id_rsa", "id_dsa"):
            key_path = Path("~/.ssh").expanduser() / name
            if key_path.exists():
                pkey = _load_key(key_path, args.key_passphrase, paramiko, silent=True)
                if pkey is None:
                    continue
                try:
                    transport.auth_publickey(username, pkey)
                    if transport.is_authenticated():
                        if args.verbose:
                            print(f"  [AUTH] Key accepted: {key_path}")
                        return
                except paramiko.SSHException:
                    continue

    # ── 4. Password ───────────────────────────────────────────────────────────
    password = args.password
    if password is None:
        password = getpass.getpass(f"Password for {username}@{args.host}: ")
    try:
        transport.auth_password(username, password)
        if transport.is_authenticated():
            return
    except paramiko.AuthenticationException:
        pass

    # ── 5. Keyboard-interactive (fallback) ────────────────────────────────────
    if not args.no_keyboard_interactive:
        _password_holder = [args.password]

        def _kbd_handler(title, instructions, fields):
            responses = []
            for prompt, echo in fields:
                if not echo:
                    pw = _password_holder[0] or getpass.getpass(str(prompt))
                    _password_holder[0] = None
                    responses.append(pw)
                else:
                    responses.append(input(str(prompt)))
            return responses

        try:
            transport.auth_interactive(username, _kbd_handler)
            if transport.is_authenticated():
                if args.verbose:
                    print("  [AUTH] Keyboard-interactive accepted")
                return
        except Exception:
            pass

    sys.exit(f"[ERROR] All authentication methods failed for {username}@{args.host}")


def _load_key(path: Path, passphrase, paramiko, silent: bool = False):
    """Try loading an SSH private key, auto-detecting type."""
    loaders = [
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
        paramiko.DSSKey,
    ]
    for loader in loaders:
        try:
            return loader.from_private_key_file(str(path), password=passphrase)
        except paramiko.ssh_exception.PasswordRequiredException:
            if passphrase is None:
                passphrase = getpass.getpass(f"Passphrase for {path}: ")
            try:
                return loader.from_private_key_file(str(path), password=passphrase)
            except Exception:
                continue
        except Exception:
            continue
    if not silent:
        print(f"  [WARN] Could not load key: {path}")
    return None


# ---------------------------------------------------------------------------
# File transfer
# ---------------------------------------------------------------------------

def _matches_pattern(name: str, patterns: list) -> bool:
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _matches_contains(name: str, substrings: list) -> bool:
    """Return True if name contains ALL specified substrings (case-insensitive)."""
    lower = name.lower()
    return all(s.lower() in lower for s in substrings)


def _should_download(local_path: Path, remote_size: int, if_exists: str) -> bool:
    if not local_path.exists():
        return True
    if if_exists == "skip":
        return False
    if if_exists == "resume":
        return local_path.stat().st_size < remote_size
    return True  # overwrite


def fetch(args, transport) -> None:
    try:
        import paramiko
    except ImportError:
        sys.exit("[ERROR] paramiko not installed")

    sftp = paramiko.SFTPClient.from_transport(transport)
    local_root = Path(args.local_root) if args.local_root else Path(__file__).parent / "data" / "raw"
    patterns   = args.pattern if args.pattern else ["*.txt"]

    remote_paths = args.remote if isinstance(args.remote, list) else [args.remote]

    total_downloaded = total_skipped = total_failed = 0

    for remote_path in remote_paths:
        print(f"\nListing {args.host}:{remote_path} ...")
        try:
            entries = sftp.listdir_attr(remote_path)
        except Exception as exc:
            print(f"  [ERROR] Cannot list '{remote_path}': {exc}")
            continue

        # Filter by pattern, name-contains, and exclude directories
        import stat as _stat
        contains = args.name_contains or []
        files = [
            e for e in entries
            if not _stat.S_ISDIR(e.st_mode or 0)
            and _matches_pattern(e.filename, patterns)
            and _matches_contains(e.filename, contains)
        ]
        files.sort(key=lambda e: e.filename)
        print(f"  {len(files)} matching file(s)")

        for entry in files:
            name        = entry.filename
            remote_size = entry.st_size or 0
            remote_full = f"{remote_path.rstrip('/')}/{name}"
            date_str    = _date_from_filename(name)
            local_dir   = local_root / date_str
            local_path  = local_dir / name

            if args.dry_run:
                status = "skip" if local_path.exists() else "new"
                print(f"  [DRY-RUN:{status:4s}] {remote_full}  ->  {local_path}")
                continue

            if not _should_download(local_path, remote_size, args.if_exists):
                if args.verbose:
                    print(f"  [SKIP] {name} (already exists)")
                total_skipped += 1
                continue

            local_dir.mkdir(parents=True, exist_ok=True)
            try:
                if args.verbose:
                    print(f"  [GET ] {remote_full}")
                sftp.get(remote_full, str(local_path))
                size_kb = local_path.stat().st_size / 1024
                print(f"  [OK  ] {name}  ->  {local_path}  ({size_kb:.1f} KB)")
                total_downloaded += 1
            except Exception as exc:
                print(f"  [FAIL] {name}: {exc}")
                total_failed += 1

    sftp.close()

    if not args.dry_run:
        print(f"\nDone — {total_downloaded} downloaded, "
              f"{total_skipped} skipped, {total_failed} failed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Fetch device CLI logs from SFTP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Connection ────────────────────────────────────────────────────────────
    conn = p.add_argument_group("Connection")
    conn.add_argument("--host",            required=True,  help="SFTP server hostname or IP")
    conn.add_argument("--port",            type=int, default=22, help="Port (default: 22)")
    conn.add_argument("--user",            required=True,  help="Username")
    conn.add_argument("--timeout",         type=float, default=30.0,
                      help="TCP connect + handshake timeout in seconds (default: 30)")
    conn.add_argument("--banner-timeout",  type=float, default=15.0,
                      help="SSH banner timeout in seconds (default: 15)")
    conn.add_argument("--auth-timeout",    type=float, default=30.0,
                      help="Authentication timeout in seconds (default: 30)")
    conn.add_argument("--tcp-keepalive",   action="store_true",
                      help="Enable TCP keepalive on the socket")
    conn.add_argument("--compress",        action="store_true",
                      help="Enable zlib compression")

    # ── Authentication ────────────────────────────────────────────────────────
    auth = p.add_argument_group("Authentication")
    auth.add_argument("--password",        default=None,
                      help="Password (prompted if omitted and key auth fails)")
    auth.add_argument("--key",             default=None,   metavar="PATH",
                      help="Path to private key file (RSA/ECDSA/Ed25519/DSS)")
    auth.add_argument("--key-passphrase",  default=None,   metavar="PHRASE",
                      help="Passphrase for encrypted private key")
    auth.add_argument("--no-agent",        action="store_true",
                      help="Disable SSH agent lookup")
    auth.add_argument("--no-keys",         action="store_true",
                      help="Disable automatic ~/.ssh/id_* key lookup")
    auth.add_argument("--no-keyboard-interactive", action="store_true",
                      help="Disable keyboard-interactive auth fallback")

    # ── Host key verification ─────────────────────────────────────────────────
    hkv = p.add_argument_group("Host key verification")
    hkv.add_argument("--host-key-check",  default="strict",
                      choices=["strict", "auto-add", "ignore"],
                      help="strict (default) | auto-add (trust+save) | ignore")
    hkv.add_argument("--known-hosts",     default="~/.ssh/known_hosts", metavar="PATH",
                      help="known_hosts file path (default: ~/.ssh/known_hosts)")

    # ── Legacy / algorithm overrides ─────────────────────────────────────────
    alg = p.add_argument_group("Algorithm overrides (legacy device support)")
    alg.add_argument("--legacy",          action="store_true",
                      help="Enable ALL legacy algorithms (kex/cipher/mac/host-key). "
                           "Use for old Cisco/network gear that rejects modern crypto.")
    alg.add_argument("--kex",             nargs="+", metavar="ALG",
                      help="Preferred key-exchange algorithm(s), prepended to negotiation list.\n"
                           "e.g. diffie-hellman-group1-sha1  diffie-hellman-group14-sha1")
    alg.add_argument("--cipher",          nargs="+", metavar="ALG",
                      help="Preferred cipher(s). e.g. aes128-cbc  3des-cbc")
    alg.add_argument("--mac",             nargs="+", metavar="ALG",
                      help="Preferred MAC(s). e.g. hmac-sha1  hmac-md5")
    alg.add_argument("--host-key-alg",    nargs="+", metavar="ALG",
                      help="Preferred host key algorithm(s). e.g. ssh-rsa  ssh-dss")

    # ── Remote / local paths ─────────────────────────────────────────────────
    paths = p.add_argument_group("Paths")
    paths.add_argument("--remote",        required=True, nargs="+", metavar="PATH",
                       help="Remote directory path(s) to fetch from (space-separated for multiple)")
    paths.add_argument("--local-root",    default=None,  metavar="PATH",
                       help="Local root directory (default: data/raw/ beside this script)")
    paths.add_argument("--pattern",       nargs="+", default=["*.txt"], metavar="GLOB",
                       help="Filename glob pattern(s) to match (default: *.txt)")
    paths.add_argument("--name-contains", nargs="+", default=None, metavar="STR",
                       help="Only fetch files whose name contains ALL given strings "
                            "(case-insensitive). e.g. --name-contains CAMA WAN")

    # ── Transfer behaviour ───────────────────────────────────────────────────
    xfer = p.add_argument_group("Transfer behaviour")
    xfer.add_argument("--if-exists",      default="overwrite",
                       choices=["overwrite", "skip", "resume"],
                       help="What to do when local file already exists "
                            "(default: overwrite)")
    xfer.add_argument("--dry-run",        action="store_true",
                       help="List files without downloading")
    xfer.add_argument("--verbose",        action="store_true",
                       help="Print extra detail (skipped files, auth method used, etc.)")

    return p


def main() -> None:
    args = _build_parser().parse_args()

    print(f"Connecting to {args.host}:{args.port} as {args.user} ...")
    try:
        transport = _build_transport(args)
    except OSError as exc:
        sys.exit(f"[ERROR] Network error: {exc}")

    try:
        fetch(args, transport)
    finally:
        transport.close()


if __name__ == "__main__":
    main()
