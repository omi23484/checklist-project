from pathlib import Path

from ttp import ttp as TTP

from parsers import _template_lookup

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "ttp"


def parse(template_name: str, raw: str):
    """
    Parse raw CLI output using a TTP template file.

    Searches all subdirectories of templates/ttp/ for <template_name>.ttp.
    Returns the parsed result — a flat list of dicts, a nested dict (when
    the template uses <group> tags), or [] when nothing matched.
    Raises FileNotFoundError if no template is found.
    Raises ttp.ttp.TTPException on template errors.
    """
    template_path = _template_lookup.find_template(_TEMPLATE_DIR, "ttp", template_name)
    parser = TTP(data=raw, template=str(template_path))
    parser.parse()
    result = parser.result(format="raw")[0][0]
    # TTP returns '' (empty string) when nothing matched
    return result if result != "" else []


def find_by_convention(platform: str, normalized_cmd: str):
    """
    Search templates/ttp/ for a convention-named file:
      {platform}_{normalized_cmd}.ttp

    Returns the template stem (passable directly to parse()) if found,
    or None if no matching file exists.

    Drop a new .ttp file with this naming pattern into any subdirectory of
    templates/ttp/ and it will be picked up automatically without any entry
    in commands.yaml.

    Example: cisco_nxos_show_ip_ospf_neighbors.ttp auto-wires to
    show_ip_ospf_neighbors on cisco_nxos.
    """
    return _template_lookup.find_by_convention(_TEMPLATE_DIR, "ttp", platform, normalized_cmd)
