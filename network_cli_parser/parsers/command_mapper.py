"""
Maps normalized command names to their parsing strategy.

Strategy dict shapes (from commands.yaml):
  {"parser": "ntc",          "template": "<ntc command string>"}
  {"parser": "custom",       "template": "<template file stem>"}
  {"parser": "hierarchical", "func":     "<multicast_parser function name>"}
  {"parser": "raw_only"}
  {"parser": "auto_discover"}   # returned for commands not in commands.yaml
"""

import warnings
from pathlib import Path

import yaml

from utils.normalization import normalize_command

_YAML_PATH = Path(__file__).parent.parent / "commands.yaml"
_AUTO_DISCOVER = {"parser": "auto_discover"}


def _load_registry(yaml_path: Path) -> dict:
    """
    Load commands.yaml and return {platform: {normalized_cmd: strategy_dict}}.

    Raises FileNotFoundError if commands.yaml is absent.
    Raises ValueError on invalid YAML or wrong top-level type.
    Warns when two raw keys normalize to the same string (last one wins).
    """
    with open(yaml_path, encoding="utf-8") as fh:
        raw_data = yaml.safe_load(fh)

    if not isinstance(raw_data, dict):
        raise ValueError(
            f"commands.yaml must be a top-level mapping, got {type(raw_data).__name__}"
        )

    platform_map: dict = {}
    for platform, commands in raw_data.items():
        if commands is None:
            platform_map[platform] = {}
            continue
        normalized: dict = {}
        for raw_cmd, strategy in commands.items():
            norm_key = normalize_command(str(raw_cmd))
            if norm_key in normalized:
                warnings.warn(
                    f"commands.yaml [{platform}]: '{raw_cmd}' normalizes to '{norm_key}' "
                    f"which already exists — keeping last entry.",
                    stacklevel=2,
                )
            # A bare key with no value (e.g. "show logging last 100:") is None in YAML.
            normalized[norm_key] = strategy if strategy is not None else {"parser": "raw_only"}
        platform_map[platform] = normalized

    return platform_map


try:
    _REGISTRY: dict = _load_registry(_YAML_PATH)
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

    Returns {"parser": "auto_discover"} for commands not in commands.yaml,
    which triggers NTC + convention-TextFSM auto-discovery in main.py.
    This is distinct from {"parser": "raw_only"}, which is an explicit
    registry entry meaning "skip parsing intentionally".
    """
    return _REGISTRY.get(platform, {}).get(normalized_cmd, _AUTO_DISCOVER)


def list_commands(platform: str) -> list:
    """Return all registered normalized command names for a platform."""
    return list(_REGISTRY.get(platform, {}).keys())
