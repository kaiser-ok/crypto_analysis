#!/usr/bin/env python3
"""
patch_report.py — 為既有的 output/report.html 補上「案情」欄位。

功能：
1. 在 thead 的「案號」之後加入 <th>案情</th>
2. 在 tbody 的每一列（按 case_id 分組）的 case-info <td> 之後插入案情分析按鈕
   - 首列使用 rowspan 合併同 case_id 的列
   - 已分析：查看案情 按鈕（綠色）
   - 未分析：案情分析 按鈕（藍色）
3. 為已分析案件在 flow-cell 加上「案件幣流」按鈕
4. 加入必要的 CSS、analysis modal HTML、JavaScript
"""

import os
import sys
import re
from collections import OrderedDict

# 確保能 import 專案模組
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import case_analyzer

REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "report.html")


def _esc(s: str) -> str:
    """HTML escape."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#x27;"))


# ── CSS to inject ──
ANALYSIS_CSS = """
/* Case analysis button */
.analysis-cell { text-align: center; vertical-align: middle; }
.analysis-btn {
    background: var(--surface); border: 1px solid var(--accent); color: var(--accent);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap;
}
.analysis-btn:hover { background: rgba(108,138,255,0.1); }
.analysis-btn:disabled { cursor: not-allowed; opacity: 0.6; }
.analysis-view-btn {
    background: rgba(52,211,153,0.1); border: 1px solid var(--green); color: var(--green);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap;
}
.analysis-view-btn:hover { background: rgba(52,211,153,0.2); }
.case-flow-btn {
    background: var(--surface); border: 1px solid #a855f7; color: #a855f7;
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap; margin-top: 4px;
    display: inline-block;
}
.case-flow-btn:hover { background: rgba(168,85,247,0.1); }
/* Case analysis modal */
.analysis-modal .modal-box { max-width: 1000px; }
.analysis-section { margin-bottom: 16px; }
.analysis-section h4 { font-size: 0.85rem; color: var(--accent); margin-bottom: 8px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.analysis-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-bottom: 12px; }
.analysis-table th { background: var(--surface2); padding: 6px 10px; text-align: left; color: var(--text-dim); font-weight: 600; font-size: 0.72rem; }
.analysis-table td { padding: 6px 10px; border-bottom: 1px solid var(--border); }
.role-victim { color: var(--orange); font-weight: 600; }
.role-suspect { color: var(--red); font-weight: 600; }
.role-unknown { color: var(--text-dim); }
.analysis-desc { font-size: 0.82rem; line-height: 1.8; color: var(--text); padding: 12px; background: var(--surface); border-radius: 8px; }
"""

# ── Analysis modal HTML ──
ANALYSIS_MODAL_HTML = """
<div class="modal-overlay analysis-modal" id="analysis-modal">
    <div class="modal-box">
        <div class="modal-header">
            <h3 id="analysis-modal-title">案情分析</h3>
            <button class="modal-close" id="analysis-modal-close">&times;</button>
        </div>
        <div class="modal-body" id="analysis-modal-body"></div>
    </div>
</div>
"""

# ── JavaScript for analysis modal and case-flow buttons ──
ANALYSIS_JS = r"""
/* 案情分析 modal */
(function() {
    const aModal = document.getElementById('analysis-modal');
    const aTitle = document.getElementById('analysis-modal-title');
    const aBody = document.getElementById('analysis-modal-body');
    const aClose = document.getElementById('analysis-modal-close');

    function renderAnalysis(data) {
        let html = '';
        html += '<div class="analysis-section"><h4>案件基本資訊</h4>';
        html += '<table class="analysis-table"><tbody>';
        html += '<tr><td style="width:100px;color:var(--text-dim)">案號</td><td>' + (data.case_id || '—') + '</td></tr>';
        html += '<tr><td style="color:var(--text-dim)">法院</td><td>' + (data.court || '—') + '</td></tr>';
        html += '<tr><td style="color:var(--text-dim)">裁判日期</td><td>' + (data.judgment_date || '—') + '</td></tr>';
        html += '<tr><td style="color:var(--text-dim)">案由</td><td>' + (data.case_type || '—') + '</td></tr>';
        html += '</tbody></table></div>';
        if (data.defendants && data.defendants.length) {
            html += '<div class="analysis-section"><h4>被告</h4><ul>';
            data.defendants.forEach(d => { html += '<li>' + d.name + ' (' + d.role + ')</li>'; });
            html += '</ul></div>';
        }
        if (data.victims && data.victims.length) {
            html += '<div class="analysis-section"><h4>告訴人/被害人</h4><ul>';
            data.victims.forEach(v => { html += '<li>' + v.name + ' (' + v.role + ')</li>'; });
            html += '</ul></div>';
        }
        if (data.wallets && data.wallets.length) {
            html += '<div class="analysis-section"><h4>涉案錢包地址</h4>';
            html += '<table class="analysis-table"><thead><tr><th>地址</th><th>角色</th><th>持有人</th><th>標籤</th><th>前後文</th></tr></thead><tbody>';
            data.wallets.forEach(w => {
                const roleCls = w.role === 'victim' ? 'role-victim' : (w.role === 'suspect' ? 'role-suspect' : 'role-unknown');
                const roleText = w.role === 'victim' ? '被害人' : (w.role === 'suspect' ? '嫌犯' : '未知');
                html += '<tr>';
                html += '<td><code style="font-size:0.7rem">' + w.address + '</code></td>';
                html += '<td class="' + roleCls + '">' + roleText + '</td>';
                html += '<td>' + (w.owner_name || '—') + '</td>';
                html += '<td>' + (w.label || '—') + '</td>';
                html += '<td style="font-size:0.72rem;color:var(--text-dim);max-width:200px">' + (w.context || '') + '</td>';
                html += '</tr>';
            });
            html += '</tbody></table></div>';
        }
        if (data.transactions && data.transactions.length) {
            html += '<div class="analysis-section"><h4>交易紀錄</h4>';
            html += '<table class="analysis-table"><thead><tr><th>金額</th><th>幣種</th><th>日期</th><th>描述</th></tr></thead><tbody>';
            data.transactions.forEach(tx => {
                html += '<tr>';
                html += '<td>' + (tx.amount || '—') + '</td>';
                html += '<td>' + (tx.currency || '—') + '</td>';
                html += '<td>' + (tx.date || '—') + '</td>';
                html += '<td>' + (tx.description || '') + '</td>';
                html += '</tr>';
            });
            html += '</tbody></table></div>';
        }
        if (data.description) {
            html += '<div class="analysis-section"><h4>案件摘要</h4>';
            html += '<div class="analysis-desc">' + data.description + '</div></div>';
        }
        return html;
    }

    function showAnalysis(data) {
        aTitle.textContent = '案情分析 — ' + (data.case_id || '');
        aBody.innerHTML = renderAnalysis(data);
        aModal.classList.add('active');
    }

    document.querySelectorAll('.analysis-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const caseId = btn.dataset.caseid;
            const court = btn.dataset.court || '';
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span>分析中...';
            try {
                const resp = await fetch('/api/case-analysis', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({case_id: caseId, court: court}),
                });
                const data = await resp.json();
                if (resp.ok) {
                    btn.className = 'analysis-view-btn';
                    btn.innerHTML = '查看案情';
                    btn.disabled = false;
                    showAnalysis(data);
                } else {
                    btn.disabled = false;
                    btn.textContent = '案情分析';
                    alert('分析失敗: ' + (data.error || '未知錯誤'));
                }
            } catch (err) {
                btn.disabled = false;
                btn.textContent = '案情分析';
                alert('分析失敗: ' + err.message);
            }
        });
    });

    document.querySelectorAll('.analysis-view-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const caseId = btn.dataset.caseid;
            aBody.innerHTML = '<div class="modal-loading">載入中…</div>';
            aModal.classList.add('active');
            try {
                const resp = await fetch('/api/case-analysis?case_id=' + encodeURIComponent(caseId));
                const data = await resp.json();
                if (resp.ok) {
                    showAnalysis(data);
                } else {
                    aBody.textContent = data.error || '載入失敗';
                }
            } catch (err) {
                aBody.textContent = '載入失敗: ' + err.message;
            }
        });
    });

    document.addEventListener('click', async (e) => {
        const btn = e.target.closest('.analysis-view-btn');
        if (!btn || btn.dataset._bound) return;
        btn.dataset._bound = '1';
        const caseId = btn.dataset.caseid;
        aBody.innerHTML = '<div class="modal-loading">載入中…</div>';
        aModal.classList.add('active');
        try {
            const resp = await fetch('/api/case-analysis?case_id=' + encodeURIComponent(caseId));
            const data = await resp.json();
            if (resp.ok) {
                showAnalysis(data);
            } else {
                aBody.textContent = data.error || '載入失敗';
            }
        } catch (err) {
            aBody.textContent = '載入失敗: ' + err.message;
        }
    });

    aClose.addEventListener('click', () => aModal.classList.remove('active'));
    aModal.addEventListener('click', (e) => {
        if (e.target === aModal) aModal.classList.remove('active');
    });
})();

/* 案件幣流按鈕 */
document.querySelectorAll('.case-flow-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
        const caseId = btn.dataset.caseid;
        const addr = btn.dataset.addr;
        const court = btn.dataset.court || '';
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>追蹤中...';
        try {
            const resp = await fetch('/api/case-flow-report', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({case_id: caseId, address: addr, max_depth: 5}),
            });
            const data = await resp.json();
            if (!resp.ok) {
                btn.disabled = false;
                btn.textContent = '案件幣流';
                alert('啟動失敗: ' + (data.error || '未知錯誤'));
                return;
            }
            const jobId = data.job_id;
            const poll = setInterval(async () => {
                try {
                    const sr = await fetch('/api/flow-report/' + jobId);
                    const sdata = await sr.json();
                    if (sdata.status === 'done') {
                        clearInterval(poll);
                        btn.disabled = false;
                        btn.textContent = '案件幣流';
                        window.open(sdata.url, '_blank');
                    } else if (sdata.status === 'error') {
                        clearInterval(poll);
                        btn.disabled = false;
                        btn.textContent = '案件幣流';
                        alert('幣流追蹤失敗: ' + (sdata.error || '未知錯誤'));
                    }
                } catch (pe) {
                    clearInterval(poll);
                    btn.disabled = false;
                    btn.textContent = '案件幣流';
                }
            }, 3000);
        } catch (err) {
            btn.disabled = false;
            btn.textContent = '案件幣流';
            alert('啟動失敗: ' + err.message);
        }
    });
});
"""


def patch_report():
    """讀取 report.html，補上案情欄位後寫回。"""
    if not os.path.isfile(REPORT_PATH):
        print(f"[錯誤] 找不到 {REPORT_PATH}")
        sys.exit(1)

    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # ── 1. 檢查是否已 patch 過 ──
    if '<th>案情</th>' in html:
        print("[跳過] report.html 已包含「案情」欄位，無需重複 patch。")
        return

    # ── 2. 注入 CSS（在 </style> 前插入）──
    html = html.replace('</style>', ANALYSIS_CSS + '\n</style>', 1)

    # ── 3. 在 thead 加入 <th>案情</th>（在「案號」之後）──
    html = html.replace(
        '<th>案號</th>',
        '<th>案號</th>\n    <th>案情</th>',
        1
    )

    # ── 4. 解析 tbody，按 case_id 分組，插入 analysis-cell ──
    tbody_start = html.find('<tbody>')
    tbody_end = html.find('</tbody>')
    if tbody_start == -1 or tbody_end == -1:
        print("[錯誤] 找不到 <tbody>...</tbody>")
        sys.exit(1)

    tbody_content = html[tbody_start:tbody_end + len('</tbody>')]

    # 用正則找出所有 <tr>...</tr>
    tr_pattern = re.compile(r'(<tr\b[^>]*>)(.*?)(</tr>)', re.DOTALL)
    matches = list(tr_pattern.finditer(tbody_content))

    if not matches:
        print("[錯誤] tbody 中找不到 <tr>")
        sys.exit(1)

    # 掃描所有列的 case_id
    row_info = []
    for m in matches:
        tr_open = m.group(1)
        tr_body = m.group(2)

        cid_match = re.search(r'data-caseid="([^"]*)"', tr_body)
        case_id = cid_match.group(1) if cid_match else ""

        court_match = re.search(r'<div class="court">([^<]*)</div>', tr_body)
        court = court_match.group(1) if court_match else ""

        addr_match = re.search(r'data-addr="([^"]*)"', tr_open)
        if not addr_match:
            addr_match = re.search(r'data-addr="([^"]*)"', tr_body)
        addr = addr_match.group(1) if addr_match else ""

        row_info.append((case_id, court, addr))

    # 按 case_id 計算每組的行數（保持順序）
    case_counts = OrderedDict()
    for cid, _, _ in row_info:
        case_counts[cid] = case_counts.get(cid, 0) + 1

    # 查詢每個 case 是否已分析
    case_analyzed = {}
    for cid in case_counts:
        if cid:
            case_analyzed[cid] = case_analyzer.has_case_analysis(cid)
        else:
            case_analyzed[cid] = False

    # 從前往後處理，收集修改後的 tr
    case_seen = set()
    new_trs = []
    for i, m in enumerate(matches):
        tr_open = m.group(1)
        tr_body = m.group(2)
        tr_close = m.group(3)
        case_id, court, addr = row_info[i]
        is_first = case_id not in case_seen
        analyzed = case_analyzed.get(case_id, False)
        rowspan = case_counts.get(case_id, 1)

        # 構建 analysis-cell（僅首列）
        analysis_td = ""
        if is_first:
            case_seen.add(case_id)
            esc_cid = _esc(case_id)
            esc_court = _esc(court)
            if analyzed:
                analysis_td = (
                    f'<td class="analysis-cell" rowspan="{rowspan}">'
                    f'<button class="analysis-view-btn" data-caseid="{esc_cid}" data-court="{esc_court}">查看案情</button>'
                    f'</td>'
                )
            else:
                analysis_td = (
                    f'<td class="analysis-cell" rowspan="{rowspan}">'
                    f'<button class="analysis-btn" data-caseid="{esc_cid}" data-court="{esc_court}">案情分析</button>'
                    f'</td>'
                )

        # 在 case-info 的 </td> 後面插入 analysis_td
        if analysis_td:
            ci_idx = tr_body.find('case-info')
            if ci_idx != -1:
                td_end = tr_body.find('</td>', ci_idx)
                if td_end != -1:
                    insert_pos = td_end + len('</td>')
                    tr_body = tr_body[:insert_pos] + '\n                ' + analysis_td + tr_body[insert_pos:]

        # 為已分析案件的 flow-cell 添加案件幣流按鈕
        if analyzed and addr:
            flow_cell_match = re.search(r'(<td class="flow-cell">)(.*?)(</td>)', tr_body, re.DOTALL)
            if flow_cell_match:
                existing_flow = flow_cell_match.group(2)
                esc_cid = _esc(case_id)
                esc_court = _esc(court)
                esc_addr = _esc(addr)
                case_flow_btn = (
                    f' <button class="case-flow-btn" data-addr="{esc_addr}" '
                    f'data-caseid="{esc_cid}" data-court="{esc_court}">案件幣流</button>'
                )
                new_flow = existing_flow + case_flow_btn
                tr_body = (tr_body[:flow_cell_match.start(2)] +
                           new_flow +
                           tr_body[flow_cell_match.end(2):])

        new_trs.append(tr_open + tr_body + tr_close)

    # 重建 tbody
    new_tbody = '<tbody>\n'
    for tr_str in new_trs:
        new_tbody += '\n            ' + tr_str + '\n'
    new_tbody += '\n</tbody>'

    html = html[:tbody_start] + new_tbody + html[tbody_end + len('</tbody>'):]

    # ── 5. 插入 analysis modal HTML（在 judgment-modal 後面）──
    # 找 judgment-modal 的結尾 </div>\n</div>
    jm_idx = html.find('id="judgment-modal"')
    if jm_idx != -1:
        # 找到 modal-overlay 的閉合：兩層 </div>
        # 從 judgment-modal 位置往後找 </div> 兩次
        pos = jm_idx
        for _ in range(2):
            pos = html.find('</div>', pos + 1)
        if pos != -1:
            insert_pos = pos + len('</div>')
            html = html[:insert_pos] + '\n' + ANALYSIS_MODAL_HTML + html[insert_pos:]
        else:
            html = html.replace('<footer>', ANALYSIS_MODAL_HTML + '\n<footer>', 1)
    else:
        html = html.replace('<footer>', ANALYSIS_MODAL_HTML + '\n<footer>', 1)

    # ── 6. 插入 JavaScript（在最後一個 </script> 前插入）──
    last_script_end = html.rfind('</script>')
    if last_script_end != -1:
        html = html[:last_script_end] + '\n' + ANALYSIS_JS + '\n' + html[last_script_end:]

    # ── 7. 寫回 ──
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    # 統計
    total_cases = len(case_counts)
    analyzed_count = sum(1 for v in case_analyzed.values() if v)
    print(f"[完成] 已 patch {REPORT_PATH}")
    print(f"  - 共 {total_cases} 個案件，{analyzed_count} 個已分析")
    print(f"  - 已加入「案情」欄位、分析按鈕、modal、JavaScript")


if __name__ == "__main__":
    patch_report()
