"""
Maps normalized command names to their parsing strategy.

Strategy dict shapes:
  {"parser": "ntc",          "template": "<ntc command string>"}
  {"parser": "custom",       "template": "<template file stem>"}
  {"parser": "hierarchical", "func":     "<multicast_parser function name>"}
  {"parser": "raw_only"}
"""

_NXOS_MAP = {
    "show_version":                    {"parser": "ntc", "template": "show version"},
    "show_env":                        {"parser": "ntc", "template": "show environment"},
    "show_module":                     {"parser": "ntc", "template": "show module"},
    "show_processes_cpu_sort":         {"parser": "ntc", "template": "show processes cpu"},
    "show_port-channel_summary":       {"parser": "ntc", "template": "show port-channel summary"},
    "show_int_brief":                  {"parser": "ntc", "template": "show interface brief"},
    "show_interface_brief":            {"parser": "ntc", "template": "show interface brief"},
    "show_ip_bgp_summary_vrf_all":     {"parser": "ntc", "template": "show ip bgp summary"},
    "show_ip_bgp_neigh_vrf_all":       {"parser": "ntc", "template": "show ip bgp neighbors"},
    "show_interface_description":      {"parser": "ntc", "template": "show interface description"},
    "show_vpc_brief":                  {"parser": "ntc", "template": "show vpc brief"},
    "show_ip_msdp_summary":            {"parser": "ntc", "template": "show ip msdp summary"},
    "show_int_loopback1":              {"parser": "ntc", "template": "show interface"},
    # Custom TextFSM
    "show_ip_pim_neigh":               {"parser": "custom", "template": "cisco_nxos_show_ip_pim_neigh"},
    # Hierarchical Python parsers
    "show_ip_mroute_summary":          {"parser": "hierarchical", "func": "parse_mroute_summary"},
    "show_ip_mroute":                  {"parser": "hierarchical", "func": "parse_mroute"},
    # Raw-only
    "show_processes_cpu_history":      {"parser": "raw_only"},
    "show_logging_last_100":           {"parser": "raw_only"},
}

_IOS_MAP = {
    "show_version":                    {"parser": "ntc", "template": "show version"},
    "show_env_all":                    {"parser": "ntc", "template": "show environment all"},
    "show_ip_int_brief":               {"parser": "ntc", "template": "show ip interface brief"},
    "show_ip_bgp_summary":             {"parser": "ntc", "template": "show ip bgp summary"},
    "show_ip_route":                   {"parser": "ntc", "template": "show ip route"},
    "show_ip_bgp_neighbor":            {"parser": "ntc", "template": "show ip bgp neighbors"},
    "show_interface_description":      {"parser": "ntc", "template": "show interface description"},
    "show_processes_cpu_sort":         {"parser": "ntc", "template": "show processes cpu"},
    # Custom TextFSM
    "show_bfd_neighbors":              {"parser": "custom", "template": "cisco_ios_show_bfd_neighbors"},
    "show_bfd_neighbors_details":      {"parser": "custom", "template": "cisco_ios_show_bfd_neighbors_details"},
    # Raw-only
    "show_logging":                    {"parser": "raw_only"},
    "show_processes_cpu_history":      {"parser": "raw_only"},
}

_PLATFORM_MAP = {
    "cisco_nxos": _NXOS_MAP,
    "cisco_ios":  _IOS_MAP,
}

_RAW_ONLY = {"parser": "raw_only"}


def get_strategy(platform: str, normalized_cmd: str) -> dict:
    """
    Return the parsing strategy for a command on a given platform.
    Falls back to raw_only for unknown commands.
    """
    return _PLATFORM_MAP.get(platform, {}).get(normalized_cmd, _RAW_ONLY)
