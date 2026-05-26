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


def _find_template(name: str) -> Path:
    for path in _TEMPLATE_DIR.rglob(f"{name}.textfsm"):
        return path
    raise FileNotFoundError(
        f"Custom TextFSM template not found: {name}.textfsm "
        f"(searched under {_TEMPLATE_DIR})"
    )
