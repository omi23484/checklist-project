# Network CLI Parser — Standard Operating Procedure

## 1. Overview

The Network CLI Structured Parser reads raw Cisco IOS / NX-OS CLI dump text files, splits them by command, parses each command's output into structured data, and writes a single JSON snapshot per file.

**Parser chain (per command):**

```
commands.yaml lookup
    ├── raw_only    → skip parsing, preserve raw text
    ├── ntc         → NTC Templates (ntc-templates library)
    ├── custom      → Custom TextFSM template
    ├── ttp         → TTP template
    ├── hierarchical→ Python regex parser (multicast commands)
    └── auto_discover (unknown commands)
            ├── Step 1: NTC Templates (reconstructed command string)
            ├── Step 2: Convention TextFSM ({platform}_{cmd}.textfsm)
            ├── Step 3: Convention TTP     ({platform}_{cmd}.ttp)
            └── no_template (raw preserved, structured parsing skipped)
```

Every command found in the log appears in the JSON output, even commands with no registered template.

---

## 2. Running the Parser

```bash
cd network_cli_parser
pip install -r requirements.txt

# Single file
python main.py --input data/raw/N9K-CAMA-WAN-1_03-May-26.txt

# Directory (processes all .txt files)
python main.py --input data/raw/

# Custom output directory
python main.py --input data/raw/ --output /tmp/parsed/
```

JSON output is written to `data/json/` by default, one file per input.

---

## 3. Directory Structure

```
network_cli_parser/
├── main.py                     # Parser entry point — orchestrates per-file processing
├── report.py                   # Report generator (delta + health subcommands)
├── commands.yaml               # Command registry (platform → command → strategy)
├── requirements.txt
│
├── parsers/
│   ├── command_mapper.py       # Loads commands.yaml; returns strategy per command
│   ├── splitter.py             # Splits CLI dump into {cmd: raw_output} dict
│   ├── ntc_engine.py           # Wrapper around ntc-templates library
│   ├── custom_engine.py        # TextFSM engine; auto-discovery support
│   ├── ttp_engine.py           # TTP engine; auto-discovery support
│   └── multicast_parser.py     # Hierarchical Python parsers for mroute commands
│
├── templates/
│   ├── custom/                 # TextFSM templates (.textfsm)
│   │   └── routing/            # Subdirectory by category (arbitrary, rglob scans all)
│   └── ttp/                    # TTP templates (.ttp)
│       └── routing/
│
├── utils/
│   ├── normalization.py        # Platform detection, hostname extraction, cmd normalization
│   ├── json_builder.py         # Assembles and writes the JSON snapshot
│   ├── delta.py                # Field-level diff engine between two snapshots
│   ├── health.py               # YAML-driven check evaluator against a snapshot
│   └── html_report.py          # Self-contained HTML renderer for both report types
│
├── checks/
│   └── example_health_checks.yaml   # Starter health check definitions
│
└── data/
    ├── raw/                    # Input CLI dump .txt files
    └── json/                   # Output JSON snapshots
```

---

## 4. Status Codes

| Status | Meaning |
|--------|---------|
| `parsed` | Parser returned structured data |
| `partial` | Parser ran but returned no rows (template matched nothing) |
| `raw_only` | Explicitly registered as skip in commands.yaml |
| `failed` | Parser threw an exception |
| `no_template` | Not in registry; auto-discovery found nothing; raw is preserved |

---

## 5. Adding a New Command

### Option A — Explicit registration (any parser type)

1. Add an entry to `commands.yaml` under the correct platform:

```yaml
cisco_nxos:
  show ip ospf neighbors:
    parser: ttp
    template: cisco_nxos_show_ip_ospf_neighbors
```

2. Create the template file (see sections 6 and 7).

3. Run — the command is now fully registered.

### Option B — Auto-discovery (no YAML edit required)

Drop a template file named `{platform}_{normalized_cmd}.textfsm` or `{platform}_{normalized_cmd}.ttp` anywhere under `templates/custom/` or `templates/ttp/` respectively. The auto-discover chain picks it up automatically on the next run.

**Naming example:**
- Command: `show ip ospf neighbors` on `cisco_nxos`
- Normalized key: `show_ip_ospf_neighbors`
- TextFSM file: `templates/custom/routing/cisco_nxos_show_ip_ospf_neighbors.textfsm`
- TTP file:     `templates/ttp/routing/cisco_nxos_show_ip_ospf_neighbors.ttp`

### Option C — Unknown command, no template yet

Run the log file anyway. The JSON will contain the command with `status: "no_template"` and the full `raw` output preserved. Build a template for it and re-run.

---

## 6. Writing TextFSM Templates

TextFSM uses a state-machine model. Templates live in `templates/custom/` (any subdirectory).

### Syntax

```
Value FIELD_NAME (regex)
Value Filldown CARRY_FORWARD_FIELD (regex)

Start
  ^header line regex -> Continue
  ^${FIELD_NAME}\s+${OTHER}  -> Record

EOF
```

- `Value` declarations at the top define captured fields.
- `Filldown` carries a field value forward until a new match overwrites it (useful for VRF headers).
- `-> Record` emits the current row; `-> Continue` re-processes the same line in another state.
- `EOF` action at the end emits any buffered row.

### Naming convention

```
{platform}_{normalized_cmd}.textfsm
```

Example: `cisco_nxos_show_ip_pim_neigh.textfsm`

### Example — Multi-VRF neighbor table

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

### Registering in commands.yaml

```yaml
cisco_nxos:
  show ip pim neigh:
    parser: custom
    template: cisco_nxos_show_ip_pim_neigh
```

---

## 7. Writing TTP Templates

TTP (Template Text Parser) uses `{{ variable }}` placeholders and native `<group>` tags for hierarchical output.

### Syntax

```
{{ field_name }}
{{ field_name | re("custom_regex") }}
```

Group tags nest output into dicts:

```xml
<group name="neighbors">
{{ neighbor_id }}  {{ state }}  {{ uptime }}
</group>
```

### Naming convention

```
{platform}_{normalized_cmd}.ttp
```

Example: `cisco_nxos_show_ip_ospf_neighbors.ttp`

### Example — Flat neighbor table

```xml
<group name="neighbors">
{{ neighbor_id }}  {{ priority }}  {{ state | re("\\S+/\\s*\\S*") }}  {{ uptime }}  {{ address }}  {{ interface }}
</group>
```

Use `re()` when the field value contains spaces (e.g., `FULL/ -`) that TTP's default whitespace split can't handle.

### Example — Hierarchical (VRF → neighbors)

```xml
<group name="vrfs">
BGP summary information for VRF {{ vrf }}, address family {{ afi | re(".+") }}
BGP router identifier {{ router_id }}, local AS number {{ local_as }}

<group name="neighbors">
{{ neighbor | re("\\d+\\.\\d+\\.\\d+\\.\\d+") }}  {{ version }}  {{ remote_as }}  {{ msg_rcvd }}  {{ msg_sent }}  {{ tbl_ver }}  {{ inq }}  {{ outq }}  {{ updown }}  {{ state_pfx }}
</group>

</group>
```

Use an IP-anchored regex on the first field to avoid accidentally matching header lines.

Result JSON structure:
```json
{
  "vrfs": [
    {
      "vrf": "default",
      "afi": "IPv4 Unicast",
      "router_id": "10.0.0.1",
      "local_as": "65001",
      "neighbors": [
        {"neighbor": "10.0.0.2", "remote_as": "65002", "state_pfx": "100"}
      ]
    }
  ]
}
```

### Registering in commands.yaml

```yaml
cisco_nxos:
  show ip ospf neighbors:
    parser: ttp
    template: cisco_nxos_show_ip_ospf_neighbors
```

---

## 8. Handling Pipe-Filtered Commands (`| include`, `| grep`, etc.)

Commands with a pipe filter produce structurally different output (only matching lines), so they need their own normalized key and their own template.

### How normalization works

The pipe filter **type** is appended as a suffix; the argument is dropped (it changes per run and can't be part of a static template name):

| Raw command | Normalized key |
|-------------|----------------|
| `show ip bgp summary` | `show_ip_bgp_summary` |
| `show ip bgp summary \| include 65001` | `show_ip_bgp_summary_include` |
| `show ip bgp summary \| exclude Connected` | `show_ip_bgp_summary_exclude` |
| `show ip route \| begin 10.0.0` | `show_ip_route_begin` |
| `show ip route \| grep 10.0.0` | `show_ip_route_grep` |
| `show ip route \| count` | `show_ip_route_count` |

Supported filter keywords: `include`, `exclude`, `begin`, `grep`, `egrep`, `count`, and any other `\w+` keyword after the pipe.

### Template naming for piped variants

**TextFSM:** `cisco_nxos_show_ip_bgp_summary_include.textfsm`
**TTP:** `cisco_nxos_show_ip_bgp_summary_include.ttp`

Drop the file in any subdirectory of `templates/custom/` or `templates/ttp/` — auto-discovery picks it up with no YAML edit required.

### Explicit registration in commands.yaml

Use `| include` literally as the YAML key (the mapper normalizes it at load time):

```yaml
cisco_nxos:
  show ip bgp summary | include:
    parser: custom
    template: cisco_nxos_show_ip_bgp_summary_include
```

### Template design for piped output

Piped output is just the filtered lines — write the template to match those lines only.

**Example — `show ip bgp summary | include 65001` output:**
```
10.0.0.2        4 65001    1234    1234        1    0    0 2w3d             100
```

**TextFSM template** (`cisco_nxos_show_ip_bgp_summary_include.textfsm`):
```
Value NEIGHBOR (\d+\.\d+\.\d+\.\d+)
Value AS (\d+)
Value UPDOWN (\S+)
Value STATE_PFX (\S+)

Start
  ^${NEIGHBOR}\s+\d+\s+${AS}\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+${UPDOWN}\s+${STATE_PFX} -> Record

EOF
```

**TTP template** (`cisco_nxos_show_ip_bgp_summary_include.ttp`):
```xml
<group name="neighbors">
{{ neighbor | re("\\d+\\.\\d+\\.\\d+\\.\\d+") }}  {{ version }}  {{ remote_as }}  {{ msg_rcvd }}  {{ msg_sent }}  {{ tbl_ver }}  {{ inq }}  {{ outq }}  {{ updown }}  {{ state_pfx }}
</group>
```

---

## 9. commands.yaml Reference

All strategy shapes:

```yaml
platform_name:
  raw command string:
    parser: ntc
    template: <ntc template name>         # e.g. "show ip bgp summary"

  raw command string:
    parser: custom
    template: <textfsm stem>              # e.g. "cisco_nxos_show_ip_pim_neigh"

  raw command string:
    parser: ttp
    template: <ttp stem>                  # e.g. "cisco_nxos_show_ip_ospf_neighbors"

  raw command string:
    parser: hierarchical
    func: <function name>                 # function in parsers/multicast_parser.py

  raw command string:
    parser: raw_only                      # preserve raw, skip all parsing
```

Keys are raw command strings (spaces, not underscores). The mapper normalizes them at load time. Duplicate normalized keys within a platform emit a warning and the second entry wins.

---

## 10. Auto-Discovery vs Explicit Registration

| Scenario | Recommended approach |
|----------|---------------------|
| Command has an NTC template | Register with `parser: ntc` OR rely on auto-discovery |
| Common command, custom TextFSM | Drop `.textfsm` file; no YAML edit needed |
| Common command, TTP (hierarchical output) | Drop `.ttp` file; no YAML edit needed |
| Piped command variant | Drop `{platform}_{cmd}_{filter_type}.textfsm/.ttp`; no YAML edit needed |
| Command that should never be parsed | Register with `parser: raw_only` in YAML |
| Hierarchical multicast (VRF nesting) | Register with `parser: hierarchical`, add function to multicast_parser.py |

---

## 11. Report Generator (`report.py`)

`report.py` operates on JSON snapshots produced by `main.py`. It provides two subcommands:

| Subcommand | Purpose |
|------------|---------|
| `delta`      | Field-level diff between two single snapshots |
| `delta-all`  | Per-device delta across two directories of snapshots |
| `health`     | Evaluate a YAML check file against a single snapshot |
| `health-all` | Run health checks across a directory of snapshots |
| `baseline`   | Auto-generate a starter check YAML from a snapshot's current values |
| `collect`    | Collect snapshots via SSH (online) or process existing `.txt` dumps (offline) |

Output format is controlled by the `--output` / `--format` argument:

| Value | Output |
|-------|--------|
| `.json` / `json` | Machine-readable JSON (also printed to stdout when `--output` is omitted) |
| `.html` / `html` | Self-contained HTML report with formatted results and expandable raw output |
| `both` | Write both `.html` and `.json` per device (multi-device subcommands only) |

```bash
cd network_cli_parser

# Auto-generate baseline checks from a snapshot
python report.py baseline \
  --snapshot data/json/N9K-CAMA-WAN-1_03-May-26.json \
  --output   checks/baseline_N9K-CAMA-WAN-1.yaml

# Collect snapshots via SSH (requires netmiko)
python report.py collect \
  --devices    devices.yaml \
  --raw-dir    data/raw/ \
  --output-dir data/json/

# Process existing .txt dumps offline (no SSH needed)
python report.py collect \
  --from-dir   data/raw/ \
  --output-dir data/json/

# Single-device health — JSON to stdout
python report.py health \
  --snapshot data/json/N9K-CAMA-WAN-1_03-May-26.json \
  --checks   checks/example_health_checks.yaml

# Single-device health with per-device overrides — HTML
python report.py health \
  --snapshot      data/json/N9K-CAMA-WAN-1_03-May-26.json \
  --checks        checks/example_health_checks.yaml \
  --device-checks checks/devices/N9K-CAMA-WAN-1.yaml \
  --output        reports/health.html

# All devices in a directory — one HTML report per device + index.html
python report.py health-all \
  --dir              data/json/ \
  --default-checks   checks/example_health_checks.yaml \
  --device-checks-dir checks/devices/ \
  --output-dir       reports/health/

# Single-device delta — HTML
python report.py delta \
  --before data/json/N9K-CAMA-WAN-1_03-May-26.json \
  --after  data/json/N9K-CAMA-WAN-1_04-May-26.json \
  --output reports/delta.html

# All devices across two collection folders — one HTML report per device + index.html
python report.py delta-all \
  --before-dir snapshots/03-May-26/ \
  --after-dir  snapshots/04-May-26/ \
  --output-dir reports/delta/
```

`report.py health` and `report.py health-all` exit with code **1** if any check fails or errors — suitable for CI pipelines.

---

## 12. Writing Health Checks

Health checks live in a YAML file under `checks/`. The top-level key is `checks`, followed by a list of check definitions.

```yaml
checks:
  - name: "Human-readable check name"
    command: show_version          # normalized command key (underscores, no spaces)
    path: "[0].os"                 # path into parsed data (see Path Syntax below)
    condition: contains
    value: "NX-OS"
```

### 12.1 Path Syntax

Paths navigate the parsed JSON structure returned by the parser.

| Token | Meaning |
|-------|---------|
| `[0]` | Index into a list |
| `[*]` | Expand all items of a list **or** all values of a dict |
| `.field` | Access a dict key |
| `field` (no dot) | Same as `.field` at the start of a path |

**Examples:**

| Path | What it accesses |
|------|-----------------|
| `[0].os` | First element of a list, `os` field |
| `[*].status` | `status` field from every row in a list |
| `vrfs[*].summary.total_routes` | `total_routes` from the summary of every VRF in a dict |
| `neighbors[*].state` | `state` from every neighbor in a list |

When `[*]` expands multiple values, `contains`/`not_contains` and `matches` check **all** values. Numeric comparisons (`gt`, `lt`, etc.) check that **all** values satisfy the condition.

### 12.2 Conditions

| Condition | Passes when |
|-----------|-------------|
| `eq` | value equals expected |
| `ne` | value does not equal expected |
| `gt` | value > expected (numeric) |
| `gte` | value ≥ expected (numeric) |
| `lt` | value < expected (numeric) |
| `lte` | value ≤ expected (numeric) |
| `contains` | string value contains expected substring |
| `not_contains` | no value contains expected substring |
| `matches` | value matches expected regex (full `re.search`) |
| `duration_gt` | parsed duration > expected duration |
| `duration_gte` | parsed duration ≥ expected duration |
| `duration_lt` | parsed duration < expected duration |
| `duration_lte` | parsed duration ≤ expected duration |

**Duration conditions** convert both the actual value and the `value` field to seconds before comparing. Use them for uptime, timer, or any field that contains a human-readable duration string.

```yaml
- name: "BGP session up at least 2 days"
  command: show_ip_bgp_summary_vrf_all
  path: "vrfs[*].neighbors[*].updown"
  condition: duration_gte
  value: "2d"
```

**Supported input formats** (both actual values and the `value` threshold accept any of these):

| Example | Meaning |
|---------|---------|
| `"5w2d"` | 5 weeks + 2 days |
| `"2d03h"` | 2 days + 3 hours |
| `"1y3w2d4h5m6s"` | full decomposition |
| `"00:03:42"` | HH:MM:SS |
| `"15:30"` | MM:SS |
| `"5week2day"` | spelled-out units |
| `"2day03hour"` | spelled-out variant |
| `"never"` / `"n/a"` | treated as 0 s |
| `"42"` | bare integer = 42 seconds |

Recognised unit abbreviations: `y`/`year`, `w`/`week`, `d`/`day`, `h`/`hour`, `m`/`min`/`minute`, `s`/`sec`/`second` — singular or plural, with or without spaces.

### `match` field — any vs all

When a path uses `[*]` and expands to multiple values, the optional `match` field controls how many must satisfy the condition.

| `match` value | Default? | Passes when |
|---------------|----------|-------------|
| `all` | Yes | **Every** expanded value satisfies the condition |
| `any` | No | **At least one** expanded value satisfies the condition |

Use `match: any` when you want a check that passes as long as at least one instance is healthy (e.g. at least one IKE peer is `Established`).

```yaml
- name: "At least one IKE peer is Established"
  command: show_crypto_gkm_ks_coop_detail
  path: "goid[*].peer[*].ike_status"
  condition: matches
  value: "Established"
  match: any
```

Omitting `match` (or setting it to `all`) preserves the original behaviour — all values must pass.

### 12.3 Severity levels

The optional `severity` field controls whether a check failure causes `report.py health` / `health-all` to exit with code 1:

| severity | Default? | Exit code on failure |
|----------|----------|---------------------|
| `critical` | Yes | exit 1 — blocks CI |
| `warn` | No | no exit 1 — visible in report only |
| `info` | No | no exit 1 — informational |

```yaml
- name: "MTU is jumbo"
  command: show_interfaces
  path: "[*].mtu"
  condition: eq
  value: 9216
  severity: warn    # MTU mismatch is a warning, not a blocker
```

Auto-generated baseline checks (`report.py baseline`) default to `severity: warn` so they never block CI until the user explicitly promotes them to `critical`.

### 12.4 Full Example (checks)

```yaml
checks:
  # Scalar field check
  - name: "Show version has OS version"
    command: show_version
    path: "[0].os"
    condition: matches
    value: '^\d+'

  # All rows must pass (not_contains scans every row)
  - name: "No interface description contains DECOM"
    command: show_interface_description
    path: "[*].description"
    condition: not_contains
    value: "DECOM"

  # Dict VRF expansion — numeric comparison
  - name: "Multicast routes present"
    command: show_ip_mroute_summary
    path: "vrfs[*].summary.total_routes"
    condition: gt
    value: 0

  # Regex on every neighbor state
  - name: "All OSPF neighbors in FULL state"
    command: show_ip_ospf_neighbors
    path: "neighbors[*].state"
    condition: matches
    value: '^FULL'
```

> **YAML quoting:** Always use single quotes (`'...'`) for `value` strings that contain regex metacharacters (`\d`, `\S`, `^`, etc.) to avoid YAML escape interpretation.

### 12.5 Check File Structure

```yaml
# checks/my_device_checks.yaml
checks:
  - name: ...
  - name: ...
```

Pass any check file with `--checks`. There is no limit on the number of checks per file.

### 12.6 Per-Device Check Overrides

In multi-device deployments, checks are split into two tiers:

- **Default checks** (`--checks` / `--default-checks`) — baseline assertions valid for all devices
- **Device-specific checks** (`--device-checks` / `--device-checks-dir`) — per-device additions or overrides

**Merge rule:** All checks from both files are included. When the same `name` appears in both, the device-specific check replaces the default. All other checks are unchanged.

```yaml
# checks/devices/N9K-CAMA-WAN-1.yaml

checks:
  # OVERRIDE: replaces the default check with the same name
  - name: "VPC peer link status is up"
    command: show_vpc_brief
    path: "[*].status"
    condition: not_contains
    value: "peer-link down"   # more permissive than default "down"

  # ADDITION: only evaluated for this device
  - name: "Hostname matches expected value"
    command: show_version
    path: "[0].hostname"
    condition: eq
    value: "N9K-CAMA-WAN-1"
```

**File naming convention for `--device-checks-dir`:** `{hostname}.yaml`

Example: `checks/devices/N9K-CAMA-WAN-1.yaml` is automatically loaded when processing a snapshot whose `metadata.hostname` is `N9K-CAMA-WAN-1`. Devices with no matching file use only the default checks.

---

## 13. Delta Report

The delta report compares every command present in either snapshot and reports field-level differences.

### How row matching works

When a command's parsed output is a **list of dicts**, the engine looks for a natural key to match rows across snapshots before diffing:

| Natural key tried (in order) | Example |
|------------------------------|---------|
| `INTERFACE` / `interface` / `port` | Interface tables |
| `NEIGHBOR` / `neighbor` / `neighbor_id` | BGP / OSPF neighbor tables |
| `NETWORK` / `PREFIX` / `network` | Route tables |
| `VLAN` / `vlan_id` | VLAN tables |
| Index (fallback) | Any other list |

This means a row moving position in the list is **not** reported as a change — only genuine field value changes are.

### Output structure (JSON)

```json
{
  "metadata": {
    "before": {"hostname": "...", "collection_time": "..."},
    "after":  {"hostname": "...", "collection_time": "..."}
  },
  "summary": {
    "commands_added":    ["cmd_a"],
    "commands_removed":  [],
    "commands_changed":  ["show_vpc_brief"],
    "commands_unchanged": ["show_version", "..."]
  },
  "changes": {
    "show_vpc_brief": {
      "diffs": [
        {
          "path":   "parsed[port=Po10].status",
          "before": "up",
          "after":  "down"
        }
      ]
    }
  }
}
```

---

## 14. HTML Reports

Both `health` and `delta` subcommands produce a self-contained HTML file when `--output` ends in `.html`. No internet connection is required — all CSS and JavaScript are embedded in the file.

### Health report layout

| Section | Description |
|---------|-------------|
| Summary cards | Total / Passed / Failed / Errors at a glance |
| Check results | Color-coded card per check (green = pass, red = fail, amber = error); failures show the offending path, actual value, and reason |
| Raw command outputs | Every command's raw CLI text, open by default; **Expand All / Collapse All** buttons |

### Delta report layout

| Section | Description |
|---------|-------------|
| Metadata comparison | Before → After hostname and timestamp side by side |
| Summary cards | Added / Removed / Changed / Unchanged |
| Added & removed pills | Command names that appeared or disappeared |
| Changed commands | Diff table per command: path / before (red) / after (green) |
| Raw command outputs | Changed commands show **before and after raw side by side**; unchanged commands show the current snapshot |

### Index pages (`health-all` and `delta-all`)

Both multi-device subcommands write an `index.html` to the output directory in addition to the per-device reports.

| Index | Columns | Row color |
|-------|---------|-----------|
| `health-all` index | Hostname / Timestamp / Status / Total / Passed / Failed / Errors / Report | Muted if all-pass; normal if any failure |
| `delta-all` index | Hostname / Status / Added / Removed / Changed / Unchanged / Report | Muted if zero changes; normal if changes; faded if unmatched |

Devices that appear in only one directory (`delta-all`) or have no snapshot file (`health-all`) are listed as **UNMATCHED** with no report link.

### Toggling raw output

Raw output blocks are **open by default**. Two buttons at the top of the raw section let you collapse or expand all blocks at once:

```
[ Expand all ]  [ Collapse all ]
```

Individual blocks can also be clicked to toggle.

---

## 15. Snapshot Collector (`report.py collect`)

The `collect` subcommand handles the full data-collection pipeline — from live device to JSON snapshot — without requiring `main.py` to be called separately.

### Offline mode (no SSH required)

Reads existing `.txt` CLI dump files and converts them to JSON snapshots using the same parsing pipeline as `main.py`:

```bash
python report.py collect \
  --from-dir data/raw/ \
  --output-dir data/json/
```

This is useful when you already have raw dump files (collected manually or via another tool) and just want to produce JSON snapshots for `delta` or `health` reports.

### SSH mode (requires netmiko)

Install the optional SSH dependency first:

```bash
pip install netmiko
```

Then run:

```bash
python report.py collect \
  --devices    devices.yaml \
  --raw-dir    data/raw/        # .txt dumps saved here (optional)
  --output-dir data/json/       # JSON snapshots written here
  --password   <pw>             # optional: override password for all devices
```

`--raw-dir` is optional. If omitted, `.txt` dumps are still produced alongside the JSON output.

### `devices.yaml` format

```yaml
defaults:
  username: admin
  password: ""       # leave blank and use --password at runtime
  timeout: 30

devices:
  - hostname: N9K-CAMA-WAN-1
    host: 192.168.1.1
    platform: cisco_nxos     # determines which commands to run + which template set

  - hostname: IOS-RTR-1
    host: 10.0.0.1
    platform: cisco_ios
    username: ops             # overrides defaults.username

  - hostname: N9K-CAMA-WAN-2
    host: 192.168.1.2
    platform: cisco_nxos
    commands:                 # optional: explicit command list (overrides registry)
      - show version
      - show ip bgp summary vrf all
```

**Platform values:** `cisco_nxos`, `cisco_ios`

**Default commands:** when `commands` is not specified for a device, all non-`raw_only` commands registered in `commands.yaml` for that platform are collected.

**Device-type mapping:**
| Platform | Netmiko device_type |
|----------|---------------------|
| `cisco_nxos` | `cisco_nxos_ssh` |
| `cisco_ios` | `cisco_ios` |

### End-to-end workflow

```bash
# 1. Collect snapshots
python report.py collect --devices devices.yaml --output-dir data/json/

# 2. Compare to previous collection
python report.py delta-all \
  --before-dir data/json-prev/ \
  --after-dir  data/json/ \
  --output-dir reports/delta/

# 3. Run health checks
python report.py health-all \
  --dir data/json/ \
  --default-checks checks/example_health_checks.yaml \
  --output-dir reports/health/
```
