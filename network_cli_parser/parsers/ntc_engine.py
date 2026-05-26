from ntc_templates.parse import parse_output


def parse(platform: str, command: str, raw: str) -> list:
    """
    Parse raw CLI output using the NTC Templates library.

    Returns a list of dicts (one per table row). Raises ValueError if the
    platform/command combination has no NTC template.
    """
    result = parse_output(platform=platform, command=command, data=raw)
    return result
