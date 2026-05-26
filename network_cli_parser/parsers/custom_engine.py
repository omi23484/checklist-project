import textfsm
from pathlib import Path

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "custom"


def parse(template_name: str, raw: str) -> list:
    """
    Parse raw CLI output using a custom TextFSM template file.

    Searches all subdirectories of templates/custom/ for <template_name>.textfsm.
    Returns a list of dicts (one per matched record).
    Raises FileNotFoundError if no template is found.
    Raises textfsm.TextFSMError on template or parse errors.
    """
    template_path = _find_template(template_name)
    with open(template_path) as fh:
        fsm = textfsm.TextFSM(fh)
    rows = fsm.ParseText(raw)
    return [dict(zip(fsm.header, row)) for row in rows]


def find_by_convention(platform: str, normalized_cmd: str) -> str | None:
    """
    Search templates/custom/ for a convention-named file:
      {platform}_{normalized_cmd}.textfsm

    Returns the template stem (passable directly to parse()) if found,
    or None if no matching file exists.

    Existing templates already follow this convention:
      cisco_nxos_show_ip_pim_neigh.textfsm
      cisco_ios_show_bfd_neighbors.textfsm

    Drop a new file with this naming pattern into any subdirectory of
    templates/custom/ and it will be picked up automatically without
    any entry in commands.yaml.
    """
    stem = f"{platform}_{normalized_cmd}"
    for _ in _TEMPLATE_DIR.rglob(f"{stem}.textfsm"):
        return stem
    return None


def _find_template(name: str) -> Path:
    for path in _TEMPLATE_DIR.rglob(f"{name}.textfsm"):
        return path
    raise FileNotFoundError(
        f"Custom TextFSM template not found: {name}.textfsm "
        f"(searched under {_TEMPLATE_DIR})"
    )
