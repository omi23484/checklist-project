"""
Maps normalized command names to their parsing strategy.

Strategy dict shapes (from commands.yaml):
  {"parser": "ntc",          "template": "<ntc command string>"}
  {"parser": "custom",       "template": "<template file stem>"}
  {"parser": "hierarchical", "func":     "<multicast_parser function name>"}
  {"parser": "raw_only"}
  {"parser": "auto_discover"}   # returned for commands not in commands.yaml

Wildcard keys:
  Use * in a commands.yaml key to match any variable part (IP, interface, VRF).
  Example: "show ip bgp neigh * routes" matches the normalized command
  "show_ip_bgp_neigh_10_0_0_1_routes" and any other variant.
  Each * matches one or more normalized characters (letters, digits, underscores).
  Exact entries always take precedence over wildcard entries.
  Wildcard entries are excluded from 'collect' command lists.
"""

import re
import warnings
from pathlib import Path

import yaml

from utils.normalization import normalize_command

_YAML_PATH = Path(__file__).parent.parent / "commands.yaml"
_AUTO_DISCOVER = {"parser": "auto_discover"}


def _load_registry(yaml_path: Path) -> tuple[dict, dict]:
    """
    Load commands.yaml and return:
      (exact_registry, wildcard_registry)

    exact_registry:    {platform: {normalized_cmd: strategy_dict}}
    wildcard_registry: {platform: [(compiled_regex, strategy_dict), ...]}

    Wildcards are patterns whose normalized key contains '*'.
    Each '*' matches one or more normalized characters ([a-z0-9_]+).
    Exact entries always win over wildcards.
    """
    with open(yaml_path, encoding="utf-8") as fh:
        raw_data = yaml.safe_load(fh)

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"commands.yaml must be a top-level mapping, got {type(raw_data).__name__}"
        )

    exact: dict = {}
    wildcards: dict = {}

    for platform, commands in raw_data.items():
        if commands is None:
            exact[platform] = {}
            continue
        normalized: dict = {}
        wc_list: list = []
        for raw_cmd, strategy in commands.items():
            norm_key = normalize_command(str(raw_cmd))
            strat    = strategy if strategy is not None else {"parser": "raw_only"}
            if "*" in norm_key:
                # Build a regex: each * → [a-z0-9_]+ (matches IPs, interface names, etc.)
                regex_str = "[a-z0-9_]+".join(re.escape(part) for part in norm_key.split("*"))
                wc_list.append((re.compile("^" + regex_str + "$"), strat))
            else:
                if norm_key in normalized:
                    warnings.warn(
                        f"commands.yaml [{platform}]: '{raw_cmd}' normalizes to '{norm_key}' "
                        f"which already exists — keeping last entry.",
                        stacklevel=2,
                    )
                normalized[norm_key] = strat
        exact[platform]    = normalized
        wildcards[platform] = wc_list

    return exact, wildcards


try:
    _REGISTRY: dict
    _WILDCARD_REGISTRY: dict
    _REGISTRY, _WILDCARD_REGISTRY = _load_registry(_YAML_PATH)
except FileNotFoundError:
    raise FileNotFoundError(
        f"commands.yaml not found at {_YAML_PATH}. "
        "This file is required to run the parser."
    ) from None
except yaml.YAMLError as exc:
    raise ValueError(f"commands.yaml contains invalid YAML: {exc}") from exc


def get_strategy(platform: str, normalized_cmd: str) -> dict:
    """
    Return the parsing strategy for a command on the given platform.

    Lookup order:
      1. Exact match in _REGISTRY  (fastest, always wins)
      2. First matching wildcard pattern in _WILDCARD_REGISTRY
      3. {"parser": "auto_discover"} — triggers NTC + TextFSM/TTP auto-discovery
    """
    plat_exact = _REGISTRY.get(platform, {})
    if normalized_cmd in plat_exact:
        return plat_exact[normalized_cmd]

    for pattern, strategy in _WILDCARD_REGISTRY.get(platform, []):
        if pattern.fullmatch(normalized_cmd):
            return strategy

    return _AUTO_DISCOVER


def list_commands(platform: str) -> list:
    """Return all registered normalized command names for a platform (exact matches only)."""
    return list(_REGISTRY.get(platform, {}).keys())


def list_wildcard_patterns(platform: str) -> list[str]:
    """Return the raw regex patterns registered as wildcards for a platform."""
    return [pat.pattern for pat, _ in _WILDCARD_REGISTRY.get(platform, [])]
