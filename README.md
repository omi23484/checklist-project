# Network CLI Structured Parser

Parses Cisco IOS/NX-OS CLI dumps, evaluates health checks, and generates delta/health reports.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `network_cli_parser/` | Main parser, report generator, health checks, templates |
| `fetch_logs.py` | Standalone SFTP log fetcher — no shared imports with the parser |

---

## Quick start

```bash
pip install -r network_cli_parser/requirements.txt

# Parse CLI dumps → JSON
python network_cli_parser/main.py --input data/raw/03-May-26/

# Run health checks
python network_cli_parser/report.py health \
  --snapshot network_cli_parser/data/json/03-May-26/N9K-WAN-1_03-May-26.json \
  --checks   network_cli_parser/checks/example_health_checks.yaml \
  --output   health.html

# Fetch raw logs from SFTP server first
pip install paramiko
python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs
```

---

## Directory structure

```
checklist-project/
├── fetch_logs.py                    # Standalone SFTP fetcher (paramiko)
│
└── network_cli_parser/
    ├── main.py                      # Parser entry point
    ├── report.py                    # delta / health / baseline / collect
    ├── commands.yaml                # Command → parser strategy registry
    ├── requirements.txt
    │
    ├── parsers/                     # NTC / TextFSM / TTP / hierarchical engines
    ├── templates/
    │   ├── custom/                  # TextFSM templates (.textfsm)
    │   └── ttp/                     # TTP templates (.ttp)
    ├── utils/
    │   ├── health.py                # Check evaluator
    │   ├── delta.py                 # Field-level diff
    │   ├── html_report.py           # Self-contained HTML renderer
    │   ├── normalization.py
    │   └── json_builder.py
    ├── checks/
    │   ├── example_health_checks.yaml
    │   └── devices/                 # Per-device check overrides
    └── data/
        ├── raw/<date>/              # Input .txt CLI dumps (date from filename)
        └── json/<date>/             # Output JSON snapshots (dated subdirectory)
```

---

## Data flow

```
SFTP server
    ↓  fetch_logs.py
data/raw/<date>/*.txt
    ↓  main.py
data/json/<date>/*.json
    ↓  report.py health / delta
health.html  delta.html
```

---

## Output paths

Both raw `.txt` files and JSON snapshots are stored in date-named subdirectories extracted from the filename. For example, `N9K-WAN-1_03-May-26.txt` is placed under `03-May-26/`. Files are overwritten if re-processed.

---

## Health checks quick reference

| What you want | path | print template |
|---|---|---|
| Check a scalar field | `[0].hostname` | `{{value}}` |
| All neighbors, value is a field | `[*].state_pfx` | `Neighbor {{.neighbor}} → {{value}}` |
| Neighbor IP is the dict key | `[*].pfxrcd` | `Neighbor {{[*]}} → {{value}}` |
| VRF + neighbor both wildcard | `[*][*].pfxrcd` | `VRF={{[*][0]}} Neighbor={{[*][1]}} → {{value}}` |
| Three-level wildcard | `[*][*].address_family[*].pfxrcd` | `VRF={{[*][0]}} Neigh={{[*][1]}} AF={{[*][2]}} → {{value}}` |

---

## SFTP fetcher quick reference

```bash
# Password auth
python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs

# Key auth
python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs --key ~/.ssh/id_rsa

# Legacy devices (old Cisco gear)
python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs --legacy

# Filter by filename substring + dry run
python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs \
    --name-contains CAMA --dry-run

# Multiple remote paths, skip existing
python fetch_logs.py --host 10.0.0.100 --user admin \
    --remote /logs/nxos /logs/ios --if-exists skip
```

---

## Documentation

Full operating procedure — parser chain, template authoring, commands.yaml reference, health check syntax, report subcommands, and the snapshot collector — is in [`network_cli_parser/PARSER_SOP.md`](network_cli_parser/PARSER_SOP.md).

---

## Running tests

```bash
cd network_cli_parser
pytest tests/
```
