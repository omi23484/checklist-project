import os
import re


_NXOS_PREFIXES = ("N9K", "N7K", "N5K", "N3K", "N2K")


def normalize_command(cmd: str) -> str:
    """Lowercase and collapse whitespace to underscores. Strips pipe filters."""
    cmd = re.sub(r'\s*\|.*$', '', cmd)  # strip pipe filter
    cmd = cmd.strip().lower()
    cmd = re.sub(r'\s+', '_', cmd)
    return cmd


def detect_platform(filename: str, content: str) -> str:
    """Return 'cisco_nxos' or 'cisco_ios' based on filename prefix or file content."""
    basename = os.path.basename(filename).upper()
    if any(basename.startswith(p) for p in _NXOS_PREFIXES):
        return "cisco_nxos"
    if "Cisco NX-OS" in content or "NX-OS Software" in content:
        return "cisco_nxos"
    if "Cisco IOS Software" in content or "IOS-XE" in content:
        return "cisco_ios"
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
