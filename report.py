"""HTML 報告生成模組：整合 tron OCR verify API + MistTrack 產生互動式網頁報告。"""

import html
import os
import time
from dataclasses import dataclass, field
from datetime import datetime

import requests
from tqdm import tqdm

from case_analyzer import has_case_analysis
from extractor import ExtractedAddress
from misttrack import MistTrackClient, MistTrackResult

TRON_API_URL = "http://localhost:3000/api/v1/verify"


@dataclass
class VerifyResult:
    """單一地址的完整驗證結果。"""
    address: str
    case_id: str
    court: str
    context: str
    checksum_valid: bool
    best_match: str | None
    confidence: float
    corrections: list[dict] = field(default_factory=list)
    verified_candidates: list[dict] = field(default_factory=list)
    unverified_candidates: list[dict] = field(default_factory=list)
    misttrack: MistTrackResult | None = None
    error_msg: str = ""


def call_tron_api(address: str) -> dict | None:
    try:
        resp = requests.post(TRON_API_URL, json={"address": address}, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def verify_all(
    extracted: list[ExtractedAddress],
    misttrack_api_key: str = "",
) -> list[VerifyResult]:
    """透過 tron API 驗證所有地址，並用 MistTrack 分析資金流向。"""
    results: list[VerifyResult] = []

    # Step 1: tron OCR verify
    for item in tqdm(extracted, desc="OCR 驗證"):
        api_resp = call_tron_api(item.address)
        if api_resp and "error" not in api_resp:
            best = api_resp.get("bestMatch")
            verified = api_resp.get("verified", [])
            unverified = api_resp.get("unverified", [])
            corrections = []
            confidence = api_resp.get("overallConfidence", 0)
            for c in verified + unverified:
                if c.get("address") == best:
                    corrections = c.get("corrections", [])
                    break
            results.append(VerifyResult(
                address=item.address, case_id=item.case_id, court=item.court,
                context=item.context, checksum_valid=api_resp.get("checksumValid", False),
                best_match=best, confidence=confidence, corrections=corrections,
                verified_candidates=verified, unverified_candidates=unverified,
            ))
        else:
            err = api_resp.get("error", "Unknown") if api_resp else "API unreachable"
            results.append(VerifyResult(
                address=item.address, case_id=item.case_id, court=item.court,
                context=item.context, checksum_valid=False, best_match=None,
                confidence=0, error_msg=err,
            ))
        time.sleep(0.1)

    # Step 2: MistTrack 分析（對有效地址或修正後地址）
    if misttrack_api_key:
        mt_client = MistTrackClient(misttrack_api_key)
        # 收集需要分析的地址（去重）
        addr_to_analyze: dict[str, None] = {}
        for r in results:
            target = r.best_match if r.best_match else (r.address if r.checksum_valid else None)
            if target:
                addr_to_analyze[target] = None

        unique_addrs = list(addr_to_analyze.keys())
        print(f"\n[MistTrack] 分析 {len(unique_addrs)} 個不重複有效地址...")
        mt_cache: dict[str, MistTrackResult] = {}
        for addr in tqdm(unique_addrs, desc="MistTrack 分析"):
            mt_cache[addr] = mt_client.analyze(addr)

        # 將結果對應回去
        for r in results:
            target = r.best_match if r.best_match else (r.address if r.checksum_valid else None)
            if target and target in mt_cache:
                r.misttrack = mt_cache[target]

    return results


# --- HTML helpers ---

def _esc(text: str) -> str:
    return html.escape(text)


def _highlight_context(context: str, address: str) -> str:
    escaped_ctx = _esc(context)
    escaped_addr = _esc(address)
    return escaped_ctx.replace(
        escaped_addr,
        f'<mark class="addr-highlight">{escaped_addr}</mark>',
    )


def _corrections_html(corrections: list[dict]) -> str:
    if not corrections:
        return ""
    parts = []
    for c in corrections:
        pos = c.get("position", "?")
        frm = _esc(c.get("from", ""))
        to = _esc(c.get("to", ""))
        typ = c.get("type", "substitution")
        if typ == "substitution":
            parts.append(f'位置 {pos}: <code>{frm}</code> → <code>{to}</code>')
        elif typ == "deletion":
            parts.append(f'位置 {pos}: 刪除 <code>{frm}</code>')
        elif typ == "insertion":
            parts.append(f'位置 {pos}: 插入 <code>{to}</code>')
    return "<br>".join(parts)


def _confidence_badge(conf: float) -> str:
    cls = "badge-high" if conf >= 0.8 else ("badge-mid" if conf >= 0.5 else "badge-low")
    return f'<span class="badge {cls}">{conf:.0%}</span>'


def _risk_badge(level: str, score: int) -> str:
    cls_map = {"Low": "risk-low", "Moderate": "risk-moderate", "High": "risk-high", "Severe": "risk-severe"}
    cls = cls_map.get(level, "risk-unknown")
    label_map = {"Low": "低風險", "Moderate": "中風險", "High": "高風險", "Severe": "嚴重"}
    label = label_map.get(level, level or "未知")
    return f'<span class="risk-badge {cls}">{label} ({score})</span>'


def _ts_to_date(ts: int) -> str:
    if not ts:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _misttrack_html(mt: MistTrackResult | None) -> str:
    if not mt:
        return '<span class="text-dim">—</span>'

    parts = []

    # Risk score
    if mt.risk_score:
        parts.append(_risk_badge(mt.risk_level, mt.risk_score))

    # Labels
    if mt.label_list:
        labels = ", ".join(mt.label_list)
        parts.append(f'<div class="mt-labels">標籤: <strong>{_esc(labels)}</strong></div>')

    # Overview
    if mt.txs_count > 0:
        parts.append(
            f'<div class="mt-overview">'
            f'餘額: {mt.balance:,.2f} TRX<br>'
            f'交易: {mt.txs_count:,} 筆 '
            f'(入 {mt.received_txs_count:,} / 出 {mt.spent_txs_count:,})<br>'
            f'總收: {mt.total_received:,.2f} · 總支: {mt.total_spent:,.2f}<br>'
            f'首見: {_ts_to_date(mt.first_seen)} · 末見: {_ts_to_date(mt.last_seen)}'
            f'</div>'
        )

    # Risk details
    if mt.detail_list:
        for d in mt.detail_list:
            parts.append(f'<div class="mt-risk-flag">&#x26A0; {_esc(d)}</div>')

    if mt.risk_detail:
        for rd in mt.risk_detail[:5]:
            entity = _esc(rd.get("entity", ""))
            rtype = rd.get("risk_type", "")
            exposure = rd.get("exposure_type", "")
            vol = rd.get("volume", 0)
            pct = rd.get("percent", 0)
            hop = rd.get("hop_num", 0)
            parts.append(
                f'<div class="mt-risk-detail">'
                f'<span class="entity">{entity}</span> '
                f'<span class="rtype">{rtype}</span> '
                f'({exposure}, hop={hop})<br>'
                f'金額: ${vol:,.0f} ({pct:.1%})'
                f'</div>'
            )

    # Malicious events
    mal_parts = []
    if mt.malicious_event:
        for cat in ["phishing", "ransom", "stealing", "laundering"]:
            info = mt.malicious_event.get(cat, {})
            if info.get("count", 0) > 0:
                cat_zh = {"phishing": "釣魚", "ransom": "勒索", "stealing": "盜竊", "laundering": "洗錢"}.get(cat, cat)
                mal_parts.append(f'<span class="mal-tag mal-{cat}">&#x1F6A8; {cat_zh} ({info["count"]})</span>')
    if mal_parts:
        parts.append('<div class="mt-malicious">' + " ".join(mal_parts) + '</div>')

    # Platforms
    if mt.use_platform:
        for cat in ["exchange", "dex", "mixer"]:
            info = mt.use_platform.get(cat, {})
            if info.get("count", 0) > 0:
                cat_zh = {"exchange": "交易所", "dex": "DEX", "mixer": "混幣器"}.get(cat, cat)
                plat_list = info.get(f"{cat}_list", [])
                platforms = ", ".join(plat_list[:5]) if plat_list else f"{info['count']} 個"
                cls = "plat-mixer" if cat == "mixer" else "plat-normal"
                parts.append(f'<div class="mt-platform {cls}">{cat_zh}: {_esc(platforms)}</div>')

    # First address (fund source)
    if mt.first_address:
        parts.append(
            f'<div class="mt-source">資金來源: '
            f'<code>{_esc(mt.first_address[:20])}...</code></div>'
        )

    return "\n".join(parts) if parts else '<span class="text-dim">無資料</span>'


def _tronscan_link(address: str) -> str:
    return f'https://tronscan.org/#/address/{address}'


def generate_html(
    results: list[VerifyResult],
    output_path: str,
) -> None:
    """產生 HTML 報告。"""
    cases: dict[str, list[VerifyResult]] = {}
    for r in results:
        key = f"{r.court} {r.case_id}"
        cases.setdefault(key, []).append(r)

    total = len(results)
    valid = sum(1 for r in results if r.checksum_valid)
    invalid = total - valid
    corrected = sum(1 for r in results if not r.checksum_valid and r.best_match)
    on_chain = sum(1 for r in results if r.verified_candidates)
    has_mt = sum(1 for r in results if r.misttrack and r.misttrack.risk_score)
    high_risk = sum(1 for r in results if r.misttrack and r.misttrack.risk_level in ("High", "Severe"))
    moderate_risk = sum(1 for r in results if r.misttrack and r.misttrack.risk_level == "Moderate")
    has_malicious = sum(
        1 for r in results if r.misttrack and r.misttrack.malicious_event and
        any(r.misttrack.malicious_event.get(c, {}).get("count", 0) > 0
            for c in ["phishing", "ransom", "stealing", "laundering"])
    )

    rows_html = []
    row_idx = 0
    for case_key, items in cases.items():
        # 檢查該案件是否已分析（per-case，同案多地址只在首行顯示按鈕）
        case_analyzed = has_case_analysis(items[0].case_id) if items else False
        case_first_row = True
        case_row_count = len(items)

        for r in items:
            row_idx += 1
            if r.checksum_valid:
                status_cls, status_text = "status-valid", "有效"
            elif r.best_match:
                status_cls, status_text = "status-corrected", "已修正"
            else:
                status_cls, status_text = "status-invalid", "無效"

            correction_detail = _corrections_html(r.corrections)

            # 鏈上驗證
            chain_html = ""
            target_addr = r.best_match if r.best_match else r.address
            if r.checksum_valid or r.best_match:
                chain_html = (
                    f'<a href="{_tronscan_link(target_addr)}" target="_blank" '
                    f'class="tronscan-link">Tronscan &#x2197;</a>'
                )
            if r.verified_candidates:
                for c in r.verified_candidates:
                    info = c.get("accountInfo")
                    if info and info.get("isActive"):
                        trx = info.get("balance", 0) / 1_000_000
                        chain_html += f'<br><small>餘額: {trx:,.2f} TRX</small>'
                        break

            # 建議地址
            suggestion_html = ""
            if r.best_match and r.best_match != r.address:
                suggestion_html = (
                    f'<code class="suggested-addr">{_esc(r.best_match)}</code> '
                    f'{_confidence_badge(r.confidence)}'
                )
                if correction_detail:
                    suggestion_html += f'<div class="correction-detail">{correction_detail}</div>'
            elif r.checksum_valid:
                suggestion_html = '<span class="no-correction">—</span>'
            else:
                suggestion_html = '<span class="no-suggestion">無法修正</span>'

            # MistTrack
            mt_html = _misttrack_html(r.misttrack)

            # 判決書原文中的案情比對：如果 MistTrack 有 malicious event，用紅色邊框
            row_extra_cls = ""
            if r.misttrack and r.misttrack.malicious_event:
                for cat in ["phishing", "ransom", "stealing", "laundering"]:
                    if r.misttrack.malicious_event.get(cat, {}).get("count", 0) > 0:
                        row_extra_cls = " row-malicious"
                        break

            # 案情分析欄（per-case，首行用 rowspan）
            analysis_td = ""
            if case_first_row:
                if case_analyzed:
                    analysis_td = (
                        f'<td class="analysis-cell" rowspan="{case_row_count}">'
                        f'<button class="analysis-view-btn" data-caseid="{_esc(r.case_id)}" data-court="{_esc(r.court)}">查看案情</button>'
                        f'</td>'
                    )
                else:
                    analysis_td = (
                        f'<td class="analysis-cell" rowspan="{case_row_count}">'
                        f'<button class="analysis-btn" data-caseid="{_esc(r.case_id)}" data-court="{_esc(r.court)}">案情分析</button>'
                        f'</td>'
                    )
                case_first_row = False

            # 幣流欄：已分析案件額外顯示「案件幣流」按鈕
            flow_btns = ""
            if r.checksum_valid or r.best_match:
                flow_btns = (
                    f'<button class="flow-btn" data-addr="{_esc(target_addr)}" data-coin="USDT-TRC20" data-case="{_esc(r.case_id)}" data-court="{_esc(r.court)}">幣流探索</button> '
                    f'<button class="exchange-btn" data-addr="{_esc(target_addr)}" data-coin="USDT-TRC20" data-case="{_esc(r.case_id)}" data-court="{_esc(r.court)}">交易所報告</button>'
                )
                if case_analyzed:
                    flow_btns += (
                        f' <button class="case-flow-btn" data-addr="{_esc(target_addr)}" data-caseid="{_esc(r.case_id)}" data-court="{_esc(r.court)}">案件幣流</button>'
                    )

            rows_html.append(f"""
            <tr class="{status_cls}{row_extra_cls}" data-addr="{_esc(target_addr)}" data-caseid="{_esc(r.case_id)}" data-original="{_esc(r.address)}">
                <td class="row-num">{row_idx}</td>
                <td class="case-info">
                    <div class="court">{_esc(r.court)}</div>
                    <a class="case-id case-link" href="#" data-caseid="{_esc(r.case_id)}">{_esc(r.case_id)}</a>
                </td>
                {analysis_td}
                <td class="original-addr"><code>{_esc(r.address)}</code></td>
                <td class="context-cell">{_highlight_context(r.context, r.address)}</td>
                <td class="status-cell"><span class="status-badge {status_cls}">{status_text}</span></td>
                <td class="suggestion-cell">{suggestion_html}</td>
                <td class="chain-cell">{chain_html}</td>
                <td class="mt-cell">{mt_html}</td>
                <td class="flow-cell">{flow_btns}</td>
            </tr>""")

    rows_joined = "\n".join(rows_html)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>詐欺案判決書 TRON 地址驗證報告</title>
<style>
:root {{
    --bg: #0f1117; --surface: #1a1d27; --surface2: #232734;
    --border: #2e3347; --text: #e0e0e8; --text-dim: #888da0;
    --accent: #6c8aff; --green: #34d399; --yellow: #fbbf24;
    --red: #f87171; --orange: #fb923c; --mark-bg: rgba(108,138,255,0.18);
}}
:root.light {{
    --bg: #f0f2f5; --surface: #ffffff; --surface2: #e8ecf1;
    --border: #c5cdd8; --text: #1b2537; --text-dim: #5a6a7e;
    --accent: #2754a8; --green: #1a7f56; --yellow: #b8860b;
    --red: #b91c1c; --orange: #c05621; --mark-bg: rgba(39,84,168,0.10);
}}
:root.light .stat-card {{ box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
:root.light .table-wrap {{ box-shadow: 0 1px 4px rgba(0,0,0,0.06); }}
:root.light .modal-box {{ box-shadow: 0 8px 32px rgba(0,0,0,0.15); }}
:root.light tbody tr:hover {{ background: rgba(39,84,168,0.04); }}
:root.light .filter-btn.active {{ background: #2754a8; border-color: #2754a8; }}
@media print {{
    :root {{
        --bg: #fff; --surface: #fff; --surface2: #f5f5f5;
        --border: #bbb; --text: #000; --text-dim: #444;
        --accent: #2754a8; --green: #1a7f56; --yellow: #b8860b;
        --red: #b91c1c; --orange: #c05621; --mark-bg: rgba(39,84,168,0.08);
    }}
    .theme-toggle, .filter-bar, .flow-cell, .analysis-cell, footer {{ display: none !important; }}
    body {{ padding: 0; font-size: 11pt; }}
    .table-wrap {{ border: 1px solid #999; }}
    table {{ font-size: 9pt; }}
    .stat-card {{ border: 1px solid #999; box-shadow: none; }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6; padding: 24px;
}}
h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 8px; }}
.subtitle {{ color: var(--text-dim); font-size: 0.9rem; margin-bottom: 24px; }}
.stats {{ display: flex; gap: 12px; margin-bottom: 24px; flex-wrap: wrap; }}
.stat-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 20px; min-width: 120px;
}}
.stat-card .label {{ font-size: 0.72rem; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; }}
.stat-card .value {{ font-size: 1.6rem; font-weight: 700; margin-top: 2px; }}
.stat-card .value.green {{ color: var(--green); }}
.stat-card .value.yellow {{ color: var(--yellow); }}
.stat-card .value.red {{ color: var(--red); }}
.stat-card .value.accent {{ color: var(--accent); }}
.stat-card .value.orange {{ color: var(--orange); }}

.filter-bar {{ margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
.filter-bar label {{ color: var(--text-dim); font-size: 0.85rem; }}
.filter-btn {{
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.82rem; transition: all 0.15s;
}}
.filter-btn:hover {{ border-color: var(--accent); }}
.filter-btn.active {{ background: var(--accent); border-color: var(--accent); color: #fff; }}
input[type="search"] {{
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 6px 14px; border-radius: 6px; font-size: 0.85rem; width: 240px;
}}
input[type="search"]::placeholder {{ color: var(--text-dim); }}

.table-wrap {{ overflow-x: auto; border-radius: 10px; border: 1px solid var(--border); }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
thead th {{
    background: var(--surface2); padding: 10px 12px; text-align: left; font-weight: 600;
    color: var(--text-dim); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px;
    position: sticky; top: 0; z-index: 1; border-bottom: 1px solid var(--border);
}}
tbody tr {{ border-bottom: 1px solid var(--border); transition: background 0.1s; }}
tbody tr:hover {{ background: rgba(108,138,255,0.05); }}
tbody tr.row-malicious {{ border-left: 3px solid var(--red); }}
td {{ padding: 8px 12px; vertical-align: top; }}
.row-num {{ color: var(--text-dim); font-size: 0.75rem; text-align: center; width: 32px; }}
.case-info .court {{ font-size: 0.72rem; color: var(--text-dim); }}
.case-info .case-id {{ font-size: 0.78rem; font-weight: 500; }}
.case-link {{ color: var(--accent); text-decoration: none; cursor: pointer; display: block; }}
.case-link:hover {{ text-decoration: underline; }}

/* Judgment modal */
.modal-overlay {{
    display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.7);
    z-index: 1000; align-items: center; justify-content: center;
}}
.modal-overlay.active {{ display: flex; }}
.modal-box {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    width: 90vw; max-width: 900px; max-height: 85vh; display: flex; flex-direction: column;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}}
.modal-header {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px 20px; border-bottom: 1px solid var(--border);
}}
.modal-header h3 {{ font-size: 0.95rem; font-weight: 600; color: var(--text); }}
.modal-close {{
    background: none; border: none; color: var(--text-dim); font-size: 1.4rem;
    cursor: pointer; padding: 4px 8px; border-radius: 4px;
}}
.modal-close:hover {{ background: var(--surface2); color: var(--text); }}
.modal-body {{
    padding: 20px; overflow-y: auto; flex: 1;
    font-size: 0.82rem; line-height: 1.8; color: var(--text); white-space: pre-wrap; word-break: break-all;
}}
.modal-loading {{ text-align: center; padding: 40px; color: var(--text-dim); }}
code {{
    font-family: "SF Mono", "Fira Code", "JetBrains Mono", monospace;
    font-size: 0.75rem; background: var(--surface2); padding: 2px 4px; border-radius: 3px; word-break: break-all;
}}
.context-cell {{ font-size: 0.75rem; color: var(--text-dim); max-width: 280px; line-height: 1.5; }}
mark.addr-highlight {{ background: var(--mark-bg); color: var(--accent); padding: 1px 3px; border-radius: 3px; font-weight: 600; }}
.status-badge {{ display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.72rem; font-weight: 600; }}
.status-badge.status-valid {{ background: rgba(52,211,153,0.15); color: var(--green); }}
.status-badge.status-corrected {{ background: rgba(251,191,36,0.15); color: var(--yellow); }}
.status-badge.status-invalid {{ background: rgba(248,113,113,0.15); color: var(--red); }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.68rem; font-weight: 600; }}
.badge-high {{ background: rgba(52,211,153,0.15); color: var(--green); }}
.badge-mid {{ background: rgba(251,191,36,0.15); color: var(--yellow); }}
.badge-low {{ background: rgba(248,113,113,0.15); color: var(--red); }}
.suggested-addr {{ color: var(--green); background: rgba(52,211,153,0.08); }}
.correction-detail {{ margin-top: 4px; font-size: 0.7rem; color: var(--text-dim); }}
.correction-detail code {{ color: var(--orange); background: rgba(251,146,60,0.1); }}
.no-correction {{ color: var(--text-dim); }}
.no-suggestion {{ color: var(--red); font-size: 0.75rem; }}
.tronscan-link {{ color: var(--accent); text-decoration: none; font-size: 0.75rem; }}
.tronscan-link:hover {{ text-decoration: underline; }}
.chain-cell {{ font-size: 0.75rem; }}
.chain-cell small {{ color: var(--text-dim); }}

/* MistTrack column */
.mt-cell {{ font-size: 0.75rem; min-width: 260px; max-width: 360px; }}
.risk-badge {{
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600; margin-bottom: 6px;
}}
.risk-low {{ background: rgba(52,211,153,0.15); color: var(--green); }}
.risk-moderate {{ background: rgba(251,191,36,0.15); color: var(--yellow); }}
.risk-high {{ background: rgba(248,113,113,0.2); color: var(--red); }}
.risk-severe {{ background: rgba(248,113,113,0.35); color: #fff; }}
.risk-unknown {{ background: var(--surface2); color: var(--text-dim); }}

.mt-labels {{ margin: 4px 0; }}
.mt-overview {{ margin: 6px 0; padding: 6px 8px; background: var(--surface); border-radius: 6px; font-size: 0.72rem; color: var(--text-dim); line-height: 1.6; }}
.mt-risk-flag {{ color: var(--orange); margin: 3px 0; font-weight: 500; }}
.mt-risk-detail {{
    margin: 4px 0; padding: 4px 8px; background: rgba(248,113,113,0.06);
    border-radius: 4px; font-size: 0.7rem; border-left: 2px solid var(--red);
}}
.mt-risk-detail .entity {{ font-weight: 600; color: var(--red); }}
.mt-risk-detail .rtype {{ color: var(--text-dim); font-size: 0.68rem; }}

.mal-tag {{
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    font-size: 0.68rem; font-weight: 600; margin: 2px 2px;
}}
.mal-phishing {{ background: rgba(251,146,60,0.15); color: var(--orange); }}
.mal-ransom {{ background: rgba(248,113,113,0.2); color: var(--red); }}
.mal-stealing {{ background: rgba(248,113,113,0.2); color: var(--red); }}
.mal-laundering {{ background: rgba(168,85,247,0.15); color: #a855f7; }}
.mt-malicious {{ margin: 6px 0; }}
.mt-platform {{ margin: 3px 0; font-size: 0.72rem; }}
.plat-mixer {{ color: var(--red); font-weight: 600; }}
.plat-normal {{ color: var(--text-dim); }}
.mt-source {{ margin-top: 4px; font-size: 0.7rem; color: var(--text-dim); }}
.text-dim {{ color: var(--text-dim); }}

/* Theme toggle */
.theme-toggle {{
    background: var(--surface2); border: 1px solid var(--border); color: var(--text-dim);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    transition: all 0.15s;
}}
.theme-toggle:hover {{ color: var(--text); border-color: var(--accent); }}

/* Case analysis button */
.analysis-cell {{ text-align: center; vertical-align: middle; }}
.analysis-btn {{
    background: var(--surface); border: 1px solid var(--accent); color: var(--accent);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap;
}}
.analysis-btn:hover {{ background: rgba(108,138,255,0.1); }}
.analysis-btn:disabled {{ cursor: not-allowed; opacity: 0.6; }}
.analysis-view-btn {{
    background: rgba(52,211,153,0.1); border: 1px solid var(--green); color: var(--green);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap;
}}
.analysis-view-btn:hover {{ background: rgba(52,211,153,0.2); }}
.case-flow-btn {{
    background: var(--surface); border: 1px solid #a855f7; color: #a855f7;
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap; margin-top: 4px;
    display: inline-block;
}}
.case-flow-btn:hover {{ background: rgba(168,85,247,0.1); }}

/* Case analysis modal */
.analysis-modal .modal-box {{ max-width: 1000px; }}
.analysis-section {{ margin-bottom: 16px; }}
.analysis-section h4 {{ font-size: 0.85rem; color: var(--accent); margin-bottom: 8px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }}
.analysis-table {{ width: 100%; border-collapse: collapse; font-size: 0.8rem; margin-bottom: 12px; }}
.analysis-table th {{ background: var(--surface2); padding: 6px 10px; text-align: left; color: var(--text-dim); font-weight: 600; font-size: 0.72rem; }}
.analysis-table td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); }}
.role-victim {{ color: var(--orange); font-weight: 600; }}
.role-suspect {{ color: var(--red); font-weight: 600; }}
.role-unknown {{ color: var(--text-dim); }}
.analysis-desc {{ font-size: 0.82rem; line-height: 1.8; color: var(--text); padding: 12px; background: var(--surface); border-radius: 8px; }}
.case-exchange-btn {{
    background: var(--orange); border: none; color: #fff; padding: 10px 24px;
    border-radius: 8px; cursor: pointer; font-size: 0.88rem; font-weight: 600;
    transition: all 0.15s;
}}
.case-exchange-btn:hover {{ filter: brightness(1.15); }}

/* Flow report button */
.flow-cell {{ text-align: center; white-space: nowrap; }}
.flow-btn {{
    background: var(--surface); border: 1px solid var(--border); color: var(--accent);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap;
}}
.flow-btn:hover {{ border-color: var(--accent); background: rgba(108,138,255,0.1); }}
.flow-btn:disabled {{ cursor: not-allowed; opacity: 0.6; }}
.exchange-btn {{
    background: var(--surface); border: 1px solid var(--orange); color: var(--orange);
    padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 0.78rem;
    font-weight: 500; transition: all 0.15s; white-space: nowrap; margin-top: 4px;
    display: inline-block;
}}
.exchange-btn:hover {{ background: rgba(251,146,60,0.1); }}
.flow-btn .spinner {{
    display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%;
    animation: spin 0.6s linear infinite; vertical-align: middle; margin-right: 4px;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
.flow-error {{
    color: var(--red); font-size: 0.7rem; margin-top: 4px; max-width: 120px; word-break: break-word;
}}

footer {{ margin-top: 32px; text-align: center; color: var(--text-dim); font-size: 0.75rem; }}
</style>
</head>
<body>

<div style="display:flex; align-items:center; gap:16px; flex-wrap:wrap;">
<h1>詐欺案判決書 TRON 地址驗證報告</h1>
<button class="theme-toggle" onclick="toggleTheme()">淺色模式</button>
</div>
<p class="subtitle">資料來源：司法院裁判書查詢系統 · 驗證：tron-ocr-verify + TronGrid · 風險分析：MistTrack</p>

<div class="stats">
    <div class="stat-card"><div class="label">地址總數</div><div class="value accent">{total}</div></div>
    <div class="stat-card"><div class="label">格式有效</div><div class="value green">{valid}</div></div>
    <div class="stat-card"><div class="label">格式無效</div><div class="value red">{invalid}</div></div>
    <div class="stat-card"><div class="label">成功修正</div><div class="value yellow">{corrected}</div></div>
    <div class="stat-card"><div class="label">鏈上驗證</div><div class="value green">{on_chain}</div></div>
    <div class="stat-card"><div class="label">案件數</div><div class="value accent">{len(cases)}</div></div>
    <div class="stat-card"><div class="label">風險分析</div><div class="value accent">{has_mt}</div></div>
    <div class="stat-card"><div class="label">中風險</div><div class="value yellow">{moderate_risk}</div></div>
    <div class="stat-card"><div class="label">高風險</div><div class="value red">{high_risk}</div></div>
    <div class="stat-card"><div class="label">涉及惡意活動</div><div class="value orange">{has_malicious}</div></div>
</div>

<div class="filter-bar">
    <label>篩選：</label>
    <button class="filter-btn active" data-filter="all">全部</button>
    <button class="filter-btn" data-filter="valid">有效</button>
    <button class="filter-btn" data-filter="corrected">已修正</button>
    <button class="filter-btn" data-filter="invalid">無效</button>
    <button class="filter-btn" data-filter="malicious">涉及惡意</button>
    <input type="search" id="search-input" placeholder="搜尋案號、地址、風險...">
    <a href="/explorer" class="filter-btn" style="margin-left:auto; text-decoration:none; color:var(--accent); border-color:var(--accent);">幣流探索器</a>
    <a href="/exchange-report" class="filter-btn" style="text-decoration:none; color:var(--orange); border-color:var(--orange);">交易所調閱報告</a>
</div>

<div class="table-wrap">
<table id="main-table">
<thead>
<tr>
    <th>#</th>
    <th>案號</th>
    <th>案情</th>
    <th>原始地址</th>
    <th>判決書原文</th>
    <th>狀態</th>
    <th>修正建議</th>
    <th>鏈上</th>
    <th>MistTrack 風險分析</th>
    <th>幣流</th>
</tr>
</thead>
<tbody>
{rows_joined}
</tbody>
</table>
</div>

<div class="modal-overlay" id="judgment-modal">
    <div class="modal-box">
        <div class="modal-header">
            <h3 id="modal-title"></h3>
            <button class="modal-close" id="modal-close">&times;</button>
        </div>
        <div class="modal-body" id="modal-body"></div>
    </div>
</div>

<div class="modal-overlay analysis-modal" id="analysis-modal">
    <div class="modal-box">
        <div class="modal-header">
            <h3 id="analysis-modal-title">案情分析</h3>
            <button class="modal-close" id="analysis-modal-close">&times;</button>
        </div>
        <div class="modal-body" id="analysis-modal-body"></div>
    </div>
</div>

<footer>Generated by crypto-acc-chk · TRON OCR Verify · MistTrack AML</footer>

<script>
/* Judgment modal */
(function() {{
    const modal = document.getElementById('judgment-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const modalClose = document.getElementById('modal-close');
    const cache = {{}};

    document.querySelectorAll('.case-link').forEach(link => {{
        link.addEventListener('click', async (e) => {{
            e.preventDefault();
            const caseId = link.dataset.caseid;
            modalTitle.textContent = caseId;
            modal.classList.add('active');

            if (cache[caseId]) {{
                modalBody.textContent = cache[caseId];
                return;
            }}
            modalBody.innerHTML = '<div class="modal-loading">載入中…</div>';
            try {{
                const resp = await fetch('/api/judgment?case_id=' + encodeURIComponent(caseId));
                const data = await resp.json();
                if (resp.ok && data.text) {{
                    cache[caseId] = data.text;
                    modalBody.textContent = data.text;
                }} else {{
                    modalBody.textContent = data.error || '無法載入判決書內容';
                }}
            }} catch (err) {{
                modalBody.textContent = '載入失敗: ' + err.message;
            }}
        }});
    }});

    modalClose.addEventListener('click', () => modal.classList.remove('active'));
    modal.addEventListener('click', (e) => {{
        if (e.target === modal) modal.classList.remove('active');
    }});
    document.addEventListener('keydown', (e) => {{
        if (e.key === 'Escape') modal.classList.remove('active');
    }});
}})();

document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const f = btn.dataset.filter;
        document.querySelectorAll('#main-table tbody tr').forEach(tr => {{
            if (f === 'all') {{ tr.style.display = ''; return; }}
            if (f === 'malicious') {{ tr.style.display = tr.classList.contains('row-malicious') ? '' : 'none'; return; }}
            tr.style.display = tr.classList.contains('status-' + f) ? '' : 'none';
        }});
    }});
}});
document.getElementById('search-input').addEventListener('input', e => {{
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('#main-table tbody tr').forEach(tr => {{
        tr.style.display = tr.textContent.toLowerCase().includes(q) ? '' : 'none';
    }});
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('[data-filter="all"]').classList.add('active');
}});

/* Flow report button — open explorer with address pre-filled */
document.querySelectorAll('.flow-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        const addr = btn.dataset.addr;
        const coin = btn.dataset.coin || 'USDT-TRC20';
        window.open('/explorer?address=' + encodeURIComponent(addr) + '&coin=' + encodeURIComponent(coin), '_blank');
    }});
}});

/* Exchange report button — open exchange report page with case data pre-filled */
document.querySelectorAll('.exchange-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
        const addr = btn.dataset.addr;
        const coin = btn.dataset.coin || 'USDT-TRC20';
        const caseId = btn.dataset.case || '';
        const court = btn.dataset.court || '';
        const params = new URLSearchParams({{
            address: addr,
            'case-number': caseId,
            agency: court,
        }});
        window.open('/exchange-report?' + params.toString(), '_blank');
    }});
}});

/* 案情分析 modal — 使用單一事件委派處理所有按鈕 */
(function() {{
    const aModal = document.getElementById('analysis-modal');
    const aTitle = document.getElementById('analysis-modal-title');
    const aBody = document.getElementById('analysis-modal-body');
    const aClose = document.getElementById('analysis-modal-close');

    function renderAnalysis(data) {{
        let html = '';
        // 案件基本資訊（僅案號、案由）
        html += '<div class="analysis-section"><h4>案件基本資訊</h4>';
        html += '<table class="analysis-table"><tbody>';
        html += '<tr><td style="width:80px;color:var(--text-dim)">案號</td><td>' + (data.case_id || '—') + '</td></tr>';
        html += '<tr><td style="color:var(--text-dim)">案由</td><td>' + (data.case_type || '—') + '</td></tr>';
        if (data.defendants && data.defendants.length) {{
            const names = data.defendants.map(d => d.name).join('、');
            html += '<tr><td style="color:var(--text-dim)">被告</td><td>' + names + '</td></tr>';
        }}
        if (data.crime_start_date || data.crime_end_date) {{
            let dateStr = '';
            if (data.crime_start_date && data.crime_end_date) {{
                dateStr = data.crime_start_date + ' ~ ' + data.crime_end_date;
            }} else {{
                dateStr = data.crime_start_date || data.crime_end_date;
            }}
            html += '<tr><td style="color:var(--text-dim)">犯罪時間</td><td>' + dateStr + '</td></tr>';
        }}
        html += '</tbody></table></div>';

        // 嫌犯錢包
        const suspectWallets = (data.wallets || []).filter(w => w.role === 'suspect');
        if (suspectWallets.length) {{
            html += '<div class="analysis-section"><h4>嫌犯錢包</h4>';
            html += '<table class="analysis-table"><thead><tr><th>地址</th><th>持有人</th><th>說明</th></tr></thead><tbody>';
            suspectWallets.forEach(w => {{
                html += '<tr><td><code style="font-size:0.7rem">' + w.address + '</code></td>';
                html += '<td class="role-suspect">' + (w.owner_name || '—') + '</td>';
                html += '<td>' + (w.label || '—') + '</td></tr>';
            }});
            html += '</tbody></table></div>';
        }}

        // 被害人錢包
        const victimWallets = (data.wallets || []).filter(w => w.role === 'victim');
        if (victimWallets.length) {{
            html += '<div class="analysis-section"><h4>被害人錢包</h4>';
            html += '<table class="analysis-table"><thead><tr><th>地址</th><th>持有人</th><th>說明</th></tr></thead><tbody>';
            victimWallets.forEach(w => {{
                html += '<tr><td><code style="font-size:0.7rem">' + w.address + '</code></td>';
                html += '<td class="role-victim">' + (w.owner_name || '—') + '</td>';
                html += '<td>' + (w.label || '—') + '</td></tr>';
            }});
            html += '</tbody></table></div>';
        }}

        // 未確認角色錢包
        const unknownWallets = (data.wallets || []).filter(w => w.role !== 'suspect' && w.role !== 'victim');
        if (unknownWallets.length) {{
            html += '<div class="analysis-section"><h4>其他相關錢包</h4>';
            html += '<table class="analysis-table"><thead><tr><th>地址</th><th>持有人</th><th>說明</th></tr></thead><tbody>';
            unknownWallets.forEach(w => {{
                html += '<tr><td><code style="font-size:0.7rem">' + w.address + '</code></td>';
                html += '<td>' + (w.owner_name || '—') + '</td>';
                html += '<td>' + (w.label || '—') + '</td></tr>';
            }});
            html += '</tbody></table></div>';
        }}

        // 交易紀錄
        if (data.transactions && data.transactions.length) {{
            html += '<div class="analysis-section"><h4>涉案交易紀錄</h4>';
            html += '<table class="analysis-table"><thead><tr><th>金額</th><th>幣種</th><th>時間</th><th>描述</th></tr></thead><tbody>';
            data.transactions.forEach(tx => {{
                html += '<tr><td>' + (tx.amount || '—') + '</td>';
                html += '<td>' + (tx.currency || '—') + '</td>';
                html += '<td>' + (tx.date || '—') + '</td>';
                html += '<td>' + (tx.description || '') + '</td></tr>';
            }});
            html += '</tbody></table></div>';
        }}

        // 案件摘要
        if (data.description) {{
            html += '<div class="analysis-section"><h4>案件摘要</h4>';
            html += '<div class="analysis-desc">' + data.description + '</div></div>';
        }}

        // 產生調閱報告按鈕（帶入所有涉案錢包）
        const allAddrs = (data.wallets || []).map(w => w.address);
        if (allAddrs.length) {{
            html += '<div class="analysis-section" style="margin-top:16px; text-align:center;">';
            html += '<button class="case-exchange-btn" data-addresses=\'' + JSON.stringify(allAddrs) + '\' ';
            html += 'data-caseid="' + (data.case_id || '') + '" ';
            html += 'data-court="' + (data.court || '') + '" ';
            html += 'data-casetype="' + (data.case_type || '詐欺') + '" ';
            html += 'data-crimestart="' + (data.crime_start_date || '') + '" ';
            html += 'data-crimeend="' + (data.crime_end_date || '') + '" ';
            html += 'data-description="' + (data.description || '').replace(/"/g, '&quot;') + '">';
            html += '產生交易所調閱報告（' + allAddrs.length + ' 個涉案錢包）</button>';
            html += '</div>';
        }}
        return html;
    }}

    function showAnalysis(data) {{
        aTitle.textContent = '案情分析 — ' + (data.case_id || '');
        aBody.innerHTML = renderAnalysis(data);
        aModal.classList.add('active');
    }}

    async function loadAndShow(caseId) {{
        aBody.innerHTML = '<div class="modal-loading">載入中…</div>';
        aModal.classList.add('active');
        try {{
            const resp = await fetch('/api/case-analysis?case_id=' + encodeURIComponent(caseId));
            const data = await resp.json();
            if (resp.ok) {{ showAnalysis(data); }}
            else {{ aBody.textContent = data.error || '載入失敗'; }}
        }} catch (err) {{ aBody.textContent = '載入失敗: ' + err.message; }}
    }}

    // 從表格收集某案件的修正地址對應：{原始地址: 修正後地址}
    function collectCorrectedAddrs(caseId) {{
        const corrections = {{}};
        document.querySelectorAll('#main-table tbody tr[data-caseid]').forEach(tr => {{
            if (tr.dataset.caseid === caseId) {{
                const corrected = tr.dataset.addr || '';
                const original = tr.dataset.original || '';
                if (corrected && original && corrected !== original) {{
                    corrections[original] = corrected;
                }}
                // 即使沒修正，也收集有效地址
                if (corrected) {{
                    corrections[corrected] = corrected;
                }}
            }}
        }});
        return corrections;
    }}

    // 單一事件委派：處理「案情分析」和「查看案情」按鈕
    document.addEventListener('click', async (e) => {{
        // 「案情分析」按鈕 — 觸發分析
        const analyzeBtn = e.target.closest('.analysis-btn');
        if (analyzeBtn) {{
            e.stopPropagation();
            const caseId = analyzeBtn.dataset.caseid;
            const court = analyzeBtn.dataset.court || '';
            const corrections = collectCorrectedAddrs(caseId);
            analyzeBtn.disabled = true;
            analyzeBtn.innerHTML = '<span class="spinner"></span>分析中...';
            try {{
                const resp = await fetch('/api/case-analysis', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{case_id: caseId, court: court, address_corrections: corrections}}),
                }});
                const data = await resp.json();
                if (resp.ok) {{
                    analyzeBtn.className = 'analysis-view-btn';
                    analyzeBtn.innerHTML = '查看案情';
                    analyzeBtn.disabled = false;
                    showAnalysis(data);
                }} else {{
                    analyzeBtn.disabled = false;
                    analyzeBtn.textContent = '案情分析';
                    alert('分析失敗: ' + (data.error || '未知錯誤'));
                }}
            }} catch (err) {{
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = '案情分析';
                alert('分析失敗: ' + err.message);
            }}
            return;
        }}

        // 「查看案情」按鈕 — 載入已分析結果
        const viewBtn = e.target.closest('.analysis-view-btn');
        if (viewBtn) {{
            e.stopPropagation();
            loadAndShow(viewBtn.dataset.caseid);
            return;
        }}
    }});

    aClose.addEventListener('click', () => aModal.classList.remove('active'));
    aModal.addEventListener('click', (e) => {{
        if (e.target === aModal) aModal.classList.remove('active');
    }});
}})();

/* 案件幣流按鈕 */
document.addEventListener('click', async (e) => {{
    const btn = e.target.closest('.case-flow-btn');
    if (!btn) return;
    const caseId = btn.dataset.caseid;
    const addr = btn.dataset.addr;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>追蹤中...';
    try {{
        const resp = await fetch('/api/case-flow-report', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{case_id: caseId, address: addr, max_depth: 5}}),
        }});
        const data = await resp.json();
        if (!resp.ok) {{
            btn.disabled = false;
            btn.textContent = '案件幣流';
            alert('啟動失敗: ' + (data.error || '未知錯誤'));
            return;
        }}
        const jobId = data.job_id;
        const poll = setInterval(async () => {{
            try {{
                const sr = await fetch('/api/flow-report/' + jobId);
                const sdata = await sr.json();
                if (sdata.status === 'done') {{
                    clearInterval(poll);
                    btn.disabled = false;
                    btn.textContent = '案件幣流';
                    window.open(sdata.url, '_blank');
                }} else if (sdata.status === 'error') {{
                    clearInterval(poll);
                    btn.disabled = false;
                    btn.textContent = '案件幣流';
                    alert('幣流追蹤失敗: ' + (sdata.error || '未知錯誤'));
                }}
            }} catch (pe) {{
                clearInterval(poll);
                btn.disabled = false;
                btn.textContent = '案件幣流';
            }}
        }}, 3000);
    }} catch (err) {{
        btn.disabled = false;
        btn.textContent = '案件幣流';
        alert('啟動失敗: ' + err.message);
    }}
}});

/* 案情分析 modal 內的「產生交易所調閱報告」按鈕 */
document.addEventListener('click', (e) => {{
    const btn = e.target.closest('.case-exchange-btn');
    if (!btn) return;
    const addresses = JSON.parse(btn.dataset.addresses || '[]');
    const caseId = btn.dataset.caseid || '';
    const court = btn.dataset.court || '';
    const caseType = btn.dataset.casetype || '詐欺';
    const description = btn.dataset.description || '';
    const crimeStart = btn.dataset.crimestart || '';
    const crimeEnd = btn.dataset.crimeend || '';
    // 組裝 URL 參數，多個地址用逗號分隔
    const params = new URLSearchParams({{
        addresses: addresses.join(','),
        'case-number': caseId,
        agency: court,
        'case-type': caseType,
        description: description,
    }});
    if (crimeStart) params.set('start-date', crimeStart);
    if (crimeEnd) params.set('end-date', crimeEnd);
    window.open('/exchange-report?' + params.toString(), '_blank');
}});

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

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
