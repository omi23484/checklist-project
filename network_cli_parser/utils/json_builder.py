import json
import os


def build_snapshot(
    hostname: str,
    platform: str,
    collection_time: str,
    source_file: str,
    commands_data: dict,
) -> dict:
    """Assemble the top-level JSON snapshot dict."""
    return {
        "metadata": {
            "hostname":        hostname,
            "platform":        platform,
            "collection_time": collection_time,
            "source_file":     os.path.basename(source_file),
        },
        "commands": commands_data,
    }


def write_snapshot(snapshot: dict, output_path: str) -> None:
    dirpart = os.path.dirname(output_path)
    if dirpart:
        os.makedirs(dirpart, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, default=str)
