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
python fetch_logs.py --host 10.0.0.100 --username admin --remote-dir /logs

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

# 4. Validate a checks YAML before using it
python network_cli_parser/report.py validate \
  --checks network_cli_parser/checks/example_health_checks.yaml

# 5. Search for an IP across all snapshots
python network_cli_parser/report.py search \
  --dir   network_cli_parser/data/json/03-May-26/ \
  --query "10.0.0.1"
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
    ├── report.py                    # 15 subcommands: health / delta / search / parse / …
    ├── commands.yaml                # Command → parser strategy registry
    ├── requirements.txt
    ├── PARSER_SOP.md                # Full operating procedure (all subcommands + check syntax)
    ├── PARSER_SOP.docx              # Word version of the SOP
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
    ↓  main.py  (or  report.py collect)
data/json/<date>/*.json
    ↓  report.py
health.html    delta.html    trend.html    search output
```

---

## Output paths

Both raw `.txt` files and JSON snapshots are stored in date-named subdirectories extracted from the filename. For example, `N9K-WAN-1_03-May-26.txt` is placed under `03-May-26/`. Files are overwritten if re-processed.

---

## `report.py` subcommand reference

| Subcommand | Key flags | Purpose |
|---|---|---|
| `health` | `--snapshot` `--checks` `--device-checks` `--baseline` `--tags` `--output` `--report-mode` `--verify-only` | Single-device health check — generates detailed + simple HTML by default |
| `health-all` | `--dir` `--default-checks` `--device-checks-dir` `--baseline-dir` `--tags` `--since-days` `--report-mode` `--verify-only` | All devices — combined HTML matrix report + simple dashboard |
| `health-diff` | `--before` `--after` `--output` | Diff two health report JSONs — show regressions/fixes |
| `health-trend` | `--runs-dir` `--output` | Time-series pass/fail trend HTML across multiple health runs |
| `validate` | `--checks` | Validate a checks YAML for syntax errors (no snapshot needed) |
| `coverage` | `--snapshot` `--checks` | Gap analysis — which commands have no health checks |
| `baseline` | `--snapshot` `--output` | Auto-generate starter check YAML from current values |
| `delta` | `--before` `--after` `--output` | Field-level diff between two snapshots |
| `delta-all` | `--before-dir` `--after-dir` `--output-dir` `--format` | Per-device delta across two snapshot directories |
| `search` | `--dir` `--query` `--command` `--raw-only` `--parsed-only` `--case-sensitive` `--context` | Full-text search across all snapshots (raw + parsed JSON) |
| `parse` | `--platform` `--command` `--raw` | Quick-parse a raw output file and print JSON to stdout |
| `test-template` | `--template` `--raw` / `--platform` `--command` `--raw` | Test a TextFSM or TTP template against raw output |
| `collect` | `--devices` or `--from-dir` `--output-dir` | SSH collection or offline .txt → JSON |

---

## Health checks quick reference

### Path syntax

| What you want | `path` | `print` template |
|---|---|---|
| Scalar field | `[0].hostname` | `{{value}}` |
| All rows, field is inside each dict | `[*].state` | `Neighbor {{.neighbor}} → {{value}}` |
| Neighbor IP is the dict key | `[*].pfxrcd` | `Neighbor {{[*]}} → {{value}}` |
| VRF + neighbor both wildcard | `[*][*].pfxrcd` | `VRF={{[*][0]}} Neighbor={{[*][1]}} → {{value}}` |
| Three-level wildcard | `[*][*].address_family[*].pfxrcd` | `VRF={{[*][0]}} Neigh={{[*][1]}} AF={{[*][2]}} → {{value}}` |

### Check types

| Feature | YAML key | What it does |
|---|---|---|
| Single condition | `condition:` + `value:` | One assertion per resolved value |
| AND conditions | `conditions:` | All listed conditions must pass per value |
| Conditional branch | `branches:` | If/elif/else per row based on another field's value |
| Cross-command check | `cross_check:` | Assert THEN rows only when IF rows match |
| Item count | `count:` | Assert how many items a path expansion produces |
| Baseline delta | `compare_baseline:` | Assert change vs a previous snapshot (diff/diff_pct) |
| Metadata check | `metadata:` | Check `hostname`, `platform`, or `collection_time` directly |
| Print-only display | *(omit condition)* | Surface values with a blue DISPLAY badge — never fails |

### Conditions (all 30)

| Category | Conditions |
|---|---|
| Equality | `eq` `ne` |
| Numeric | `gt` `gte` `lt` `lte` |
| String | `contains` `not_contains` `matches` |
| Set | `one_of` `not_one_of` |
| Duration | `duration_gt` `duration_gte` `duration_lt` `duration_lte` |
| Length | `len_eq` `len_ne` `len_gt` `len_gte` `len_lt` `len_lte` |
| Date | `date_before` `date_after` `date_within_days` `date_older_than_days` |
| Delta | `diff_gt` `diff_gte` `diff_lt` `diff_lte` `diff_pct_gt` `diff_pct_gte` `diff_pct_lt` `diff_pct_lte` |

### Optional check fields

| Field | Values | Effect |
|---|---|---|
| `severity` | `critical` (default) / `warn` / `info` | Controls whether failure causes exit 1 |
| `match` | `all` (default) / `any` | Whether all or any expanded values must pass |
| `tags` | list of strings | Filter checks with `--tags bgp,ospf` at CLI |
| `skip_if` | `metadata:` + condition | Skip check when metadata condition is true |
| `print` | `true` or template string | Show resolved values in terminal and HTML |

### HTML report modes (`--report-mode`)

By default both `health` and `health-all` generate **two** HTML files:

| File | Contents | Use case |
|---|---|---|
| `health.html` | Full detail — raw CLI output, parsed JSON panels, check conditions, actual values | Engineering review |
| `health_simple.html` | Pass/fail per check only — no raw output, no config values | Safe to forward to management |

Control with `--report-mode both` (default) / `detailed` / `simple`.

---

## SFTP fetcher quick reference

```bash
# Password auth
python fetch_logs.py --host 10.0.0.100 --username admin --password 's3cr3t'

# Key auth
python fetch_logs.py --host 10.0.0.100 --username admin --key ~/.ssh/id_rsa

# Legacy devices (old Cisco gear — enables old KEX/cipher algorithms)
python fetch_logs.py --host 10.0.0.100 --username admin --legacy --no-verify-host

# Filter by filename substring + dry run
python fetch_logs.py --host 10.0.0.100 --username admin \
    --name-contains CAMA --dry-run

# Resume partial download
python fetch_logs.py --host 10.0.0.100 --username admin --if-exists resume

# Parallel download with progress bar (requires tqdm)
pip install tqdm
python fetch_logs.py --host 10.0.0.100 --username admin --workers 8 --progress
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

Full operating procedure — all 15 subcommands, all 30 conditions, every check type, 8 end-to-end workflows, template authoring, playbook runner, and SFTP fetcher — is in:

- [`network_cli_parser/PARSER_SOP.md`](network_cli_parser/PARSER_SOP.md) — Markdown
- [`network_cli_parser/PARSER_SOP.docx`](network_cli_parser/PARSER_SOP.docx) — Word document

---

## Running tests

```bash
cd network_cli_parser
pytest tests/
```
