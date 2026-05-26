"""
Network CLI Structured Parser

Usage:
    python main.py --input <file.txt>
    python main.py --input <directory/>      # processes all .txt files
    python main.py --input <file.txt> --output <output_dir>
"""

import argparse
import os
import sys
import traceback

from parsers import command_mapper, custom_engine, ntc_engine, splitter
from parsers import multicast_parser as mp
from utils import json_builder, normalization


def _parse_command(platform: str, cmd: str, raw: str) -> tuple[dict, str]:
    """
    Dispatch a single command to the appropriate parser.

    Returns (parsed_data, status) where status is one of:
        parsed | partial | raw_only | failed
    """
    strategy = command_mapper.get_strategy(platform, cmd)
    parser_type = strategy["parser"]

    if parser_type == "raw_only":
        return {}, "raw_only"

    if parser_type == "hierarchical":
        func_name = strategy["func"]
        func = getattr(mp, func_name, None)
        if func is None:
            return {}, "failed"
        try:
            return func(raw), "parsed"
        except Exception:
            traceback.print_exc()
            return {}, "failed"

    if parser_type == "ntc":
        try:
            rows = ntc_engine.parse(platform, strategy["template"], raw)
            status = "parsed" if rows else "partial"
            return rows, status
        except Exception:
            # NTC template missing or parse error — try custom fallback
            if "template" in strategy:
                try:
                    rows = custom_engine.parse(strategy["template"], raw)
                    status = "parsed" if rows else "partial"
                    return rows, status
                except Exception:
                    pass
            return {}, "failed"

    if parser_type == "custom":
        try:
            rows = custom_engine.parse(strategy["template"], raw)
            status = "parsed" if rows else "partial"
            return rows, status
        except Exception:
            traceback.print_exc()
            return {}, "failed"

    return {}, "raw_only"


def process_file(input_path: str, output_dir: str) -> str:
    """
    Parse a single CLI dump file and write a JSON snapshot.
    Returns the path to the written JSON file.
    """
    with open(input_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    hostname        = normalization.extract_hostname(input_path)
    collection_time = normalization.extract_collection_time(input_path)
    platform        = normalization.detect_platform(input_path, content)

    print(f"  hostname:   {hostname}")
    print(f"  platform:   {platform}")
    print(f"  timestamp:  {collection_time}")

    raw_commands = splitter.split_commands(content)
    print(f"  commands detected: {len(raw_commands)}")

    commands_data: dict = {}
    for cmd, raw_output in raw_commands.items():
        parsed, status = _parse_command(platform, cmd, raw_output)
        commands_data[cmd] = {
            "status": status,
            "raw":    raw_output,
            "parsed": parsed,
        }
        print(f"    [{status:10s}] {cmd}")

    snapshot = json_builder.build_snapshot(
        hostname=hostname,
        platform=platform,
        collection_time=collection_time,
        source_file=input_path,
        commands_data=commands_data,
    )

    basename    = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, f"{basename}.json")
    json_builder.write_snapshot(snapshot, output_path)
    print(f"  -> {output_path}")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Network CLI Structured Parser")
    parser.add_argument("--input",  required=True, help="Input .txt file or directory")
    parser.add_argument("--output", default=None,  help="Output directory (default: data/json/)")
    args = parser.parse_args()

    script_dir  = os.path.dirname(os.path.abspath(__file__))
    default_out = os.path.join(script_dir, "data", "json")
    output_dir  = args.output or default_out

    input_path = args.input
    if os.path.isdir(input_path):
        txt_files = [
            os.path.join(input_path, f)
            for f in sorted(os.listdir(input_path))
            if f.lower().endswith(".txt")
        ]
        if not txt_files:
            print(f"No .txt files found in {input_path}")
            sys.exit(1)
        for fpath in txt_files:
            print(f"\nProcessing: {fpath}")
            process_file(fpath, output_dir)
    elif os.path.isfile(input_path):
        print(f"\nProcessing: {input_path}")
        process_file(input_path, output_dir)
    else:
        print(f"Input not found: {input_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
