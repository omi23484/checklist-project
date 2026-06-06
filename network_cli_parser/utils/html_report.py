"""Self-contained HTML report renderer for health and delta reports."""

import html as _html
import json
from datetime import datetime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _e(text) -> str:
    return _html.escape(str(text) if text is not None else "")


def _badge(cls: str, label=None) -> str:
    return f'<span class="badge {_e(cls)}">{_e(label or cls.upper())}</span>'


def _json_block(data) -> str:
    return f'<pre class="raw-output">{_e(json.dumps(data, indent=2))}</pre>'


def _raw_block(cmd: str, status: str, raw_text: str, extra_html: str = "") -> str:
    return f"""
<details class="raw-block" open>
  <summary>
    <span class="arrow-icon">▶</span>
    <span class="summary-cmd">{_e(cmd)}</span>
    {_badge(status)}
    <button class="copy-btn" onclick="event.stopPropagation();copyText(this,this.closest('details').querySelector('pre').textContent)">Copy</button>
  </summary>
  <pre class="raw-output">{_e(raw_text.strip())}</pre>
  {extra_html}
</details>"""


# ---------------------------------------------------------------------------
# CSS + JS (embedded, no external deps)
# ---------------------------------------------------------------------------

_CSS = """
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#f1f5f9;--surface:#fff;--border:#e2e8f0;
  --text:#0f172a;--muted:#64748b;--faint:#94a3b8;
  --pass:#16a34a;--pass-bg:#dcfce7;
  --fail:#dc2626;--fail-bg:#fee2e2;
  --warn:#d97706;--warn-bg:#fef3c7;
  --info:#2563eb;--info-bg:#dbeafe;
  --added:#059669;--added-bg:#d1fae5;
  --removed:#dc2626;--removed-bg:#fee2e2;
  --changed:#7c3aed;--changed-bg:#ede9fe;
  --code-bg:#0f172a;--code-fg:#e2e8f0;
  --r:8px;--r-sm:4px;--r-lg:12px;
  --sh:0 1px 3px rgba(0,0,0,.1),0 1px 2px rgba(0,0,0,.06);
  --sh-sm:0 1px 2px rgba(0,0,0,.05)
}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.5;font-size:14px}

/* ---- header ---- */
.page-header{
  background:linear-gradient(135deg,#1e293b 0%,#334155 100%);
  color:#f8fafc;padding:20px 32px;
  display:flex;align-items:center;justify-content:space-between;
  gap:16px;flex-wrap:wrap
}
.header-left h1{font-size:1.2rem;font-weight:700;letter-spacing:-.02em;margin-bottom:2px}
.header-left .sub{font-size:.78rem;color:#94a3b8}
.header-right{font-size:.78rem;color:#94a3b8;text-align:right}

/* ---- layout ---- */
.container{max-width:1080px;margin:0 auto;padding:28px 24px}

/* ---- stat cards ---- */
.summary-grid{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:12px;margin-bottom:32px
}
.stat-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-lg);padding:16px 18px;box-shadow:var(--sh)
}
.stat-card .lbl{font-size:.68rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.08em;color:var(--faint);margin-bottom:4px}
.stat-card .val{font-size:2rem;font-weight:800;line-height:1}
.stat-card.total  .val{color:var(--text)}
.stat-card.pass   .val{color:var(--pass)}
.stat-card.fail   .val{color:var(--fail)}
.stat-card.error  .val{color:var(--warn)}
.stat-card.added  .val{color:var(--added)}
.stat-card.removed .val{color:var(--removed)}
.stat-card.changed .val{color:var(--changed)}
.stat-card.unchanged .val{color:var(--muted)}

/* ---- section title ---- */
.sec-title{
  font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;
  color:var(--faint);margin:28px 0 10px;padding-bottom:7px;border-bottom:1px solid var(--border)
}

/* ---- toolbar ---- */
.toolbar{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.toolbar-label{font-size:.78rem;color:var(--muted)}
.btn{
  font-size:.75rem;font-weight:500;padding:5px 12px;
  border:1px solid var(--border);border-radius:6px;
  background:var(--surface);cursor:pointer;color:var(--text);line-height:1
}
.btn:hover{background:#f8fafc;border-color:#cbd5e1}

/* ---- check cards ---- */
.check-list{display:flex;flex-direction:column;gap:8px}
.check-card{
  background:var(--surface);border:1px solid var(--border);
  border-left:4px solid var(--border);border-radius:var(--r);box-shadow:var(--sh-sm)
}
.check-card.pass {border-left-color:var(--pass)}
.check-card.fail {border-left-color:var(--fail)}
.check-card.error{border-left-color:var(--warn)}
.check-hdr{display:flex;align-items:center;gap:10px;padding:11px 15px;flex-wrap:wrap}
.check-name{font-weight:500;flex:1}
.check-cmd{
  font-family:'SFMono-Regular',Consolas,monospace;font-size:.72rem;
  color:var(--muted);background:#f8fafc;border:1px solid var(--border);
  border-radius:var(--r-sm);padding:2px 6px
}
.check-body{padding:2px 15px 12px}

/* detail grid inside check cards */
.dg{display:grid;grid-template-columns:max-content 1fr;gap:3px 14px;font-size:.82rem}
.dg .dk{
  color:var(--faint);font-size:.7rem;text-transform:uppercase;
  letter-spacing:.05em;font-weight:600;padding-top:1px
}
.dg code{
  font-family:'SFMono-Regular',Consolas,monospace;
  background:#f1f5f9;padding:1px 4px;border-radius:3px;font-size:.82em;word-break:break-all
}

/* failures */
.failure-row{
  background:var(--fail-bg);border-radius:var(--r-sm);
  padding:8px 11px;margin-bottom:5px;font-size:.8rem
}
.failure-row .fp{font-family:monospace;color:var(--fail);font-weight:600;margin-bottom:2px}
.failure-row .fa{margin-bottom:1px}
.failure-row .fa span{font-family:monospace}
.failure-row .fr{color:#7f1d1d;font-size:.78rem}

/* badge */
.badge{
  font-size:.62rem;font-weight:800;letter-spacing:.07em;
  padding:3px 7px;border-radius:var(--r-sm);white-space:nowrap;flex-shrink:0
}
.badge.PASS,.badge.pass,.badge.parsed{background:var(--pass-bg);color:var(--pass)}
.badge.FAIL,.badge.fail,.badge.failed{background:var(--fail-bg);color:var(--fail)}
.badge.ERROR,.badge.error,.badge.partial{background:var(--warn-bg);color:var(--warn)}
.badge.raw_only,.badge.no_template{background:var(--info-bg);color:var(--info)}
.badge.added{background:var(--added-bg);color:var(--added)}
.badge.removed{background:var(--removed-bg);color:var(--removed)}
.badge.changed{background:var(--changed-bg);color:var(--changed)}
.badge.clean{background:var(--pass-bg);color:var(--pass)}
.badge.warn,.badge.unmatched{background:var(--warn-bg);color:var(--warn)}
.badge.unchanged{background:#f1f5f9;color:var(--muted)}
.badge.sev-warn{background:var(--warn-bg);color:var(--warn)}
.badge.sev-info{background:var(--info-bg);color:var(--info)}
.badge.display{background:#e8f0fe;color:#1a56db}

/* ---- raw output blocks ---- */
.raw-list{display:flex;flex-direction:column;gap:8px}
details.raw-block{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);box-shadow:var(--sh-sm);overflow:hidden
}
details.raw-block>summary{
  display:flex;align-items:center;gap:10px;
  padding:11px 15px;cursor:pointer;user-select:none;list-style:none
}
details.raw-block>summary::-webkit-details-marker{display:none}
.arrow-icon{
  font-size:.6rem;color:var(--faint);
  transition:transform .15s ease;display:inline-block;flex-shrink:0;width:12px
}
details[open]>summary .arrow-icon{transform:rotate(90deg)}
.summary-cmd{font-family:'SFMono-Regular',Consolas,monospace;font-size:.85rem;font-weight:500;flex:1}
pre.raw-output{
  background:var(--code-bg);color:var(--code-fg);
  padding:14px 18px;margin:0;overflow-x:auto;
  font-size:.77rem;line-height:1.65;
  font-family:'SFMono-Regular',Consolas,'Courier New',monospace;
  white-space:pre;border-top:1px solid #1e3a5f
}

/* ---- delta specific ---- */
.meta-compare{
  display:grid;grid-template-columns:1fr auto 1fr;
  gap:14px;align-items:center;margin-bottom:28px
}
.meta-box{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:15px 18px;box-shadow:var(--sh-sm)
}
.meta-box .mb-label{
  font-size:.68rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.08em;color:var(--faint);margin-bottom:6px
}
.meta-box .mb-host{font-size:.95rem;font-weight:600;margin-bottom:3px}
.meta-box .mb-ts{font-size:.82rem;color:var(--muted)}
.meta-arrow{font-size:1.4rem;color:var(--faint);text-align:center}

.cmd-card{
  background:var(--surface);border:1px solid var(--border);
  border-left:4px solid var(--border);border-radius:var(--r);
  box-shadow:var(--sh-sm);margin-bottom:10px;overflow:hidden
}
.cmd-card.changed {border-left-color:var(--changed)}
.cmd-card.added   {border-left-color:var(--added)}
.cmd-card.removed {border-left-color:var(--removed)}
.cmd-hdr{display:flex;align-items:center;gap:10px;padding:11px 15px}
.cmd-name{font-family:monospace;font-size:.88rem;font-weight:500;flex:1}
.diff-count{font-size:.75rem;color:var(--muted)}

.diff-table{width:100%;border-collapse:collapse;font-size:.82rem}
.diff-table th{
  text-align:left;padding:7px 15px;
  background:#f8fafc;border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  font-size:.68rem;text-transform:uppercase;letter-spacing:.07em;color:var(--faint)
}
.diff-table td{padding:7px 15px;border-bottom:1px solid #f1f5f9;vertical-align:top}
.diff-table tr:last-child td{border-bottom:none}
.diff-table .dp{font-family:monospace;color:var(--muted);font-size:.79rem}
.diff-table .db{font-family:monospace;color:var(--fail)}
.diff-table .da{font-family:monospace;color:var(--pass)}
.diff-table .null{color:var(--faint);font-style:italic;font-family:sans-serif;font-size:.8rem}

.pill-list{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0}
.pill{font-family:monospace;font-size:.78rem;padding:3px 9px;border-radius:var(--r-sm)}
.pill.added  {background:var(--added-bg);  color:var(--added)}
.pill.removed{background:var(--removed-bg);color:var(--removed)}

@media(max-width:640px){
  .page-header{padding:14px 18px}
  .container{padding:18px 14px}
  .meta-compare{grid-template-columns:1fr}
  .meta-arrow{display:none}
}

/* ---- json output blocks ---- */
details.json-block{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--sh-sm);overflow:hidden}
details.json-block>summary{display:flex;align-items:center;gap:10px;padding:11px 15px;cursor:pointer;user-select:none;list-style:none}
details.json-block>summary::-webkit-details-marker{display:none}
pre.json-output{background:var(--code-bg);color:var(--code-fg);padding:14px 18px;margin:0;overflow-x:auto;font-size:.77rem;line-height:1.65;font-family:'SFMono-Regular',Consolas,'Courier New',monospace;white-space:pre;border-top:1px solid #1e3a5f}

/* ---- check matrix ---- */
.matrix-wrap{overflow-x:auto;margin-bottom:1.5rem}
.check-matrix{width:100%;border-collapse:collapse;font-size:.82rem}
.check-matrix th{background:#1a355e;color:#fff;padding:.45rem .65rem;text-align:center;white-space:nowrap;font-size:.73rem;font-weight:700}
.check-matrix th:first-child{text-align:left;min-width:200px}
.check-matrix td{padding:.4rem .65rem;border-bottom:1px solid #e8eaf0;text-align:center;font-size:.8rem}
.check-matrix td:first-child{text-align:left;color:var(--text)}
.check-matrix td a{text-decoration:none;color:inherit;display:block}
.check-matrix td.m-pass{background:#e6f4ea;color:#1a7a40;font-weight:700}
.check-matrix td.m-fail{background:#fdecea;color:#b31b1b;font-weight:700}
.check-matrix td.m-error{background:#fff3e0;color:#b36b00;font-weight:700}
.check-matrix td.m-na{color:#94a3b8;font-size:.75rem}
.check-matrix tr:hover td{filter:brightness(.96)}

/* ---- device accordion ---- */
details.device-accordion{margin-bottom:1rem;border:1px solid var(--border);border-radius:var(--r);background:var(--surface);box-shadow:var(--sh-sm)}
details.device-accordion>summary{padding:.7rem 1.1rem;cursor:pointer;font-size:.95rem;display:flex;align-items:center;gap:.7rem;list-style:none;background:#f8fafc;border-radius:var(--r)}
details.device-accordion>summary::-webkit-details-marker{display:none}
details.device-accordion[open]>summary{border-bottom:1px solid var(--border);border-radius:var(--r) var(--r) 0 0}
.device-inner{padding:1rem 1.2rem}

/* ---- copy button ---- */
.copy-btn{margin-left:auto;padding:2px 10px;font-size:.72rem;border:1px solid var(--border);border-radius:var(--r-sm);background:var(--surface);cursor:pointer;color:var(--muted);font-family:inherit;transition:background .12s,color .12s,border-color .12s;flex-shrink:0}
.copy-btn:hover{background:var(--border);color:var(--text)}
.copy-btn.copied{border-color:var(--pass);color:var(--pass);background:var(--pass-bg)}

/* ---- json tree browser ---- */
.jt-tree{background:var(--code-bg);padding:12px 16px;overflow-x:auto;border-top:1px solid #1e3a5f;font-family:'SFMono-Regular',Consolas,monospace;font-size:.77rem;line-height:1.65}
.jt-leaf{cursor:pointer;padding:1px 3px;border-radius:3px;color:var(--code-fg)}
.jt-leaf:hover{background:rgba(255,255,255,.07)}
details.jt-group{margin:0}
.jt-sum{cursor:pointer;list-style:none;padding:1px 3px;border-radius:3px;color:var(--code-fg)}
.jt-sum::-webkit-details-marker{display:none}
.jt-sum:hover{background:rgba(255,255,255,.07)}
.jt-ch{padding-left:18px;border-left:1px solid #2d4a6e}
.jt-key{color:#7dd3fc}.jt-idx{color:#94a3b8}
.jt-str{color:#86efac}.jt-num{color:#fbbf24}.jt-bool{color:#f472b6}.jt-null{color:#94a3b8;font-style:italic}
.jt-preview{color:#64748b;font-size:.73rem}
.jt-path-toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#0f172a;color:#e2e8f0;padding:7px 16px;border-radius:8px;font-size:.78rem;font-family:'SFMono-Regular',Consolas,monospace;pointer-events:none;opacity:0;transition:opacity .2s;z-index:9999;white-space:nowrap;max-width:90vw;overflow:hidden;text-overflow:ellipsis;box-shadow:0 4px 12px rgba(0,0,0,.4)}
.jt-path-toast.show{opacity:1}
"""

_JS = """
function setAllRaw(open) {
  document.querySelectorAll('details.raw-block').forEach(d => { d.open = open; });
}
function setAllJson(open) {
  document.querySelectorAll('details.json-block').forEach(d => { d.open = open; });
}
function copyText(btn, text) {
  navigator.clipboard.writeText(text).then(function() {
    var t = btn.textContent;
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(function() { btn.textContent = t; btn.classList.remove('copied'); }, 1500);
  }).catch(function() {});
}
function _jtE(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function _jtVal(v){
  if(v===null) return '<span class="jt-null">null</span>';
  if(typeof v==='boolean') return '<span class="jt-bool">'+v+'</span>';
  if(typeof v==='number') return '<span class="jt-num">'+v+'</span>';
  if(typeof v==='string') return '<span class="jt-str">"'+_jtE(v)+'"</span>';
  return '';
}
function _jtNode(key, val, path){
  var isIdx = typeof key==='number';
  var keyHtml = isIdx ? '<span class="jt-idx">['+key+']</span>' : '<span class="jt-key">"'+_jtE(String(key))+'"</span>';
  var pa = 'data-path="'+_jtE(path)+'"';
  if(val!==null && typeof val==='object'){
    var arr=Array.isArray(val);
    var entries=arr?val.map(function(v,i){return [i,v];}):Object.entries(val);
    var cnt=entries.length;
    var prev=arr?'['+cnt+']':'{'+cnt+'}';
    if(cnt===0) return '<div class="jt-leaf" '+pa+' onclick="jtPath(event,this)">'+keyHtml+': <span class="jt-preview">'+prev+'</span></div>';
    var inner=entries.map(function(e){return _jtNode(e[0],e[1],arr?path+'['+e[0]+']':path+'.'+e[0]);}).join('');
    return '<details class="jt-group"><summary class="jt-sum" '+pa+' onclick="jtPath(event,this)">'+keyHtml+': <span class="jt-preview">'+prev+'</summary><div class="jt-ch">'+inner+'</div></details>';
  }
  return '<div class="jt-leaf" '+pa+' onclick="jtPath(event,this)">'+keyHtml+': '+_jtVal(val)+'</div>';
}
function _jtRender(data, base){
  if(Array.isArray(data)) return data.map(function(v,i){return _jtNode(i,v,base+'['+i+']');}).join('');
  if(data!==null && typeof data==='object') return Object.entries(data).map(function(e){return _jtNode(e[0],e[1],base?base+'.'+e[0]:e[0]);}).join('');
  return '<span class="jt-leaf">'+_jtVal(data)+'</span>';
}
function jtPath(e,el){
  e.stopPropagation();
  var path=el.dataset.path||'';
  navigator.clipboard.writeText(path).then(function(){
    var t=document.getElementById('jt-toast');
    if(!t){t=document.createElement('div');t.id='jt-toast';t.className='jt-path-toast';document.body.appendChild(t);}
    t.textContent=path||'(root)';
    t.classList.add('show');
    clearTimeout(t._tid);
    t._tid=setTimeout(function(){t.classList.remove('show');},2200);
  }).catch(function(){});
}
function jtInit(det){
  var src=det.querySelector('.jt-src');
  var tree=det.querySelector('.jt-tree');
  if(!src||!tree||tree.dataset.loaded) return;
  try{
    var data=JSON.parse(src.textContent);
    tree.innerHTML=_jtRender(data,'');
    tree.dataset.loaded='1';
  }catch(ex){tree.textContent='JSON parse error: '+ex.message;}
}
document.addEventListener('toggle',function(e){
  var d=e.target;
  if(d.open&&d.classList&&d.classList.contains('json-block')) jtInit(d);
},true);
"""


def _page(title: str, body: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
<script>{_JS}</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Health report
# ---------------------------------------------------------------------------

def render_health(report: dict, snapshot: dict) -> str:
    meta = report.get("metadata", {})
    s    = report.get("summary", {})
    hostname = meta.get("hostname", "Unknown")
    ts       = meta.get("collection_time", "")

    # Summary cards
    cards = _summary_cards([
        ("total",   "Total",   s.get("total",  0)),
        ("pass",    "Passed",  s.get("passed", 0)),
        ("fail",    "Failed",  s.get("failed", 0)),
        ("error",   "Errors",  s.get("error",  0)),
    ])

    # Check result cards
    checks_html = _health_check_list(report.get("results", []))

    # Raw + JSON output sections
    raw_html  = _raw_outputs_section(snapshot.get("commands", {}))
    json_html = _json_outputs_section(snapshot.get("commands", {}))

    body = f"""
<div class="page-header">
  <div class="header-left">
    <h1>Health Report</h1>
    <div class="sub">{_e(hostname)} &nbsp;·&nbsp; {_e(ts)}</div>
  </div>
  <div class="header-right">
    Generated {_e(datetime.now().strftime("%Y-%m-%d %H:%M"))}
  </div>
</div>
<div class="container">
  {cards}
  <div class="sec-title">Check Results</div>
  {checks_html}
  {raw_html}
  {json_html}
</div>"""

    return _page(f"Health Report — {hostname}", body)


def render_health_all(device_data: list[dict], checks_file: str) -> str:
    """Single combined HTML report for health-all: matrix + per-device accordions."""
    import os
    n_devices    = len(device_data)
    checks_name  = os.path.basename(checks_file) if checks_file else ""
    total_checks = sum(item["report"].get("summary", {}).get("total",  0) for item in device_data)
    total_passed = sum(item["report"].get("summary", {}).get("passed", 0) for item in device_data)
    total_failed = sum(item["report"].get("summary", {}).get("failed", 0) for item in device_data)
    total_errors = sum(item["report"].get("summary", {}).get("error",  0) for item in device_data)

    cards = _summary_cards([
        ("total", "Devices",      n_devices),
        ("total", "Check Evals",  total_checks),
        ("pass",  "Passed",       total_passed),
        ("fail",  "Failed",       total_failed),
        ("error", "Errors",       total_errors),
    ])

    matrix     = _check_matrix(device_data)
    accordions = "".join(
        _device_accordion(item["report"], item["snapshot"]) for item in device_data
    )

    body = f"""
<div class="page-header">
  <div class="header-left">
    <h1>Health Report</h1>
    <div class="sub">{n_devices} device(s) &nbsp;·&nbsp; {_e(checks_name)}</div>
  </div>
  <div class="header-right">Generated {_e(datetime.now().strftime("%Y-%m-%d %H:%M"))}</div>
</div>
<div class="container">
  {cards}
  <div class="sec-title">Check Results Matrix</div>
  {matrix}
  <div class="sec-title">Per-Device Detail</div>
  {accordions}
</div>"""

    return _page(f"Health Report — {n_devices} Devices", body)


def _health_check_list(results: list) -> str:
    if not results:
        return "<p style='color:var(--muted)'>No checks defined.</p>"
    items = []
    for r in results:
        status   = r.get("status", "error")
        name     = r.get("name", "(unnamed)")
        check    = r.get("check", {})
        cmd      = check.get("command", "")
        path     = check.get("path", "")
        severity = r.get("severity", "critical")
        cond       = check.get("condition", "")
        val        = check.get("value", "")
        match_mode = check.get("match", "all")
        match_tag  = (
            f' <span style="font-size:.65rem;background:#ede9fe;color:#7c3aed;'
            f'padding:1px 5px;border-radius:3px;font-weight:700">match:{match_mode}</span>'
            if match_mode != "all" else ""
        )
        sev_badge = (
            f" {_badge('sev-' + severity, severity.upper())}"
            if severity != "critical" and status == "fail" else ""
        )
        print_only = r.get("print_only", False)

        # Build the Condition row content based on check type
        if print_only:
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
</div>"""
        elif "cross_check" in check:
            cc   = check["cross_check"]
            if_s = cc.get("if", {})
            th_s = cc.get("then", {})
            flt  = th_s.get("filter", {})
            asr  = th_s.get("assert", {})
            if_cmd_str   = _e(if_s.get("command", check.get("command", "")))
            then_cmd_str = _e(th_s.get("command", check.get("command", "")))
            cond_html = (
                f"IF <code>{if_cmd_str}</code> <code>{_e(if_s.get('path',''))}</code> "
                f"[{_e(if_s.get('field',''))} {_e(if_s.get('condition',''))} "
                f"<em>{_e(str(if_s.get('value','')))}</em>]"
                f" &#x27A1; "
                f"THEN <code>{then_cmd_str}</code> <code>{_e(th_s.get('path',''))}</code>"
            )
            if flt:
                cond_html += (f" filter [{_e(flt.get('field',''))} = "
                              f"<em>{_e(str(flt.get('value','')))}</em>]")
            cond_html += (f" assert [{_e(asr.get('field',''))} "
                          f"{_e(asr.get('condition',''))} "
                          f"<em>{_e(str(asr.get('value','')))}</em>]")
            detail_rows = f"""
<div class="dg">
  <span class="dk">Cross-Check</span><span style="font-size:.82rem">{cond_html}</span>
</div>"""
        elif "branches" in check:
            branch_parts = []
            for b in check["branches"]:
                if "when" in b:
                    w = b["when"]
                    t = b.get("then", {})
                    branch_parts.append(
                        f"IF {_e(str(w.get('field','')))} {_e(str(w.get('condition','')))} "
                        f"{_e(str(w.get('value','')))} "
                        f"-> {_e(str(t.get('field','')))} {_e(str(t.get('condition','')))} "
                        f"{_e(str(t.get('value','')))}"
                    )
                elif "default" in b:
                    d = b["default"]
                    branch_parts.append(
                        f"ELSE {_e(str(d.get('field','')))} {_e(str(d.get('condition','')))} "
                        f"{_e(str(d.get('value','')))}"
                    )
            cond_html = "<br>".join(branch_parts)
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
  <span class="dk">Condition</span><span>{cond_html}</span>{match_tag}
</div>"""
        elif "conditions" in check:
            parts = []
            for s in check["conditions"]:
                parts.append(f"<code>{_e(str(s.get('condition','')))} {_e(str(s.get('value','')))}</code>")
            cond_html = ' <span style="color:var(--muted);font-weight:700">AND</span> '.join(parts)
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
  <span class="dk">Condition</span><span>{cond_html}</span>{match_tag}
</div>"""
        elif cond in ("one_of", "not_one_of") and isinstance(val, list):
            pills = "".join(
                f'<span style="background:var(--info-bg);color:var(--info);padding:1px 6px;'
                f'border-radius:3px;font-size:.78rem;margin-right:4px">{_e(str(v))}</span>'
                for v in val
            )
            cond_html = f"<code>{_e(cond)}</code> {pills}"
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
  <span class="dk">Condition</span><span>{cond_html}</span>{match_tag}
</div>"""
        else:
            cond_html = f"<code>{_e(cond)} {_e(str(val))}</code>"
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
  <span class="dk">Condition</span><span>{cond_html}</span>{match_tag}
</div>"""

        extra = ""
        if status == "fail":
            failures = r.get("failures", [])
            rows = ""
            for f in failures:
                msgs = f.get("messages") or ([f["message"]] if f.get("message") else [])
                reason_html = "".join(f'<div class="fr">{_e(m)}</div>' for m in msgs)
                rows += f"""<div class="failure-row">
  <div class="fp">{_e(f["path"])}</div>
  <div class="fa">Actual: <span>{_e(str(f["actual"]))}</span></div>
  {reason_html}
</div>"""
            extra = f'<div class="failures">{rows}</div>'
        elif status == "error":
            msg = r.get("message", "")
            extra = f'<div class="failure-row"><div class="fr">{_e(msg)}</div></div>'
        elif r.get("note") and not print_only:
            extra = f'<div style="font-size:.78rem;color:var(--muted);margin-top:4px">&#x2139; {_e(r["note"])}</div>'

        # print: always show resolved values (blue for print-only, muted for regular)
        printed = r.get("printed")
        if printed:
            colour = "#1a56db" if print_only else "var(--muted)"
            printed_rows = "".join(
                f'<div style="font-size:.78rem;color:{colour};padding:1px 0">'
                f'<code>{_e(line)}</code></div>'
                for line in printed
            )
            extra += f'<div style="margin-top:6px">{printed_rows}</div>'

        status_badge = _badge("display", "DISPLAY") if print_only else f"{_badge(status)}{sev_badge}"
        card_class = 'pass' if print_only else _e(status)
        items.append(f"""
<div class="check-card {card_class}">
  <div class="check-hdr">
    {status_badge}
    <span class="check-name">{_e(name)}</span>
    <span class="check-cmd">{_e(cmd)}</span>
  </div>
  <div class="check-body">{detail_rows}{extra}</div>
</div>""")

    return f'<div class="check-list">{"".join(items)}</div>'


# ---------------------------------------------------------------------------
# Delta report
# ---------------------------------------------------------------------------

def render_delta(report: dict, before_snap: dict, after_snap: dict) -> str:
    b_meta = report["metadata"].get("before", {})
    a_meta = report["metadata"].get("after",  {})
    s      = report.get("summary", {})
    hostname = b_meta.get("hostname", a_meta.get("hostname", "Unknown"))

    # Metadata comparison header
    meta_html = f"""
<div class="meta-compare">
  <div class="meta-box">
    <div class="mb-label">Before</div>
    <div class="mb-host">{_e(b_meta.get("hostname","?"))}</div>
    <div class="mb-ts">{_e(b_meta.get("collection_time","?"))}</div>
  </div>
  <div class="meta-arrow">→</div>
  <div class="meta-box">
    <div class="mb-label">After</div>
    <div class="mb-host">{_e(a_meta.get("hostname","?"))}</div>
    <div class="mb-ts">{_e(a_meta.get("collection_time","?"))}</div>
  </div>
</div>"""

    cards = _summary_cards([
        ("added",     "Added",     len(s.get("commands_added",    []))),
        ("removed",   "Removed",   len(s.get("commands_removed",  []))),
        ("changed",   "Changed",   len(s.get("commands_changed",  []))),
        ("unchanged", "Unchanged", len(s.get("commands_unchanged",[]))),
    ])

    # Added / removed pills
    added_pills   = _pill_list(s.get("commands_added",   []), "added")
    removed_pills = _pill_list(s.get("commands_removed", []), "removed")
    pills_html = ""
    if added_pills or removed_pills:
        pills_html = f"""
<div class="sec-title">Added &amp; Removed Commands</div>
{added_pills}{removed_pills}"""

    # Changed commands with diffs
    changes_html = _delta_changes(report.get("changes", {}))

    # Raw outputs from "after" snapshot (changed commands only, then all others)
    changed_keys = set(report.get("changes", {}).keys())
    after_cmds   = after_snap.get("commands", {})
    before_cmds  = before_snap.get("commands", {})
    raw_html     = _delta_raw_section(changed_keys, before_cmds, after_cmds)

    body = f"""
<div class="page-header">
  <div class="header-left">
    <h1>Delta Report</h1>
    <div class="sub">{_e(hostname)} &nbsp;·&nbsp; {_e(b_meta.get("collection_time","?"))} → {_e(a_meta.get("collection_time","?"))}</div>
  </div>
  <div class="header-right">
    Generated {_e(datetime.now().strftime("%Y-%m-%d %H:%M"))}
  </div>
</div>
<div class="container">
  {meta_html}
  {cards}
  {pills_html}
  {changes_html}
  {raw_html}
</div>"""

    return _page(f"Delta Report — {hostname}", body)


def _delta_changes(changes: dict) -> str:
    if not changes:
        return ""

    items = []
    for cmd, data in sorted(changes.items()):
        diffs = data.get("diffs", [])
        rows  = "".join(
            f"""<tr>
  <td class="dp">{_e(d["path"])}</td>
  <td class="db">{_e_val(d["before"])}</td>
  <td class="da">{_e_val(d["after"])}</td>
</tr>"""
            for d in diffs
        )
        items.append(f"""
<div class="cmd-card changed">
  <div class="cmd-hdr">
    {_badge("changed")}
    <span class="cmd-name">{_e(cmd)}</span>
    <span class="diff-count">{len(diffs)} diff(s)</span>
  </div>
  <table class="diff-table">
    <thead><tr><th>Path</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>""")

    return f"""
<div class="sec-title">Changed Commands</div>
{"".join(items)}"""


def _e_val(v) -> str:
    if v is None:
        return '<span class="null">— null —</span>'
    if isinstance(v, (dict, list)):
        return f"<code>{_e(json.dumps(v))}</code>"
    return _e(str(v))


def _delta_raw_section(changed_keys: set, before_cmds: dict, after_cmds: dict) -> str:
    all_keys = sorted(set(before_cmds) | set(after_cmds))
    if not all_keys:
        return ""

    blocks = []
    for cmd in all_keys:
        if cmd in changed_keys:
            # Show both before and after side by side for changed commands
            b = before_cmds.get(cmd, {})
            a = after_cmds.get(cmd, {})
            inner = f"""
<div style="display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#1e3a5f">
  <div>
    <div style="background:#1e293b;color:#94a3b8;font-size:.68rem;padding:5px 14px;font-family:monospace;text-transform:uppercase;letter-spacing:.07em">Before</div>
    <pre class="raw-output" style="border-top:none">{_e(b.get("raw","").strip())}</pre>
  </div>
  <div>
    <div style="background:#1e293b;color:#94a3b8;font-size:.68rem;padding:5px 14px;font-family:monospace;text-transform:uppercase;letter-spacing:.07em">After</div>
    <pre class="raw-output" style="border-top:none">{_e(a.get("raw","").strip())}</pre>
  </div>
</div>"""
            status = a.get("status", b.get("status", ""))
            blocks.append(f"""
<details class="raw-block" open>
  <summary>
    <span class="arrow-icon">▶</span>
    <span class="summary-cmd">{_e(cmd)}</span>
    {_badge(status)}
    {_badge("changed")}
  </summary>
  {inner}
</details>""")
        else:
            src = after_cmds.get(cmd) or before_cmds.get(cmd, {})
            blocks.append(_raw_block(cmd, src.get("status", ""), src.get("raw", "")))

    toolbar = """
<div class="toolbar">
  <span class="toolbar-label">Raw output:</span>
  <button class="btn" onclick="setAllRaw(true)">Expand all</button>
  <button class="btn" onclick="setAllRaw(false)">Collapse all</button>
</div>"""

    return f"""
<div class="sec-title">Raw Command Outputs</div>
{toolbar}
<div class="raw-list">{"".join(blocks)}</div>"""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _raw_outputs_section(commands: dict) -> str:
    if not commands:
        return ""
    blocks = [
        _raw_block(cmd, data.get("status", ""), data.get("raw", ""))
        for cmd, data in sorted(commands.items())
    ]
    toolbar = """
<div class="toolbar">
  <span class="toolbar-label">Raw output:</span>
  <button class="btn" onclick="setAllRaw(true)">Expand all</button>
  <button class="btn" onclick="setAllRaw(false)">Collapse all</button>
</div>"""
    return f"""
<div class="sec-title">Raw Command Outputs</div>
{toolbar}
<div class="raw-list">{"".join(blocks)}</div>"""


def _json_outputs_section(commands: dict) -> str:
    if not commands:
        return ""
    blocks = []
    for cmd, data in sorted(commands.items()):
        parsed = data.get("parsed")
        if not parsed:
            continue
        json_str = json.dumps(parsed, indent=2, default=str)
        blocks.append(f"""
<details class="json-block">
  <summary>
    <span class="arrow-icon">▶</span>
    <span class="summary-cmd">{_e(cmd)}</span>
    {_badge("parsed")}
    <button class="copy-btn" onclick="event.stopPropagation();copyText(this,this.closest('details').querySelector('.jt-src').textContent)">Copy JSON</button>
  </summary>
  <div class="jt-src" style="display:none">{_e(json_str)}</div>
  <div class="jt-tree"></div>
</details>""")
    if not blocks:
        return ""
    toolbar = """
<div class="toolbar">
  <span class="toolbar-label">Parsed JSON:</span>
  <button class="btn" onclick="setAllJson(true)">Expand all</button>
  <button class="btn" onclick="setAllJson(false)">Collapse all</button>
</div>"""
    return f"""
<div class="sec-title">Parsed JSON Outputs</div>
{toolbar}
<div class="raw-list">{"".join(blocks)}</div>"""


def _check_matrix(device_data: list[dict]) -> str:
    # Collect unique check names preserving first-seen order
    seen: dict[str, int] = {}
    for item in device_data:
        for r in item["report"].get("results", []):
            name = r.get("name", "")
            if name not in seen:
                seen[name] = len(seen)
    check_names = list(seen.keys())

    if not check_names:
        return "<p style='color:var(--muted)'>No checks found.</p>"

    # Per-device status lookup and hostname
    devices = []
    for item in device_data:
        hn = item["report"].get("metadata", {}).get("hostname", item.get("hostname", "?"))
        lookup = {r.get("name", ""): r.get("status", "error")
                  for r in item["report"].get("results", [])}
        devices.append((hn, lookup))

    # Header row — abbreviate long hostnames with full name as tooltip
    hdrs = "".join(
        f'<th title="{_e(hn)}">{_e(hn[:15] + "…" if len(hn) > 15 else hn)}</th>'
        for hn, _ in devices
    )
    header_row = f'<tr><th>Check</th>{hdrs}</tr>'

    # Data rows
    data_rows = []
    for check_name in check_names:
        cells = ""
        for hn, lookup in devices:
            anchor = _e(hn.replace(" ", "_"))
            status = lookup.get(check_name)
            if status is None:
                cells += '<td class="m-na">—</td>'
            elif status == "pass":
                cells += f'<td class="m-pass"><a href="#device-{anchor}">PASS</a></td>'
            elif status == "fail":
                cells += f'<td class="m-fail"><a href="#device-{anchor}">FAIL</a></td>'
            else:
                cells += f'<td class="m-error"><a href="#device-{anchor}">ERR</a></td>'
        data_rows.append(f'<tr><td>{_e(check_name)}</td>{cells}</tr>')

    return f"""<div class="matrix-wrap">
<table class="check-matrix">
  <thead>{header_row}</thead>
  <tbody>{"".join(data_rows)}</tbody>
</table>
</div>"""


def _device_accordion(report: dict, snapshot: dict) -> str:
    meta     = report.get("metadata", {})
    s        = report.get("summary", {})
    hostname = meta.get("hostname", "?")
    ts       = meta.get("collection_time", "")
    anchor   = _e(hostname.replace(" ", "_"))

    pass_badge = _badge("pass", f'✓ {s.get("passed", 0)} Passed')
    fail_count = s.get("failed", 0)
    err_count  = s.get("error",  0)
    fail_badge = f" {_badge('fail',  f'✗ {fail_count} Failed')}" if fail_count else ""
    err_badge  = f" {_badge('error', f'! {err_count} Errors')}"  if err_count  else ""

    cards       = _summary_cards([
        ("total", "Total",  s.get("total",  0)),
        ("pass",  "Passed", s.get("passed", 0)),
        ("fail",  "Failed", s.get("failed", 0)),
        ("error", "Errors", s.get("error",  0)),
    ])
    checks_html = _health_check_list(report.get("results", []))
    raw_html    = _raw_outputs_section(snapshot.get("commands", {}))
    json_html   = _json_outputs_section(snapshot.get("commands", {}))

    return f"""
<details class="device-accordion" id="device-{anchor}">
  <summary>
    <span class="arrow-icon">▶</span>
    <strong>{_e(hostname)}</strong>
    <span style="font-size:.8rem;color:var(--muted)">{_e(ts)}</span>
    {pass_badge}{fail_badge}{err_badge}
  </summary>
  <div class="device-inner">
    {cards}
    <div class="sec-title">Check Results</div>
    {checks_html}
    {raw_html}
    {json_html}
  </div>
</details>"""


def _summary_cards(items: list[tuple]) -> str:
    cards = "".join(
        f"""<div class="stat-card {_e(cls)}">
  <div class="lbl">{_e(label)}</div>
  <div class="val">{_e(str(value))}</div>
</div>"""
        for cls, label, value in items
    )
    return f'<div class="summary-grid">{cards}</div>'


def _pill_list(cmds: list, cls: str) -> str:
    if not cmds:
        return ""
    pills = "".join(
        f'<span class="pill {_e(cls)}">{_e(cmd)}</span>' for cmd in cmds
    )
    return f'<div class="pill-list">{pills}</div>'


# ---------------------------------------------------------------------------
# Shared index-table CSS (scoped, injected once per index page)
# ---------------------------------------------------------------------------

_INDEX_TABLE_CSS = """
<style>
.index-table{width:100%;border-collapse:collapse;font-size:.82rem;
  background:var(--surface);border-radius:var(--r);overflow:hidden;
  box-shadow:var(--sh);border:1px solid var(--border)}
.index-table th{text-align:left;padding:9px 14px;background:#f8fafc;
  border-bottom:1px solid var(--border);font-size:.68rem;
  text-transform:uppercase;letter-spacing:.07em;color:var(--faint)}
.index-table td{padding:8px 14px;border-bottom:1px solid #f1f5f9;vertical-align:middle}
.index-table tr:last-child td{border-bottom:none}
.index-table a{color:var(--info);text-decoration:none}
.index-table a:hover{text-decoration:underline}
</style>"""


# ---------------------------------------------------------------------------
# Delta index page
# ---------------------------------------------------------------------------

def render_delta_index(results: list[dict], before_dir: str, after_dir: str) -> str:
    total     = len(results)
    matched   = sum(1 for r in results if r["status"] == "matched")
    unmatched = total - matched

    cards = _summary_cards([
        ("total",   "Devices",   total),
        ("changed", "Matched",   matched),
        ("removed", "Unmatched", unmatched),
    ])

    body = f"""
<div class="page-header">
  <div class="header-left">
    <h1>Delta-All Index</h1>
    <div class="sub">Before: {_e(before_dir)} &nbsp;→&nbsp; After: {_e(after_dir)}</div>
  </div>
  <div class="header-right">Generated {_e(datetime.now().strftime("%Y-%m-%d %H:%M"))}</div>
</div>
<div class="container">
  {cards}
  <div class="sec-title">Per-Device Summary</div>
  {_INDEX_TABLE_CSS}
  {_delta_index_table(results)}
</div>"""

    return _page("Delta-All Index", body)


def _delta_index_table(results: list[dict]) -> str:
    rows = []
    for r in results:
        hostname = _e(r["hostname"])
        if r["status"] == "unmatched":
            side = "after only" if r.get("side") == "after-only" else "before only"
            rows.append(f"""
<tr style="opacity:.45">
  <td><code>{hostname}</code></td>
  <td>{_badge("unmatched", side.upper())}</td>
  <td style="color:var(--faint)" colspan="4">—</td>
  <td style="color:var(--faint)">— no report —</td>
</tr>""")
        else:
            s       = r["summary"]
            added   = len(s["commands_added"])
            removed = len(s["commands_removed"])
            changed = len(s["commands_changed"])
            unch    = len(s["commands_unchanged"])
            has_changes = (added + removed + changed) > 0
            row_style   = "" if has_changes else 'style="opacity:.55"'
            status_badge = _badge("changed", "CHANGED") if has_changes else _badge("clean", "CLEAN")
            link = f'<a href="{_e(r["report_path"])}">{_e(r["report_path"])}</a>' if r.get("report_path") else "—"
            rows.append(f"""
<tr {row_style}>
  <td><code>{hostname}</code></td>
  <td>{status_badge}</td>
  <td style="color:var(--added)">{added}</td>
  <td style="color:var(--removed)">{removed}</td>
  <td style="color:var(--changed)">{changed}</td>
  <td style="color:var(--muted)">{unch}</td>
  <td>{link}</td>
</tr>""")

    return f"""<table class="index-table">
  <thead><tr>
    <th>Hostname</th><th>Status</th>
    <th>Added</th><th>Removed</th><th>Changed</th><th>Unchanged</th>
    <th>Report</th>
  </tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


# ---------------------------------------------------------------------------
# Health index page
# ---------------------------------------------------------------------------

def render_health_index(results: list[dict], snapshot_dir: str) -> str:
    total    = len(results)
    all_pass = sum(1 for r in results if r["summary"]["failed"] == 0 and r["summary"]["error"] == 0)
    failures = total - all_pass

    cards = _summary_cards([
        ("total",  "Devices",      total),
        ("pass",   "All Pass",     all_pass),
        ("fail",   "Has Failures", failures),
    ])

    body = f"""
<div class="page-header">
  <div class="header-left">
    <h1>Health-All Index</h1>
    <div class="sub">Snapshots: {_e(snapshot_dir)}</div>
  </div>
  <div class="header-right">Generated {_e(datetime.now().strftime("%Y-%m-%d %H:%M"))}</div>
</div>
<div class="container">
  {cards}
  <div class="sec-title">Per-Device Summary</div>
  {_INDEX_TABLE_CSS}
  {_health_index_table(results)}
</div>"""

    return _page("Health-All Index", body)


def _health_index_table(results: list[dict]) -> str:
    rows = []
    for r in results:
        s        = r["summary"]
        hostname = _e(r["hostname"])
        ts       = _e(r.get("timestamp", "?"))
        clean    = s["failed"] == 0 and s["error"] == 0
        badge    = _badge("pass", "PASS") if clean else _badge("fail", "FAIL")
        row_style = 'style="opacity:.55"' if clean else ""
        link = f'<a href="{_e(r["report_path"])}">{_e(r["report_path"])}</a>' if r.get("report_path") else "—"
        rows.append(f"""
<tr {row_style}>
  <td><code>{hostname}</code></td>
  <td>{ts}</td>
  <td>{badge}</td>
  <td>{s["total"]}</td>
  <td style="color:var(--pass)">{s["passed"]}</td>
  <td style="color:var(--fail)">{s["failed"]}</td>
  <td style="color:var(--warn)">{s["error"]}</td>
  <td>{link}</td>
</tr>""")

    return f"""<table class="index-table">
  <thead><tr>
    <th>Hostname</th><th>Timestamp</th><th>Status</th>
    <th>Total</th><th>Passed</th><th>Failed</th><th>Errors</th>
    <th>Report</th>
  </tr></thead>
  <tbody>{"".join(rows)}</tbody>
</table>"""


def render_health_diff(
    before_report: dict,
    after_report:  dict,
    before_path:   str = "",
    after_path:    str = "",
) -> str:
    """Render an HTML page comparing two health report JSON files."""
    bm = before_report.get("metadata", {})
    am = after_report.get("metadata", {})

    before_map = {r["name"]: r for r in before_report.get("results", [])}
    after_map  = {r["name"]: r for r in after_report.get("results", [])}
    all_names  = list(dict.fromkeys(list(before_map) + list(after_map)))

    regressions = fixed = added = removed = unchanged = 0
    rows_html   = []

    for name in all_names:
        br = before_map.get(name)
        ar = after_map.get(name)

        if br and ar:
            bs, as_ = br["status"], ar["status"]
            if bs == as_:
                unchanged += 1
                change_badge = f'<span style="color:var(--muted)">—</span>'
                row_cls = ""
            elif bs == "pass" and as_ != "pass":
                regressions += 1
                change_badge = _badge("fail", "⬇ Regressed")
                row_cls = ' style="background:#fff8f8"'
            else:
                fixed += 1
                change_badge = _badge("pass", "⬆ Fixed")
                row_cls = ' style="background:#f8fff8"'
        elif br and not ar:
            removed += 1
            bs, as_ = br["status"], None
            change_badge = _badge("removed", "✖ Removed")
            row_cls = ' style="opacity:.6"'
        else:
            added += 1
            bs, as_ = None, ar["status"]
            change_badge = _badge("added", "✚ Added")
            row_cls = ""

        b_cell = _badge(bs) if bs else '<span style="color:var(--faint)">—</span>'
        a_cell = _badge(as_) if as_ else '<span style="color:var(--faint)">—</span>'
        rows_html.append(
            f'<tr{row_cls}>'
            f'<td>{_e(name)}</td>'
            f'<td style="text-align:center">{b_cell}</td>'
            f'<td style="text-align:center">{a_cell}</td>'
            f'<td style="text-align:center">{change_badge}</td>'
            f'</tr>'
        )

    cards = _summary_cards([
        ("fail",      "Regressions", regressions),
        ("pass",      "Fixed",       fixed),
        ("info",      "Added",       added),
        ("unchanged", "Removed",     removed),
        ("total",     "Unchanged",   unchanged),
    ])

    regression_banner = (
        f'<div style="background:var(--fail-bg);color:var(--fail);font-weight:600;'
        f'padding:10px 16px;border-radius:var(--r);margin-bottom:1rem">'
        f'⚠ {regressions} regression(s) detected — checks that were passing are now failing'
        f'</div>'
    ) if regressions else ""

    table_html = f"""
<table class="diff-table" style="width:100%">
  <thead>
    <tr>
      <th style="text-align:left">Check name</th>
      <th>Before</th>
      <th>After</th>
      <th>Change</th>
    </tr>
  </thead>
  <tbody>{"".join(rows_html)}</tbody>
</table>"""

    body = f"""
<div class="page-header">
  <div class="header-left">
    <h1>Health Diff</h1>
    <div class="sub">
      {_e(bm.get("hostname", "?"))} &nbsp;·&nbsp;
      {_e(bm.get("collection_time", "?"))} → {_e(am.get("collection_time", "?"))}
    </div>
  </div>
  <div class="header-right">Generated {_e(datetime.now().strftime("%Y-%m-%d %H:%M"))}</div>
</div>
<div class="container">
  <div class="sec-title">Summary</div>
  {cards}
  {regression_banner}
  <div class="sec-title">Check-by-check Diff</div>
  <div style="font-size:.8rem;color:var(--muted);margin-bottom:.75rem">
    Before: <code>{_e(before_path)}</code> &nbsp;·&nbsp;
    After: <code>{_e(after_path)}</code>
  </div>
  {table_html}
</div>"""

    return _page(f"Health Diff — {bm.get('hostname', '?')}", body)
