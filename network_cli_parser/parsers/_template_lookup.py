import glob
from pathlib import Path


def find_by_convention(template_dir: Path, ext: str, platform: str, normalized_cmd: str):
    """Return '{platform}_{normalized_cmd}' if that file exists under template_dir, else None."""
    stem = f"{platform}_{normalized_cmd}"
    for _ in template_dir.rglob(glob.escape(f"{stem}.{ext}")):
        return stem
    return None


def find_template(template_dir: Path, ext: str, name: str) -> Path:
    """Return the path to '{name}.{ext}' under template_dir, or raise FileNotFoundError."""
    for path in template_dir.rglob(glob.escape(f"{name}.{ext}")):
        return path
    raise FileNotFoundError(f"Template not found: {name}.{ext} (searched under {template_dir})")
