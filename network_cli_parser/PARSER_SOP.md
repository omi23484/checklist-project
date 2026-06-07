# Network CLI Parser — Standard Operating Procedure

> **Audience:** Engineers who collect, parse, and assert against Cisco IOS / NX-OS CLI output.
> **Scope:** Full reference — every CLI option, every condition, every check type, every permutation.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Directory Structure](#3-directory-structure)
4. [Parser — `main.py`](#4-parser--mainpy)
5. [Status Codes](#5-status-codes)
6. [Template Management](#6-template-management)
7. [Report Generator — `report.py`](#7-report-generator--reportpy)
8. [Health Check YAML Reference](#8-health-check-yaml-reference)
9. [HTML Reports](#9-html-reports)
10. [Exit Codes and CI/CD Integration](#10-exit-codes-and-cicd-integration)
11. [Playbook Runner — `playbook.py`](#11-playbook-runner--playbookpy)
12. [SFTP Log Fetcher — `fetch_logs.py`](#12-sftp-log-fetcher--fetch_logspy)
13. [End-to-End Workflows](#13-end-to-end-workflows)

---

## 1. Overview

The Network CLI Structured Parser reads raw Cisco IOS / NX-OS CLI dump text files, splits them by command, parses each command's output into structured JSON, and writes one snapshot file per device. The `report.py` toolchain then operates on those snapshots to produce health reports, delta comparisons, trend charts, and more.

### Parser chain (per command)

```
commands.yaml lookup
    ├── raw_only       → skip parsing, preserve raw text only
    ├── ntc            → NTC Templates (ntc-templates library)
    ├── custom         → Custom TextFSM template
    ├── ttp            → TTP template (supports nested/hierarchical output)
    ├── hierarchical   → Python regex parser (multicast commands)
    └── auto_discover  → (unknown commands, no YAML entry)
            ├── Step 1: NTC Templates (reconstructed command string)
            ├── Step 2: Convention TextFSM  ({platform}_{cmd}.textfsm anywhere under templates/custom/)
            ├── Step 3: Convention TTP       ({platform}_{cmd}.ttp anywhere under templates/ttp/)
            └── no_template  (raw preserved, structured parsing skipped)
```

Every command found in the dump appears in the JSON output — even commands with no registered template.

---

## 2. Installation

```bash
# Clone and enter the parser directory
cd network_cli_parser
pip install -r requirements.txt

# Optional: SSH collection support
pip install netmiko

# Optional: progress bars for SFTP fetcher
pip install tqdm
```

**Python:** 3.9 or newer required (f-strings with walrus in reports need 3.8+; type hints use 3.9+ syntax).

---

## 3. Directory Structure

```
checklist-project/                        ← repository root
├── fetch_logs.py                         ← standalone SFTP log fetcher
├── playbook.py                           ← CSV-driven playbook runner
│
└── network_cli_parser/
    ├── main.py                           ← parser entry point
    ├── report.py                         ← report generator (15 subcommands)
    ├── commands.yaml                     ← command registry (platform → command → strategy)
    ├── requirements.txt
    ├── PARSER_SOP.md                     ← this file
    │
    ├── parsers/
    │   ├── command_mapper.py             ← loads commands.yaml; returns strategy per command
    │   ├── splitter.py                   ← splits CLI dump into {cmd: raw_output} dict
    │   ├── ntc_engine.py                 ← wrapper around ntc-templates library
    │   ├── custom_engine.py              ← TextFSM engine + auto-discovery
    │   ├── ttp_engine.py                 ← TTP engine + auto-discovery
    │   └── multicast_parser.py           ← Python parsers for multicast commands
    │
    ├── templates/
    │   ├── custom/                       ← TextFSM templates (.textfsm)
    │   │   ├── routing/
    │   │   ├── interfaces/
    │   │   └── ...                       ← any subdirectory; rglob scans them all
    │   └── ttp/                          ← TTP templates (.ttp)
    │       └── routing/
    │
    ├── utils/
    │   ├── normalization.py              ← platform detection, hostname, cmd normalization
    │   ├── json_builder.py               ← assembles and writes the JSON snapshot
    │   ├── delta.py                      ← field-level diff between two snapshots
    │   ├── health.py                     ← YAML-driven check evaluator
    │   ├── html_report.py                ← self-contained HTML renderer
    │   └── collector.py                  ← SSH + offline collection pipeline
    │
    ├── checks/
    │   ├── example_health_checks.yaml    ← starter check definitions
    │   └── devices/                      ← per-device check overrides ({hostname}.yaml)
    │
    ├── playbooks/
    │   ├── reference.csv                 ← every step type with all flag variants
    │   ├── example.csv                   ← 7-step end-to-end workflow
    │   └── daily_health.csv              ← minimal 3-step offline workflow
    │
    └── data/
        ├── raw/
        │   └── <date>/                   ← input CLI dump .txt files
        └── json/
            └── <date>/                   ← output JSON snapshots
```

---

## 4. Parser — `main.py`

```bash
# Single .txt file
python main.py --input data/raw/N9K-CAMA-WAN-1_03-May-26.txt

# All .txt files in a directory
python main.py --input data/raw/

# Custom output directory
python main.py --input data/raw/ --output /tmp/parsed/

# Override the platform (when filename detection fails)
python main.py --input data/raw/device.txt --platform cisco_ios
```

Output is written to `data/json/<date>/` by default. The date is extracted from the filename (`DD-Mon-YY`). Each input file produces one `.json` snapshot.

### JSON Snapshot format

```json
{
  "metadata": {
    "hostname":        "N9K-CAMA-WAN-1",
    "platform":        "cisco_nxos",
    "collection_time": "03-May-26",
    "source_file":     "N9K-CAMA-WAN-1_03-May-26.txt"
  },
  "commands": {
    "show_version": {
      "status": "parsed",
      "raw":    "...",
      "parsed": [{"hostname": "N9K-CAMA-WAN-1", "os": "NX-OS", "version": "9.3(10)"}]
    },
    "show_ip_bgp_summary": {
      "status": "no_template",
      "raw":    "...",
      "parsed": {}
    }
  }
}
```

---

## 5. Status Codes

| Status | Meaning |
|--------|---------|
| `parsed` | Parser returned structured data — usable by health checks |
| `partial` | Parser ran but returned zero rows — template matched nothing |
| `raw_only` | Explicitly registered as skip in `commands.yaml`; raw preserved |
| `failed` | Parser threw an exception; raw preserved |
| `no_template` | Not in registry; auto-discovery found nothing; raw preserved |

Only `parsed` status produces data that health checks can evaluate against.

---

## 6. Template Management

### 6.1 Writing TextFSM Templates

TextFSM uses a state-machine model. Files live anywhere under `templates/custom/`.

```
Value FIELD_NAME (regex)
Value Filldown CARRY_FORWARD (regex)

Start
  ^header line regex -> Continue
  ^${FIELD_NAME}\s+${OTHER}  -> Record

EOF
```

- `Filldown` carries the last matched value forward (useful for VRF headers).
- `-> Record` emits the current row. `-> Continue` re-processes the line in another state.
- `EOF` emits any buffered row at end of input.

**Naming convention:** `{platform}_{normalized_cmd}.textfsm`

Example: `cisco_nxos_show_ip_pim_neigh.textfsm`

**Registering in commands.yaml:**

```yaml
cisco_nxos:
  show ip pim neigh:
    parser: custom
    template: cisco_nxos_show_ip_pim_neigh
```

**Multi-VRF example with Filldown:**

```
Value Filldown VRF (\S+)
Value NEIGHBOR (\d+\.\d+\.\d+\.\d+)
Value UPTIME (\S+)
Value STATE (\S+)

Start
  ^PIM Neighbor.*VRF\s+${VRF} -> Neighbors

Neighbors
  ^\s*${NEIGHBOR}\s+\S+\s+${UPTIME}\s+${STATE} -> Record
  ^PIM Neighbor.*VRF\s+${VRF} -> Continue.Record

EOF
```

---

### 6.2 Writing TTP Templates

TTP uses `{{ variable }}` placeholders and `<group>` tags for nested output.

```xml
{{ field_name }}
{{ field_name | re("custom_regex") }}
```

Use `re()` when a value contains spaces that TTP's default split can't handle.

**Naming convention:** `{platform}_{normalized_cmd}.ttp`

**Registering in commands.yaml:**

```yaml
cisco_nxos:
  show ip ospf neighbors:
    parser: ttp
    template: cisco_nxos_show_ip_ospf_neighbors
```

**Flat neighbor table:**

```xml
<group name="neighbors">
{{ neighbor_id }}  {{ priority }}  {{ state | re("\\S+/\\s*\\S*") }}  {{ uptime }}  {{ address }}  {{ interface }}
</group>
```

**Hierarchical (VRF → neighbors):**

```xml
<group name="vrfs">
BGP summary information for VRF {{ vrf }}, address family {{ afi | re(".+") }}
BGP router identifier {{ router_id }}, local AS number {{ local_as }}

<group name="neighbors">
{{ neighbor | re("\\d+\\.\\d+\\.\\d+\\.\\d+") }}  {{ version }}  {{ remote_as }}  {{ msg_rcvd }}  {{ msg_sent }}  {{ tbl_ver }}  {{ inq }}  {{ outq }}  {{ updown }}  {{ state_pfx }}
</group>

</group>
```

Result structure: `[{"vrfs": [{"vrf": "default", "neighbors": [{...}]}]}]`

---

### 6.3 `commands.yaml` Reference

All five strategy shapes:

```yaml
cisco_nxos:

  # NTC Templates library
  show ip route:
    parser: ntc
    template: cisco_nxos_show_ip_route

  # Custom TextFSM
  show ip pim neigh:
    parser: custom
    template: cisco_nxos_show_ip_pim_neigh

  # TTP (hierarchical output)
  show ip bgp summary vrf all:
    parser: ttp
    template: cisco_nxos_show_ip_bgp_summary_vrf_all

  # Hierarchical Python parser (multicast VRF nesting)
  show ip mroute:
    parser: hierarchical
    func: parse_mroute

  # Skip entirely — preserve raw only
  show tech-support:
    parser: raw_only
```

Keys are raw command strings (spaces, not underscores). The mapper normalizes them at load time. Duplicate normalized keys within a platform emit a warning; the second entry wins.

---

### 6.4 Pipe-Filtered Commands

Commands with a pipe filter produce structurally different output and need their own normalized key.

| Raw command | Normalized key |
|-------------|----------------|
| `show ip bgp summary` | `show_ip_bgp_summary` |
| `show ip bgp summary \| include 65001` | `show_ip_bgp_summary_include` |
| `show ip bgp summary \| exclude Connected` | `show_ip_bgp_summary_exclude` |
| `show ip route \| begin 10.0.0` | `show_ip_route_begin` |
| `show ip route \| grep 10.0.0` | `show_ip_route_grep` |
| `show ip route \| count` | `show_ip_route_count` |

**Template naming:** `cisco_nxos_show_ip_bgp_summary_include.textfsm` / `.ttp`

Drop it in any subdirectory — auto-discovery picks it up. No YAML edit needed.

**Explicit registration:**

```yaml
cisco_nxos:
  show ip bgp summary | include:
    parser: custom
    template: cisco_nxos_show_ip_bgp_summary_include
```

---

### 6.5 Auto-Discovery vs Explicit Registration

| Scenario | Approach |
|----------|----------|
| Command has an NTC template | `parser: ntc` OR rely on auto-discovery |
| Custom TextFSM | Drop `.textfsm` file; no YAML edit needed |
| TTP (hierarchical output) | Drop `.ttp` file; no YAML edit needed |
| Piped variant | Drop `{platform}_{cmd}_{filter}.textfsm/.ttp` |
| Should never be parsed | `parser: raw_only` in YAML |
| Hierarchical multicast | `parser: hierarchical` + function in `multicast_parser.py` |

---

## 7. Report Generator — `report.py`

### Quick reference — all 15 subcommands

```bash
python report.py COMMAND [OPTIONS]
```

| Subcommand | Purpose |
|------------|---------|
| `collect`      | Collect snapshots via SSH or process `.txt` dumps offline |
| `parse`        | Quick-parse a single raw output file, print JSON to stdout |
| `validate`     | Validate a checks YAML without needing a snapshot |
| `baseline`     | Auto-generate a starter check YAML from a snapshot |
| `coverage`     | Report which commands have health checks and which don't |
| `health`       | Run health checks against a single snapshot |
| `health-all`   | Run health checks across a directory of snapshots |
| `health-diff`  | Diff two health report JSON files (regressions / fixes) |
| `health-trend` | Time-series trend report across multiple health JSON files |
| `delta`        | Field-level diff between two snapshots |
| `delta-all`    | Per-device delta across two snapshot directories |
| `search`       | Full-text search across all snapshot commands (raw + parsed) |
| `test-template`| Test a TextFSM or TTP template against a raw output file |

---

### 7.1 `collect` — Snapshot Collection

#### Offline mode (no SSH required)

Reads existing `.txt` dump files and converts them to JSON snapshots:

```bash
python report.py collect \
  --from-dir   data/raw/ \
  --output-dir data/json/
```

#### SSH mode (requires `pip install netmiko`)

```bash
python report.py collect \
  --devices    devices.yaml \
  --raw-dir    data/raw/       # optional: where to save .txt dumps
  --output-dir data/json/ \
  --password   '<pw>'          # optional: override password for all devices
```

#### `devices.yaml` format

```yaml
defaults:
  username: admin
  password: ""        # leave blank and pass --password at runtime
  timeout: 30

devices:
  - hostname: N9K-CAMA-WAN-1
    host: 192.168.1.1
    platform: cisco_nxos      # determines command list + template set

  - hostname: IOS-RTR-1
    host: 10.0.0.1
    platform: cisco_ios
    username: ops             # device-specific override

  - hostname: N9K-CAMA-WAN-2
    host: 192.168.1.2
    platform: cisco_nxos
    commands:                 # optional: explicit command list overrides registry
      - show version
      - show ip bgp summary vrf all
```

**Platform → netmiko device_type:**

| Platform | device_type |
|----------|-------------|
| `cisco_nxos` | `cisco_nxos_ssh` |
| `cisco_ios` | `cisco_ios` |

When `commands:` is omitted, all non-`raw_only` commands registered for that platform in `commands.yaml` are collected.

---

### 7.2 `parse` — Quick Parse

Parse a single raw CLI output file and print structured JSON to stdout. No snapshot file is created — useful for template development and testing.

```bash
# From file
python report.py parse \
  --platform cisco_nxos \
  --command  "show ip bgp summary" \
  --raw      data/raw/bgp_output.txt

# From stdin (pipe)
cat data/raw/bgp_output.txt | \
  python report.py parse --platform cisco_nxos --command "show ip bgp summary"
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--platform` | Yes | Device platform (`cisco_nxos`, `cisco_ios`) |
| `--command` | Yes | Raw command string (spaces, not underscores) |
| `--raw` | No | Path to raw text file; reads stdin if omitted |

**Output:**

```
Status:   parsed
Command:  show_ip_bgp_summary  (cisco_nxos)

{
  "neighbors": [
    {"neighbor": "10.0.0.1", "remote_as": "65001", "updown": "5w2d", ...}
  ]
}
```

**Exit code:** `0` for `parsed`/`partial`; `1` for `no_template`/`failed`/`raw_only`.

---

### 7.3 `validate` — Check YAML Validation

Validates a checks YAML file for syntax errors **without needing a snapshot**. Use as a CI pre-flight check.

```bash
python report.py validate --checks checks/base.yaml

# Success:
# OK — 12 check(s) validated: checks/base.yaml

# Failure:
# [ERROR] 'BGP prefix count': must have 'condition', 'conditions', or 'branches'
# FAIL — 1 validation error(s) in 'checks/base.yaml' — fix and retry
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--checks` | Yes | Health checks YAML to validate |

**Exit code:** `0` on success; `1` on any validation error.

**What gets checked:**

| Error type | Fatal? | Example |
|---|---|---|
| Missing `name` field | Yes | `- command: show_version` (no name) |
| Missing `command` (non-metadata/cross_check) | Yes | `- name: "test"` (no command) |
| Missing `path` | Yes | name+command only, no path |
| No `condition`/`conditions`/`branches` when needed | Yes | check with `value` but no condition |
| `condition` has no `value` | Yes | `condition: eq` with no `value:` |
| Unknown condition name | Warning | `condition: equals` (should be `eq`) |
| Unknown severity | Warning | `severity: blocker` |
| Unknown match value | Warning | `match: every` |
| Duplicate check name | Warning | two checks named `"BGP peers up"` |

Fatal errors exit 1. Warnings are printed but do not prevent execution when loaded by `health`/`health-all`.

---

### 7.4 `baseline` — Auto-Generate Starter Checks

Reads a snapshot and writes a YAML check file with every scalar field's current value as an `eq` assertion. Review and delete dynamic fields (counters, uptime, timestamps) before using in CI.

```bash
python report.py baseline \
  --snapshot data/json/N9K-CAMA-WAN-1_03-May-26.json \
  --output   checks/baseline_N9K-CAMA-WAN-1.yaml

# Omit --output to print to stdout instead
python report.py baseline --snapshot data/json/device.json
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--snapshot` | Yes | JSON snapshot file |
| `--output` | No | Output YAML path; prints to stdout if omitted |

**Output format:**

```yaml
# AUTO-GENERATED baseline — review before use.
# Delete or adjust dynamic fields (counters, uptime, timestamps).
# Generated: 2026-05-03 14:30  Source: N9K-CAMA-WAN-1_03-May-26.json  Host: N9K-CAMA-WAN-1

checks:
  - name: "[show_version] hostname baseline"
    command: show_version
    path: "[0].hostname"
    condition: eq
    value: "N9K-CAMA-WAN-1"
    severity: warn
```

All generated checks default to `severity: warn` so they never block CI until explicitly promoted to `critical`.

---

### 7.5 `coverage` — Check Coverage Analysis

Cross-references a snapshot against a check YAML and reports the gaps.

```bash
# With checks — full gap analysis
python report.py coverage \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml

# Without checks — just list parsed commands
python report.py coverage --snapshot data/json/N9K.json

# Save result as JSON
python report.py coverage \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --output   coverage_report.json
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--snapshot` | Yes | JSON snapshot file |
| `--checks` | No | Health checks YAML; shows full gap analysis when provided |
| `--output` | No | Output JSON file; prints to stdout if omitted |

**Output sections:**

| Section | Meaning |
|---------|---------|
| **Parsed but unchecked** | Commands that have parsed output but no health check — prime candidates for new checks |
| **Checks with no snapshot data** | YAML references a command key not in the snapshot — check will silently produce no results |
| **Checks on non-parsed commands** | Command exists but has `no_template`/`partial`/`failed` status — check may evaluate against empty data |

---

### 7.6 `health` — Single Device Health Checks

```bash
# Print JSON results to stdout (no output file)
python report.py health \
  --snapshot data/json/N9K-CAMA-WAN-1_03-May-26.json \
  --checks   checks/base.yaml

# HTML report
python report.py health \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --output   reports/health.html

# JSON report
python report.py health \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --output   reports/health.json

# Device-specific checks (merged on top of base)
python report.py health \
  --snapshot      data/json/N9K.json \
  --checks        checks/base.yaml \
  --device-checks checks/devices/N9K-CAMA-WAN-1.yaml \
  --output        reports/health.html

# Baseline delta comparison (compare_baseline: checks require this)
python report.py health \
  --snapshot data/json/N9K_today.json \
  --checks   checks/base.yaml \
  --baseline data/json/N9K_yesterday.json \
  --output   reports/health.html

# Tag filter — only run checks tagged "bgp" or "ospf"
python report.py health \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --tags     bgp,ospf

# Verify-only — run checks, print results, write NO files
python report.py health \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --verify-only
```

**All options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--snapshot` | Yes | — | JSON snapshot file |
| `--checks` | Yes | — | Default health checks YAML |
| `--device-checks` | No | — | Device-specific checks YAML; overrides on name clash |
| `--baseline` | No | — | Previous snapshot JSON for `compare_baseline:` checks |
| `--tags` | No | — | Comma-separated tag filter (OR logic) |
| `--output` | No | stdout | Output file (`.html` or `.json`) |
| `--verify-only` | No | off | Run and print but write no files |

**Exit code:** `0` if no critical failures; `1` if any critical check fails or errors.

---

### 7.7 `health-all` — Multi-Device Health Checks

Runs health checks across every snapshot in a directory and produces a single combined HTML report.

```bash
# Minimal — all devices, default checks, HTML to health-reports/
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml

# Full options
python report.py health-all \
  --dir               data/json/ \
  --default-checks    checks/base.yaml \
  --device-checks-dir checks/devices/ \
  --baseline-dir      data/json-prev/ \
  --output-dir        reports/health/ \
  --output-file       health_report.html \
  --format            html \
  --since-days        7 \
  --tags              bgp,ospf \
  --verify-only

# --since-days also accepts a date string
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --since-days     "03-May-2026"

# Produce both HTML and per-device JSON
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --output-dir     reports/health/ \
  --format         both
```

**All options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--dir` | Yes | — | Directory of JSON snapshots |
| `--default-checks` | Yes | — | Base health checks YAML (all devices) |
| `--device-checks-dir` | No | — | Directory of `{hostname}.yaml` override files |
| `--baseline-dir` | No | — | Directory of previous snapshots for `compare_baseline:` checks |
| `--output-dir` | No | `health-reports/` | Output directory |
| `--output-file` | No | `health_report.html` | Combined HTML filename inside `--output-dir` |
| `--format` | No | `html` | `html` / `json` / `both` |
| `--since-days` | No | — | Skip snapshots older than N days (or a date string like `"03-May-2026"`) |
| `--tags` | No | — | Comma-separated tag filter (OR logic) |
| `--verify-only` | No | off | Run and print but write no files |

**Device-checks merge rule:** Device-specific checks in `--device-checks-dir/{hostname}.yaml` override base checks with the same `name`; all other checks are additive.

**`--format both`:** Writes the combined `health_report.html` (matrix + per-device accordions) **and** per-device `{hostname}_health.json` files.

**`--since-days`:** Accepts either an integer (days before today) or any supported date string (`DD-Mon-YYYY`, `YYYY-MM-DD`, `DD/MM/YYYY`, etc.). Snapshots whose `collection_time` can't be parsed are always included.

**Exit code:** `0` if no critical failures; `1` if any device has critical failures.

---

### 7.8 `health-diff` — Compare Two Health Runs

Compares two health report JSON files (not snapshots — health result files) and shows which checks regressed or were fixed.

```bash
# Save health results as JSON
python report.py health \
  --snapshot data/json/device_yesterday.json \
  --checks   checks/base.yaml \
  --output   runs/health_yesterday.json

python report.py health \
  --snapshot data/json/device_today.json \
  --checks   checks/base.yaml \
  --output   runs/health_today.json

# Diff the two runs
python report.py health-diff \
  --before runs/health_yesterday.json \
  --after  runs/health_today.json \
  --output reports/health_diff.html
```

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--before` | Yes | — | Older health report JSON |
| `--after` | Yes | — | Newer health report JSON |
| `--output` | No | stdout | Output file (`.html` or `.json`) |

**Change categories:**

| Tag | Meaning |
|-----|---------|
| `[REGRESS]` | pass → fail (new failure introduced) |
| `[FIXED  ]` | fail → pass (problem resolved) |
| `[ADDED  ]` | check only in "after" (newly added to YAML) |
| `[REMOVED]` | check only in "before" (removed from YAML) |
| `[--     ]` | status unchanged |

**Exit code:** `0` if no regressions; `1` if any check went from pass to fail.

---

### 7.9 `health-trend` — Time-Series Trend Report

Reads multiple health JSON result files from a directory and renders a time-series pass/fail matrix with sparklines.

```bash
# Save per-run health JSON files during each collection
python report.py health \
  --snapshot data/json/N9K_$(date +%d-%b-%y).json \
  --checks   checks/base.yaml \
  --output   trend-data/N9K_$(date +%Y%m%d).json

# Build trend report after accumulating several runs
python report.py health-trend \
  --runs-dir trend-data/ \
  --output   reports/trend.html
```

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--runs-dir` | Yes | — | Directory of health JSON result files |
| `--checks` | No | — | Checks YAML (for context labels; optional) |
| `--output` | No | `health_trend.html` | Output HTML file |

**Input file naming:** Any `*.json` files in `--runs-dir`. Files are sorted lexicographically — prefix with ISO date (`YYYYMMDD`) for correct chronological order.

---

### 7.10 `delta` — Single-Device Snapshot Diff

Compares two snapshots of the same device and reports field-level differences.

```bash
# Print JSON to stdout
python report.py delta \
  --before data/json/N9K_03-May-26.json \
  --after  data/json/N9K_04-May-26.json

# HTML report
python report.py delta \
  --before data/json/N9K_03-May-26.json \
  --after  data/json/N9K_04-May-26.json \
  --output reports/delta.html
```

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--before` | Yes | — | Older snapshot JSON |
| `--after` | Yes | — | Newer snapshot JSON |
| `--output` | No | stdout | Output file (`.html` or `.json`) |

**Row matching:** For list-of-dicts tables, the engine looks for a natural key (`interface`, `neighbor`, `neighbor_id`, `network`, `prefix`, `vlan_id`) to match rows across snapshots before diffing — position changes don't appear as diffs.

---

### 7.11 `delta-all` — Multi-Device Snapshot Diff

Matches snapshots by hostname across two directories and runs a delta for each device.

```bash
python report.py delta-all \
  --before-dir snapshots/03-May-26/ \
  --after-dir  snapshots/04-May-26/ \
  --output-dir reports/delta/ \
  --output-file index.html \
  --format      html
```

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--before-dir` | Yes | — | Directory of "before" snapshots |
| `--after-dir` | Yes | — | Directory of "after" snapshots |
| `--output-dir` | No | `delta-reports/` | Output directory |
| `--output-file` | No | `index.html` | Index HTML filename inside output dir |
| `--format` | No | `html` | `html` / `json` / `both` |

Devices in one directory only print `[WARN] unmatched`. An `index.html` is always written to `--output-dir`.

---

### 7.12 `search` — Full-Text Search Across Snapshots

Searches for a string inside every snapshot's raw CLI output and/or parsed JSON values.

```bash
# Search everything — raw + parsed
python report.py search --dir data/json/ --query "10.0.0.100"

# Limit to one command
python report.py search --dir data/json/ --query "10.0.0.100" \
  --command show_ip_bgp_summary

# Raw output only
python report.py search --dir data/json/ --query "BGP_ERR" --raw-only

# Parsed JSON only
python report.py search --dir data/json/ --query "65001" --parsed-only

# Case-sensitive
python report.py search --dir data/json/ --query "FULL" --case-sensitive

# Show 2 lines of context around each raw match
python report.py search --dir data/json/ --query "Error" --context 2
```

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--dir` | Yes | — | Directory of JSON snapshots |
| `--query` | Yes | — | Search string |
| `--command` | No | — | Limit search to this one command key |
| `--raw-only` | No | off | Search only raw output |
| `--parsed-only` | No | off | Search only parsed JSON values |
| `--case-sensitive` | No | off | Case-insensitive by default |
| `--context` | No | `0` | Lines of surrounding raw context per match |

**Output example:**

```
[N9K-WAN-1]
  show_ip_bgp_summary  (raw, line 14)
    10.0.0.100        4 65001    1234    1234
  show_ip_route        (parsed, [3].next_hop)
    10.0.0.100

Found 2 match(es) in 1 device(s)  [query: '10.0.0.100']
```

**Exit code:** `0` if any match found; `1` if no matches (useful in shell scripts/CI).

---

### 7.13 `test-template` — Template Development

Parses a raw CLI output file with a specific template and shows what rows it produces.

```bash
# Direct template path
python report.py test-template \
  --template templates/custom/routing/cisco_nxos_show_ip_bgp_summary.textfsm \
  --raw      data/raw/bgp_output.txt

# TTP template
python report.py test-template \
  --template templates/ttp/routing/cisco_nxos_show_ip_bgp_summary_vrf_all.ttp \
  --raw      data/raw/bgp_output.txt

# Auto-discovery mode (finds template by convention)
python report.py test-template \
  --platform cisco_nxos \
  --command  "show ip bgp summary" \
  --raw      data/raw/bgp_output.txt
```

**Options:**

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--template` | No* | — | Template file path (`.textfsm` or `.ttp`) |
| `--raw` | Yes | — | Raw CLI output text file |
| `--platform` | No* | — | Platform for auto-discovery mode |
| `--command` | No* | — | Command string for auto-discovery mode |

*Either `--template` OR (`--platform` + `--command`) is required.

**Output:**

```
Template: templates/custom/routing/cisco_nxos_show_ip_bgp_summary.textfsm  [textfsm]
Rows:     4
Columns:  NEIGHBOR, VERSION, REMOTE_AS, UPDOWN, STATE_PFX

First 5 rows:
  {"NEIGHBOR": "10.0.0.1", "REMOTE_AS": "65001", "UPDOWN": "5w2d", "STATE_PFX": "419918"}
  ...
```

---

## 8. Health Check YAML Reference

### 8.1 File Structure

```yaml
# checks/my_checks.yaml
checks:
  - name: "Human-readable check name"    # required
    command: show_version                 # required (unless metadata: or cross_check:)
    path: "[0].version"                  # required (unless count: or metadata: or cross_check:)
    condition: matches
    value: '^\d+'
    severity: critical                   # optional (default: critical)
    match: all                           # optional (default: all)
    tags: [bgp, ci-blocking]             # optional
    skip_if:                             # optional
      metadata: hostname
      condition: not_matches
      value: "^N9K-"
    print: "Version: {{value}}"          # optional
```

Top-level check fields summary:

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique human-readable label |
| `command` | Mostly | Normalized command key (underscores) |
| `path` | Mostly | JSON path into parsed output |
| `condition` | One of these | Single condition (string) |
| `conditions` | One of these | AND list of conditions |
| `branches` | One of these | If/elif/else per row |
| `cross_check` | One of these | Cross-command check |
| `count` | One of these | Assert item count from path expansion |
| `compare_baseline` | One of these | Delta vs previous snapshot |
| `metadata` | One of these | Check snapshot metadata fields |
| `value` | Depends | Expected value for single condition |
| `severity` | No | `critical` (default) / `warn` / `info` |
| `match` | No | `all` (default) / `any` |
| `tags` | No | List of string tags |
| `skip_if` | No | Skip condition (metadata-based) |
| `print` | No | Print template for surfacing resolved values |

---

### 8.2 Path Syntax

Paths navigate the parsed JSON structure.

| Token | Meaning |
|-------|---------|
| `[0]` | Index into a list |
| `[*]` | Expand all items of a list or all values of a dict |
| `.field` | Access a dict key |
| `field` (no dot) | Same as `.field` at path start |

| Path | Accesses |
|------|---------|
| `[0].os` | First list element, `os` field |
| `[*].status` | `status` field from every row |
| `neighbors[*].state` | `state` from every neighbor |
| `vrfs[*].summary.total_routes` | Nested VRF → summary → total_routes |
| `[*][*].address_family[*].pfxrcd` | Three-level wildcard (VRF → neighbor → AF) |

**Empty path expansion:** If `[*]` expands to zero items, the check vacuously passes (no items violate the condition).

**Mixed-dict expansion:** When `[*]` hits a dict with both scalar values and nested dicts, scalar entries are automatically skipped — only nested dicts/lists are expanded.

---

### 8.3 All Conditions

#### Basic comparison

| Condition | Passes when |
|-----------|-------------|
| `eq` | actual == expected |
| `ne` | actual != expected |
| `gt` | actual > expected (numeric) |
| `gte` | actual ≥ expected (numeric) |
| `lt` | actual < expected (numeric) |
| `lte` | actual ≤ expected (numeric) |

#### String matching

| Condition | Passes when |
|-----------|-------------|
| `contains` | actual contains expected as substring |
| `not_contains` | actual does NOT contain expected |
| `matches` | `re.search(expected, str(actual))` succeeds |

#### Set membership

| Condition | Passes when | `value` must be |
|-----------|-------------|-----------------|
| `one_of` | actual is in the list | YAML list `[...]` |
| `not_one_of` | actual is NOT in the list | YAML list `[...]` |

#### Duration comparison

Both `actual` (from snapshot) and `value` (threshold) are parsed through the same duration parser.

| Condition | Passes when actual duration is |
|-----------|-------------------------------|
| `duration_gte` | ≥ expected |
| `duration_gt` | > expected |
| `duration_lte` | ≤ expected |
| `duration_lt` | < expected |

**Supported duration input formats:**

| Example | Meaning |
|---------|---------|
| `"5w2d"` | 5 weeks + 2 days |
| `"2d03h"` | 2 days + 3 hours |
| `"1y3w2d4h5m6s"` | full decomposition |
| `"00:03:42"` | HH:MM:SS |
| `"15:30"` | MM:SS |
| `"30m"` | 30 minutes |
| `"5week2day"` | spelled-out units |
| `"never"` / `"n/a"` / `"-"` | 0 seconds |
| `"42"` | bare integer = 42 seconds |

#### Length comparison

Apply `len()` to actual value before comparing. Works on strings, lists, and dicts.

| Condition | Passes when `len(actual)` is |
|-----------|------------------------------|
| `len_eq` | == expected |
| `len_ne` | != expected |
| `len_gt` | > expected |
| `len_gte` | ≥ expected |
| `len_lt` | < expected |
| `len_lte` | ≤ expected |

#### Date comparison

Actual field value is parsed as a date/datetime. Supports all common formats (see §8.3.1).

| Condition | Passes when |
|-----------|-------------|
| `date_before` | actual date is before expected date |
| `date_after` | actual date is after expected date |
| `date_within_days` | actual date is at most N days ago |
| `date_older_than_days` | actual date is more than N days ago |

#### Delta (baseline diff) conditions

Used inside `compare_baseline:` checks only (see §8.9).

| Condition | Passes when |
|-----------|-------------|
| `diff_eq` / `diff_ne` | `abs(current − baseline)` == / != value |
| `diff_gt` / `diff_gte` | `abs(current − baseline)` > / ≥ value |
| `diff_lt` / `diff_lte` | `abs(current − baseline)` < / ≤ value |
| `diff_pct_gt` / `diff_pct_gte` | percentage change > / ≥ value |
| `diff_pct_lt` / `diff_pct_lte` | percentage change < / ≤ value |

---

#### 8.3.1 Supported Date Formats

Used by `date_before`/`date_after`/`date_within_days`/`date_older_than_days` and by `--since-days` when a date string is passed:

| Format | Example |
|--------|---------|
| `DD-Mon-YYYY` | `03-May-2026` |
| `DD-Mon-YY` | `03-May-26` |
| `DD-MM-YYYY` | `03-05-2026` |
| `DD/MM/YYYY` | `03/05/2026` |
| `YYYY-MM-DD` | `2026-05-03` |
| `YYYY/MM/DD` | `2026/05/03` |
| `Mon DD YYYY` | `May 3 2026` |
| `DD Mon YYYY` | `03 May 2026` |
| `YYYY-MM-DDTHH:MM:SS` | ISO with time |

---

### 8.4 Check Types

#### 8.4.1 Simple — single condition

```yaml
- name: "OS version format"
  command: show_version
  path: "[0].os"
  condition: contains
  value: "NX-OS"

- name: "All OSPF neighbors FULL"
  command: show_ip_ospf_neighbors
  path: "neighbors[*].state"
  condition: matches
  value: '^FULL'
  match: all

- name: "Interface line protocol healthy"
  command: show_interfaces
  path: "[*].line_protocol"
  condition: one_of
  value: ["up", "connected"]

- name: "No DECOM interface active"
  command: show_interface_description
  path: "[*].description"
  condition: not_one_of
  value: ["DECOM", "DECOMMISSIONED", "SHUTDOWN"]

- name: "BGP session up at least 2 days"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].updown"
  condition: duration_gte
  value: "2d"
  severity: warn

- name: "At least one KS peer REDUNDANT"
  command: show_crypto_gkm_ks_coop_detail
  path: "GETVPN-P2P[*].state"
  condition: eq
  value: "REDUNDANT"
  match: any

- name: "Hostname at least 5 characters"
  command: show_version
  path: "[0].hostname"
  condition: len_gte
  value: 5

- name: "Snapshot collected recently"
  metadata: collection_time
  condition: date_within_days
  value: 7
```

---

#### 8.4.2 AND conditions — `conditions:` list

All conditions in the list must pass for each resolved item.

```yaml
- name: "BGP prefix count in valid range"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].prefixes_received"
  conditions:
    - condition: gte
      value: 1
    - condition: lte
      value: 900000
  print: "VRF={{[*][0]}} neighbor={{[*][1]}} → {{value}} prefixes"

- name: "Interface speed and MTU correct"
  command: show_interfaces
  path: "[*].bandwidth"
  conditions:
    - condition: gte
      value: 1000
    - condition: lte
      value: 100000

- name: "CPU utilisation acceptable"
  command: show_processes_cpu
  path: "[0].cpu_5min"
  conditions:
    - condition: gte
      value: 0
    - condition: lte
      value: 80
  severity: warn
  print: "CPU 5-min: {{value}}%"
```

**Rules:**
- `conditions:` and `condition:` are mutually exclusive.
- `match: any/all` works with `conditions:` — controls whether all *rows* must pass or any one row.
- Each item needs `condition` and `value` keys.

---

#### 8.4.3 Conditional branches — `branches:`

Use when the expected value depends on another field in the same row. Evaluates IF/ELIF/ELSE per dict row.

```yaml
- name: "MTU matches interface type"
  command: show_interfaces
  path: "[*]"
  branches:
    - when:
        field: type
        condition: matches
        value: "^loopback"
      then:
        field: mtu
        condition: eq
        value: 65535
    - when:
        field: type
        condition: matches
        value: "Ethernet|port-channel"
      then:
        field: mtu
        condition: eq
        value: 9216
    - default:
        field: mtu
        condition: gte
        value: 1500
  severity: warn
  print: "{{path}} MTU={{value}}"
```

```yaml
- name: "BGP prefix count by peer type"
  command: show_ip_bgp_summary
  path: "neighbors[*]"
  branches:
    - when:
        field: peer_type
        condition: eq
        value: "iBGP"
      then:
        field: prefixes_received
        condition: gte
        value: 500
    - when:
        field: peer_type
        condition: eq
        value: "eBGP"
      then:
        field: prefixes_received
        conditions:
          - condition: gte
            value: 1
          - condition: lte
            value: 10
    - default:
        field: prefixes_received
        condition: gte
        value: 0
```

```yaml
- name: "VPC role-specific check"
  command: show_vpc_brief
  path: "[*]"
  branches:
    - when:
        field: vpc_role
        condition: eq
        value: "primary"
      then:
        field: peer_status
        condition: eq
        value: "peer-link ok"
    - when:
        field: vpc_role
        condition: eq
        value: "secondary"
      then:
        field: consistency_status
        condition: eq
        value: "SUCCESS"
    # No default — non-VPC devices have neither field; rows without a match are skipped
```

**Rules:**
- `path:` must resolve to dicts (`[*]` to expand a list of dicts).
- Branches are evaluated in order — first matching `when:` wins.
- If no `when:` matches and no `default:` is defined, the row is skipped (vacuously passes).
- `when:` supports every standard condition.
- `then:` can contain either `condition`/`value` OR a nested `conditions:` list.
- `print:` emits one line per row using the asserted field's value.

---

#### 8.4.4 Cross-check — `cross_check:`

Assert a condition on one set of rows **only when** another condition is true. The IF side and THEN side can reference the same command or different commands.

```yaml
# Same-command: if Gi1/1/0 has "PR" in description → Loopback10 must be up
- name: "PR site loopback check"
  command: show_interfaces
  cross_check:
    if:
      path: "[*]"
      field: description
      condition: contains
      value: "PR"
    then:
      path: "[*]"
      filter:
        field: interface
        condition: eq
        value: "Loopback10"
      assert:
        field: status
        condition: eq
        value: "up"
  severity: warn
```

```yaml
# Different commands: BGP must have sessions when OSPF neighbor is FULL
- name: "BGP up when OSPF present"
  cross_check:
    if:
      command: show_ip_ospf_neighbors
      path: "[*]"
      field: state
      condition: eq
      value: "FULL"
    then:
      command: show_ip_bgp_summary
      path: "neighbors[*]"
      filter:
        field: up_down
        condition: ne
        value: "never"
      assert:
        field: prefixes_received
        condition: gte
        value: 1
```

```yaml
# Metadata-gated: only check NX-OS devices
- name: "Loopback check (NX-OS only)"
  cross_check:
    if:
      metadata: platform
      condition: eq
      value: "cisco_nxos"
    then:
      command: show_interfaces
      path: "[*]"
      filter:
        field: interface
        condition: matches
        value: "^Loopback"
      assert:
        field: status
        condition: eq
        value: "up"
```

**Semantics:**
1. Resolve `if.path` — keep rows where `if.field if.condition if.value` is true.
2. Zero IF matches → **vacuously pass** (condition not applicable on this device).
3. One or more IF matches → resolve `then.path`, apply `then.filter`.
4. Zero THEN rows after filter → **error** ("target not found").
5. Assert `then.assert` on every remaining THEN row.

**Fields:**
- `if.command` / `then.command` — optional when top-level `command:` is present (defaults both sides).
- `if.metadata` — use a metadata field (`hostname`, `platform`, `collection_time`) instead of a data path.
- `then.filter` — narrow which THEN rows to assert; optional.
- `then.assert` — the actual assertion; required.

---

#### 8.4.5 Count check — `count:`

Assert how many items the path expansion produces.

```yaml
# Must have at least 4 BGP neighbors
- name: "BGP neighbor count"
  command: show_ip_bgp_summary
  path: "neighbors[*]"
  count:
    condition: gte
    value: 4

# Exactly 2 VPC peers
- name: "VPC peer count"
  command: show_vpc_brief
  path: "[*]"
  count:
    condition: eq
    value: 2

# No more than 500 routes (sanity check)
- name: "Route table not overflowing"
  command: show_ip_route
  path: "[*]"
  count:
    condition: lte
    value: 500
  severity: warn

# OSPF neighbor count within range
- name: "OSPF neighbor count 2-8"
  command: show_ip_ospf_neighbors
  path: "neighbors[*]"
  count:
    condition: gte
    value: 2
  # Add a second count check or use conditions: if you need both gte AND lte
```

`count.condition` accepts all standard numeric conditions: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`.

---

#### 8.4.6 Baseline comparison — `compare_baseline:`

Compare current values against the same path in a previous snapshot. Requires `--baseline <old.json>` (for `health`) or `--baseline-dir <dir>` (for `health-all`).

```yaml
# Absolute difference: prefix count must not change by more than 100
- name: "BGP prefix count stable"
  command: show_ip_bgp_summary
  path: "neighbors[*].prefixes_received"
  compare_baseline:
    condition: diff_lte
    value: 100

# Percentage difference: must stay within 20% of yesterday
- name: "BGP prefix count within 20% of baseline"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].prefixes_received"
  compare_baseline:
    condition: diff_pct_lte
    value: 20
  severity: warn

# Standard condition: current must be >= baseline (no drop allowed)
- name: "Route count not lower than baseline"
  command: show_ip_route
  path: "[*]"
  compare_baseline:
    condition: gte   # current count >= baseline count
  # note: no 'value' needed — baseline_value is the reference

# Exact match: hostname must not change
- name: "Hostname unchanged"
  command: show_version
  path: "[0].hostname"
  compare_baseline:
    condition: eq
```

**Delta conditions:**

| Condition | Formula | Passes when |
|-----------|---------|-------------|
| `diff_lte` | `abs(current − baseline)` | ≤ value |
| `diff_gte` | `abs(current − baseline)` | ≥ value |
| `diff_lt` | `abs(current − baseline)` | < value |
| `diff_gt` | `abs(current − baseline)` | > value |
| `diff_pct_lte` | `abs(current − baseline) / baseline × 100` | ≤ value % |
| `diff_pct_gte` | `abs(current − baseline) / baseline × 100` | ≥ value % |
| `diff_pct_lt` | `abs(current − baseline) / baseline × 100` | < value % |
| `diff_pct_gt` | `abs(current − baseline) / baseline × 100` | > value % |

Standard conditions (`eq`, `gte`, etc.) inside `compare_baseline:` use the baseline value as the expected, so no `value` field is needed.

**Using with `health`:**

```bash
python report.py health \
  --snapshot  data/json/N9K_today.json \
  --checks    checks/base.yaml \
  --baseline  data/json/N9K_yesterday.json
```

**Using with `health-all`:**

```bash
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --baseline-dir   data/json-prev/
```

The newest `{hostname}*.json` file in `--baseline-dir` is used for each device.

---

#### 8.4.7 Metadata check — `metadata:`

Check fields from the snapshot's `metadata` block directly, without needing a path into `commands`.

```yaml
# Hostname starts with expected prefix
- name: "Hostname starts with N9K"
  metadata: hostname
  condition: matches
  value: "^N9K-"

# Platform is NX-OS
- name: "Platform is cisco_nxos"
  metadata: platform
  condition: eq
  value: "cisco_nxos"

# Snapshot was collected within the last 7 days
- name: "Snapshot is current"
  metadata: collection_time
  condition: date_within_days
  value: 7
  severity: warn

# Collection time is after a specific date
- name: "Snapshot collected after cutover"
  metadata: collection_time
  condition: date_after
  value: "01-Jan-2026"
```

Available metadata fields from `snapshot["metadata"]`:
- `hostname` — device hostname extracted from filename/output
- `platform` — `cisco_nxos` or `cisco_ios`
- `collection_time` — date string from filename (format: `DD-Mon-YY`)
- `source_file` — original filename

---

#### 8.4.8 Metadata in `branches:` `when:` clause

Branches can route on metadata fields instead of row fields:

```yaml
- name: "MTU rule by device type"
  command: show_interfaces
  path: "[*]"
  branches:
    - when:
        metadata: platform           # ← metadata instead of field
        condition: eq
        value: "cisco_nxos"
      then:
        field: mtu
        condition: eq
        value: 9216
    - default:
        field: mtu
        condition: gte
        value: 1500
```

---

### 8.5 `match` — Any vs All

When a path uses `[*]` and expands to multiple values, `match` controls the passing threshold.

| Value | Default? | Passes when |
|-------|----------|-------------|
| `all` | Yes | Every expanded value satisfies the condition |
| `any` | No | At least one expanded value satisfies the condition |

```yaml
# PASS if every OSPF neighbor is FULL (default all)
- name: "All OSPF neighbors FULL"
  command: show_ip_ospf_neighbors
  path: "neighbors[*].state"
  condition: matches
  value: '^FULL'

# PASS if at least one GETVPN peer is REDUNDANT
- name: "At least one KS peer REDUNDANT"
  command: show_crypto_gkm_ks_coop_detail
  path: "GETVPN-P2P[*].state"
  condition: eq
  value: "REDUNDANT"
  match: any
  print: "KS peer {{[*]}} is {{value}}"

# PASS if any PIM neighbor recently reset (warning)
- name: "PIM neighbor recently reset"
  command: show_ip_pim_neighbor
  path: "[*].UPTIME"
  condition: duration_lt
  value: "1h"
  match: any
  severity: warn
  print: "PIM neighbor {{[*]}} uptime={{value}} (recently reset?)"
```

---

### 8.6 `severity` — Check Impact on Exit Code

| Value | Default? | Failure behaviour |
|-------|----------|-------------------|
| `critical` | Yes | Exit 1 — blocks CI |
| `warn` | No | No exit 1 — visible in report only |
| `info` | No | No exit 1 — purely informational |

```yaml
- name: "MTU is jumbo"
  command: show_interfaces
  path: "[*].mtu"
  condition: eq
  value: 9216
  severity: warn    # MTU mismatch is visible but never blocks CI

- name: "CPU utilisation"
  command: show_processes_cpu
  path: "[0].cpu_5min"
  condition: lte
  value: 80
  severity: info    # surface the value, never fail

- name: "OSPF neighbors all FULL"
  command: show_ip_ospf_neighbors
  path: "neighbors[*].state"
  condition: matches
  value: '^FULL'
                    # severity: critical is the default — blocks CI
```

HTML report shows colour-coded severity badges: `WARN` (amber), `INFO` (blue), no badge for `critical`.

---

### 8.7 `skip_if` — Conditional Skip

Skip a check based on a metadata condition. Useful to gate platform-specific or site-specific checks.

```yaml
# Only run BGP check on WAN-prefixed devices
- name: "BGP neighbor count"
  command: show_ip_bgp_summary
  path: "neighbors[*]"
  count:
    condition: gte
    value: 2
  skip_if:
    metadata: hostname
    condition: not_matches
    value: "^WAN-"

# Skip VPC check on non-NX-OS devices
- name: "VPC peer link"
  command: show_vpc_brief
  path: "[*].peer_status"
  condition: eq
  value: "peer-link ok"
  skip_if:
    metadata: platform
    condition: ne
    value: "cisco_nxos"

# Skip if snapshot is too old (separate from date_within_days check)
- name: "OSPF neighbors FULL"
  command: show_ip_ospf_neighbors
  path: "neighbors[*].state"
  condition: matches
  value: '^FULL'
  skip_if:
    metadata: collection_time
    condition: date_older_than_days
    value: 30
```

**Behaviour:**
- If `skip_if` condition is **true** → check returns `status: skip` — not pass, not fail.
- Skipped checks are counted in `summary.skipped` and shown with a grey `SKIP` badge in HTML.
- `skip_if` currently supports `metadata:` fields only.
- Skipped checks never contribute to the failure count or exit code.

---

### 8.8 `tags` — Check Filtering

Tags let you run subsets of checks without maintaining separate YAML files.

```yaml
- name: "BGP prefix count"
  command: show_ip_bgp_summary
  path: "neighbors[*].prefixes_received"
  condition: gte
  value: 1
  tags: [bgp, routing, ci-blocking]

- name: "OSPF neighbors FULL"
  command: show_ip_ospf_neighbors
  path: "neighbors[*].state"
  condition: matches
  value: '^FULL'
  tags: [ospf, routing]

- name: "Interface MTU"
  command: show_interfaces
  path: "[*].mtu"
  condition: eq
  value: 9216
  tags: [interfaces, warn-only]
  severity: warn
```

**CLI usage:**

```bash
# Run only BGP checks
python report.py health \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --tags     bgp

# Run routing + interfaces (OR logic — any matching tag)
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --tags           routing,interfaces

# No --tags → all checks run regardless of tags
```

**Filter logic:** OR — a check is included if it has **any** of the requested tags. Checks with no `tags:` field run normally when `--tags` is not specified, but are excluded when `--tags` is given.

---

### 8.9 Print Templates

The optional `print` field renders a human-readable line per resolved value in terminal output and HTML reports.

```yaml
# print: true — auto-format as "path -> value"
- name: "BGP uptime"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].updown"
  condition: duration_gte
  value: "2d"
  print: true
  # output: vrfs[0].neighbors[0].updown -> '5w2d'

# print: "template"
- name: "BGP prefix counts"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].prefixes_received"
  condition: gte
  value: 1
  print: "VRF={{[*][0]}} neighbor={{[*][1]}} → {{value}} prefixes"
  # output: VRF=default neighbor=10.0.0.1 → 419918 prefixes
```

#### All template variables

| Variable | Expands to |
|----------|-----------|
| `{value}` | Actual resolved value (original single-brace syntax) |
| `{path}` | Full resolved path string (original single-brace) |
| `{{value}}` | Same as `{value}` (double-brace synonym) |
| `{{path}}` | Same as `{path}` (double-brace synonym) |
| `{{[*]}}` | First wildcard key — shorthand for `{{[*][0]}}` |
| `{{[*][N]}}` | Nth wildcard key (0-indexed, counting only `[*]` hops) |
| `{{.field}}` | Value of a sibling field in the same dict row |

#### `{{[*][N]}}` indexing

Only `[*]` wildcard expansions add a bracket to the resolved path. Named key accesses (`.field`) are invisible to the index counter.

**Path:** `vrfs[*].neighbors[*].updown`

| Resolved path | `{{[*][0]}}` | `{{[*][1]}}` | `{{value}}` |
|---|---|---|---|
| `vrfs[default].neighbors[10.0.0.1].updown` | `default` | `10.0.0.1` | `5w2d` |
| `vrfs[MGMT].neighbors[10.0.0.2].updown` | `MGMT` | `10.0.0.2` | `2d03h` |

**Mental model:** Count `[*]` tokens left-to-right in your path. Each `[*]` = one index slot.

```
vrfs[*]          .neighbors[*]          .updown
  ↑                    ↑                   ← named key, not counted
index 0              index 1
```

#### Sibling field lookup (`{{.field}}`)

Fetches another field from the same parent dict as the resolved value.

```yaml
path:  "[*].pfxrcd"
print: "Neighbor={{[*]}} uptime={{.updown}} prefixes={{value}}"
# → "Neighbor=10.0.0.1 uptime=5w2d prefixes=419918"
```

#### Print-only checks (no condition)

Omit `condition`, `value`, `conditions`, and `branches` entirely. Check always passes. Displays a blue `DISPLAY` badge in HTML reports.

```yaml
# Auto-format
- name: "Current NX-OS version"
  command: show_version
  path: "[0].version"

# Custom template
- name: "BGP peer uptime"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].updown"
  print: "VRF={{[*][0]}} neighbor={{[*][1]}} up for {{value}}"

# GETVPN peer states
- name: "GETVPN peer states (informational)"
  command: show_crypto_gkm_ks_coop_detail
  path: "GETVPN-P2P[*].state"
  print: "Peer {{[*]}} → {{value}}"

# All interface descriptions
- name: "Interface descriptions"
  command: show_interface_description
  path: "[*].description"
  print: "{{[*]}} — {{value}}"
```

---

### 8.10 Per-Device Check Overrides

Split checks into two tiers for multi-device deployments:

- **Default checks** (`--checks` / `--default-checks`) — baseline for all devices
- **Device-specific checks** (`--device-checks` / `--device-checks-dir`) — per-device additions or overrides

**Merge rule:** All checks from both files are included. When the same `name` exists in both, the device-specific check **replaces** the default. All other checks are additive.

```yaml
# checks/devices/N9K-CAMA-WAN-1.yaml

checks:
  # OVERRIDE: replaces the same-named default check
  - name: "VPC peer link status"
    command: show_vpc_brief
    path: "[*].status"
    condition: not_contains
    value: "peer-link down"   # more permissive wording than default

  # ADDITION: only evaluated for this device
  - name: "Hostname matches expected"
    command: show_version
    path: "[0].hostname"
    condition: eq
    value: "N9K-CAMA-WAN-1"
    severity: critical
```

**File naming convention for `--device-checks-dir`:** `{hostname}.yaml`

`checks/devices/N9K-CAMA-WAN-1.yaml` is loaded automatically when the snapshot's `metadata.hostname` is `N9K-CAMA-WAN-1`.

---

### 8.11 Complete Example Check File

```yaml
checks:
  # ── Print-only (DISPLAY badge, no assertion) ────────────────────────────────
  - name: "Current NX-OS version (info)"
    command: show_version
    path: "[0].version"
    tags: [info]

  # ── Metadata check ───────────────────────────────────────────────────────────
  - name: "Snapshot is current"
    metadata: collection_time
    condition: date_within_days
    value: 7
    severity: warn
    tags: [metadata, warn-only]

  # ── Basic scalar ─────────────────────────────────────────────────────────────
  - name: "OS version format"
    command: show_version
    path: "[0].os"
    condition: matches
    value: '^\d+'
    tags: [baseline, ci-blocking]

  # ── Wildcard expansion (all rows must pass) ──────────────────────────────────
  - name: "No DECOM interface active"
    command: show_interface_description
    path: "[*].description"
    condition: not_one_of
    value: ["DECOM", "DECOMMISSIONED", "SHUTDOWN"]
    tags: [interfaces, ci-blocking]

  # ── Wildcard expansion (any one must pass) ───────────────────────────────────
  - name: "At least one GETVPN KS REDUNDANT"
    command: show_crypto_gkm_ks_coop_detail
    path: "GETVPN-P2P[*].state"
    condition: eq
    value: "REDUNDANT"
    match: any
    print: "KS peer {{[*]}} state: {{value}}"
    tags: [getvpn]

  # ── AND conditions ────────────────────────────────────────────────────────────
  - name: "BGP prefix count in valid range"
    command: show_ip_bgp_summary_vrf_all
    path: "vrfs[*].neighbors[*].prefixes_received"
    conditions:
      - condition: gte
        value: 1
      - condition: lte
        value: 900000
    print: "VRF={{[*][0]}} neighbor={{[*][1]}} → {{value}} prefixes"
    tags: [bgp, routing]

  # ── one_of / not_one_of ───────────────────────────────────────────────────────
  - name: "Interface line protocol healthy"
    command: show_interfaces
    path: "[*].line_protocol"
    condition: one_of
    value: ["up", "connected"]
    tags: [interfaces]

  # ── Duration conditions ───────────────────────────────────────────────────────
  - name: "BGP sessions established for at least 2 days"
    command: show_ip_bgp_summary_vrf_all
    path: "vrfs[*].neighbors[*].updown"
    condition: duration_gte
    value: "2d"
    severity: warn
    print: "VRF={{[*][0]}} neighbor={{[*][1]}} up for {{value}}"
    tags: [bgp, stability]

  # ── Length condition ──────────────────────────────────────────────────────────
  - name: "Hostname length sanity"
    command: show_version
    path: "[0].hostname"
    condition: len_gte
    value: 5
    tags: [baseline]

  # ── Count check ───────────────────────────────────────────────────────────────
  - name: "BGP neighbor count at least 2"
    command: show_ip_bgp_summary
    path: "neighbors[*]"
    count:
      condition: gte
      value: 2
    tags: [bgp, count]

  # ── Conditional branches ──────────────────────────────────────────────────────
  - name: "MTU matches interface type"
    command: show_interfaces
    path: "[*]"
    branches:
      - when:
          field: type
          condition: matches
          value: "^loopback"
        then:
          field: mtu
          condition: eq
          value: 65535
      - when:
          field: type
          condition: matches
          value: "Ethernet|port-channel"
        then:
          field: mtu
          condition: eq
          value: 9216
      - default:
          field: mtu
          condition: gte
          value: 1500
    severity: warn
    tags: [interfaces, warn-only]

  # ── Cross-check ───────────────────────────────────────────────────────────────
  - name: "PR site loopback up"
    command: show_interfaces
    cross_check:
      if:
        path: "[*]"
        field: description
        condition: contains
        value: "PR"
      then:
        path: "[*]"
        filter:
          field: interface
          condition: matches
          value: "Loopback"
        assert:
          field: status
          condition: eq
          value: "up"
    severity: warn
    tags: [cross-check]

  # ── Baseline comparison ───────────────────────────────────────────────────────
  - name: "BGP prefix count stable (diff ≤ 100)"
    command: show_ip_bgp_summary
    path: "neighbors[*].prefixes_received"
    compare_baseline:
      condition: diff_lte
      value: 100
    severity: warn
    tags: [bgp, baseline]

  # ── skip_if: skip WAN-only checks on non-WAN devices ─────────────────────────
  - name: "WAN site BGP neighbors"
    command: show_ip_bgp_summary
    path: "neighbors[*]"
    count:
      condition: gte
      value: 2
    skip_if:
      metadata: hostname
      condition: not_matches
      value: "^WAN-"
    tags: [bgp, wan]

  # ── Severity: info ────────────────────────────────────────────────────────────
  - name: "CPU 5-min utilisation"
    command: show_processes_cpu
    path: "[0].cpu_5min"
    condition: lte
    value: 90
    severity: info
    print: "CPU 5-min: {{value}}%"
    tags: [performance, info]
```

---

## 9. HTML Reports

All HTML reports are self-contained — CSS and JavaScript are embedded, no internet required.

### Single-device health report (`health --output health.html`)

| Section | Description |
|---------|-------------|
| Summary cards | Total / Passed / Failed / Errors at a glance |
| **Filter bar** | `[All] [Pass] [Fail] [Error] [Skip]` buttons + search box — filters cards in-page without reload |
| Check result cards | Green = pass, red = fail, amber = error, grey = skip, blue = display |
| Tag pills | Small coloured pills on each card showing the check's tags |
| Failure details | Offending path, actual value, failure reason |
| Severity badge | `WARN` or `INFO` badge on fail cards (no badge = critical) |
| Raw command outputs | Every command's raw CLI text; **Expand All / Collapse All** toolbar |
| Parsed JSON outputs | Every command's structured JSON; independent **Expand All / Collapse All** |

### Combined health-all report (`health_report.html`)

`health-all` writes a single `health_report.html`. No per-device HTML files.

| Section | Description |
|---------|-------------|
| Summary cards | Devices / Check Evals / Total Passed / Total Failed / Errors |
| Check Results Matrix | Check × device table. Cells: **PASS** (green) / **FAIL** (red) / **ERR** (amber) / **—** (absent). Click a cell to scroll to that device's section. |
| Per-Device Detail | Collapsible accordion per device — check results + raw CLI + parsed JSON |

Use `--format both` to also write per-device `{hostname}_health.json` alongside the matrix HTML.

### Health diff report (`health-diff`)

| Badge | Meaning |
|-------|---------|
| ⬇ Regressed | pass → fail |
| ⬆ Fixed | fail → pass |
| ✚ Added | new check in "after" |
| ✖ Removed | check removed from YAML |
| — | unchanged |

### Delta report (`delta`, `delta-all`)

Changed commands show before/after raw side by side. `delta-all` also writes an `index.html` summary table.

### Interactive HTML filtering

Every health report has a filter bar above the check list:

```
[All] [Pass] [Fail] [Error] [Skip]   🔍 Filter by name...
```

Clicking a status button shows only cards with that status. The search box filters by check name (substring, case-insensitive). Both filters work together.

---

## 10. Exit Codes and CI/CD Integration

| Subcommand | Exit 1 when |
|------------|-------------|
| `health` | Any critical check fails or errors |
| `health-all` | Any device has a critical failure or error |
| `health-diff` | Any check regressed (pass → fail) |
| `validate` | Any fatal validation error |
| `search` | No matches found (query not present in any snapshot) |
| `parse` | Template returned `no_template`, `failed`, or `raw_only` |
| `collect` (SSH) | Any device failed to connect or collect |
| All others | Always 0 (errors printed to stderr) |

### CI/CD pipeline examples

```bash
# GitHub Actions / GitLab CI — assert health, no files written
python report.py health \
  --snapshot data/json/device.json \
  --checks   checks/base.yaml \
  --verify-only
echo "Health exit: $?"

# Pre-commit hook — validate check files
python report.py validate --checks checks/base.yaml
python report.py validate --checks checks/devices/N9K-WAN-1.yaml

# Daily cron — full pipeline
python report.py collect --from-dir data/raw/ --output-dir data/json/ && \
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --output-dir     /var/www/reports/health/

# Alert on regression between runs
python report.py health \
  --snapshot data/json/device_today.json \
  --checks   checks/base.yaml \
  --output   runs/today.json

python report.py health-diff \
  --before runs/yesterday.json \
  --after  runs/today.json
# exits 1 if any regression → triggers alert
```

---

## 11. Playbook Runner — `playbook.py`

Executes a sequence of toolchain jobs defined in a CSV file from the repository root.

```bash
# Run all enabled steps
python playbook.py --playbook network_cli_parser/playbooks/daily.csv

# List steps without running
python playbook.py --playbook network_cli_parser/playbooks/daily.csv --list

# Dry-run: print commands but don't execute
python playbook.py --playbook network_cli_parser/playbooks/daily.csv --dry-run

# Run only step 3
python playbook.py --playbook network_cli_parser/playbooks/daily.csv --step 3

# Start from step 2
python playbook.py --playbook network_cli_parser/playbooks/daily.csv --from-step 2

# Only fetch and parse steps
python playbook.py --playbook network_cli_parser/playbooks/daily.csv --only-type fetch,parse
```

### CSV format

| Column | Type | Purpose |
|--------|------|---------|
| `step` | integer | Execution order |
| `name` | string | Human-readable label |
| `enabled` | `yes` / `no` | Skip without deleting the row |
| `type` | string | Which script/subcommand to call |
| `args` | string | CLI arguments passed verbatim |
| `continue_on_error` | `yes` / `no` | `no` = abort playbook on non-zero exit |
| `description` | string | Notes — ignored by runner |

### Step types

| `type` | Calls |
|--------|-------|
| `fetch` | `python fetch_logs.py <args>` |
| `parse` | `python network_cli_parser/main.py <args>` |
| `health` | `python network_cli_parser/report.py health <args>` |
| `health-all` | `python network_cli_parser/report.py health-all <args>` |
| `health-diff` | `python network_cli_parser/report.py health-diff <args>` |
| `coverage` | `python network_cli_parser/report.py coverage <args>` |
| `delta` | `python network_cli_parser/report.py delta <args>` |
| `delta-all` | `python network_cli_parser/report.py delta-all <args>` |
| `baseline` | `python network_cli_parser/report.py baseline <args>` |
| `collect` | `python network_cli_parser/report.py collect <args>` |

### Variable substitution

| Variable | Expands to | Example |
|----------|-----------|---------|
| `{date}` | Today in DD-Mon-YY | `03-May-26` |
| `{today}` | Today in YYYY-MM-DD | `2026-05-03` |
| `{yesterday}` | Yesterday in YYYY-MM-DD | `2026-05-02` |
| `{timestamp}` | Current datetime | `20260503_143000` |

### Example CSV

```csv
step,name,enabled,type,args,continue_on_error,description
1,Fetch logs,yes,fetch,--host 10.0.0.5 --username collector --legacy --name-contains N9K,no,Pull today's NX-OS CLI dumps
2,Parse dumps,yes,parse,--input network_cli_parser/data/raw/{date}/,no,Convert .txt to JSON
3,Health checks,yes,health-all,--dir network_cli_parser/data/json/{date}/ --default-checks network_cli_parser/checks/base.yaml --device-checks-dir network_cli_parser/checks/devices/ --output-dir reports/{date}/health/ --since-days 1,no,Assert health; exit 1 on critical failures
4,Coverage,yes,coverage,--snapshot network_cli_parser/data/json/{date}/N9K-WAN-1_{date}.json --checks network_cli_parser/checks/base.yaml,yes,Show unchecked commands
5,Health diff,no,health-diff,--before reports/{yesterday}/health/device_health.json --after reports/{today}/health/device_health.json,yes,Highlight regressions (disabled until day 2)
```

### Shipped playbooks

| File | Purpose |
|------|---------|
| `playbooks/reference.csv` | 30-row cheat-sheet — every step type, all flag variants (`enabled=no`; copy rows to build your own) |
| `playbooks/example.csv` | 7-step end-to-end: fetch → parse → health-all → coverage → health-diff → delta-all |
| `playbooks/daily_health.csv` | Minimal 3-step offline: collect → health-all → coverage |

---

## 12. SFTP Log Fetcher — `fetch_logs.py`

Standalone script at the repository root. Downloads device CLI log files from an SFTP server into the dated `data/raw/<date>/` directory structure.

**Dependency:** `pip install paramiko` (intentionally not in `requirements.txt`).

### Quick start

```bash
# Password auth — download everything
python fetch_logs.py \
  --host 10.0.0.5 \
  --username collector \
  --password 's3cr3t'

# Key auth
python fetch_logs.py --host 10.0.0.5 --username collector --key ~/.ssh/id_rsa

# Filter by device name
python fetch_logs.py \
  --host 10.0.0.5 \
  --username collector \
  --name-contains N9K-CAMA-WAN

# Legacy gear (old algorithms)
python fetch_logs.py \
  --host 192.168.1.254 \
  --username admin \
  --password cisco \
  --legacy \
  --no-verify-host

# Dry-run (no downloads)
python fetch_logs.py --host 10.0.0.5 --username collector --dry-run

# Resume partial download
python fetch_logs.py --host 10.0.0.5 --username collector --if-exists resume

# Recursive + progress bar
python fetch_logs.py \
  --host 10.0.0.5 \
  --username collector \
  --remote-recursive \
  --progress \
  --workers 8
```

### All options

#### Connection

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | required | SFTP server hostname or IP |
| `--port` | `22` | SSH port |
| `--timeout` | `30` | TCP connect + banner timeout (seconds) |

#### Authentication

| Option | Default | Description |
|--------|---------|-------------|
| `--username` | required | SSH username |
| `--password` | — | Password (fallback if key auth fails) |
| `--key` | — | Path to private key file |

**Auth order:** explicit key → SSH agent → default key files (`~/.ssh/id_rsa`, `id_ecdsa`, `id_ed25519`) → password → keyboard-interactive.

#### Host key

| Option | Default | Description |
|--------|---------|-------------|
| `--known-hosts` | `~/.ssh/known_hosts` | Known hosts file |
| `--no-verify-host` | off | Disable host key checking (lab only) |
| `--add-host-key` | off | Trust-on-first-use (save unknown key) |

#### Legacy algorithm overrides

| Option | Default | Description |
|--------|---------|-------------|
| `--legacy` | off | Enable old KEX + cipher + host-key algorithms |
| `--kex` | — | Comma-separated KEX algorithms |
| `--ciphers` | — | Comma-separated cipher algorithms |
| `--host-key-algs` | — | Comma-separated host key algorithms |

`--legacy` enables: `diffie-hellman-group14-sha1`, `diffie-hellman-group1-sha1`, `diffie-hellman-group-exchange-sha1` + ciphers `aes128-cbc`, `aes192-cbc`, `aes256-cbc`, `3des-cbc` + host keys `ssh-rsa`, `ssh-dss`.

#### Paths

| Option | Default | Description |
|--------|---------|-------------|
| `--remote-dir` | `/logs` | Remote SFTP directory |
| `--remote-recursive` | off | Recurse into subdirectories |
| `--local-dir` | `network_cli_parser/data/raw` | Local base; files land in `<local-dir>/<date>/` |
| `--filename-pattern` | `*.txt` | Glob pattern for remote filenames |

#### Transfer

| Option | Default | Description |
|--------|---------|-------------|
| `--name-contains` | — | Only download files whose name contains this substring (case-insensitive) |
| `--if-exists` | `skip` | `skip` / `overwrite` / `resume` |
| `--dry-run` | off | List without downloading |
| `--workers` | `4` | Parallel download threads |
| `--progress` | off | Per-file progress bar (requires `tqdm`) |

---

## 13. End-to-End Workflows

### Workflow A — Daily offline collection + health check

```bash
# 1. Collect fresh snapshots from .txt dumps
python report.py collect \
  --from-dir   data/raw/ \
  --output-dir data/json/

# 2. Run health checks on all devices
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --device-checks-dir checks/devices/ \
  --output-dir     reports/health/

# Open: reports/health/health_report.html
```

### Workflow B — Daily SSH collection + baseline delta

```bash
# 1. Collect
python report.py collect \
  --devices    devices.yaml \
  --output-dir data/json/

# 2. Health checks with baseline comparison
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --baseline-dir   data/json-prev/ \
  --output-dir     reports/health/

# 3. Snapshot diff
python report.py delta-all \
  --before-dir data/json-prev/ \
  --after-dir  data/json/ \
  --output-dir reports/delta/
```

### Workflow C — Building checks from scratch for a new device

```bash
# 1. Parse the dump
python main.py --input data/raw/N9K-WAN-1_03-May-26.txt

# 2. See what commands parsed
python report.py coverage \
  --snapshot data/json/N9K-WAN-1_03-May-26.json

# 3. Generate a baseline check file
python report.py baseline \
  --snapshot data/json/N9K-WAN-1_03-May-26.json \
  --output   checks/baseline_N9K-WAN-1.yaml
  # Edit: delete uptime/counter fields, promote good checks to severity: critical

# 4. Validate the new file
python report.py validate --checks checks/baseline_N9K-WAN-1.yaml

# 5. Test it
python report.py health \
  --snapshot data/json/N9K-WAN-1_03-May-26.json \
  --checks   checks/baseline_N9K-WAN-1.yaml \
  --output   reports/health.html
```

### Workflow D — Template development

```bash
# 1. See what the parser produces with current template
python report.py parse \
  --platform cisco_nxos \
  --command  "show ip bgp summary" \
  --raw      data/raw/bgp_output.txt

# 2. Test a specific template file
python report.py test-template \
  --template templates/custom/routing/cisco_nxos_show_ip_bgp_summary.textfsm \
  --raw      data/raw/bgp_output.txt

# 3. Auto-discover mode
python report.py test-template \
  --platform cisco_nxos \
  --command  "show ip bgp summary" \
  --raw      data/raw/bgp_output.txt

# 4. Drop new template (no YAML edit needed)
cp my_new_template.textfsm templates/custom/routing/cisco_nxos_show_ip_bgp_summary.textfsm

# 5. Re-parse to confirm
python report.py parse \
  --platform cisco_nxos \
  --command  "show ip bgp summary" \
  --raw      data/raw/bgp_output.txt
```

### Workflow E — Searching across all snapshots

```bash
# Find any snapshot that has this peer IP anywhere
python report.py search --dir data/json/ --query "10.0.0.100"

# Find "BGP_ERR" in raw show ip bgp summary output only
python report.py search \
  --dir        data/json/ \
  --query      "BGP_ERR" \
  --command    show_ip_bgp_summary \
  --raw-only

# Find all snapshots where a specific AS number appears (parsed JSON)
python report.py search \
  --dir         data/json/ \
  --query       "65001" \
  --parsed-only

# Case-sensitive search with 3 lines of context
python report.py search \
  --dir            data/json/ \
  --query          "Error" \
  --case-sensitive \
  --context        3
```

### Workflow F — CI/CD integration (verify only, no artefacts)

```bash
# In CI: validate YAML, then assert health — no files written
set -e
python report.py validate --checks checks/base.yaml
python report.py health \
  --snapshot data/json/device.json \
  --checks   checks/base.yaml \
  --verify-only
echo "All checks passed"
```

### Workflow G — Trend monitoring

```bash
# After each daily run, save the health result JSON
python report.py health \
  --snapshot data/json/N9K_$(date +%d-%b-%y).json \
  --checks   checks/base.yaml \
  --output   trend-data/N9K_$(date +%Y%m%d).json

# After accumulating a week of data, render the trend
python report.py health-trend \
  --runs-dir trend-data/ \
  --output   reports/trend.html
```

### Workflow H — Tag-based partial runs

```bash
# Quick BGP-only check (fast CI gate)
python report.py health \
  --snapshot data/json/N9K.json \
  --checks   checks/base.yaml \
  --tags     bgp,ci-blocking \
  --verify-only

# Full check run for the weekly report
python report.py health-all \
  --dir            data/json/ \
  --default-checks checks/base.yaml \
  --output-dir     reports/weekly/
```

---

> **YAML quoting tip:** Always use single quotes (`'...'`) for `value` strings that contain regex metacharacters (`\d`, `\S`, `^`, `.`, `*`, etc.) to prevent YAML escape interpretation.
>
> **Normalized command keys:** Health checks reference commands using underscore-separated normalized keys (e.g. `show_ip_bgp_summary`), not raw command strings with spaces. The same key is used as the filename stem for templates.
>
> **Snapshot independence:** Every `report.py` subcommand reads from JSON snapshot files already on disk — `main.py` (or `report.py collect`) must run first to produce those files.
