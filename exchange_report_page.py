"""交易所調閱報告 — Web 前端頁面 HTML 生成。"""


def generate_exchange_report_page_html() -> str:
    """產生交易所調閱報告的前端 HTML 頁面。"""
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>交易所調閱用幣流分析報告</title>
<style>
:root {{
    --bg: #0f1117; --surface: #1a1d27; --surface2: #232734;
    --border: #2e3347; --text: #e0e0e8; --text-dim: #888da0;
    --accent: #6c8aff; --green: #34d399; --yellow: #fbbf24;
    --red: #f87171; --orange: #fb923c; --purple: #a855f7;
}}
:root.light {{
    --bg: #f0f2f5; --surface: #ffffff; --surface2: #e8ecf1;
    --border: #c5cdd8; --text: #1b2537; --text-dim: #5a6a7e;
    --accent: #2754a8; --green: #1a7f56; --yellow: #b8860b;
    --red: #b91c1c; --orange: #c05621; --purple: #6d28d9;
}}
:root.light .card {{ box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
:root.light .btn-primary {{ background: #2754a8; border-color: #2754a8; }}
:root.light .btn-primary:hover {{ filter: brightness(1.1); }}
@media print {{
    :root {{
        --bg: #fff; --surface: #fff; --surface2: #f5f5f5;
        --border: #bbb; --text: #000; --text-dim: #444;
        --accent: #2754a8; --green: #1a7f56; --yellow: #b8860b;
        --red: #b91c1c; --orange: #c05621; --purple: #6d28d9;
    }}
    .theme-toggle {{ display: none; }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px;
    max-width: 900px; margin: 0 auto; padding-bottom: 56px;
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

/* --- Card --- */
.card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 20px 24px; margin-bottom: 20px;
}}
.card h2 {{
    font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: var(--text);
    padding-bottom: 8px; border-bottom: 1px solid var(--border);
}}
.card h3 {{
    font-size: 0.88rem; font-weight: 600; margin-top: 16px; margin-bottom: 8px;
    color: var(--text-dim);
}}

/* --- Form --- */
.form-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
}}
.form-group {{
    display: flex; flex-direction: column; gap: 4px;
}}
.form-group.full {{ grid-column: 1 / -1; }}
.form-group label {{
    font-size: 0.78rem; color: var(--text-dim); font-weight: 500;
}}
.form-group .hint {{
    font-size: 0.7rem; color: var(--text-dim); opacity: 0.7; margin-top: 2px;
}}
.form-group input, .form-group textarea, .form-group select {{
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 9px 14px; border-radius: 6px; font-size: 0.88rem;
    font-family: inherit;
}}
.form-group input::placeholder, .form-group textarea::placeholder {{ color: var(--text-dim); opacity: 0.5; }}
.form-group textarea {{ resize: vertical; min-height: 60px; }}
.form-group input.mono {{
    font-family: "SF Mono", "Fira Code", monospace; font-size: 0.82rem;
}}
.form-group select {{
    cursor: pointer;
}}

/* --- Address list --- */
.addr-list {{
    display: flex; flex-direction: column; gap: 6px; margin-top: 4px;
}}
.addr-row {{
    display: flex; gap: 8px; align-items: center;
}}
.addr-row input {{ flex: 1; }}
.addr-row .btn-remove {{
    background: none; border: 1px solid var(--border); color: var(--red);
    padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 0.82rem;
    transition: all 0.15s;
}}
.addr-row .btn-remove:hover {{ background: rgba(248,113,113,0.15); }}
.btn-add {{
    background: var(--surface2); border: 1px dashed var(--border); color: var(--text-dim);
    padding: 8px; border-radius: 6px; cursor: pointer; font-size: 0.82rem;
    text-align: center; transition: all 0.15s; margin-top: 4px;
}}
.btn-add:hover {{ border-color: var(--accent); color: var(--accent); }}

/* --- Buttons --- */
.btn {{
    padding: 10px 22px; border-radius: 8px; font-size: 0.88rem; font-weight: 600;
    cursor: pointer; border: 1px solid var(--border); transition: all 0.15s;
}}
.btn-primary {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
.btn-primary:hover {{ filter: brightness(1.15); }}
.btn-primary:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.btn-secondary {{ background: var(--surface2); color: var(--text-dim); }}
.btn-secondary:hover {{ color: var(--text); }}

.actions {{ display: flex; gap: 12px; align-items: center; margin-top: 20px; }}

/* --- Progress --- */
.progress-panel {{
    display: none; margin-top: 20px;
}}
.progress-panel.visible {{ display: block; }}
.progress-bar-wrap {{
    background: var(--bg); border-radius: 8px; height: 6px; overflow: hidden;
    margin-bottom: 12px;
}}
.progress-bar {{
    height: 100%; background: var(--accent); border-radius: 8px;
    width: 0%; transition: width 0.4s;
}}
.progress-bar.indeterminate {{
    width: 30%; animation: indeterminate 1.5s ease-in-out infinite;
}}
@keyframes indeterminate {{
    0% {{ margin-left: 0; }}
    50% {{ margin-left: 70%; }}
    100% {{ margin-left: 0; }}
}}
.progress-text {{
    font-size: 0.82rem; color: var(--text-dim); text-align: center;
}}
.progress-text.done {{ color: var(--green); }}
.progress-text.error {{ color: var(--red); }}

/* --- Result --- */
.result-panel {{
    display: none; margin-top: 20px; padding: 16px; border-radius: 8px;
    border: 1px solid var(--green); background: rgba(52,211,153,0.05);
}}
.result-panel.visible {{ display: block; }}
.result-panel h3 {{ color: var(--green); margin: 0 0 8px; font-size: 0.95rem; }}
.result-panel a {{
    display: inline-block; padding: 8px 18px; border-radius: 6px;
    background: var(--green); color: #000; font-weight: 600; font-size: 0.88rem;
    margin-top: 8px;
}}
.result-panel a:hover {{ filter: brightness(1.1); text-decoration: none; }}

/* --- Status Bar --- */
.status-bar {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: var(--surface); border-top: 1px solid var(--border);
    padding: 8px 24px; font-size: 0.78rem; color: var(--text-dim);
    display: flex; justify-content: space-between; align-items: center;
    z-index: 100;
}}

/* --- Toast --- */
.toast {{
    position: fixed; top: 20px; right: 20px; padding: 12px 20px;
    border-radius: 8px; font-size: 0.82rem; z-index: 200;
    opacity: 0; transform: translateY(-10px); transition: all 0.3s;
    max-width: 400px;
}}
.toast.visible {{ opacity: 1; transform: translateY(0); }}
.toast-error {{ background: rgba(248,113,113,0.9); color: #fff; }}
.toast-info {{ background: rgba(108,138,255,0.9); color: #fff; }}

/* --- Responsive --- */
/* --- Theme toggle --- */
.theme-toggle {{
    background: var(--surface2); border: 1px solid var(--border); color: var(--text-dim);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    transition: all 0.15s;
}}
.theme-toggle:hover {{ color: var(--text); border-color: var(--accent); }}

@media (max-width: 640px) {{
    .form-grid {{ grid-template-columns: 1fr; }}
    .form-group.full {{ grid-column: 1; }}
}}
</style>
</head>
<body>

<div class="header">
    <h1>交易所調閱用幣流分析報告</h1>
    <a href="/explorer" class="back-link">← 互動式探索器</a>
    <a href="/" class="back-link">← 驗證報告</a>
    <button class="theme-toggle" onclick="toggleTheme()">淺色模式</button>
</div>

<!-- 地址與幣別 -->
<div class="card">
    <h2>追蹤目標</h2>
    <div class="form-grid">
        <div class="form-group full">
            <label>追蹤起始地址</label>
            <div class="addr-list" id="addr-list">
                <div class="addr-row">
                    <input type="text" class="mono addr-input" placeholder="T... (TRON 地址)">
                    <button class="btn-remove" onclick="removeAddr(this)" title="移除">✕</button>
                </div>
            </div>
            <button class="btn-add" onclick="addAddr()">+ 新增地址</button>
        </div>
        <div class="form-group">
            <label>幣別</label>
            <select id="inp-coin">
                <option value="USDT-TRC20">USDT-TRC20</option>
                <option value="TRX">TRX</option>
            </select>
        </div>
        <div class="form-group">
            <label>最大追蹤深度</label>
            <select id="inp-depth">
                <option value="2">2 層</option>
                <option value="3">3 層</option>
                <option value="4" selected>4 層（預設）</option>
                <option value="5">5 層</option>
                <option value="6">6 層</option>
            </select>
        </div>
        <div class="form-group">
            <label>每層展開上限（Top N）</label>
            <select id="inp-topn">
                <option value="3" selected>前 3 個（省 API，推薦）</option>
                <option value="5">前 5 個</option>
                <option value="10">前 10 個</option>
                <option value="0">不限制（全部展開）</option>
            </select>
            <span class="hint">只追蹤金額最高、交易最頻繁的地址，大幅降低 API 成本</span>
        </div>
        <div class="form-group">
            <label>犯罪時間起始日</label>
            <input type="date" id="inp-start-date">
            <span class="hint">選填，限縮起始地址的交易時間範圍</span>
        </div>
        <div class="form-group">
            <label>犯罪時間結束日</label>
            <input type="date" id="inp-end-date">
            <span class="hint">選填，與起始日搭配使用</span>
        </div>
        <div class="form-group">
            <label>目標交易所</label>
            <select id="inp-target-exchange">
                <option value="">全部（不限）</option>
                <option value="maicoin">MaiCoin / MAX</option>
                <option value="binance">Binance</option>
                <option value="bitopro">BitoPro</option>
                <option value="okx">OKX</option>
                <option value="ace">ACE</option>
                <option value="bybit">Bybit</option>
                <option value="__custom__">其他（自填）</option>
            </select>
            <span class="hint">選填，僅保留通往指定交易所的資金路徑</span>
        </div>
        <div class="form-group" id="custom-exchange-group" style="display:none;">
            <label>自訂交易所關鍵字</label>
            <input type="text" id="inp-custom-exchange" placeholder="如：kucoin">
        </div>
    </div>
</div>

<!-- 案件資訊 -->
<div class="card">
    <h2>案件資訊</h2>
    <div class="form-grid">
        <div class="form-group">
            <label>機關名稱</label>
            <input type="text" id="inp-agency" placeholder="如：○○市政府警察局">
        </div>
        <div class="form-group">
            <label>分局/大隊</label>
            <input type="text" id="inp-division" placeholder="如：刑事警察大隊">
        </div>
        <div class="form-group">
            <label>案號</label>
            <input type="text" id="inp-case-number" placeholder="如：114年度金訴字第1375號">
        </div>
        <div class="form-group">
            <label>案類</label>
            <input type="text" id="inp-case-type" value="詐欺" placeholder="詐欺">
        </div>
        <div class="form-group">
            <label>分析人員</label>
            <input type="text" id="inp-analyst" placeholder="職稱 姓名（如：偵查佐 王大明）">
        </div>
        <div class="form-group">
            <label>審核人員</label>
            <input type="text" id="inp-reviewer" placeholder="職稱 姓名（如：副隊長 李小華）">
        </div>
        <div class="form-group full">
            <label>案件描述（選填）</label>
            <textarea id="inp-description" placeholder="案件說明、偵辦緣由等..."></textarea>
        </div>
    </div>
</div>

<!-- 操作 -->
<div class="card">
    <div class="actions">
        <button class="btn btn-primary" id="btn-generate" onclick="startGenerate()">
            產生交易所調閱報告
        </button>
        <span style="font-size:0.78rem; color:var(--text-dim);">
            將執行 BFS 幣流追蹤 → TRX 油費分析 → 錢包分類 → 產生報告
        </span>
    </div>

    <div class="progress-panel" id="progress-panel">
        <div class="progress-bar-wrap">
            <div class="progress-bar indeterminate" id="progress-bar"></div>
        </div>
        <div class="progress-text" id="progress-text">準備中...</div>
    </div>

    <div class="result-panel" id="result-panel">
        <h3>報告產生完成</h3>
        <p style="font-size:0.85rem; color:var(--text-dim);" id="result-desc"></p>
        <a id="result-link" href="#" target="_blank">開啟報告 ↗</a>
    </div>
</div>

<div class="status-bar">
    <span id="status-text">就緒</span>
</div>

<div class="toast" id="toast"></div>

<script>
(function() {{

    /* ========== DOM ========== */
    const $addrList = document.getElementById('addr-list');
    const $btn = document.getElementById('btn-generate');
    const $progress = document.getElementById('progress-panel');
    const $progressBar = document.getElementById('progress-bar');
    const $progressText = document.getElementById('progress-text');
    const $result = document.getElementById('result-panel');
    const $resultDesc = document.getElementById('result-desc');
    const $resultLink = document.getElementById('result-link');
    const $statusText = document.getElementById('status-text');

    /* ========== Utils ========== */
    function showToast(msg, type) {{
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.className = 'toast visible toast-' + (type || 'info');
        setTimeout(() => t.className = 'toast', 4000);
    }}

    function setStatus(msg) {{ $statusText.textContent = msg; }}

    /* ========== Address list ========== */
    window.addAddr = function() {{
        const row = document.createElement('div');
        row.className = 'addr-row';
        row.innerHTML = '<input type="text" class="mono addr-input" placeholder="T... (TRON 地址)">'
            + '<button class="btn-remove" onclick="removeAddr(this)" title="移除">✕</button>';
        $addrList.appendChild(row);
    }};

    window.removeAddr = function(btn) {{
        const rows = $addrList.querySelectorAll('.addr-row');
        if (rows.length <= 1) return; // 至少保留一個
        btn.closest('.addr-row').remove();
    }};

    function getAddresses() {{
        const inputs = $addrList.querySelectorAll('.addr-input');
        const addrs = [];
        inputs.forEach(inp => {{
            const v = inp.value.trim();
            if (v) addrs.push(v);
        }});
        return addrs;
    }}

    /* ========== Auto-fill from URL params ========== */
    (function autoFill() {{
        const params = new URLSearchParams(window.location.search);
        // 支援多地址：addresses=addr1,addr2,addr3
        const addrsParam = params.get('addresses');
        const addr = params.get('address');
        if (addrsParam) {{
            const addrs = addrsParam.split(',').filter(a => a.trim());
            if (addrs.length > 0) {{
                const firstInput = $addrList.querySelector('.addr-input');
                if (firstInput) firstInput.value = addrs[0];
                for (let i = 1; i < addrs.length; i++) {{
                    window.addAddr();
                    const inputs = $addrList.querySelectorAll('.addr-input');
                    inputs[inputs.length - 1].value = addrs[i];
                }}
            }}
        }} else if (addr) {{
            const firstInput = $addrList.querySelector('.addr-input');
            if (firstInput) firstInput.value = addr;
        }}
        ['agency', 'division', 'case-number', 'case-type', 'analyst', 'reviewer', 'description'].forEach(key => {{
            const val = params.get(key);
            if (val) {{
                const el = document.getElementById('inp-' + key);
                if (el) el.value = val;
            }}
        }});
        // 犯罪時間起始/結束日
        const startDate = params.get('start-date');
        const endDate = params.get('end-date');
        if (startDate) document.getElementById('inp-start-date').value = startDate;
        if (endDate) document.getElementById('inp-end-date').value = endDate;
    }})();

    /* ========== Target exchange custom toggle ========== */
    document.getElementById('inp-target-exchange').addEventListener('change', function() {{
        const customGroup = document.getElementById('custom-exchange-group');
        customGroup.style.display = this.value === '__custom__' ? 'flex' : 'none';
    }});

    /* ========== Generate ========== */
    window.startGenerate = async function() {{
        const addresses = getAddresses();
        if (addresses.length === 0) {{
            showToast('請至少輸入一個 TRON 地址', 'error');
            return;
        }}

        // Validate addresses
        for (const addr of addresses) {{
            if (!addr.startsWith('T') || addr.length !== 34) {{
                showToast('地址格式不正確: ' + addr, 'error');
                return;
            }}
        }}

        const coin = document.getElementById('inp-coin').value;
        const maxDepth = parseInt(document.getElementById('inp-depth').value);
        const topN = parseInt(document.getElementById('inp-topn').value);
        const agency = document.getElementById('inp-agency').value.trim();
        const division = document.getElementById('inp-division').value.trim();
        const caseNumber = document.getElementById('inp-case-number').value.trim();
        const caseType = document.getElementById('inp-case-type').value.trim() || '詐欺';
        const analyst = document.getElementById('inp-analyst').value.trim();
        const reviewer = document.getElementById('inp-reviewer').value.trim();
        const description = document.getElementById('inp-description').value.trim();

        // 時間範圍：轉為毫秒 Unix timestamp
        const startDateStr = document.getElementById('inp-start-date').value;
        const endDateStr = document.getElementById('inp-end-date').value;
        let minTimestamp = 0;
        let maxTimestamp = 0;
        if (startDateStr) {{
            minTimestamp = new Date(startDateStr + 'T00:00:00').getTime();
        }}
        if (endDateStr) {{
            // 結束日包含當天：設為當天 23:59:59.999
            maxTimestamp = new Date(endDateStr + 'T23:59:59.999').getTime();
        }}

        // 目標交易所
        let targetExchangeVal = document.getElementById('inp-target-exchange').value;
        if (targetExchangeVal === '__custom__') {{
            targetExchangeVal = document.getElementById('inp-custom-exchange').value.trim();
        }}
        const targetExchange = targetExchangeVal || '';

        // Show progress
        $btn.disabled = true;
        $progress.classList.add('visible');
        $result.classList.remove('visible');
        $progressBar.className = 'progress-bar indeterminate';
        $progressText.textContent = '提交任務中...';
        $progressText.className = 'progress-text';
        setStatus('正在產生報告...');

        try {{
            // Submit job for first address (one at a time)
            const address = addresses[0];
            const resp = await fetch('/api/exchange-report', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{
                    address: address,
                    coin: coin,
                    max_depth: maxDepth,
                    top_n: topN,
                    min_timestamp: minTimestamp,
                    max_timestamp: maxTimestamp,
                    target_exchange: targetExchange,
                    agency: agency,
                    division: division,
                    case_number: caseNumber,
                    case_type: caseType,
                    analyst: analyst,
                    reviewer: reviewer,
                    description: description,
                }}),
            }});

            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'API 錯誤');

            const jobId = data.job_id;
            $progressText.textContent = '背景執行中：BFS 幣流追蹤 → TRX 分析 → 錢包分類 → 產生報告...';

            // Poll for status
            let pollCount = 0;
            while (true) {{
                await new Promise(r => setTimeout(r, 3000));
                pollCount++;

                const pollResp = await fetch('/api/exchange-report/' + jobId);
                const st = await pollResp.json();

                if (st.status === 'done') {{
                    // Done!
                    $progressBar.className = 'progress-bar';
                    $progressBar.style.width = '100%';
                    $progressText.textContent = '報告產生完成！';
                    $progressText.className = 'progress-text done';

                    $result.classList.add('visible');
                    $resultDesc.textContent = '地址 ' + address.slice(0, 8) + '... 之交易所調閱報告已產生。';
                    $resultLink.href = st.url;

                    setStatus('完成');

                    // Auto-open
                    const w = window.open(st.url, '_blank');
                    if (!w) showToast('請點擊下方連結開啟報告（彈出視窗被阻擋）', 'info');
                    break;

                }} else if (st.status === 'error') {{
                    throw new Error(st.error || '報告產生失敗');
                }}

                // Still running
                const dots = '.'.repeat((pollCount % 3) + 1);
                $progressText.textContent = '背景執行中' + dots + '（已等待 ' + (pollCount * 3) + ' 秒）';
            }}

        }} catch (e) {{
            $progressBar.className = 'progress-bar';
            $progressBar.style.width = '100%';
            $progressBar.style.background = 'var(--red)';
            $progressText.textContent = '失敗: ' + e.message;
            $progressText.className = 'progress-text error';
            setStatus('失敗');
            showToast(e.message, 'error');
        }} finally {{
            $btn.disabled = false;
        }}
    }};

}})();

/* Theme toggle */
window.toggleTheme = function() {{
    const root = document.documentElement;
    const btn = document.querySelector('.theme-toggle');
    root.classList.toggle('light');
    const isLight = root.classList.contains('light');
    btn.textContent = isLight ? '深色模式' : '淺色模式';
    localStorage.setItem('theme', isLight ? 'light' : 'dark');
}};
(function() {{
    if (localStorage.getItem('theme') === 'light') {{
        document.documentElement.classList.add('light');
        const btn = document.querySelector('.theme-toggle');
        if (btn) btn.textContent = '深色模式';
    }}
}})();
</script>
</body>
</html>"""
