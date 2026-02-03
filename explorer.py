"""互動式幣流探索器 — SPA 頁面 HTML 生成。"""


def generate_explorer_html() -> str:
    """產生互動式幣流探索器的完整 HTML 頁面。"""
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>互動式幣流探索器</title>
<style>
:root {{
    --bg: #0f1117; --surface: #1a1d27; --surface2: #232734;
    --border: #2e3347; --text: #e0e0e8; --text-dim: #888da0;
    --accent: #6c8aff; --green: #34d399; --yellow: #fbbf24;
    --red: #f87171; --orange: #fb923c; --purple: #a855f7;
    --mark-bg: rgba(108,138,255,0.18);
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px;
    max-width: 1400px; margin: 0 auto;
}}
a {{ color: var(--accent); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
code {{
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", monospace;
    font-size: 0.78rem; background: var(--surface2); padding: 2px 5px; border-radius: 3px;
    word-break: break-all;
}}

/* --- Header --- */
.header {{ display: flex; align-items: center; gap: 16px; margin-bottom: 24px; flex-wrap: wrap; }}
.header h1 {{ font-size: 1.4rem; font-weight: 700; white-space: nowrap; }}
.header .back-link {{ font-size: 0.85rem; color: var(--text-dim); }}

/* --- Input Bar --- */
.input-bar {{
    display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 20px; margin-bottom: 24px;
}}
.input-bar label {{ font-size: 0.82rem; color: var(--text-dim); }}
.input-bar input[type="text"] {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 8px 14px; border-radius: 6px; font-size: 0.88rem; width: 380px;
    font-family: "SF Mono", monospace;
}}
.input-bar input[type="text"]::placeholder {{ color: var(--text-dim); }}
.input-bar select {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 6px; font-size: 0.85rem;
}}
.btn {{
    padding: 8px 18px; border-radius: 6px; font-size: 0.85rem; font-weight: 600;
    cursor: pointer; border: 1px solid var(--border); transition: all 0.15s;
}}
.btn-primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.btn-primary:hover {{ filter: brightness(1.15); }}
.btn-primary:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.btn-sm {{ padding: 4px 10px; font-size: 0.75rem; }}
.btn-out {{ background: rgba(108,138,255,0.12); border-color: var(--accent); color: var(--accent); }}
.btn-out:hover {{ background: rgba(108,138,255,0.25); }}
.btn-in {{ background: rgba(168,85,247,0.12); border-color: var(--purple); color: var(--purple); }}
.btn-in:hover {{ background: rgba(168,85,247,0.25); }}
.btn-detail {{ background: var(--surface2); color: var(--text-dim); }}
.btn-detail:hover {{ color: var(--text); }}

/* --- Root Node Card --- */
.root-card {{
    background: var(--surface); border: 1px solid var(--accent); border-radius: 10px;
    padding: 20px; margin-bottom: 24px; display: none;
}}
.root-card.visible {{ display: block; }}
.root-card .node-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
.root-card .alias {{ font-size: 1.2rem; font-weight: 700; color: var(--accent); }}
.root-card .address {{ font-size: 0.82rem; color: var(--text-dim); }}
.node-badges {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }}
.badge {{
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600;
}}
.badge-risk-low {{ background: rgba(52,211,153,0.15); color: var(--green); }}
.badge-risk-moderate {{ background: rgba(251,191,36,0.15); color: var(--yellow); }}
.badge-risk-high {{ background: rgba(248,113,113,0.2); color: var(--red); }}
.badge-risk-severe {{ background: rgba(248,113,113,0.35); color: #fff; }}
.badge-exchange {{ background: rgba(251,146,60,0.15); color: var(--orange); }}
.badge-label {{ background: var(--surface2); color: var(--text-dim); }}
.badge-kyc {{ background: rgba(52,211,153,0.2); color: var(--green); font-weight: 700; }}
.badge-mule {{ background: rgba(251,191,36,0.15); color: var(--yellow); }}
.badge-house {{ background: rgba(168,85,247,0.15); color: var(--purple); }}
.node-stats {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 8px; font-size: 0.78rem;
}}
.node-stats .stat {{ background: var(--bg); border-radius: 6px; padding: 8px 12px; }}
.node-stats .stat-label {{ color: var(--text-dim); font-size: 0.7rem; }}
.node-stats .stat-value {{ font-weight: 600; margin-top: 2px; }}

/* --- Explorer Tree --- */
.tree-section {{ margin-bottom: 24px; }}
.tree-section h2 {{ font-size: 1rem; font-weight: 600; margin-bottom: 12px; color: var(--text-dim); }}
.tree-table-wrap {{
    overflow-x: auto; border-radius: 10px; border: 1px solid var(--border);
}}
table.tree-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; }}
table.tree-table thead th {{
    background: var(--surface2); padding: 8px 12px; text-align: left; font-weight: 600;
    color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px;
    position: sticky; top: 0; z-index: 1; border-bottom: 1px solid var(--border);
}}
table.tree-table tbody tr {{
    border-bottom: 1px solid var(--border); transition: background 0.1s;
}}
table.tree-table tbody tr:hover {{ background: rgba(108,138,255,0.04); }}
table.tree-table tbody tr.is-exchange {{ border-left: 3px solid var(--orange); }}
table.tree-table td {{ padding: 7px 12px; vertical-align: middle; }}
.indent-cell {{ white-space: nowrap; }}
.indent-marker {{ color: var(--border); margin-right: 2px; }}
.alias-cell {{ font-weight: 700; }}
.addr-cell {{ font-family: "SF Mono", monospace; font-size: 0.72rem; color: var(--text-dim); }}
.addr-cell a {{ color: var(--text-dim); }}
.addr-cell a:hover {{ color: var(--accent); }}
.labels-cell {{ font-size: 0.72rem; }}
.dir-in {{ color: var(--purple); font-weight: 600; }}
.dir-out {{ color: var(--accent); font-weight: 600; }}
.amount-cell {{ font-weight: 600; text-align: right; white-space: nowrap; }}
.count-cell {{ text-align: center; color: var(--text-dim); }}
.risk-cell {{ text-align: center; }}
.actions-cell {{ white-space: nowrap; display: flex; gap: 4px; }}
.child-rows {{ }}
.child-rows.collapsed {{ display: none; }}
.spinner-inline {{
    display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.6s linear infinite; vertical-align: middle;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.no-data {{ color: var(--text-dim); font-size: 0.78rem; text-align: center; padding: 20px; }}
.heuristic-tag {{
    font-size: 0.65rem; padding: 1px 6px; border-radius: 10px; margin-left: 4px;
    vertical-align: middle;
}}

/* --- Report Panel --- */
.report-panel {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px; margin-bottom: 24px; display: none;
}}
.report-panel.visible {{ display: block; }}
.report-panel h2 {{ font-size: 1rem; font-weight: 600; margin-bottom: 16px; }}
.report-form {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.report-form .form-group {{ display: flex; flex-direction: column; gap: 4px; }}
.report-form .form-group.full {{ grid-column: 1 / -1; }}
.report-form label {{ font-size: 0.78rem; color: var(--text-dim); }}
.report-form input {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 6px; font-size: 0.85rem;
}}
.report-form input::placeholder {{ color: var(--text-dim); }}
.report-actions {{ grid-column: 1 / -1; display: flex; gap: 10px; margin-top: 8px; }}

/* --- Status Bar --- */
.status-bar {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: var(--surface); border-top: 1px solid var(--border);
    padding: 8px 24px; font-size: 0.78rem; color: var(--text-dim);
    display: flex; justify-content: space-between; align-items: center;
    z-index: 100;
}}
.status-bar .api-count {{ color: var(--accent); font-weight: 600; }}
body {{ padding-bottom: 56px; }}

/* --- Toast --- */
.toast {{
    position: fixed; top: 20px; right: 20px; padding: 12px 20px;
    border-radius: 8px; font-size: 0.82rem; z-index: 200;
    opacity: 0; transform: translateY(-10px); transition: all 0.3s;
}}
.toast.visible {{ opacity: 1; transform: translateY(0); }}
.toast-error {{ background: rgba(248,113,113,0.9); color: #fff; }}
.toast-info {{ background: rgba(108,138,255,0.9); color: #fff; }}
</style>
</head>
<body>

<div class="header">
    <h1>互動式幣流探索器</h1>
    <a href="/" class="back-link">← 驗證報告</a>
    <a href="/exchange-report" class="back-link">← 交易所調閱報告</a>
</div>

<div class="input-bar">
    <label>目標地址</label>
    <input type="text" id="inp-address" placeholder="T... (TRON 地址)">
    <label>幣別</label>
    <select id="inp-coin">
        <option value="USDT-TRC20">USDT-TRC20</option>
        <option value="TRX">TRX</option>
    </select>
    <button class="btn btn-primary" id="btn-start">開始探索</button>
</div>

<div class="root-card" id="root-card">
    <div class="node-header">
        <span class="alias">A</span>
        <span class="address" id="root-addr"></span>
        <a id="root-tronscan" href="#" target="_blank" style="font-size:0.75rem;">Tronscan</a>
    </div>
    <div class="node-badges" id="root-badges"></div>
    <div class="node-stats" id="root-stats"></div>
    <div style="margin-top:14px; display:flex; gap:8px;">
        <button class="btn btn-sm btn-out" onclick="doExpand('__ROOT__','out')">展開 OUT</button>
        <button class="btn btn-sm btn-in" onclick="doExpand('__ROOT__','in')">展開 IN</button>
        <button class="btn btn-sm btn-primary" id="btn-show-report" style="margin-left:auto;" onclick="toggleReport()">產生報告</button>
    </div>
</div>

<div class="report-panel" id="report-panel">
    <h2>產生警用幣流分析報告</h2>
    <div class="report-form">
        <div class="form-group"><label>機關名稱</label><input id="rpt-agency" placeholder="如：內政部警政署刑事警察局"></div>
        <div class="form-group"><label>分局名稱</label><input id="rpt-division" placeholder="如：偵查第九大隊"></div>
        <div class="form-group"><label>案號</label><input id="rpt-case" placeholder="如：113 年偵字第 12345 號"></div>
        <div class="form-group"><label>分析人員</label><input id="rpt-analyst" placeholder="職稱 姓名"></div>
        <div class="form-group"><label>審核人員</label><input id="rpt-reviewer" placeholder="職稱 姓名"></div>
        <div class="report-actions">
            <button class="btn btn-primary" id="btn-gen-report" onclick="generateReport()">送出產生報告</button>
            <span id="report-status" style="font-size:0.82rem; color:var(--text-dim); align-self:center;"></span>
        </div>
    </div>
</div>

<div class="tree-section" id="tree-section" style="display:none;">
    <h2>探索樹</h2>
    <div class="tree-table-wrap">
        <table class="tree-table">
            <thead>
                <tr>
                    <th>別名</th>
                    <th>地址</th>
                    <th>標籤</th>
                    <th>方向</th>
                    <th style="text-align:right;">金額</th>
                    <th style="text-align:center;">筆數</th>
                    <th style="text-align:center;">風險</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody id="tree-body"></tbody>
        </table>
    </div>
</div>

<div class="status-bar">
    <span>API 呼叫: <span class="api-count" id="api-count">0</span></span>
    <span id="status-text">就緒</span>
</div>

<div class="toast" id="toast"></div>

<script>
(function() {{
    /* ========== State ========== */
    let sessionId = null;
    let rootAddress = '';
    let apiCalls = 0;
    let nodeMap = {{}};    // address -> node_info
    let aliasCounter = {{}};  // layer -> count
    let treeRows = [];     // flat list of row data for rendering
    let expandedSet = new Set(); // "addr:dir" -> expanded

    const LAYER_LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';

    /* ========== DOM refs ========== */
    const $addr = document.getElementById('inp-address');
    const $coin = document.getElementById('inp-coin');
    const $btnStart = document.getElementById('btn-start');
    const $rootCard = document.getElementById('root-card');
    const $rootAddr = document.getElementById('root-addr');
    const $rootTronscan = document.getElementById('root-tronscan');
    const $rootBadges = document.getElementById('root-badges');
    const $rootStats = document.getElementById('root-stats');
    const $treeSection = document.getElementById('tree-section');
    const $treeBody = document.getElementById('tree-body');
    const $apiCount = document.getElementById('api-count');
    const $statusText = document.getElementById('status-text');
    const $reportPanel = document.getElementById('report-panel');

    /* ========== Utils ========== */
    function esc(s) {{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }}
    function shortAddr(a) {{ return a.length > 16 ? a.slice(0,6)+'...'+a.slice(-6) : a; }}
    function fmtAmount(v, token) {{
        if (v === 0) return '0 ' + token;
        if (v >= 1) return v.toLocaleString(undefined, {{minimumFractionDigits:2, maximumFractionDigits:2}}) + ' ' + token;
        return v.toFixed(6) + ' ' + token;
    }}
    function tronscanUrl(addr) {{ return 'https://tronscan.org/#/address/' + addr; }}

    function showToast(msg, type) {{
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = 'toast visible toast-' + (type || 'info');
        setTimeout(() => t.className = 'toast', 3000);
    }}

    function setStatus(msg) {{ $statusText.textContent = msg; }}
    function incApi(n) {{ apiCalls += (n||1); $apiCount.textContent = apiCalls; }}

    function riskBadgeHtml(level, score) {{
        if (!level && !score) return '';
        const cls = {{'Low':'badge-risk-low','Moderate':'badge-risk-moderate','High':'badge-risk-high','Severe':'badge-risk-severe'}}[level] || 'badge-label';
        const zh = {{'Low':'低風險','Moderate':'中風險','High':'高風險','Severe':'嚴重'}}[level] || (level||'未知');
        return '<span class="badge '+cls+'">'+zh+' ('+score+')</span>';
    }}

    function heuristicTags(info) {{
        /* 啟發式判斷：車手 vs 水房 */
        const tags = [];
        if (!info || info.is_exchange) return '';
        const rcv = info.received_txs_count || 0;
        const snt = info.spent_txs_count || 0;
        const first = info.first_seen || 0;
        const last = info.last_seen || 0;
        const daySpan = (first && last) ? (last - first) / 86400 : 999;

        /* 車手特徵：使用時間短、交易少、收支近 1:1 */
        if (daySpan < 30 && (rcv + snt) < 60 && rcv > 0 && snt > 0 && (rcv / snt) < 2) {{
            tags.push('<span class="heuristic-tag badge-mule">疑似車手</span>');
        }}
        /* 水房特徵：收入次數 > 支出 2 倍、交易數中高 */
        if (rcv > 0 && snt > 0 && (rcv / snt) >= 2 && (rcv + snt) >= 50) {{
            tags.push('<span class="heuristic-tag badge-house">疑似水房</span>');
        }}
        return tags.join('');
    }}

    /* ========== API calls ========== */
    async function apiPost(path, body) {{
        const resp = await fetch(path, {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify(body),
        }});
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'API error ' + resp.status);
        return data;
    }}

    /* ========== Start ========== */
    $btnStart.addEventListener('click', startExplore);
    $addr.addEventListener('keydown', e => {{ if (e.key === 'Enter') startExplore(); }});

    /* Auto-start if URL has ?address= parameter */
    (function autoStart() {{
        const params = new URLSearchParams(window.location.search);
        const addr = params.get('address');
        const coin = params.get('coin');
        if (addr) {{
            $addr.value = addr;
            if (coin) $coin.value = coin;
            setTimeout(startExplore, 300);
        }}
    }})();

    async function startExplore() {{
        const address = $addr.value.trim();
        if (!address) {{ showToast('請輸入地址', 'error'); return; }}
        const coin = $coin.value;

        $btnStart.disabled = true;
        $btnStart.textContent = '查詢中…';
        setStatus('正在查詢地址資訊…');

        try {{
            const data = await apiPost('/api/explorer/start', {{ address, coin }});
            incApi(3);
            sessionId = data.session_id;
            rootAddress = address;
            const info = data.node_info;
            nodeMap = {{}};
            nodeMap[address] = info;
            aliasCounter = {{ 0: 1 }};
            treeRows = [];
            expandedSet = new Set();

            // Render root card
            renderRootCard(info);
            $rootCard.classList.add('visible');
            $treeSection.style.display = 'none';
            $treeBody.innerHTML = '';
            $reportPanel.classList.remove('visible');

            setStatus('就緒 — 可展開 IN/OUT 探索');
        }} catch (e) {{
            showToast(e.message, 'error');
            setStatus('查詢失敗');
        }} finally {{
            $btnStart.disabled = false;
            $btnStart.textContent = '開始探索';
        }}
    }}

    function renderRootCard(info) {{
        $rootAddr.textContent = info.address;
        $rootTronscan.href = tronscanUrl(info.address);

        let badges = '';
        if (info.labels && info.labels.length) {{
            info.labels.forEach(l => {{ badges += '<span class="badge badge-label">'+esc(l)+'</span>'; }});
        }}
        if (info.is_exchange) badges += '<span class="badge badge-exchange">交易所</span>';
        badges += riskBadgeHtml(info.risk_level, info.risk_score);
        badges += heuristicTags(info);
        $rootBadges.innerHTML = badges;

        $rootStats.innerHTML = `
            <div class="stat"><div class="stat-label">餘額</div><div class="stat-value">${{fmtAmount(info.balance||0, 'TRX')}}</div></div>
            <div class="stat"><div class="stat-label">總收入</div><div class="stat-value">${{fmtAmount(info.total_received||0, '')}}</div></div>
            <div class="stat"><div class="stat-label">總支出</div><div class="stat-value">${{fmtAmount(info.total_spent||0, '')}}</div></div>
            <div class="stat"><div class="stat-label">交易筆數</div><div class="stat-value">${{(info.txs_count||0).toLocaleString()}}</div></div>
            <div class="stat"><div class="stat-label">首見</div><div class="stat-value">${{info.first_seen ? new Date(info.first_seen*1000).toLocaleDateString() : '—'}}</div></div>
            <div class="stat"><div class="stat-label">末見</div><div class="stat-value">${{info.last_seen ? new Date(info.last_seen*1000).toLocaleDateString() : '—'}}</div></div>
        `;
    }}

    /* ========== Expand ========== */
    window.doExpand = async function(rowKey, direction) {{
        const address = rowKey === '__ROOT__' ? rootAddress : rowKey;
        const expandKey = address + ':' + direction;

        if (expandedSet.has(expandKey)) {{
            // Toggle collapse
            toggleChildren(expandKey);
            return;
        }}

        setStatus('正在查詢 ' + shortAddr(address) + ' 的' + (direction==='out'?'轉出':'轉入') + '…');

        try {{
            const data = await apiPost('/api/explorer/expand', {{
                session_id: sessionId, address, direction,
            }});
            incApi(1);
            expandedSet.add(expandKey);

            const counterparties = data.counterparties || [];
            if (counterparties.length === 0) {{
                showToast('無' + (direction==='out'?'轉出':'轉入') + '交易', 'info');
                setStatus('就緒');
                return;
            }}

            // Determine parent layer
            const parentInfo = nodeMap[address];
            const parentLayer = parentInfo ? (parentInfo.layer || 0) : 0;
            const childLayer = parentLayer + 1;
            if (!aliasCounter[childLayer]) aliasCounter[childLayer] = 0;

            // Build rows
            const newRows = [];
            counterparties.forEach(cp => {{
                const idx = aliasCounter[childLayer]++;
                const letter = childLayer < LAYER_LETTERS.length ? LAYER_LETTERS[childLayer] : 'L' + childLayer;
                const alias = childLayer === 0 ? letter : letter + (idx + 1);
                const cpAddr = cp.address;

                const rowData = {{
                    expandKey: expandKey,
                    address: cpAddr,
                    alias: alias,
                    labels: cp.labels || [],
                    is_exchange: cp.is_exchange || false,
                    direction: direction,
                    amount: cp.amount || 0,
                    token: cp.token || 'USDT',
                    tx_count: cp.tx_count || 0,
                    risk_score: 0,
                    risk_level: '',
                    layer: childLayer,
                    parentAddress: address,
                    detailLoaded: false,
                }};

                // Cache basic info
                if (!nodeMap[cpAddr]) {{
                    nodeMap[cpAddr] = {{
                        address: cpAddr, alias: alias, labels: cp.labels || [],
                        is_exchange: cp.is_exchange, layer: childLayer,
                        risk_score: 0, risk_level: '', balance: 0,
                        total_received: 0, total_spent: 0,
                        received_txs_count: 0, spent_txs_count: 0,
                        first_seen: 0, last_seen: 0, txs_count: 0,
                    }};
                }}

                treeRows.push(rowData);
                newRows.push(rowData);
            }});

            renderTree();
            $treeSection.style.display = '';
            setStatus('就緒 — 找到 ' + counterparties.length + ' 個對手方');
        }} catch (e) {{
            showToast(e.message, 'error');
            setStatus('查詢失敗');
        }}
    }};

    /* ========== Node Detail (lazy load) ========== */
    window.doDetail = async function(address) {{
        setStatus('正在載入 ' + shortAddr(address) + ' 詳情…');
        try {{
            const data = await apiPost('/api/explorer/node-detail', {{
                session_id: sessionId, address: address,
            }});
            incApi(3);

            // Update cache
            const old = nodeMap[address] || {{}};
            Object.assign(old, data);
            nodeMap[address] = old;

            // Update row data
            treeRows.forEach(r => {{
                if (r.address === address) {{
                    r.risk_score = data.risk_score || 0;
                    r.risk_level = data.risk_level || '';
                    r.detailLoaded = true;
                }}
            }});

            renderTree();
            setStatus('就緒');
        }} catch (e) {{
            showToast(e.message, 'error');
            setStatus('載入失敗');
        }}
    }};

    /* ========== Render Tree ========== */
    function renderTree() {{
        let html = '';
        treeRows.forEach((row, idx) => {{
            const depthIndent = '│ '.repeat(Math.max(0, row.layer - 1)) + (row.layer > 0 ? '├ ' : '');
            const exchCls = row.is_exchange ? ' is-exchange' : '';
            const dirCls = row.direction === 'in' ? 'dir-in' : 'dir-out';
            const dirLabel = row.direction === 'in' ? '← IN' : '→ OUT';

            let labelHtml = '';
            if (row.labels && row.labels.length) {{
                labelHtml = row.labels.map(l => '<span class="badge badge-label">' + esc(l) + '</span>').join(' ');
            }}
            if (row.is_exchange) {{
                labelHtml += ' <span class="badge badge-kyc">KYC</span>';
            }}

            let riskHtml = '';
            if (row.detailLoaded) {{
                riskHtml = riskBadgeHtml(row.risk_level, row.risk_score);
                riskHtml += heuristicTags(nodeMap[row.address]);
            }}

            let actionsHtml = '';
            if (!row.is_exchange) {{
                actionsHtml += '<button class="btn btn-sm btn-out" onclick="doExpand(&#39;'+row.address+'&#39;,&#39;out&#39;)">OUT</button>';
                actionsHtml += '<button class="btn btn-sm btn-in" onclick="doExpand(&#39;'+row.address+'&#39;,&#39;in&#39;)">IN</button>';
            }}
            if (!row.detailLoaded) {{
                actionsHtml += '<button class="btn btn-sm btn-detail" onclick="doDetail(&#39;'+row.address+'&#39;)">詳情</button>';
            }}

            html += '<tr class="tree-row' + exchCls + '" data-addr="' + row.address + '">'
                + '<td class="indent-cell"><span class="indent-marker">' + esc(depthIndent) + '</span><span class="alias-cell">' + esc(row.alias) + '</span></td>'
                + '<td class="addr-cell"><a href="' + tronscanUrl(row.address) + '" target="_blank" title="' + esc(row.address) + '">' + shortAddr(row.address) + '</a></td>'
                + '<td class="labels-cell">' + labelHtml + '</td>'
                + '<td><span class="' + dirCls + '">' + dirLabel + '</span></td>'
                + '<td class="amount-cell">' + fmtAmount(row.amount, row.token) + '</td>'
                + '<td class="count-cell">' + (row.tx_count || '—') + '</td>'
                + '<td class="risk-cell">' + riskHtml + '</td>'
                + '<td class="actions-cell">' + actionsHtml + '</td>'
                + '</tr>';
        }});

        $treeBody.innerHTML = html || '<tr><td colspan="8" class="no-data">尚未展開任何節點</td></tr>';
    }}

    function toggleChildren(expandKey) {{
        // Simple toggle: hide/show rows belonging to this expandKey
        // For now we just remove them from display if already shown
        // This is a simplistic approach; a full tree would be more complex
    }}

    /* ========== Report ========== */
    window.toggleReport = function() {{
        $reportPanel.classList.toggle('visible');
    }};

    window.generateReport = async function() {{
        const btn = document.getElementById('btn-gen-report');
        const status = document.getElementById('report-status');
        btn.disabled = true;
        status.textContent = '產生中…';

        try {{
            const data = await apiPost('/api/explorer/report', {{
                session_id: sessionId,
                agency: document.getElementById('rpt-agency').value,
                division: document.getElementById('rpt-division').value,
                case_number: document.getElementById('rpt-case').value,
                analyst: document.getElementById('rpt-analyst').value,
                reviewer: document.getElementById('rpt-reviewer').value,
            }});
            incApi(1);

            const jobId = data.job_id;
            status.textContent = '背景產生中，請稍候…';

            // Poll
            while (true) {{
                await new Promise(r => setTimeout(r, 3000));
                const poll = await fetch('/api/flow-report/' + jobId);
                const st = await poll.json();
                if (st.status === 'done') {{
                    status.innerHTML = '報告已產生！ <a href="'+st.url+'" target="_blank" style="color:var(--accent);font-weight:600;">點此開啟報告 ↗</a>';
                    // 嘗試自動開啟（可能被瀏覽器擋）
                    const w = window.open(st.url, '_blank');
                    if (!w) showToast('請點擊上方連結開啟報告（彈出視窗被阻擋）', 'info');
                    break;
                }} else if (st.status === 'error') {{
                    throw new Error(st.error || '產生失敗');
                }}
                status.textContent = '背景產生中…';
            }}
        }} catch (e) {{
            status.textContent = '失敗: ' + e.message;
            showToast(e.message, 'error');
        }} finally {{
            btn.disabled = false;
        }}
    }};

}})();
</script>
</body>
</html>"""
