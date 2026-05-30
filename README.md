# Network CLI Structured Parser

Parses Cisco IOS/NX-OS CLI dumps, evaluates health checks, and generates delta/health reports.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `network_cli_parser/` | Main parser, report generator, health checks, templates |
| `fetch_logs.py` | Standalone SFTP log fetcher — no shared imports with the parser |
| `playbook.py` | Job runner — executes a CSV-defined sequence of toolchain steps |
| `network_cli_parser/playbooks/` | Example playbook CSV files |

---

## Quick start

```bash
pip install -r network_cli_parser/requirements.txt

# 1. Fetch raw logs from SFTP server
pip install paramiko
python fetch_logs.py --host 10.0.0.100 --user admin --remote /logs

# 2. Parse CLI dumps → JSON
python network_cli_parser/main.py --input network_cli_parser/data/raw/03-May-26/

# 3. Run health checks (HTML report + exit 1 on critical failures)
python network_cli_parser/report.py health \
  --snapshot network_cli_parser/data/json/03-May-26/N9K-WAN-1_03-May-26.json \
  --checks   network_cli_parser/checks/example_health_checks.yaml \
  --output   health.html

# 3b. CI mode — no files written, exit code only
python network_cli_parser/report.py health \
  --snapshot network_cli_parser/data/json/03-May-26/N9K-WAN-1_03-May-26.json \
  --checks   network_cli_parser/checks/example_health_checks.yaml \
  --verify-only
```

---

## Directory structure

```
checklist-project/
├── fetch_logs.py                    # Standalone SFTP fetcher (paramiko)
├── playbook.py                      # Job runner — executes CSV-defined step sequences
│
└── network_cli_parser/
    ├── main.py                      # Parser entry point
    ├── report.py                    # health / delta / coverage / diff / baseline / collect
    ├── commands.yaml                # Command → parser strategy registry
    ├── requirements.txt
    │
    ├── parsers/                     # NTC / TextFSM / TTP / hierarchical engines
    ├── templates/
    │   ├── custom/                  # TextFSM templates (.textfsm)
    │   └── ttp/                     # TTP templates (.ttp)
    ├── utils/
    │   ├── health.py                # Check evaluator + YAML schema validation
    │   ├── delta.py                 # Field-level diff
    │   ├── html_report.py           # Self-contained HTML renderer
    │   ├── normalization.py
    │   └── json_builder.py
    ├── checks/
    │   ├── example_health_checks.yaml
    │   └── devices/                 # Per-device check overrides ({hostname}.yaml)
    ├── playbooks/
    │   ├── reference.csv            # Full cheat-sheet — every step type + flag variant
    │   ├── example.csv              # 7-step end-to-end workflow
    │   └── daily_health.csv         # Minimal 3-step offline workflow
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

## `report.py` subcommand reference

| Subcommand | Key flags | Purpose |
|---|---|---|
| `health` | `--snapshot` `--checks` `--output` `--verify-only` | Single-device health check |
| `health-all` | `--dir` `--default-checks` `--since-days` `--verify-only` | All devices — combined HTML matrix |
| `health-diff` | `--before` `--after` `--output` | Diff two health report JSONs — show regressions |
| `coverage` | `--snapshot` `--checks` | Gap analysis — which commands have no checks |
| `delta` | `--before` `--after` `--output` | Field-level diff between two snapshots |
| `delta-all` | `--before-dir` `--after-dir` `--output-dir` | Per-device delta across two directories |
| `baseline` | `--snapshot` `--output` | Auto-generate starter check YAML |
| `collect` | `--devices` or `--from-dir` `--output-dir` | SSH collection or offline .txt → JSON |

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

## Playbook runner

Chain multiple steps into a single job using a CSV file:

```bash
# List steps without running
python playbook.py --playbook network_cli_parser/playbooks/example.csv --list

# Dry-run — print commands without executing
python playbook.py --playbook network_cli_parser/playbooks/example.csv --dry-run

# Run the full playbook
python playbook.py --playbook network_cli_parser/playbooks/daily_health.csv

# Run only fetch + parse steps
python playbook.py --playbook network_cli_parser/playbooks/example.csv --only-type fetch,parse

# Resume from step 3 after a previous partial run
python playbook.py --playbook network_cli_parser/playbooks/example.csv --from-step 3
```

`{date}`, `{today}`, `{yesterday}`, and `{timestamp}` in the `args` column are substituted at runtime, so a single playbook file works across daily runs without editing.

---

## Documentation

Full operating procedure — parser chain, template authoring, commands.yaml reference, health check syntax, report subcommands, playbook runner, and the snapshot collector — is in [`network_cli_parser/PARSER_SOP.md`](network_cli_parser/PARSER_SOP.md).

---

## Running tests

```bash
cd network_cli_parser
pytest tests/
```
