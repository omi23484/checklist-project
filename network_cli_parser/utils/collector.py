"""SSH-based snapshot collector and .txt-to-JSON pipeline helper."""

from pathlib import Path

try:
    import netmiko as _netmiko
    HAS_NETMIKO = True
except ImportError:
    HAS_NETMIKO = False

_PLATFORM_TO_DEVICE_TYPE = {
    "cisco_nxos": "cisco_nxos_ssh",
    "cisco_ios":  "cisco_ios",
}


def collect_device(device_cfg: dict, commands: list) -> dict:
    if not HAS_NETMIKO:
        raise RuntimeError("netmiko not installed — run: pip install netmiko")

    conn_args = {
        "device_type": _PLATFORM_TO_DEVICE_TYPE.get(
            device_cfg.get("platform", ""), "cisco_ios"
        ),
        "host":     device_cfg["host"],
        "username": device_cfg["username"],
        "password": device_cfg.get("password", ""),
        "timeout":  int(device_cfg.get("timeout", 30)),
    }

    outputs = {}
    conn = _netmiko.ConnectHandler(**conn_args)
    try:
        for cmd in commands:
            try:
                output = conn.send_command(cmd, read_timeout=60)
                outputs[cmd] = output
            except Exception as exc:
                print(f"\n    [WARN] '{cmd}' failed: {exc}")
                outputs[cmd] = f"<collection-error: {exc}>"
    finally:
        conn.disconnect()

    return outputs


def write_txt_dump(hostname: str, ts: str, command_outputs: dict, raw_dir: Path) -> Path:
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    for cmd, output in command_outputs.items():
        lines.append(f"{hostname}# {cmd}")
        if output:
            lines.append(output.strip())
        lines.append(f"{hostname}#")
        lines.append("")

    txt_path = raw_dir / f"{hostname}_{ts}.txt"
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return txt_path
