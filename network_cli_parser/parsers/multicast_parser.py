"""
Hierarchical Python parsers for Cisco NX-OS multicast commands.

These commands produce nested group/source structures that do not map cleanly
to flat TextFSM records, so they are parsed with explicit regex state machines.
"""

import re


# ---------------------------------------------------------------------------
# show ip mroute summary
# ---------------------------------------------------------------------------

_VRF_HEADER_RE    = re.compile(r'IP Multicast Routing Table for VRF\s+"(\S+)"')
_TOTAL_ROUTES_RE  = re.compile(r'Total number of routes:\s+(\d+)')
_STAR_G_RE        = re.compile(r'Total number of \(\*,G\) routes:\s+(\d+)')
_SG_RE            = re.compile(r'Total number of \(S,G\) routes:\s+(\d+)')
_STAR_G_PFX_RE    = re.compile(r'Total number of \(\*,G-prefix\) routes:\s+(\d+)')
_GROUP_HDR_RE     = re.compile(r'Group:\s+([\d\.\/]+),\s+Source count:\s+(\d+)')
_SOURCE_ENTRY_RE  = re.compile(
    r'^\s*(\([^)]+\)|\*)\s+'
    r'(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d\.]+ \w+)\s+(\d+)'
)


def parse_mroute_summary(raw: str) -> dict:
    """
    Parse 'show ip mroute summary' into a hierarchical dict.

    Output shape:
      {
        "vrfs": {
          "default": {
            "summary": {
              "total_routes": int,
              "star_g_routes": int,
              "sg_routes": int,
              "star_g_prefix_routes": int
            },
            "groups": [
              {
                "group": str,
                "source_count": int,
                "entries": [
                  {
                    "source_type": str,
                    "packets": int,
                    "bytes": int,
                    "aps": int,
                    "pps": int,
                    "bitrate": str,
                    "oifs": int
                  }
                ]
              }
            ]
          }
        }
      }
    """
    result: dict = {"vrfs": {}}
    current_vrf: dict | None = None
    current_group: dict | None = None
    vrf_name: str = "default"

    for line in raw.splitlines():
        m = _VRF_HEADER_RE.search(line)
        if m:
            vrf_name = m.group(1)
            current_vrf = {"summary": {}, "groups": []}
            result["vrfs"][vrf_name] = current_vrf
            current_group = None
            continue

        if current_vrf is None:
            current_vrf = {"summary": {}, "groups": []}
            result["vrfs"][vrf_name] = current_vrf

        m = _TOTAL_ROUTES_RE.search(line)
        if m:
            current_vrf["summary"]["total_routes"] = int(m.group(1))
            continue

        m = _STAR_G_RE.search(line)
        if m:
            current_vrf["summary"]["star_g_routes"] = int(m.group(1))
            continue

        m = _SG_RE.search(line)
        if m:
            current_vrf["summary"]["sg_routes"] = int(m.group(1))
            continue

        m = _STAR_G_PFX_RE.search(line)
        if m:
            current_vrf["summary"]["star_g_prefix_routes"] = int(m.group(1))
            continue

        m = _GROUP_HDR_RE.search(line)
        if m:
            current_group = {
                "group": m.group(1),
                "source_count": int(m.group(2)),
                "entries": [],
            }
            current_vrf["groups"].append(current_group)
            continue

        m = _SOURCE_ENTRY_RE.match(line)
        if m and current_group is not None:
            current_group["entries"].append({
                "source_type": m.group(1),
                "packets":     int(m.group(2)),
                "bytes":       int(m.group(3)),
                "aps":         int(m.group(4)),
                "pps":         int(m.group(5)),
                "bitrate":     m.group(6),
                "oifs":        int(m.group(7)),
            })

    return result


# ---------------------------------------------------------------------------
# show ip mroute
# ---------------------------------------------------------------------------

_MROUTE_VRF_RE    = re.compile(r'IP Multicast Routing Table for VRF\s+"(\S+)"')
_MROUTE_ENTRY_RE  = re.compile(
    r'^\((\*|\d+\.\d+\.\d+\.\d+),\s*([\d\.\/]+)\),?\s*'
    r'uptime:\s*(\S+),\s*(.+)'
)
# Incoming interface / RPF line
_INCOMING_RE      = re.compile(
    r'Incoming interface:\s*(\S+(?:\s+\S+)?),\s*RPF\s+nbr:\s*(\S+)',
    re.IGNORECASE,
)
# OIF line formats:
#   "    Ethernet1/2, uptime: 2w3d, expires: 00:02:30"
#   "    10  Ethernet1/2  uptime: 2w3d  expires: 00:02:30"
_OIF_NAMED_RE = re.compile(
    r'^\s{2,}(\S+),\s+uptime:\s+(\S+),\s+expires:\s+(\S+)'
)
_OIF_INDEX_RE = re.compile(
    r'^\s{2,}\d+\s+(\S+)\s+uptime:\s+(\S+)\s+expires:\s+(\S+)'
)


def parse_mroute(raw: str) -> dict:
    """
    Parse 'show ip mroute' into a hierarchical dict.

    Output shape:
      {
        "vrfs": {
          "default": {
            "entries": [
              {
                "source": str,        # "*" for (*,G) entries
                "group":  str,
                "uptime": str,
                "flags":  str,
                "rpf_neighbor": str,
                "oifs":   [{"oif": str, "uptime": str, "expires": str}]
              }
            ]
          }
        }
      }
    """
    result: dict = {"vrfs": {}}
    current_vrf_name: str = "default"
    current_vrf: dict = {"entries": []}
    result["vrfs"][current_vrf_name] = current_vrf
    current_entry: dict | None = None

    for line in raw.splitlines():
        m = _MROUTE_VRF_RE.search(line)
        if m:
            current_vrf_name = m.group(1)
            current_vrf = {"entries": []}
            result["vrfs"][current_vrf_name] = current_vrf
            current_entry = None
            continue

        m = _MROUTE_ENTRY_RE.match(line)
        if m:
            current_entry = {
                "source":       m.group(1),
                "group":        m.group(2),
                "uptime":       m.group(3),
                "flags":        m.group(4).strip(),
                "rpf_neighbor": "",
                "oifs":         [],
            }
            current_vrf["entries"].append(current_entry)
            continue

        if current_entry is None:
            continue

        # Incoming interface / RPF neighbor line
        inc_m = _INCOMING_RE.search(line)
        if inc_m:
            current_entry["incoming_interface"] = inc_m.group(1).rstrip(",")
            current_entry["rpf_neighbor"] = inc_m.group(2)
            continue

        # OIF lines — try both named and indexed formats
        oif_m = _OIF_NAMED_RE.match(line) or _OIF_INDEX_RE.match(line)
        if oif_m:
            current_entry["oifs"].append({
                "oif":     oif_m.group(1),
                "uptime":  oif_m.group(2),
                "expires": oif_m.group(3),
            })

    return result
