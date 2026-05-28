import os
import re


_NXOS_PREFIXES  = ("N9K", "N7K", "N5K", "N3K", "N2K")
_IOSXE_PREFIXES = ("CSR", "ISR", "ASR")

_PIPE_FILTER_RE = re.compile(r'\|\s*(\w+)')
_PROMPT_GT_RE   = re.compile(r'^\S+>\s*show\s', re.MULTILINE)


def normalize_command(cmd: str) -> str:
    """
    Lowercase and collapse whitespace to underscores.

    Pipe filter TYPE is preserved as a suffix; the argument is dropped.
    This lets piped variants have their own templates while keeping the
    key stable across different argument values.

    Examples:
      'show ip bgp summary'                -> 'show_ip_bgp_summary'
      'show ip bgp summary | include 65001'-> 'show_ip_bgp_summary_include'
      'show ip route | grep 10.0.0'        -> 'show_ip_route_grep'
      'show ip route | exclude Connected'  -> 'show_ip_route_exclude'
    """
    pipe_m = _PIPE_FILTER_RE.search(cmd)
    pipe_suffix = f"_{pipe_m.group(1).lower()}" if pipe_m else ""
    cmd = re.sub(r'\s*\|.*$', '', cmd)
    cmd = cmd.strip().lower()
    cmd = re.sub(r'\s+', '_', cmd)
    return cmd + pipe_suffix


def detect_platform(filename: str, content: str, warn: bool = True) -> str:
    """Detect platform from filename prefix, content keywords, or prompt pattern.

    Detection tiers (first match wins):
      1. Filename prefix  — N9K/N7K/... → cisco_nxos; CSR/ISR/ASR → cisco_iosxe
      2. Content keywords — NX-OS / IOS XE / IOS Software strings
      3. Prompt heuristic — 'hostname> show' indicates classic IOS interactive mode
      4. Fallback         — cisco_ios with a [WARN] printed (suppressed if warn=False)
    """
    basename = os.path.basename(filename).upper()

    # Tier 1: filename prefix
    if any(basename.startswith(p) for p in _NXOS_PREFIXES):
        return "cisco_nxos"
    if any(basename.startswith(p) for p in _IOSXE_PREFIXES):
        return "cisco_iosxe"

    # Tier 2: content keywords
    if "Cisco NX-OS" in content or "NX-OS Software" in content:
        return "cisco_nxos"
    if ("IOS XE Software" in content or "IOS-XE Software" in content
            or "Cisco IOS XE" in content):
        return "cisco_iosxe"
    if "Cisco IOS Software" in content:
        return "cisco_ios"

    # Tier 3: prompt heuristic — IOS uses 'hostname>' for unprivileged mode
    if _PROMPT_GT_RE.search(content):
        return "cisco_ios"

    # Tier 4: fallback
    if warn:
        print(
            f"[WARN] platform detection fell back to 'cisco_ios' for "
            f"{os.path.basename(filename)!r} — use --platform to override"
        )
    return "cisco_ios"


def extract_hostname(filename: str) -> str:
    """N9K-CAMA-WAN-1_03-May-26.txt -> N9K-CAMA-WAN-1"""
    base = os.path.basename(filename).rsplit(".", 1)[0]
    parts = base.rsplit("_", 1)
    return parts[0] if len(parts) == 2 else base


def extract_collection_time(filename: str) -> str:
    """N9K-CAMA-WAN-1_03-May-26.txt -> 03-May-26"""
    base = os.path.basename(filename).rsplit(".", 1)[0]
    parts = base.rsplit("_", 1)
    return parts[1] if len(parts) == 2 else ""


def denormalize_command(normalized_cmd: str) -> str:
    """
    Convert a normalized command key back to a space-separated string.

    Inverse of normalize_command() for NTC Templates lookup.
    Hyphens are preserved (normalize_command never touches them).

    Example: 'show_ip_bgp_summary_vrf_all' -> 'show ip bgp summary vrf all'
             'show_port-channel_summary'   -> 'show port-channel summary'
    """
    return normalized_cmd.replace("_", " ")
