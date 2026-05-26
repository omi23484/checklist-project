import re
from utils.normalization import normalize_command

# Matches an optional device prompt followed by a show command.
# Examples:
#   "show version"
#   "N9K-DEVICE# show version"
#   "N9K-DEVICE> show ip bgp summary vrf all"
_COMMAND_RE = re.compile(
    r'^(?:[\w\-\.]+[#>]\s+)?(show\s+[\w][\w\s\-\/\.]*?)(?:\s*\|.*)?$',
    re.IGNORECASE,
)

# Standalone device prompt lines (e.g. "N9K-HOST#") with no trailing command.
_PROMPT_ONLY_RE = re.compile(r'^[\w\-\.]+[#>]\s*$')


def split_commands(content: str) -> dict:
    """
    Split a raw CLI dump into {normalized_command: raw_output_block}.

    Duplicate commands get a numeric suffix: show_version, show_version_2, etc.
    The raw output block for each command preserves the original whitespace/newlines.
    """
    lines = content.splitlines()
    segments: dict = {}
    counts: dict = {}
    current_cmd: str | None = None
    current_lines: list = []

    for line in lines:
        stripped = line.rstrip()
        m = _COMMAND_RE.match(stripped)
        if m:
            if current_cmd is not None:
                _store(segments, counts, current_cmd, "\n".join(current_lines).rstrip())
            current_cmd = normalize_command(m.group(1))
            current_lines = []
        elif _PROMPT_ONLY_RE.match(stripped):
            # Bare device prompt with no command — skip it
            pass
        else:
            if current_cmd is not None:
                current_lines.append(line)

    if current_cmd is not None:
        _store(segments, counts, current_cmd, "\n".join(current_lines).rstrip())

    return segments


def _store(segments: dict, counts: dict, cmd: str, output: str) -> None:
    if cmd not in counts:
        counts[cmd] = 1
        segments[cmd] = output
    else:
        counts[cmd] += 1
        segments[f"{cmd}_{counts[cmd]}"] = output
