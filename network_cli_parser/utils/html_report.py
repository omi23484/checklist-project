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


def _anchor(hostname: str) -> str:
    """HTML id/fragment-safe slug — '#' or quotes in a hostname would break
    the href fragment or produce mismatched id attributes."""
    import re as _re
    return _re.sub(r'[^A-Za-z0-9_-]', '_', str(hostname))


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
  /* Apple Liquid Glass tokens — see design-system.md */
  --bg:#f5f5f7;--surface:#fff;--hover:#fbfbfd;
  --text:#1d1d1f;--text-body:#424245;--text-2:#6e6e73;--text-3:#86868b;--faint:#d2d2d7;
  --hairline:rgba(0,0,0,.07);
  --accent:#0071e3;--accent-bg:rgba(0,113,227,.08);
  --pass:#1f9d4d;--pass-bg:rgba(31,157,77,.1);
  --fail:#ff3b30;--fail-bg:rgba(255,59,48,.08);
  --warn:#ff9500;--warn-bg:rgba(255,149,0,.1);
  --added:#1f9d4d;--added-bg:rgba(31,157,77,.1);
  --removed:#ff3b30;--removed-bg:rgba(255,59,48,.08);
  --changed:#5e5ce6;--changed-bg:rgba(94,92,230,.1);
  --border:var(--hairline);--muted:var(--text-2);
  --code-bg:#1d1d1f;--code-fg:#e2e2e6;
  --r-pill:999px;--r-chip:6px;--r-sm:8px;--r:12px;--r-panel:18px;
  --sh-card:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.05);
  --sh-panel:0 1px 3px rgba(0,0,0,.05),0 14px 40px rgba(0,0,0,.05);
  --sh-sm:0 1px 2px rgba(0,0,0,.04)
}
body{font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','SF Pro Display',
  'Helvetica Neue','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
  -webkit-font-smoothing:antialiased;font-optical-sizing:auto;
  background:var(--bg);color:var(--text);line-height:1.5;font-size:14px}

/* ---- header (flat hero, no glass — nothing scrolls beneath it) ---- */
.page-header{
  background:var(--bg);color:var(--text);padding:26px 32px 18px;
  display:flex;align-items:flex-end;justify-content:space-between;
  gap:16px;flex-wrap:wrap;max-width:1080px;margin:0 auto
}
.header-left h1{font-size:clamp(20px,3vw,26px);font-weight:700;letter-spacing:-.02em;
  color:var(--text);margin-bottom:4px}
.header-left .sub{font-size:.82rem;color:var(--text-2)}
.header-right{font-size:.76rem;color:var(--text-3)}

/* ---- layout ---- */
.container{max-width:1080px;margin:0 auto;padding:8px 24px 40px}

/* ---- stat cards ---- */
.summary-grid{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
  gap:12px;margin-bottom:36px
}
.stat-card{
  background:var(--surface);border-radius:var(--r);padding:16px 18px;box-shadow:var(--sh-card)
}
.stat-card .lbl{font-size:.68rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.07em;color:var(--text-3);margin-bottom:6px}
.stat-card .val{font-size:1.9rem;font-weight:700;line-height:1;letter-spacing:-.02em;
  font-variant-numeric:tabular-nums}
.stat-card.total  .val{color:var(--text)}
.stat-card.pass   .val{color:var(--pass)}
.stat-card.fail   .val{color:var(--fail)}
.stat-card.error  .val{color:var(--warn)}
.stat-card.added  .val{color:var(--added)}
.stat-card.removed .val{color:var(--removed)}
.stat-card.changed .val{color:var(--changed)}
.stat-card.unchanged .val{color:var(--text-2)}

/* ---- section title ---- */
.sec-title{
  font-size:.78rem;font-weight:600;letter-spacing:-.005em;
  color:var(--text);margin:36px 0 10px;padding-bottom:8px;border-bottom:1px solid var(--hairline)
}

/* ---- toolbar ---- */
.toolbar{display:flex;align-items:center;gap:8px;margin-bottom:12px}
.toolbar-label{font-size:.78rem;color:var(--text-2)}
.btn{
  font-size:.76rem;font-weight:550;padding:6px 14px;
  border:none;border-radius:var(--r-pill);
  background:rgba(0,0,0,.05);cursor:pointer;color:var(--text);line-height:1;
  transition:background .15s
}
.btn:hover{background:rgba(0,0,0,.08)}

/* ---- check list: ONE panel, hairline-separated rows (not fragmented cards) ---- */
.check-list{background:var(--surface);border-radius:var(--r-panel);box-shadow:var(--sh-panel);overflow:hidden}
.check-card{background:transparent;transition:background .15s}
.check-card:hover{background:var(--hover)}
.check-card+.check-card{border-top:1px solid var(--hairline)}
.check-hdr{display:flex;align-items:center;gap:10px;padding:13px 20px;flex-wrap:wrap}
.check-name{font-weight:500;flex:1;letter-spacing:-.005em}
.check-cmd{
  font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);font-size:.72rem;
  color:var(--text-2);background:rgba(0,0,0,.04);
  border-radius:var(--r-chip);padding:2px 7px
}
.check-body{padding:0 20px 14px}

/* detail grid inside check rows */
.dg{display:grid;grid-template-columns:max-content 1fr;gap:3px 14px;font-size:.82rem}
.dg .dk{
  color:var(--text-3);font-size:.68rem;text-transform:uppercase;
  letter-spacing:.05em;font-weight:600;padding-top:1px
}
.dg code{
  font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);
  background:rgba(0,0,0,.04);padding:1px 5px;border-radius:var(--r-chip);font-size:.82em;word-break:break-all
}

/* failures */
.failure-row{
  background:var(--fail-bg);border-radius:var(--r-sm);
  padding:9px 12px;margin-bottom:5px;font-size:.8rem
}
.failure-row .fp{font-family:var(--mono,monospace);color:var(--fail);font-weight:600;margin-bottom:2px}
.failure-row .fa{margin-bottom:1px}
.failure-row .fa span{font-family:var(--mono,monospace)}
.failure-row .fr{color:var(--fail);opacity:.8;font-size:.78rem}

/* badge — pill, colour used only for the status it names */
.badge{
  font-size:.66rem;font-weight:650;letter-spacing:.02em;
  padding:3px 9px;border-radius:var(--r-pill);white-space:nowrap;flex-shrink:0
}
.badge.PASS,.badge.pass,.badge.parsed{background:var(--pass-bg);color:var(--pass)}
.badge.FAIL,.badge.fail,.badge.failed{background:var(--fail-bg);color:var(--fail)}
.badge.ERROR,.badge.error,.badge.partial{background:var(--warn-bg);color:var(--warn)}
.badge.raw_only,.badge.no_template{background:var(--accent-bg);color:var(--accent)}
.badge.added{background:var(--added-bg);color:var(--added)}
.badge.removed{background:var(--removed-bg);color:var(--removed)}
.badge.changed{background:var(--changed-bg);color:var(--changed)}
.badge.clean{background:var(--pass-bg);color:var(--pass)}
.badge.warn,.badge.unmatched{background:var(--warn-bg);color:var(--warn)}
.badge.unchanged{background:rgba(0,0,0,.05);color:var(--text-2)}
.badge.sev-warn{background:var(--warn-bg);color:var(--warn)}
.badge.sev-info{background:var(--accent-bg);color:var(--accent)}
.badge.display{background:var(--accent-bg);color:var(--accent)}
.badge.skip,.badge.SKIP{background:rgba(0,0,0,.05);color:var(--text-3)}

/* ---- check row: skipped ---- */
.check-card.skip{opacity:.6}

/* ---- tag pills ---- */
.tag-pill{background:var(--accent-bg);color:var(--accent);border-radius:var(--r-pill);padding:.15rem .5rem;font-size:.68rem;margin-right:.3rem;font-weight:550}

/* ---- filter bar: segmented pill control ---- */
.filter-bar{display:flex;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.fb-btn{font-size:.76rem;font-weight:550;padding:6px 13px;border:none;border-radius:var(--r-pill);background:rgba(0,0,0,.05);cursor:pointer;color:var(--text-2);transition:all .2s cubic-bezier(.25,.1,.25,1)}
.fb-btn:hover{color:var(--text)}
.fb-btn.active{background:var(--text);color:#fff;font-weight:600}
#check-search{font-size:.8rem;padding:6px 14px;border:none;background:rgba(0,0,0,.05);border-radius:var(--r-pill);outline:none;min-width:180px;font-family:inherit;color:var(--text)}
#check-search:focus{background:rgba(0,0,0,.08)}

/* ---- trend report ---- */
.trend-wrap{overflow-x:auto;margin-bottom:1.5rem;background:var(--surface);border-radius:var(--r-panel);box-shadow:var(--sh-panel)}
.trend-table{width:100%;border-collapse:collapse;font-size:.82rem}
.trend-table th{background:var(--hover);color:var(--text-2);padding:.55rem .7rem;text-align:center;white-space:nowrap;font-size:.68rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--hairline)}
.trend-table th:first-child{text-align:left;min-width:220px}
.trend-table td{padding:.45rem .7rem;border-bottom:1px solid var(--hairline);text-align:center;font-size:.79rem;font-variant-numeric:tabular-nums}
.trend-table td:first-child{text-align:left;color:var(--text)}
.trend-table td.t-pass{color:var(--pass);font-weight:600}
.trend-table td.t-fail{color:var(--fail);font-weight:600}
.trend-table td.t-error{color:var(--warn);font-weight:600}
.trend-table td.t-skip{color:var(--text-3)}
.trend-table td.t-na{color:var(--faint);font-size:.72rem}
.trend-table tr:hover td{background:var(--hover)}
.sparkline{display:inline-block;vertical-align:middle;margin-left:6px}

/* ---- raw output blocks: ONE panel, hairline-separated ---- */
.raw-list{background:var(--surface);border-radius:var(--r-panel);box-shadow:var(--sh-panel);overflow:hidden}
details.raw-block{background:transparent}
details.raw-block+details.raw-block{border-top:1px solid var(--hairline)}
details.raw-block>summary{
  display:flex;align-items:center;gap:10px;
  padding:13px 20px;cursor:pointer;user-select:none;list-style:none;transition:background .15s
}
details.raw-block>summary:hover{background:var(--hover)}
details.raw-block>summary::-webkit-details-marker{display:none}
.arrow-icon{
  font-size:.6rem;color:var(--faint);
  transition:transform .15s ease;display:inline-block;flex-shrink:0;width:12px
}
details[open]>summary .arrow-icon{transform:rotate(90deg)}
.summary-cmd{font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);font-size:.85rem;font-weight:500;flex:1}
pre.raw-output{
  background:var(--code-bg);color:var(--code-fg);
  padding:16px 20px;margin:0;overflow-x:auto;
  font-size:.77rem;line-height:1.65;
  font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);
  white-space:pre
}

/* ---- delta specific ---- */
.meta-compare{
  display:grid;grid-template-columns:1fr auto 1fr;
  gap:14px;align-items:center;margin-bottom:32px
}
.meta-box{
  background:var(--surface);border-radius:var(--r);padding:16px 18px;box-shadow:var(--sh-card)
}
.meta-box .mb-label{
  font-size:.68rem;font-weight:600;text-transform:uppercase;
  letter-spacing:.07em;color:var(--text-3);margin-bottom:6px
}
.meta-box .mb-host{font-size:.95rem;font-weight:600;letter-spacing:-.01em;margin-bottom:3px}
.meta-box .mb-ts{font-size:.82rem;color:var(--text-2)}
.meta-arrow{font-size:1.4rem;color:var(--faint);text-align:center}

.cmd-card{
  background:var(--surface);border-radius:var(--r);
  box-shadow:var(--sh-card);margin-bottom:10px;overflow:hidden
}
.cmd-card.changed,.cmd-card.added,.cmd-card.removed{box-shadow:var(--sh-card)}
.cmd-hdr{display:flex;align-items:center;gap:10px;padding:13px 18px}
.cmd-name{font-family:var(--mono,monospace);font-size:.88rem;font-weight:500;flex:1}
.diff-count{font-size:.75rem;color:var(--text-2)}

.diff-table{width:100%;border-collapse:collapse;font-size:.82rem}
.diff-table th{
  text-align:left;padding:8px 18px;
  background:var(--hover);border-top:1px solid var(--hairline);border-bottom:1px solid var(--hairline);
  font-size:.66rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text-3);font-weight:600
}
.diff-table td{padding:8px 18px;border-bottom:1px solid var(--hairline);vertical-align:top}
.diff-table tr:last-child td{border-bottom:none}
.diff-table .dp{font-family:var(--mono,monospace);color:var(--text-2);font-size:.79rem}
.diff-table .db{font-family:var(--mono,monospace);color:var(--fail)}
.diff-table .da{font-family:var(--mono,monospace);color:var(--pass)}
.diff-table .null{color:var(--faint);font-style:italic;font-family:sans-serif;font-size:.8rem}

.pill-list{display:flex;flex-wrap:wrap;gap:7px;margin:8px 0}
.pill{font-family:var(--mono,monospace);font-size:.78rem;padding:3px 10px;border-radius:var(--r-pill)}
.pill.added  {background:var(--added-bg);  color:var(--added)}
.pill.removed{background:var(--removed-bg);color:var(--removed)}

@media(max-width:640px){
  .page-header{padding:18px 18px 14px}
  .container{padding:8px 14px 32px}
  .meta-compare{grid-template-columns:1fr}
  .meta-arrow{display:none}
}

/* ---- json output blocks: ONE panel, hairline-separated ---- */
.raw-list details.json-block{background:transparent}
details.json-block{background:var(--surface);border-radius:var(--r-panel);box-shadow:var(--sh-panel);overflow:hidden}
.raw-list details.json-block+details.json-block{border-top:1px solid var(--hairline)}
details.json-block>summary{display:flex;align-items:center;gap:10px;padding:13px 20px;cursor:pointer;user-select:none;list-style:none;transition:background .15s}
details.json-block>summary:hover{background:var(--hover)}
details.json-block>summary::-webkit-details-marker{display:none}
pre.json-output{background:var(--code-bg);color:var(--code-fg);padding:16px 20px;margin:0;overflow-x:auto;font-size:.77rem;line-height:1.65;font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);white-space:pre}

/* ---- check matrix ---- */
.matrix-wrap{overflow-x:auto;margin-bottom:1.5rem;background:var(--surface);border-radius:var(--r-panel);box-shadow:var(--sh-panel)}
.check-matrix{width:100%;border-collapse:collapse;font-size:.82rem}
.check-matrix th{background:var(--hover);color:var(--text-2);padding:.55rem .75rem;text-align:center;white-space:nowrap;font-size:.69rem;font-weight:600;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--hairline)}
.check-matrix th:first-child{text-align:left;min-width:200px}
.check-matrix td{padding:.45rem .75rem;border-bottom:1px solid var(--hairline);text-align:center;font-size:.8rem}
.check-matrix td:first-child{text-align:left;color:var(--text)}
.check-matrix td a{text-decoration:none;color:inherit;display:block}
.check-matrix td.m-pass{color:var(--pass);font-weight:650}
.check-matrix td.m-fail{color:var(--fail);font-weight:650}
.check-matrix td.m-error{color:var(--warn);font-weight:650}
.check-matrix td.m-skip{color:var(--text-3);font-weight:600}
.check-matrix td.m-na{color:var(--faint);font-size:.75rem}
.check-matrix tr:hover td{background:var(--hover)}

/* ---- device accordion (genuinely independent objects — cards are correct here) ---- */
details.device-accordion{margin-bottom:12px;border-radius:var(--r);background:var(--surface);box-shadow:var(--sh-card);overflow:hidden}
details.device-accordion>summary{padding:.8rem 1.2rem;cursor:pointer;font-size:.95rem;display:flex;align-items:center;gap:.7rem;list-style:none;transition:background .15s}
details.device-accordion>summary:hover{background:var(--hover)}
details.device-accordion>summary::-webkit-details-marker{display:none}
details.device-accordion[open]>summary{border-bottom:1px solid var(--hairline)}
.device-inner{padding:1.1rem 1.3rem}

/* ---- copy button ---- */
.copy-btn{margin-left:auto;padding:3px 12px;font-size:.72rem;border:none;border-radius:var(--r-pill);background:rgba(0,0,0,.05);cursor:pointer;color:var(--text-2);font-family:inherit;transition:background .15s,color .15s;flex-shrink:0}
.copy-btn:hover{background:rgba(0,0,0,.08);color:var(--text)}
.copy-btn.copied{color:var(--pass);background:var(--pass-bg)}

/* ---- json tree browser ---- */
.jt-tree{background:var(--code-bg);padding:14px 18px;overflow-x:auto;font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);font-size:.77rem;line-height:1.65}
.jt-leaf{cursor:pointer;padding:1px 3px;border-radius:3px;color:var(--code-fg)}
.jt-leaf:hover{background:rgba(255,255,255,.08)}
details.jt-group{margin:0}
.jt-sum{cursor:pointer;list-style:none;padding:1px 3px;border-radius:3px;color:var(--code-fg)}
.jt-sum::-webkit-details-marker{display:none}
.jt-sum:hover{background:rgba(255,255,255,.08)}
.jt-ch{padding-left:18px;border-left:1px solid rgba(255,255,255,.12)}
.jt-key{color:#7dd3fc}.jt-idx{color:#9a9aa0}
.jt-str{color:#86efac}.jt-num{color:#fbbf24}.jt-bool{color:#f472b6}.jt-null{color:#9a9aa0;font-style:italic}
.jt-preview{color:#9a9aa0;font-size:.73rem}
.jt-path-toast{position:fixed;bottom:22px;left:50%;transform:translateX(-50%);background:#1d1d1f;color:#f5f5f7;padding:8px 18px;border-radius:var(--r-pill);font-size:.78rem;font-family:var(--mono,ui-monospace,'SF Mono',Menlo,monospace);pointer-events:none;opacity:0;transition:opacity .2s;z-index:9999;white-space:nowrap;max-width:90vw;overflow:hidden;text-overflow:ellipsis;box-shadow:var(--sh-overlay,0 2px 8px rgba(0,0,0,.1),0 30px 80px rgba(0,0,0,.24))}
.jt-path-toast.show{opacity:1}
/* ── Simple executive dashboard ── */
.simple-table{width:100%;border-collapse:collapse;font-size:.88rem;background:var(--surface);border-radius:var(--r-panel);box-shadow:var(--sh-panel);overflow:hidden}
.simple-table th{background:var(--hover);color:var(--text-2);padding:.55rem .8rem;text-align:left;font-weight:600;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;border-bottom:1px solid var(--hairline)}
.simple-table td{padding:.5rem .8rem;border-bottom:1px solid var(--hairline);vertical-align:middle}
.simple-table tr:last-child td{border-bottom:none}
.simple-table tr:hover td{background:var(--hover)}
.fail-count{font-size:.8rem;color:var(--fail);margin-left:.4rem;font-style:italic}
.err-msg{font-size:.8rem;color:var(--warn);margin-left:.4rem;font-style:italic}
.skip-note{font-size:.8rem;color:var(--text-2);margin-left:.4rem;font-style:italic}
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
function filterChecks(){
  var active=document.querySelector('.fb-btn.active');
  var filter=active?active.dataset.fb:'all';
  var q=(document.getElementById('check-search')||{}).value||'';
  q=q.toLowerCase();
  document.querySelectorAll('.check-card').forEach(function(card){
    var st=card.dataset.status||'';
    var nm=(card.dataset.name||'').toLowerCase();
    var show=(filter==='all'||st===filter)&&(!q||nm.includes(q));
    card.style.display=show?'':'none';
  });
}
document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('.fb-btn').forEach(function(btn){
    btn.addEventListener('click',function(){
      document.querySelectorAll('.fb-btn').forEach(function(b){b.classList.remove('active');});
      btn.classList.add('active');
      filterChecks();
    });
  });
  var s=document.getElementById('check-search');
  if(s) s.addEventListener('input',filterChecks);
});
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


def _page_header(h1: str, sub_html: str) -> str:
    ts = _e(datetime.now().strftime("%Y-%m-%d %H:%M"))
    return f"""<div class="page-header">
  <div class="header-left">
    <h1>{h1}</h1>
    <div class="sub">{sub_html}</div>
  </div>
  <div class="header-right">Generated {ts}</div>
</div>"""


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
{_page_header("Health Report", f"{_e(hostname)} &nbsp;·&nbsp; {_e(ts)}")}
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
{_page_header("Health Report", f"{n_devices} device(s) &nbsp;·&nbsp; {_e(checks_name)}")}
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

    filter_bar = """
<div class="filter-bar">
  <button class="fb-btn active" data-fb="all">All</button>
  <button class="fb-btn" data-fb="pass">Pass</button>
  <button class="fb-btn" data-fb="fail">Fail</button>
  <button class="fb-btn" data-fb="error">Error</button>
  <button class="fb-btn" data-fb="skip">Skip</button>
  <input type="search" id="check-search" placeholder="Filter by name…">
</div>"""

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

        # Tag pills
        tags = check.get("tags", []) or []
        tags_html = "".join(
            f'<span class="tag-pill">{_e(str(t))}</span>' for t in tags
        ) if tags else ""

        # Build the Condition row content based on check type
        if status == "skip":
            skip_note = r.get("note", "")
            skip_spec = check.get("skip_if", {})
            skip_cond = f"{_e(skip_spec.get('metadata', skip_spec.get('field', '')))} {_e(skip_spec.get('condition', ''))} {_e(str(skip_spec.get('value', '')))}"
            detail_rows = f"""
<div class="dg">
  <span class="dk">Skip-If</span><code>{skip_cond}</code>
  <span class="dk">Note</span><span style="font-size:.8rem;color:var(--muted)">{_e(skip_note)}</span>
</div>"""
        elif print_only:
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
</div>"""
        elif "metadata" in check:
            detail_rows = f"""
<div class="dg">
  <span class="dk">Metadata</span><code>{_e(check['metadata'])}</code>
  <span class="dk">Condition</span><code>{_e(cond)} {_e(str(val))}</code>
</div>"""
        elif "count" in check:
            cs = check["count"]
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
  <span class="dk">Count</span><code>{_e(str(cs.get('condition','')))} {_e(str(cs.get('value','')))}</code>
</div>"""
        elif "compare_baseline" in check:
            cb = check["compare_baseline"]
            detail_rows = f"""
<div class="dg">
  <span class="dk">Command</span><code>{_e(cmd)}</code>
  <span class="dk">Path</span><code>{_e(path)}</code>
  <span class="dk">vs Baseline</span><code>{_e(str(cb.get('condition','')))} {_e(str(cb.get('value','baseline')))}</code>
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
                f'<span style="background:var(--accent-bg);color:var(--accent);padding:1px 6px;'
                f'border-radius:var(--r-chip);font-size:.78rem;margin-right:4px">{_e(str(v))}</span>'
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
  <div class="fp">{_e(f.get("path", ""))}</div>
  <div class="fa">Actual: <span>{_e(str(f.get("actual", "")))}</span></div>
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

        if print_only:
            status_badge = _badge("display", "DISPLAY")
        elif status == "skip":
            status_badge = _badge("skip", "SKIP")
        else:
            status_badge = f"{_badge(status)}{sev_badge}"
        card_class = 'pass' if print_only else _e(status)
        items.append(f"""
<div class="check-card {card_class}" data-status="{_e(status)}" data-name="{_e(name)}">
  <div class="check-hdr">
    {status_badge}
    <span class="check-name">{_e(name)}</span>
    {tags_html}
    <span class="check-cmd">{_e(cmd)}</span>
  </div>
  <div class="check-body">{detail_rows}{extra}</div>
</div>""")

    return f'{filter_bar}<div class="check-list">{"".join(items)}</div>'


# ---------------------------------------------------------------------------
# Delta report
# ---------------------------------------------------------------------------

def render_delta(report: dict, before_snap: dict, after_snap: dict) -> str:
    meta   = report.get("metadata", {})
    b_meta = meta.get("before", {})
    a_meta = meta.get("after",  {})
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
{_page_header("Delta Report", f'{_e(hostname)} &nbsp;·&nbsp; {_e(b_meta.get("collection_time","?"))} → {_e(a_meta.get("collection_time","?"))}')}
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
  <td class="dp">{_e(d.get("path", ""))}</td>
  <td class="db">{_e_val(d.get("before"))}</td>
  <td class="da">{_e_val(d.get("after"))}</td>
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


def _check_matrix(device_data: list[dict], link: bool = True) -> str:
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
            anchor = _anchor(hn)
            status = lookup.get(check_name)
            if status is None:
                cells += '<td class="m-na">—</td>'
                continue
            cls, label = {
                "pass": ("m-pass", "PASS"),
                "fail": ("m-fail", "FAIL"),
                "skip": ("m-skip", "SKIP"),
            }.get(status, ("m-error", "ERR"))
            if link:
                cells += f'<td class="{cls}"><a href="#device-{anchor}">{label}</a></td>'
            else:
                cells += f'<td class="{cls}">{label}</td>'
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
    anchor   = _anchor(hostname)

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
  background:var(--surface);border-radius:var(--r-panel);overflow:hidden;
  box-shadow:var(--sh-panel)}
.index-table th{text-align:left;padding:10px 16px;background:var(--hover);
  border-bottom:1px solid var(--hairline);font-size:.68rem;font-weight:600;
  text-transform:uppercase;letter-spacing:.06em;color:var(--text-3)}
.index-table td{padding:9px 16px;border-bottom:1px solid var(--hairline);vertical-align:middle}
.index-table tr:last-child td{border-bottom:none}
.index-table tr:hover td{background:var(--hover)}
.index-table a{color:var(--accent);text-decoration:none}
.index-table a:hover{text-decoration:underline}
</style>"""


# ---------------------------------------------------------------------------
# Delta index page
# ---------------------------------------------------------------------------

def render_delta_index(results: list[dict], before_dir: str, after_dir: str) -> str:
    total     = len(results)
    matched   = sum(1 for r in results if r.get("status") == "matched")
    unmatched = total - matched

    cards = _summary_cards([
        ("total",   "Devices",   total),
        ("changed", "Matched",   matched),
        ("removed", "Unmatched", unmatched),
    ])

    body = f"""
{_page_header("Delta-All Index", f"Before: {_e(before_dir)} &nbsp;→&nbsp; After: {_e(after_dir)}")}
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
        hostname = _e(r.get("hostname", "?"))
        if r.get("status") == "unmatched":
            side = "after only" if r.get("side") == "after-only" else "before only"
            rows.append(f"""
<tr style="opacity:.45">
  <td><code>{hostname}</code></td>
  <td>{_badge("unmatched", side.upper())}</td>
  <td style="color:var(--faint)" colspan="4">—</td>
  <td style="color:var(--faint)">— no report —</td>
</tr>""")
        else:
            s       = r.get("summary") or {}
            added   = len(s.get("commands_added",   []))
            removed = len(s.get("commands_removed", []))
            changed = len(s.get("commands_changed", []))
            unch    = len(s.get("commands_unchanged", []))
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
    all_pass = sum(1 for r in results
                   if (r.get("summary") or {}).get("failed", 0) == 0
                   and (r.get("summary") or {}).get("error", 0) == 0)
    failures = total - all_pass

    cards = _summary_cards([
        ("total",  "Devices",      total),
        ("pass",   "All Pass",     all_pass),
        ("fail",   "Has Failures", failures),
    ])

    body = f"""
{_page_header("Health-All Index", f"Snapshots: {_e(snapshot_dir)}")}
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
        s        = r.get("summary") or {}
        hostname = _e(r.get("hostname", "?"))
        ts       = _e(r.get("timestamp", "?"))
        clean    = s.get("failed", 0) == 0 and s.get("error", 0) == 0
        badge    = _badge("pass", "PASS") if clean else _badge("fail", "FAIL")
        row_style = 'style="opacity:.55"' if clean else ""
        link = f'<a href="{_e(r["report_path"])}">{_e(r["report_path"])}</a>' if r.get("report_path") else "—"
        rows.append(f"""
<tr {row_style}>
  <td><code>{hostname}</code></td>
  <td>{ts}</td>
  <td>{badge}</td>
  <td>{s.get("total",  0)}</td>
  <td style="color:var(--pass)">{s.get("passed", 0)}</td>
  <td style="color:var(--fail)">{s.get("failed", 0)}</td>
  <td style="color:var(--warn)">{s.get("error",  0)}</td>
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

    before_map = {r.get("name", f"(unnamed-{i})"): r
                  for i, r in enumerate(before_report.get("results", []))}
    after_map  = {r.get("name", f"(unnamed-{i})"): r
                  for i, r in enumerate(after_report.get("results", []))}
    all_names  = list(dict.fromkeys(list(before_map) + list(after_map)))

    # Same rank logic as report.py cmd_health_diff: a move to a worse status
    # (skip→fail, fail→error) is a regression, not just pass→non-pass
    _RANK = {"error": 0, "fail": 1, "skip": 2, "pass": 3}

    regressions = fixed = added = removed = unchanged = 0
    rows_html   = []

    for name in all_names:
        br = before_map.get(name)
        ar = after_map.get(name)

        if br and ar:
            bs, as_ = br.get("status", "error"), ar.get("status", "error")
            if bs == as_:
                unchanged += 1
                change_badge = f'<span style="color:var(--muted)">—</span>'
                row_cls = ""
            elif _RANK.get(as_, 0) < _RANK.get(bs, 0):
                regressions += 1
                change_badge = _badge("fail", "⬇ Regressed")
                row_cls = ' style="background:#fff8f8"'
            else:
                fixed += 1
                change_badge = _badge("pass", "⬆ Fixed")
                row_cls = ' style="background:#f8fff8"'
        elif br and not ar:
            removed += 1
            bs, as_ = br.get("status", "error"), None
            change_badge = _badge("removed", "✖ Removed")
            row_cls = ' style="opacity:.6"'
        else:
            added += 1
            bs, as_ = None, ar.get("status", "error")
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
{_page_header("Health Diff", f'{_e(bm.get("hostname", "?"))} &nbsp;·&nbsp; {_e(bm.get("collection_time", "?"))} → {_e(am.get("collection_time", "?"))}')}
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


# ---------------------------------------------------------------------------
# Health trend report
# ---------------------------------------------------------------------------

def render_health_trend(trend_data: list[dict]) -> str:
    """Time-series trend HTML from a list of health run dicts."""
    if not trend_data:
        return _page("Health Trend", "<p>No data.</p>")

    # Collect unique check names (union across all runs, first-seen order)
    seen: dict = {}
    for item in trend_data:
        for r in item.get("results", []):
            n = r.get("name", "")
            if n not in seen:
                seen[n] = len(seen)
    check_names = list(seen.keys())

    dates = [item.get("timestamp", item.get("filename", "?")) for item in trend_data]

    # Build header
    hdrs = "".join(
        f'<th title="{_e(d)}">{_e(d[:12] + "…" if len(str(d)) > 12 else d)}</th>'
        for d in dates
    )
    header_row = f'<tr><th>Check</th>{hdrs}<th>Trend</th></tr>'

    _STATUS_CLASS = {"pass": "t-pass", "fail": "t-fail", "error": "t-error",
                     "skip": "t-skip"}

    data_rows = []
    for check_name in check_names:
        cells = []
        statuses = []
        for item in trend_data:
            lookup = {r.get("name", ""): r.get("status", "") for r in item.get("results", [])}
            st = lookup.get(check_name)
            statuses.append(st)
            cls = _STATUS_CLASS.get(st, "t-na")
            label = st.upper()[:4] if st else "—"
            cells.append(f'<td class="{cls}">{label}</td>')

        # Sparkline: mini SVG bar chart (pass=green, fail=red, missing=grey)
        bar_w, bar_h = 6, 16
        bars = ""
        for i, st in enumerate(statuses):
            colour = "#16a34a" if st == "pass" else "#dc2626" if st == "fail" else \
                     "#d97706" if st == "error" else "#ccc"
            x = i * (bar_w + 2)
            bars += f'<rect x="{x}" y="0" width="{bar_w}" height="{bar_h}" fill="{colour}" rx="1"/>'
        total_w = len(statuses) * (bar_w + 2)
        sparkline = (f'<svg class="sparkline" width="{total_w}" height="{bar_h}" '
                     f'viewBox="0 0 {total_w} {bar_h}">{bars}</svg>')

        data_rows.append(
            f'<tr><td>{_e(check_name)}</td>{"".join(cells)}<td>{sparkline}</td></tr>'
        )

    n_runs    = len(trend_data)
    hostnames = sorted({item.get("hostname", "?") for item in trend_data})
    subtitle  = f"{n_runs} run(s) · {', '.join(hostnames[:3])}{'…' if len(hostnames) > 3 else ''}"

    total_pass  = sum(s.get("passed", 0) for item in trend_data for s in [item.get("summary", {})])
    total_fail  = sum(s.get("failed", 0) for item in trend_data for s in [item.get("summary", {})])
    total_error = sum(s.get("error",  0) for item in trend_data for s in [item.get("summary", {})])

    cards = _summary_cards([
        ("total", "Runs",   n_runs),
        ("pass",  "Passes", total_pass),
        ("fail",  "Fails",  total_fail),
        ("error", "Errors", total_error),
    ])

    table_html = f"""<div class="trend-wrap">
<table class="trend-table">
  <thead>{header_row}</thead>
  <tbody>{"".join(data_rows)}</tbody>
</table>
</div>"""

    body = f"""
{_page_header("Health Trend", _e(subtitle))}
<div class="container">
  {cards}
  <div class="sec-title">Check Trend Matrix</div>
  {table_html}
</div>"""

    return _page("Health Trend", body)


# ---------------------------------------------------------------------------
# Minimalist executive dashboard — no raw output, no JSON, no config values
# ---------------------------------------------------------------------------

def render_health_simple(report: dict) -> str:
    """Single-device executive dashboard: status per check, no raw/JSON data."""
    meta     = report.get("metadata", {})
    s        = report.get("summary", {})
    hostname = meta.get("hostname", "Unknown")
    ts       = meta.get("collection_time", "")

    card_items = [
        ("total", "Total",   s.get("total",  0)),
        ("pass",  "Passed",  s.get("passed", 0)),
        ("fail",  "Failed",  s.get("failed", 0)),
        ("error", "Errors",  s.get("error",  0)),
    ]
    if s.get("skipped", 0):
        card_items.append(("total", "Skipped", s["skipped"]))
    cards = _summary_cards(card_items)

    rows = []
    for r in report.get("results", []):
        status   = r.get("status", "error")
        name     = r.get("name", "(unnamed)")
        check    = r.get("check", {})
        cmd      = check.get("command", "")
        severity = r.get("severity", "critical")
        tags     = check.get("tags", [])

        tag_html = " ".join(f'<span class="tag-pill">{_e(t)}</span>' for t in (tags or []))

        if status == "pass":
            if r.get("print_only"):
                badge = _badge("display", "DISPLAY")
                detail = ""
            else:
                badge = _badge("pass", "PASS")
                detail = ""
        elif status == "fail":
            badge = _badge("fail", "FAIL")
            n_fail = len(r.get("failures", []))
            detail = f'<span class="fail-count">{n_fail} value(s) failed</span>' if n_fail else ""
        elif status == "skip":
            badge = _badge("skip", "SKIP")
            skip_spec = check.get("skip_if", {})
            detail = f'<span class="skip-note">skipped: {_e(skip_spec.get("metadata", "condition met"))}</span>'
        elif status == "error":
            badge = _badge("error", "ERROR")
            detail = f'<span class="err-msg">{_e(str(r.get("message", ""))[:80])}</span>'
        else:
            badge = _badge(_e(status))
            detail = ""

        sev_html = ""
        if severity and severity != "critical":
            sev_html = f'<span class="badge sev-{_e(severity)}">{_e(severity.upper())}</span>'

        rows.append(f"""<tr>
  <td>{badge}{sev_html}</td>
  <td>{_e(name)}{detail}</td>
  <td><code style="font-size:.82rem">{_e(cmd)}</code></td>
  <td>{tag_html}</td>
</tr>""")

    table_html = f"""<table class="simple-table">
<thead><tr><th>Status</th><th>Check</th><th>Command</th><th>Tags</th></tr></thead>
<tbody>{"".join(rows) if rows else "<tr><td colspan='4' style='color:var(--muted)'>No checks defined.</td></tr>"}</tbody>
</table>"""

    body = f"""
{_page_header("Health Dashboard", f"{_e(hostname)} &nbsp;·&nbsp; {_e(ts)}")}
<div class="container">
  {cards}
  <div class="sec-title">Check Results</div>
  {table_html}
</div>"""

    return _page(f"Health Dashboard — {hostname}", body)


def render_health_all_simple(device_data: list[dict]) -> str:
    """Multi-device executive dashboard: check matrix + device summary table."""
    n_devices    = len(device_data)
    total_passed = sum(item["report"].get("summary", {}).get("passed", 0) for item in device_data)
    total_failed = sum(item["report"].get("summary", {}).get("failed", 0) for item in device_data)
    total_errors = sum(item["report"].get("summary", {}).get("error",  0) for item in device_data)

    cards = _summary_cards([
        ("total", "Devices", n_devices),
        ("pass",  "Passed",  total_passed),
        ("fail",  "Failed",  total_failed),
        ("error", "Errors",  total_errors),
    ])

    matrix = _check_matrix(device_data, link=False)

    dev_rows = []
    for item in device_data:
        hn = item["report"].get("metadata", {}).get("hostname", item.get("hostname", "?"))
        ts = item["report"].get("metadata", {}).get("collection_time", "")
        s  = item["report"].get("summary", {})
        fc = s.get("failed_critical", s.get("failed", 0))
        overall = _badge("fail", "FAIL") if (fc or s.get("error", 0)) else _badge("pass", "PASS")
        dev_rows.append(f"""<tr>
  <td>{overall}</td>
  <td><strong>{_e(hn)}</strong></td>
  <td style="color:var(--muted);font-size:.82rem">{_e(ts)}</td>
  <td style="text-align:center">{s.get("total",  0)}</td>
  <td style="text-align:center;color:var(--pass)">{s.get("passed", 0)}</td>
  <td style="text-align:center;color:var(--fail)">{s.get("failed", 0)}</td>
  <td style="text-align:center;color:var(--warn)">{s.get("error",  0)}</td>
</tr>""")

    dev_table = f"""<table class="simple-table">
<thead><tr><th>Status</th><th>Device</th><th>Collected</th>
<th style="text-align:center">Total</th><th style="text-align:center">Passed</th>
<th style="text-align:center">Failed</th><th style="text-align:center">Errors</th></tr></thead>
<tbody>{"".join(dev_rows)}</tbody>
</table>"""

    body = f"""
{_page_header("Health Dashboard", f"{n_devices} device(s)")}
<div class="container">
  {cards}
  <div class="sec-title">Device Summary</div>
  {dev_table}
  <div class="sec-title">Check Results Matrix</div>
  {matrix}
</div>"""

    return _page(f"Health Dashboard — {n_devices} Devices", body)
