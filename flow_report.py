"""警用格式虛擬通貨幣流分析報告 HTML 生成器。"""

import html
import os
from datetime import datetime

from flow_tracer import FlowGraph, FlowNode, FlowEdge, CaseInfo, LAYER_LETTERS
from templates.disclaimer import DISCLAIMER_TEXT
from templates.glossary import GLOSSARY_ITEMS


def _esc(text: str) -> str:
    return html.escape(str(text))


def _short_addr(address: str) -> str:
    """截短地址顯示：前 6 + ... + 後 6。"""
    if len(address) <= 16:
        return address
    return f"{address[:6]}...{address[-6:]}"


def _ts_to_str(ts: int) -> str:
    """Unix timestamp 轉中文日期。"""
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _ts_to_date(ts: int) -> str:
    if not ts:
        return "未知"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def _format_amount(amount: float, token: str = "USDT") -> str:
    """格式化金額。"""
    if amount == 0:
        return f"0 {token}"
    if amount >= 1:
        return f"{amount:,.2f} {token}"
    return f"{amount:.6f} {token}"


def _tronscan_addr_link(address: str) -> str:
    return f"https://tronscan.org/#/address/{address}"


def _tronscan_tx_link(tx_hash: str) -> str:
    return f"https://tronscan.org/#/transaction/{tx_hash}"


# --- SVG 幣流分析圖 ---

def _generate_flow_svg(graph: FlowGraph) -> str:
    """產生幣流分析圖 SVG — 左到右分層排列。"""
    if not graph.nodes:
        return '<svg width="400" height="100"><text x="50" y="50">無資料</text></svg>'

    # 計算佈局
    layer_keys = sorted(graph.layers.keys())
    max_nodes_per_layer = max(len(graph.layers[k]) for k in layer_keys) if layer_keys else 1

    node_w = 200
    node_h = 60
    h_gap = 100
    v_gap = 30

    svg_w = len(layer_keys) * (node_w + h_gap) + h_gap
    svg_h = max(max_nodes_per_layer * (node_h + v_gap) + v_gap + 40, 200)

    # 計算每個節點位置
    positions: dict[str, tuple[float, float]] = {}
    for li, layer_idx in enumerate(layer_keys):
        addrs = graph.layers[layer_idx]
        layer_height = len(addrs) * (node_h + v_gap) - v_gap
        start_y = (svg_h - layer_height) / 2
        x = h_gap + li * (node_w + h_gap)
        for ni, addr in enumerate(addrs):
            y = start_y + ni * (node_h + v_gap)
            positions[addr] = (x, y)

    # 開始繪製 SVG
    parts = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{svg_w}" height="{svg_h}" '
        f'viewBox="0 0 {svg_w} {svg_h}" '
        f'style="font-family: \'Noto Sans TC\', sans-serif; background: #fff;">'
    )

    # 定義箭頭 marker
    parts.append("""
    <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill="#555" />
        </marker>
    </defs>
    """)

    # 繪製邊（箭頭 + 金額）
    for edge in graph.edges:
        if edge.from_address not in positions or edge.to_address not in positions:
            continue
        x1, y1 = positions[edge.from_address]
        x2, y2 = positions[edge.to_address]
        # 從右側中點到左側中點
        sx = x1 + node_w
        sy = y1 + node_h / 2
        ex = x2
        ey = y2 + node_h / 2

        # 金額標示
        mid_x = (sx + ex) / 2
        mid_y = (sy + ey) / 2 - 8

        amount_text = _format_amount(edge.amount, edge.token)

        parts.append(
            f'<line x1="{sx}" y1="{sy}" x2="{ex - 5}" y2="{ey}" '
            f'stroke="#888" stroke-width="1.5" marker-end="url(#arrowhead)" />'
        )
        parts.append(
            f'<text x="{mid_x}" y="{mid_y}" text-anchor="middle" '
            f'font-size="9" fill="#666">{_esc(amount_text)}</text>'
        )

    # 繪製節點
    for addr, node in graph.nodes.items():
        if addr not in positions:
            continue
        x, y = positions[addr]

        # 節點顏色
        if node.is_exchange:
            fill = "#FFF3E0"
            stroke = "#FF9800"
        elif node.layer == 0:
            fill = "#E3F2FD"
            stroke = "#1976D2"
        else:
            fill = "#F5F5F5"
            stroke = "#9E9E9E"

        # 圓角矩形
        parts.append(
            f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" '
            f'rx="8" ry="8" fill="{fill}" stroke="{stroke}" stroke-width="1.5" />'
        )

        # Alias（粗體）
        parts.append(
            f'<text x="{x + 10}" y="{y + 18}" font-size="13" font-weight="bold" fill="#333">'
            f'{_esc(node.alias)}</text>'
        )

        # 截短地址
        parts.append(
            f'<text x="{x + 10}" y="{y + 34}" font-size="9" fill="#666" '
            f'font-family="monospace">{_esc(_short_addr(addr))}</text>'
        )

        # 標籤
        label_text = ", ".join(node.labels[:2]) if node.labels else ""
        if label_text:
            parts.append(
                f'<text x="{x + 10}" y="{y + 50}" font-size="9" fill="{stroke}" '
                f'font-weight="500">{_esc(label_text)}</text>'
            )

    parts.append('</svg>')
    return "\n".join(parts)


# --- 分析敘述自動生成 ---

def _generate_narrative(graph: FlowGraph) -> str:
    """依拓撲順序走訪 FlowGraph 的 edges，生成中文分析敘述。"""
    if not graph.edges:
        return "本案未追蹤到任何交易紀錄。"

    paragraphs = []

    # 按 from_address 的 layer 排序，同 layer 按 timestamp
    sorted_edges = sorted(graph.edges, key=lambda e: (
        graph.nodes.get(e.from_address, FlowNode("", 0, "")).layer,
        e.timestamp,
    ))

    # 按 from_address 分組
    from_groups: dict[str, list[FlowEdge]] = {}
    for edge in sorted_edges:
        from_groups.setdefault(edge.from_address, []).append(edge)

    for from_addr, edges in from_groups.items():
        from_node = graph.nodes.get(from_addr)
        if not from_node:
            continue

        for edge in edges:
            to_node = graph.nodes.get(edge.to_address)
            if not to_node:
                continue

            date_str = _ts_to_str(edge.timestamp) if edge.timestamp else "未知時間"
            amount_str = _format_amount(edge.amount, edge.token)

            line = (
                f"經分析，地址 {from_node.alias}（{_short_addr(from_addr)}）"
                f"於 {date_str} 將 {amount_str} 轉出至"
                f"地址 {to_node.alias}（{_short_addr(edge.to_address)}）"
            )

            if edge.tx_hash:
                line += f"，交易序號為 {edge.tx_hash[:16]}..."

            if to_node.is_exchange:
                exchange_name = ", ".join(to_node.labels) if to_node.labels else "交易所"
                line += f"。地址 {to_node.alias} 經查為{exchange_name}之地址"

            line += "。"
            paragraphs.append(line)

    return "\n\n".join(paragraphs)


# --- 結論及建議自動生成 ---

def _generate_conclusion(graph: FlowGraph) -> str:
    """根據追蹤結果生成結論及建議事項。"""
    parts = []

    # 資金流向摘要
    exchange_nodes = [n for n in graph.nodes.values() if n.is_exchange]
    non_exchange = [n for n in graph.nodes.values() if not n.is_exchange and n.layer > 0]

    total_amount = sum(e.amount for e in graph.edges)
    parts.append(
        f"本案追蹤起始地址（{_short_addr(graph.source_address)}）之資金流向，"
        f"共發現 {len(graph.nodes)} 個相關地址、{len(graph.edges)} 筆交易，"
        f"涉及金額共計約 {_format_amount(total_amount, graph.coin_type.split('-')[0])}。"
    )

    if exchange_nodes:
        # 收集交易所名稱
        exchange_names: dict[str, list[str]] = {}  # name -> [alias]
        for node in exchange_nodes:
            name = ", ".join(node.labels) if node.labels else "未知交易所"
            exchange_names.setdefault(name, []).append(node.alias)

        parts.append("")
        parts.append("資金最終流入以下虛擬通貨交易所：")
        parts.append("")

        for name, aliases in exchange_names.items():
            alias_str = "、".join(aliases)
            parts.append(f"  ● {name}（地址 {alias_str}）")

        parts.append("")
        parts.append("建議事項：")
        parts.append("")

        for i, (name, aliases) in enumerate(exchange_names.items(), 1):
            parts.append(
                f"  {i}. 建議向{name}調閱上述地址之註冊帳戶資料（含 KYC 身分資訊）"
                f"及相關交易紀錄，以釐清資金實際受益人身分。"
            )

    if non_exchange:
        parts.append("")
        parts.append(
            f"另有 {len(non_exchange)} 個中間地址尚未確認歸屬，"
            f"建議持續追蹤或透過其他偵查手段確認其持有人身分。"
        )

    return "\n".join(parts)


# --- HTML 報告生成 ---

def generate_flow_report(
    graph: FlowGraph,
    case_info: CaseInfo,
    output_path: str,
) -> str:
    """產生完整的虛擬通貨幣流分析報告 HTML。"""

    now = datetime.now()
    report_date = case_info.request_date or now.strftime("%Y年%m月%d日")

    # 收集所有交易序號
    tx_hashes = list(dict.fromkeys(e.tx_hash for e in graph.edges if e.tx_hash))

    # 收集各層地址
    layer_sections = []
    for layer_idx in sorted(graph.layers.keys()):
        addrs = graph.layers[layer_idx]
        letter = LAYER_LETTERS[layer_idx] if layer_idx < len(LAYER_LETTERS) else f"L{layer_idx}"
        items = []
        for addr in addrs:
            node = graph.nodes.get(addr)
            alias = node.alias if node else letter
            label = f"（{', '.join(node.labels)}）" if node and node.labels else ""
            items.append(f"{alias}: {addr} {label}")
        layer_sections.append({
            "letter": letter,
            "layer": layer_idx,
            "items": items,
        })

    # SVG 幣流圖
    svg_content = _generate_flow_svg(graph)

    # 分析敘述
    narrative = _generate_narrative(graph)

    # 結論
    conclusion = _generate_conclusion(graph)

    # 組合 HTML
    html_content = _build_html(
        case_info=case_info,
        report_date=report_date,
        layer_sections=layer_sections,
        tx_hashes=tx_hashes,
        svg_content=svg_content,
        narrative=narrative,
        conclusion=conclusion,
        graph=graph,
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path


def _build_html(
    case_info: CaseInfo,
    report_date: str,
    layer_sections: list[dict],
    tx_hashes: list[str],
    svg_content: str,
    narrative: str,
    conclusion: str,
    graph: FlowGraph,
) -> str:
    """組建完整 HTML 文件。"""

    # --- 封面 ---
    cover_html = f"""
    <div class="cover page-break-after">
        <div class="cover-agency">{_esc(case_info.agency)}</div>
        {f'<div class="cover-division">{_esc(case_info.division)}</div>' if case_info.division else ''}
        <h1 class="cover-title">虛擬通貨幣流分析報告</h1>
        <div class="cover-case-info">
            <p>案號：{_esc(case_info.case_number)}</p>
            <p>案類：{_esc(case_info.case_type)}</p>
            <p>幣別：{_esc(case_info.coin_type)}</p>
        </div>
        {f'<div class="cover-description">{_esc(case_info.description)}</div>' if case_info.description else ''}
        <div class="cover-personnel">
            <table class="personnel-table">
                <tr><td>分析人員：</td><td>{_esc(case_info.analyst_name)} {_esc(case_info.analyst_rank)}</td></tr>
                <tr><td>審核人員：</td><td>{_esc(case_info.reviewer_name)} {_esc(case_info.reviewer_rank)}</td></tr>
            </table>
        </div>
        <div class="cover-date">中華民國 {_esc(report_date)}</div>
    </div>
    """

    # --- 目錄 ---
    toc_html = """
    <div class="toc page-break-after">
        <h2 class="section-title">目　錄</h2>
        <ul class="toc-list">
            <li>免責聲明</li>
            <li>一、案件資訊</li>
            <li>二、分析情形</li>
            <li>三、結論及建議事項</li>
            <li>四、名詞解釋</li>
        </ul>
    </div>
    """

    # --- 免責聲明 ---
    disclaimer_paragraphs = "\n".join(
        f"<p>{_esc(line)}</p>" for line in DISCLAIMER_TEXT.split("\n\n") if line.strip()
    )
    disclaimer_html = f"""
    <div class="section page-break-after">
        <h2 class="section-title">免責聲明</h2>
        <div class="disclaimer-text">{disclaimer_paragraphs}</div>
    </div>
    """

    # --- 一、案件資訊 ---
    addresses_html_parts = []
    for section in layer_sections:
        letter = section["letter"]
        items_html = "\n".join(
            f'<li class="address-item"><code>{_esc(item)}</code></li>'
            for item in section["items"]
        )
        layer_label = f"第 {letter} 層地址" if section["layer"] > 0 else "起始地址（A 層）"
        addresses_html_parts.append(f"""
        <div class="address-layer">
            <h4>{_esc(layer_label)}</h4>
            <ul class="address-list">{items_html}</ul>
        </div>
        """)
    addresses_html = "\n".join(addresses_html_parts)

    tx_list_html = ""
    if tx_hashes:
        tx_items = "\n".join(
            f'<li><code class="tx-hash">{_esc(h)}</code></li>'
            for h in tx_hashes
        )
        tx_list_html = f"""
        <div class="tx-section">
            <h4>交易序號列表（共 {len(tx_hashes)} 筆）</h4>
            <ol class="tx-list">{tx_items}</ol>
        </div>
        """

    case_info_html = f"""
    <div class="section page-break-after">
        <h2 class="section-title">一、案件資訊</h2>
        <table class="info-table">
            <tr><th>承辦單位</th><td>{_esc(case_info.agency)} {_esc(case_info.division)}</td></tr>
            <tr><th>案號</th><td>{_esc(case_info.case_number)}</td></tr>
            <tr><th>案類</th><td>{_esc(case_info.case_type)}</td></tr>
            <tr><th>幣別</th><td>{_esc(case_info.coin_type)}</td></tr>
            <tr><th>分析人員</th><td>{_esc(case_info.analyst_name)} {_esc(case_info.analyst_rank)}</td></tr>
            <tr><th>審核人員</th><td>{_esc(case_info.reviewer_name)} {_esc(case_info.reviewer_rank)}</td></tr>
            <tr><th>報告日期</th><td>{_esc(report_date)}</td></tr>
        </table>

        <h3>錢包地址列表</h3>
        {addresses_html}
        {tx_list_html}
    </div>
    """

    # --- 二、分析情形 ---
    narrative_paragraphs = "\n".join(
        f"<p>{_esc(line)}</p>" for line in narrative.split("\n\n") if line.strip()
    )

    analysis_html = f"""
    <div class="section page-break-after">
        <h2 class="section-title">二、分析情形</h2>

        <h3>幣流分析圖</h3>
        <div class="flow-diagram">
            {svg_content}
        </div>

        <h3>分析說明</h3>
        <div class="narrative">{narrative_paragraphs}</div>
    </div>
    """

    # --- 三、結論及建議事項 ---
    conclusion_paragraphs = "\n".join(
        f"<p>{_esc(line)}</p>" if not line.strip().startswith("●") and not line.strip().startswith(("1.", "2.", "3.", "4.", "5."))
        else f"<p class='indent'>{_esc(line)}</p>"
        for line in conclusion.split("\n") if line.strip()
    )

    conclusion_html = f"""
    <div class="section page-break-after">
        <h2 class="section-title">三、結論及建議事項</h2>
        <div class="conclusion">{conclusion_paragraphs}</div>
    </div>
    """

    # --- 四、名詞解釋 ---
    glossary_items_html = "\n".join(
        f"""<dt>{_esc(item['term'])}</dt><dd>{_esc(item['definition'])}</dd>"""
        for item in GLOSSARY_ITEMS
    )

    glossary_html = f"""
    <div class="section">
        <h2 class="section-title">四、名詞解釋</h2>
        <dl class="glossary">{glossary_items_html}</dl>
    </div>
    """

    # --- 組合完整 HTML ---
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>虛擬通貨幣流分析報告 — {_esc(case_info.case_number)}</title>
<style>
{_get_print_css()}
</style>
</head>
<body>
{cover_html}
{toc_html}
{disclaimer_html}
{case_info_html}
{analysis_html}
{conclusion_html}
{glossary_html}

<footer class="page-footer">
    <span class="footer-case">{_esc(case_info.case_number)}</span>
    <span class="footer-gen">Generated by crypto-acc-chk · MistTrack AML</span>
</footer>
</body>
</html>"""


def _get_print_css() -> str:
    """列印優化 CSS — A4 頁面。"""
    return """
/* === 基礎排版 === */
@page {
    size: A4;
    margin: 20mm 18mm 25mm 18mm;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC",
                 -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 12pt;
    line-height: 1.8;
    color: #222;
    background: #fff;
    max-width: 210mm;
    margin: 0 auto;
    padding: 20mm 18mm;
}

@media screen {
    body {
        padding: 40px;
        max-width: 900px;
        box-shadow: 0 0 20px rgba(0,0,0,0.1);
    }
}

/* === 分頁控制 === */
.page-break-after {
    page-break-after: always;
}

@media screen {
    .page-break-after {
        border-bottom: 2px dashed #ccc;
        padding-bottom: 40px;
        margin-bottom: 40px;
    }
}

/* === 封面 === */
.cover {
    text-align: center;
    padding-top: 80px;
    min-height: 700px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
}

.cover-agency {
    font-size: 18pt;
    font-weight: 700;
    letter-spacing: 4px;
    margin-bottom: 8px;
}

.cover-division {
    font-size: 14pt;
    color: #555;
    margin-bottom: 40px;
}

.cover-title {
    font-size: 26pt;
    font-weight: 900;
    letter-spacing: 6px;
    margin-bottom: 50px;
    border-bottom: 3px solid #333;
    padding-bottom: 16px;
}

.cover-case-info {
    font-size: 13pt;
    line-height: 2.2;
    margin-bottom: 30px;
}

.cover-description {
    font-size: 11pt;
    color: #555;
    max-width: 500px;
    margin-bottom: 30px;
    line-height: 1.8;
}

.cover-personnel {
    margin-bottom: 40px;
}

.personnel-table {
    margin: 0 auto;
    font-size: 12pt;
    border: none;
}

.personnel-table td {
    padding: 4px 12px;
    text-align: left;
}

.cover-date {
    font-size: 13pt;
    margin-top: 20px;
}

/* === 目錄 === */
.toc {
    padding-top: 40px;
}

.toc-list {
    list-style: none;
    padding: 0;
    font-size: 13pt;
    line-height: 2.5;
}

.toc-list li {
    border-bottom: 1px dotted #ccc;
    padding: 4px 0;
}

/* === 段落標題 === */
.section {
    padding-top: 20px;
}

.section-title {
    font-size: 18pt;
    font-weight: 700;
    margin-bottom: 20px;
    padding-bottom: 8px;
    border-bottom: 2px solid #333;
}

h3 {
    font-size: 14pt;
    font-weight: 600;
    margin-top: 24px;
    margin-bottom: 12px;
    color: #333;
}

h4 {
    font-size: 12pt;
    font-weight: 600;
    margin-top: 16px;
    margin-bottom: 8px;
    color: #444;
}

/* === 案件資訊表格 === */
.info-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
    font-size: 11pt;
}

.info-table th,
.info-table td {
    border: 1px solid #999;
    padding: 8px 12px;
    text-align: left;
}

.info-table th {
    background: #f0f0f0;
    width: 120px;
    font-weight: 600;
}

/* === 地址列表 === */
.address-layer {
    margin-bottom: 12px;
}

.address-list {
    list-style: none;
    padding: 0;
    margin: 4px 0;
}

.address-item {
    padding: 4px 0;
    font-size: 10pt;
}

.address-item code {
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 9pt;
    background: #f5f5f5;
    padding: 2px 6px;
    border-radius: 3px;
    word-break: break-all;
}

/* === 交易序號 === */
.tx-section {
    margin-top: 16px;
}

.tx-list {
    padding-left: 24px;
    font-size: 10pt;
}

.tx-list li {
    padding: 2px 0;
}

.tx-hash {
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
    font-size: 8pt;
    background: #f5f5f5;
    padding: 2px 4px;
    border-radius: 3px;
    word-break: break-all;
}

/* === 幣流分析圖 === */
.flow-diagram {
    overflow-x: auto;
    margin: 16px 0;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: #fff;
    text-align: center;
}

.flow-diagram svg {
    max-width: 100%;
    height: auto;
}

/* === 分析敘述 === */
.narrative p,
.conclusion p,
.disclaimer-text p {
    text-indent: 2em;
    margin-bottom: 8px;
    text-align: justify;
}

.conclusion p.indent {
    text-indent: 4em;
}

/* === 名詞解釋 === */
.glossary {
    margin-top: 12px;
}

.glossary dt {
    font-weight: 700;
    font-size: 11pt;
    margin-top: 16px;
    margin-bottom: 4px;
}

.glossary dd {
    font-size: 11pt;
    line-height: 1.8;
    text-align: justify;
    margin-left: 0;
    margin-bottom: 8px;
}

/* === 頁尾 === */
.page-footer {
    display: flex;
    justify-content: space-between;
    margin-top: 40px;
    padding-top: 12px;
    border-top: 1px solid #ccc;
    font-size: 8pt;
    color: #999;
}

@media print {
    .page-footer {
        position: fixed;
        bottom: 0;
        left: 0;
        right: 0;
        padding: 8px 18mm;
    }

    body {
        padding: 0;
        max-width: none;
    }
}
"""
