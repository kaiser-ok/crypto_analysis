"""多層資金流向追蹤引擎 — BFS 演算法追蹤虛擬通貨幣流。"""

import time
from collections import deque
from dataclasses import dataclass, field

from tqdm import tqdm

from misttrack import MistTrackClient, RATE_LIMIT_DELAY


# --- 資料結構 ---

@dataclass
class FlowNode:
    """幣流圖中的一個地址節點。"""
    address: str
    layer: int              # 0=A, 1=B, 2=C, 3=D...
    alias: str              # "A", "B1", "C2", "D1"
    labels: list[str] = field(default_factory=list)
    risk_score: int = 0
    risk_level: str = ""
    balance: float = 0.0
    total_received: float = 0.0
    total_spent: float = 0.0
    is_exchange: bool = False
    first_seen: int = 0             # 首次交易 Unix timestamp
    last_seen: int = 0              # 最近交易 Unix timestamp
    txs_count: int = 0              # 總交易次數
    received_txs_count: int = 0     # 入帳次數
    spent_txs_count: int = 0        # 出帳次數
    wallet_type: str = ""           # "relay"(中繼) / "profit"(獲利) / ""


@dataclass
class FlowEdge:
    """幣流圖中的一條交易邊。"""
    tx_hash: str
    from_address: str
    to_address: str
    amount: float
    token: str              # "USDT", "TRX"
    timestamp: int = 0


@dataclass
class FlowGraph:
    """完整的幣流追蹤圖。"""
    source_address: str
    coin_type: str
    nodes: dict[str, FlowNode] = field(default_factory=dict)
    edges: list[FlowEdge] = field(default_factory=list)
    layers: dict[int, list[str]] = field(default_factory=dict)
    alias_map: dict[str, str] = field(default_factory=dict)   # address -> alias


@dataclass
class CaseInfo:
    """案件基本資訊。"""
    agency: str = ""            # 機關名稱
    division: str = ""          # 分局名稱
    case_type: str = "詐欺"    # 案類
    case_number: str = ""       # 案號
    analyst_name: str = ""      # 分析人員
    analyst_rank: str = ""      # 職稱
    reviewer_name: str = ""     # 審核人員
    reviewer_rank: str = ""     # 職稱
    request_date: str = ""      # 申請日期
    description: str = ""       # 案件描述
    coin_type: str = "USDT-TRC20"
    source_addresses: list[str] = field(default_factory=list)
    min_timestamp: int = 0      # 犯罪時間起始（毫秒 Unix timestamp）
    max_timestamp: int = 0      # 犯罪時間結束（毫秒 Unix timestamp）
    target_exchange: str = ""   # 目標交易所關鍵字


# --- 層別名稱對應 ---

LAYER_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _make_alias(layer: int, index: int) -> str:
    """產生節點別名，如 A, B1, B2, C1 等。Layer 0 固定為 'A'。"""
    letter = LAYER_LETTERS[layer] if layer < len(LAYER_LETTERS) else f"L{layer}"
    if layer == 0:
        return letter
    return f"{letter}{index + 1}"


# --- 交易所標籤辨識 ---

EXCHANGE_KEYWORDS = {
    "binance", "bitopro", "maicoin", "max", "okx", "huobi", "htx",
    "bybit", "kucoin", "gate.io", "kraken", "coinbase", "bitfinex",
    "poloniex", "bitstamp", "gemini", "ace", "bito",
}


def _is_exchange_label(labels: list[str]) -> bool:
    """判斷標籤是否包含交易所名稱。"""
    for label in labels:
        if label.lower() in EXCHANGE_KEYWORDS:
            return True
        # 部分匹配（如 "Binance Hot Wallet"）
        for kw in EXCHANGE_KEYWORDS:
            if kw in label.lower():
                return True
    return False


# --- BFS 追蹤引擎 ---

def trace_flow(
    source_address: str,
    coin_type: str,
    misttrack_client: MistTrackClient,
    max_depth: int = 4,
    moralis_client=None,
    trongrid_client=None,
    top_n: int = 0,
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    target_exchange: str = "",
) -> FlowGraph:
    """BFS 從起始地址向外追蹤資金流向。

    1. 起始地址 = Layer 0 (alias "A")
    2. 呼叫 transactions_investigation(type="out") 取得下游地址
    3. 對每個下游地址呼叫 address_labels 判斷是否為交易所
    4. 若是交易所 → 標記為終端節點，不再遞迴
    5. 若否 → 加入下一層繼續 BFS
    6. 重複至 max_depth 或全部為交易所
    7. Alias 依各層內 timestamp 排序

    top_n: 每個節點展開時只取前 N 個下游地址（依金額+交易次數排序）。
           0 表示不限制（全部展開）。可大幅降低 API 呼叫數量。
    min_timestamp / max_timestamp: 毫秒 Unix timestamp。所有層的 TronGrid 查詢都會套用時間範圍過濾，
           只取犯罪時間窗口內的交易，避免無關交易干擾分析。
    target_exchange: 目標交易所關鍵字（如 "maicoin"）。BFS 完成後剪枝，只保留通往該交易所的路徑。
           空字串表示不剪枝（保留全部）。
    """
    graph = FlowGraph(source_address=source_address, coin_type=coin_type)

    # 初始化起始節點（Layer 0 使用時間窗口過濾）
    source_info = fetch_node_info(
        source_address, misttrack_client, trongrid_client=trongrid_client,
        min_timestamp=min_timestamp, max_timestamp=max_timestamp,
    )
    source_node = FlowNode(
        address=source_address,
        layer=0,
        alias="A",
        labels=source_info["labels"],
        risk_score=source_info["risk_score"],
        risk_level=source_info["risk_level"],
        balance=source_info["balance"],
        total_received=source_info["total_received"],
        total_spent=source_info["total_spent"],
        is_exchange=source_info["is_exchange"],
        first_seen=source_info["first_seen"],
        last_seen=source_info["last_seen"],
        txs_count=source_info["txs_count"],
        received_txs_count=source_info["received_txs_count"],
        spent_txs_count=source_info["spent_txs_count"],
    )
    graph.nodes[source_address] = source_node
    graph.layers[0] = [source_address]
    graph.alias_map[source_address] = "A"

    # BFS queue: (address, current_layer)
    queue: deque[tuple[str, int]] = deque()
    queue.append((source_address, 0))
    visited: set[str] = {source_address}

    print(f"[FlowTracer] 開始 BFS 追蹤: {source_address[:12]}...")

    while queue:
        current_addr, current_layer = queue.popleft()

        if current_layer >= max_depth:
            continue

        next_layer = current_layer + 1

        # 取得下游交易
        print(f"  Layer {current_layer} → 查詢 {current_addr[:12]}... 的下游交易")

        downstream = None

        # 優先使用 TronGrid 取得完整鏈上交易
        # 所有層都使用時間窗口過濾（若有設定），限縮查詢範圍
        # Layer 0 使用完整頁數（50頁），深層節點限制頁數以加速
        layer_max_pages = 50 if current_layer == 0 else 10
        if trongrid_client:
            trc20_txs = trongrid_client.get_all_trc20_transfers(
                current_addr,
                min_timestamp=min_timestamp or None,
                max_timestamp=max_timestamp or None,
                max_pages=layer_max_pages,
            )
            if trc20_txs:
                downstream = parse_trongrid_downstream(trc20_txs, current_addr)
                print(f"    [TronGrid] 取得 {len(trc20_txs)} 筆 TRC20 交易, "
                      f"解析出 {len(downstream)} 個下游地址")

        # 無 TronGrid 或 TronGrid 無資料時退回 MistTrack
        if downstream is None:
            tx_data = misttrack_client.get_transactions(current_addr, direction="out")
            time.sleep(RATE_LIMIT_DELAY)

            if not tx_data:
                print(f"    [!] 無法取得 {current_addr[:12]}... 的下游交易資料"
                      f"（API 可能回傳錯誤，請檢查 API key 權限）")
                continue

            downstream = parse_downstream(tx_data, current_addr, coin_type)

        if not downstream:
            continue

        # top_n 篩選：只保留金額最高 + 交易次數最多的前 N 個地址
        if top_n > 0 and len(downstream) > top_n:
            # 依金額排序取 top_n
            by_amount = sorted(downstream, key=lambda x: x["amount"], reverse=True)
            top_addrs = set()
            for item in by_amount[:top_n]:
                top_addrs.add(item["to_address"])
            # 依交易次數排序取 top_n（取聯集）
            by_tx_count = sorted(
                downstream,
                key=lambda x: len(x.get("tx_hash_list", [])),
                reverse=True,
            )
            for item in by_tx_count[:top_n]:
                top_addrs.add(item["to_address"])
            skipped = len(downstream) - len([d for d in downstream if d["to_address"] in top_addrs])
            downstream = [d for d in downstream if d["to_address"] in top_addrs]
            if skipped > 0:
                print(f"    [top_n={top_n}] 保留 {len(downstream)} 個地址，跳過 {skipped} 個低金額/低頻地址")

        # 收集本層新發現的節點（按 timestamp 排序後分配 alias）
        new_nodes_in_layer: list[tuple[str, int]] = []  # (address, earliest_ts)

        for item in downstream:
            to_addr = item["to_address"]
            tx_hash_list = item.get("tx_hash_list", [])

            # 記錄邊 — 每筆 tx_hash 各建一條 edge，同對地址最多 MAX_EDGES_PER_PAIR 條
            MAX_EDGES_PER_PAIR = 10
            if tx_hash_list:
                capped = tx_hash_list[:MAX_EDGES_PER_PAIR]
                remaining_amount = item["amount"]
                # 被截斷的交易金額歸入最後一條邊
                per_tx_amount = item["amount"] / len(tx_hash_list)
                for idx, txh in enumerate(capped):
                    if idx < len(capped) - 1:
                        edge_amount = per_tx_amount
                    else:
                        # 最後一條邊承接剩餘全部金額
                        edge_amount = remaining_amount
                    remaining_amount -= per_tx_amount
                    graph.edges.append(FlowEdge(
                        tx_hash=txh,
                        from_address=current_addr,
                        to_address=to_addr,
                        amount=edge_amount,
                        token=item["token"],
                        timestamp=item["timestamp"],
                    ))
            else:
                graph.edges.append(FlowEdge(
                    tx_hash=item.get("tx_hash", ""),
                    from_address=current_addr,
                    to_address=to_addr,
                    amount=item["amount"],
                    token=item["token"],
                    timestamp=item["timestamp"],
                ))

            if to_addr in visited:
                continue
            visited.add(to_addr)

            new_nodes_in_layer.append((to_addr, item["timestamp"]))

        # 按 timestamp 排序分配 alias
        new_nodes_in_layer.sort(key=lambda x: x[1])

        layer_addrs = graph.layers.get(next_layer, [])

        for to_addr, _ts in new_nodes_in_layer:
            # 查詢地址資訊
            node_info = fetch_node_info(to_addr, misttrack_client, trongrid_client=trongrid_client)

            idx = len(layer_addrs)
            alias = _make_alias(next_layer, idx)

            node = FlowNode(
                address=to_addr,
                layer=next_layer,
                alias=alias,
                labels=node_info["labels"],
                risk_score=node_info["risk_score"],
                risk_level=node_info["risk_level"],
                balance=node_info["balance"],
                total_received=node_info["total_received"],
                total_spent=node_info["total_spent"],
                is_exchange=node_info["is_exchange"],
                first_seen=node_info["first_seen"],
                last_seen=node_info["last_seen"],
                txs_count=node_info["txs_count"],
                received_txs_count=node_info["received_txs_count"],
                spent_txs_count=node_info["spent_txs_count"],
            )

            graph.nodes[to_addr] = node
            layer_addrs.append(to_addr)
            graph.alias_map[to_addr] = alias

            print(f"    {alias}: {to_addr[:12]}... "
                  f"{'[交易所: ' + ', '.join(node.labels) + ']' if node.is_exchange else ''}")

            # 非交易所才繼續遞迴
            if not node.is_exchange:
                queue.append((to_addr, next_layer))

        graph.layers[next_layer] = layer_addrs

    # 路徑剪枝：只保留通往目標交易所的路徑
    if target_exchange:
        _prune_to_exchange(graph, target_exchange)

    # 統計
    total_nodes = len(graph.nodes)
    total_edges = len(graph.edges)
    exchange_count = sum(1 for n in graph.nodes.values() if n.is_exchange)
    print(f"[FlowTracer] 完成: {total_nodes} 個節點, {total_edges} 條邊, "
          f"{exchange_count} 個交易所地址")

    return graph


def fetch_node_info(
    address: str, client: MistTrackClient, trongrid_client=None,
    min_timestamp: int = 0, max_timestamp: int = 0,
) -> dict:
    """取得地址的標籤、風險分數和概覽資訊。

    若有 trongrid_client，使用 TronGrid 取得完整鏈上數據（餘額、交易統計）；
    MistTrack 僅用於標籤和風險分數。
    min_timestamp / max_timestamp: 若非零，TronGrid 概覽統計僅計算此時間窗口內的交易。
    """
    info = {
        "labels": [],
        "risk_score": 0,
        "risk_level": "",
        "balance": 0.0,
        "total_received": 0.0,
        "total_spent": 0.0,
        "is_exchange": False,
        "first_seen": 0,
        "last_seen": 0,
        "txs_count": 0,
        "received_txs_count": 0,
        "spent_txs_count": 0,
    }

    # Labels（MistTrack 情報分析）
    labels_data = client.get_labels(address)
    time.sleep(RATE_LIMIT_DELAY)
    if labels_data:
        info["labels"] = labels_data.get("label_list", [])
        info["is_exchange"] = _is_exchange_label(info["labels"])

    # Risk score（MistTrack 情報分析）
    risk_data = client.get_risk_score(address)
    time.sleep(RATE_LIMIT_DELAY)
    if risk_data:
        info["risk_score"] = risk_data.get("score", 0)
        info["risk_level"] = risk_data.get("risk_level", "")

    # 交易所地址是終端節點，不需要抓取完整鏈上交易歷史（大幅節省時間）
    if info["is_exchange"]:
        print(f"  [skip] {address[:12]}... 為交易所地址，跳過鏈上交易歷史查詢")
        return info

    # 鏈上數據：優先 TronGrid，備用 MistTrack overview
    trongrid_ok = False
    if trongrid_client:
        trongrid_ok = _fetch_trongrid_overview(
            address, trongrid_client, info,
            min_timestamp=min_timestamp, max_timestamp=max_timestamp,
        )

    if not trongrid_ok:
        # MistTrack overview 作為備用
        overview = client.get_overview(address)
        time.sleep(RATE_LIMIT_DELAY)
        if overview:
            info["balance"] = overview.get("balance", 0.0)
            info["total_received"] = overview.get("total_received", 0.0)
            info["total_spent"] = overview.get("total_spent", 0.0)
            info["first_seen"] = overview.get("first_seen", 0)
            info["last_seen"] = overview.get("last_seen", 0)
            info["txs_count"] = overview.get("txs_count", 0)
            info["received_txs_count"] = overview.get("received_txs_count", 0)
            info["spent_txs_count"] = overview.get("spent_txs_count", 0)

    return info


def _fetch_trongrid_overview(
    address: str, trongrid_client, info: dict,
    min_timestamp: int = 0, max_timestamp: int = 0,
) -> bool:
    """使用 TronGrid 取得帳戶概覽數據，寫入 info dict。回傳是否成功。

    min_timestamp / max_timestamp: 若非零，統計僅計算此時間窗口內的交易。
    """
    # 取得即時餘額
    account = trongrid_client.get_account(address)
    if account and account.get("data"):
        acct_data = account["data"][0] if isinstance(account["data"], list) else account["data"]
        # TRX 餘額（sun -> TRX）
        trx_balance = acct_data.get("balance", 0) / 1_000_000
        # TRC20 餘額（從 trc20 陣列中找 USDT）
        trc20_list = acct_data.get("trc20", [])
        usdt_balance = 0.0
        from trongrid import USDT_TRC20_CONTRACT
        for token_map in trc20_list:
            if isinstance(token_map, dict):
                usdt_raw = token_map.get(USDT_TRC20_CONTRACT, "0")
                usdt_balance = int(usdt_raw) / 1_000_000
                break
        info["balance"] = usdt_balance

    # 取得 TRC20 轉帳歷史來計算統計（若有時間範圍則伺服器端過濾）
    all_txs = trongrid_client.get_all_trc20_transfers(
        address,
        min_timestamp=min_timestamp or None,
        max_timestamp=max_timestamp or None,
    )
    if not all_txs:
        return False

    total_received = 0.0
    total_spent = 0.0
    received_count = 0
    spent_count = 0
    first_seen = 0
    last_seen = 0

    for tx in all_txs:
        token_info = tx.get("token_info", {})
        decimals = int(token_info.get("decimals", 6))
        value = int(tx.get("value", "0")) / (10 ** decimals)
        ts = tx.get("block_timestamp", 0)

        if ts and (first_seen == 0 or ts < first_seen):
            first_seen = ts
        if ts and ts > last_seen:
            last_seen = ts

        from_addr = tx.get("from", "")
        to_addr = tx.get("to", "")

        if to_addr.lower() == address.lower():
            total_received += value
            received_count += 1
        if from_addr.lower() == address.lower():
            total_spent += value
            spent_count += 1

    info["total_received"] = total_received
    info["total_spent"] = total_spent
    info["received_txs_count"] = received_count
    info["spent_txs_count"] = spent_count
    info["txs_count"] = received_count + spent_count
    # 轉為秒級 timestamp（TronGrid 回傳毫秒）
    info["first_seen"] = first_seen // 1000 if first_seen else 0
    info["last_seen"] = last_seen // 1000 if last_seen else 0

    return True


def _prune_to_exchange(graph: FlowGraph, target_exchange: str) -> None:
    """剪枝：只保留通往目標交易所的路徑，原地修改 graph。

    1. 找出所有 is_exchange 且 labels 匹配 target_exchange 的終端節點
    2. 從這些節點沿 edges 反向回溯，標記所有祖先節點為「路徑上」
    3. 移除不在路徑上的節點和邊
    4. 重新整理 graph.layers
    """
    target_kw = target_exchange.lower().strip()
    if not target_kw:
        return

    # 找出匹配目標交易所的終端節點
    target_addrs: set[str] = set()
    for addr, node in graph.nodes.items():
        if not node.is_exchange:
            continue
        for label in node.labels:
            if target_kw in label.lower():
                target_addrs.add(addr)
                break

    if not target_addrs:
        print(f"[Prune] 未找到匹配 '{target_exchange}' 的交易所節點，跳過剪枝")
        return

    print(f"[Prune] 找到 {len(target_addrs)} 個匹配 '{target_exchange}' 的交易所節點，開始反向回溯...")

    # 建立反向邊索引: to_addr -> [from_addr]
    reverse_edges: dict[str, set[str]] = {}
    for edge in graph.edges:
        reverse_edges.setdefault(edge.to_address, set()).add(edge.from_address)

    # BFS 反向回溯，標記所有祖先節點
    on_path: set[str] = set(target_addrs)
    queue = deque(target_addrs)
    while queue:
        addr = queue.popleft()
        for parent_addr in reverse_edges.get(addr, set()):
            if parent_addr not in on_path:
                on_path.add(parent_addr)
                queue.append(parent_addr)

    # 確保起始地址始終保留
    on_path.add(graph.source_address)

    # 移除不在路徑上的節點
    removed_count = 0
    for addr in list(graph.nodes.keys()):
        if addr not in on_path:
            del graph.nodes[addr]
            graph.alias_map.pop(addr, None)
            removed_count += 1

    # 移除不在路徑上的邊
    graph.edges = [
        e for e in graph.edges
        if e.from_address in on_path and e.to_address in on_path
    ]

    # 重建 layers
    new_layers: dict[int, list[str]] = {}
    for addr, node in graph.nodes.items():
        new_layers.setdefault(node.layer, []).append(addr)
    graph.layers = new_layers

    print(f"[Prune] 剪枝完成：移除 {removed_count} 個節點，"
          f"保留 {len(graph.nodes)} 個節點、{len(graph.edges)} 條邊")


def prune_to_any_exchange(graph: FlowGraph) -> None:
    """剪枝：只保留通往任意交易所的路徑，移除不連通交易所的死路分支。

    與 _prune_to_exchange 類似，但不限定特定交易所——
    只要路徑終端是交易所地址就保留。適用於交易所調閱報告場景。
    """
    # 找出所有交易所節點
    exchange_addrs: set[str] = set()
    for addr, node in graph.nodes.items():
        if node.is_exchange:
            exchange_addrs.add(addr)

    if not exchange_addrs:
        print("[Prune] 未找到任何交易所節點，跳過剪枝")
        return

    print(f"[Prune] 找到 {len(exchange_addrs)} 個交易所節點，開始反向回溯保留通往交易所的路徑...")

    # 建立反向邊索引: to_addr -> [from_addr]
    reverse_edges: dict[str, set[str]] = {}
    for edge in graph.edges:
        reverse_edges.setdefault(edge.to_address, set()).add(edge.from_address)

    # BFS 反向回溯，標記所有祖先節點
    on_path: set[str] = set(exchange_addrs)
    queue = deque(exchange_addrs)
    while queue:
        addr = queue.popleft()
        for parent_addr in reverse_edges.get(addr, set()):
            if parent_addr not in on_path:
                on_path.add(parent_addr)
                queue.append(parent_addr)

    # 確保起始地址始終保留
    on_path.add(graph.source_address)

    # 移除不在路徑上的節點
    removed_count = 0
    for addr in list(graph.nodes.keys()):
        if addr not in on_path:
            del graph.nodes[addr]
            graph.alias_map.pop(addr, None)
            removed_count += 1

    # 移除不在路徑上的邊
    graph.edges = [
        e for e in graph.edges
        if e.from_address in on_path and e.to_address in on_path
    ]

    # 重建 layers
    new_layers: dict[int, list[str]] = {}
    for addr, node in graph.nodes.items():
        new_layers.setdefault(node.layer, []).append(addr)
    graph.layers = new_layers

    print(f"[Prune] 交易所路徑剪枝完成：移除 {removed_count} 個無關節點，"
          f"保留 {len(graph.nodes)} 個節點、{len(graph.edges)} 條邊")


def prune_to_case_addresses(graph: FlowGraph, case_addresses: set[str]) -> None:
    """剪枝：只保留連接案件相關地址的路徑。

    case_addresses: 從 case_info.json 取得的所有案件相關錢包地址集合。

    演算法：
    1. 標記所有 case_addresses 中存在於 graph 中的節點
    2. 加上所有 is_exchange 的終端節點（交易所始終保留）
    3. 反向 BFS 從這些節點回溯，標記路徑上的所有祖先
    4. 正向 BFS 從 source 出發，標記路徑上的所有後代
    5. 取交集：只保留同時可從 source 到達、且可到達 case 節點的路徑
    6. 刪除非路徑上的節點和邊，重建 layers
    """
    # 目標節點集合：案件相關地址 + 交易所節點
    target_addrs: set[str] = set()
    for addr in case_addresses:
        if addr in graph.nodes:
            target_addrs.add(addr)
    for addr, node in graph.nodes.items():
        if node.is_exchange:
            target_addrs.add(addr)

    if not target_addrs:
        print(f"[CasePrune] 未找到任何案件相關地址在圖中，跳過剪枝")
        return

    print(f"[CasePrune] 目標節點: {len(target_addrs)} 個 "
          f"(案件地址 {len(case_addresses & set(graph.nodes.keys()))} + "
          f"交易所 {sum(1 for n in graph.nodes.values() if n.is_exchange)})")

    # 建立邊索引
    forward_edges: dict[str, set[str]] = {}   # from -> {to}
    reverse_edges: dict[str, set[str]] = {}   # to -> {from}
    for edge in graph.edges:
        forward_edges.setdefault(edge.from_address, set()).add(edge.to_address)
        reverse_edges.setdefault(edge.to_address, set()).add(edge.from_address)

    # 反向 BFS：從目標節點回溯到 source
    backward_reachable: set[str] = set(target_addrs)
    queue = deque(target_addrs)
    while queue:
        addr = queue.popleft()
        for parent in reverse_edges.get(addr, set()):
            if parent not in backward_reachable:
                backward_reachable.add(parent)
                queue.append(parent)

    # 正向 BFS：從 source 出發可到達的節點
    forward_reachable: set[str] = {graph.source_address}
    queue = deque([graph.source_address])
    while queue:
        addr = queue.popleft()
        for child in forward_edges.get(addr, set()):
            if child not in forward_reachable:
                forward_reachable.add(child)
                queue.append(child)

    # 取交集：同時可從 source 到達、且可到達目標節點
    on_path = forward_reachable & backward_reachable
    # 確保起始地址始終保留
    on_path.add(graph.source_address)

    # 移除不在路徑上的節點
    removed_count = 0
    for addr in list(graph.nodes.keys()):
        if addr not in on_path:
            del graph.nodes[addr]
            graph.alias_map.pop(addr, None)
            removed_count += 1

    # 移除不在路徑上的邊
    graph.edges = [
        e for e in graph.edges
        if e.from_address in on_path and e.to_address in on_path
    ]

    # 重建 layers
    new_layers: dict[int, list[str]] = {}
    for addr, node in graph.nodes.items():
        new_layers.setdefault(node.layer, []).append(addr)
    graph.layers = new_layers

    print(f"[CasePrune] 剪枝完成：移除 {removed_count} 個節點，"
          f"保留 {len(graph.nodes)} 個節點、{len(graph.edges)} 條邊")


def parse_downstream(
    tx_data: dict,
    from_address: str,
    coin_type: str,
) -> list[dict]:
    """從 transactions_investigation 回傳資料解析下游地址。

    實際 API 回傳格式：
    {"out": [{"address": ..., "amount": ..., "tx_hash_list": [...], "type": ..., "label": ...}],
     "in": [...], "page": 1, "total_pages": 1}
    """
    results = []
    seen_addrs: set[str] = set()
    default_token = coin_type.split("-")[0] if "-" in coin_type else coin_type

    # 主要格式: {"out": [{"address": ..., "amount": ..., "tx_hash_list": [...]}]}
    out_list = tx_data.get("out", [])
    if isinstance(out_list, list):
        for item in out_list:
            to_addr = item.get("address", "")
            if not to_addr or to_addr == from_address:
                continue

            amount = _parse_amount(item.get("amount", 0))
            token = item.get("token", default_token)
            tx_hashes = item.get("tx_hash_list", [])
            timestamp = item.get("timestamp", 0)
            label = item.get("label", "")

            if to_addr not in seen_addrs:
                results.append({
                    "to_address": to_addr,
                    "amount": amount,
                    "token": token,
                    "tx_hash": tx_hashes[0] if tx_hashes else "",
                    "tx_hash_list": tx_hashes,
                    "timestamp": timestamp,
                    "label": label,
                })
                seen_addrs.add(to_addr)

    # 備用格式: {"receive": [...]}
    if not results:
        receive_list = tx_data.get("receive", [])
        if isinstance(receive_list, list):
            for item in receive_list:
                to_addr = item.get("address", "")
                if not to_addr or to_addr == from_address:
                    continue

                amount = _parse_amount(item.get("amount", 0))
                token = item.get("token", default_token)
                tx_hashes = item.get("tx_hash_list", [])
                timestamp = item.get("timestamp", 0)

                if to_addr not in seen_addrs:
                    results.append({
                        "to_address": to_addr,
                        "amount": amount,
                        "token": token,
                        "tx_hash": tx_hashes[0] if tx_hashes else "",
                        "tx_hash_list": tx_hashes,
                        "timestamp": timestamp,
                        "label": "",
                    })
                    seen_addrs.add(to_addr)

    return results


def parse_upstream(
    tx_data: dict,
    to_address: str,
    coin_type: str,
) -> list[dict]:
    """從 transactions_investigation(type=in) 回傳資料解析上游地址。

    API 回傳格式：
    {"in": [{"address": ..., "amount": ..., "tx_hash_list": [...], "label": ...}],
     "out": [...], "page": 1, "total_pages": 1}
    """
    results = []
    seen_addrs: set[str] = set()
    default_token = coin_type.split("-")[0] if "-" in coin_type else coin_type

    in_list = tx_data.get("in", [])
    if isinstance(in_list, list):
        for item in in_list:
            from_addr = item.get("address", "")
            if not from_addr or from_addr == to_address:
                continue

            amount = _parse_amount(item.get("amount", 0))
            token = item.get("token", default_token)
            tx_hashes = item.get("tx_hash_list", [])
            timestamp = item.get("timestamp", 0)
            label = item.get("label", "")

            if from_addr not in seen_addrs:
                results.append({
                    "from_address": from_addr,
                    "amount": amount,
                    "token": token,
                    "tx_hash": tx_hashes[0] if tx_hashes else "",
                    "tx_hash_list": tx_hashes,
                    "timestamp": timestamp,
                    "label": label,
                })
                seen_addrs.add(from_addr)

    return results


def parse_trongrid_downstream(
    trc20_txs: list[dict],
    from_address: str,
    min_amount: float = 1.0,
) -> list[dict]:
    """從 TronGrid TRC20 轉帳紀錄中解析下游地址（from == current_addr 的交易）。

    按 to 地址聚合金額和 tx_hash，回傳格式與 parse_downstream() 相同。
    min_amount: 最低金額門檻（預設 1.0），過濾 0 值 approve 及微額交易。
    """
    # 聚合: to_addr -> {amount, tx_hashes, earliest_ts, token}
    agg: dict[str, dict] = {}

    for tx in trc20_txs:
        tx_from = tx.get("from", "")
        tx_to = tx.get("to", "")

        if tx_from.lower() != from_address.lower():
            continue
        if not tx_to or tx_to.lower() == from_address.lower():
            continue

        token_info = tx.get("token_info", {})
        decimals = int(token_info.get("decimals", 6))
        symbol = token_info.get("symbol", "USDT")
        value = int(tx.get("value", "0")) / (10 ** decimals)
        tx_hash = tx.get("transaction_id", "")
        ts = tx.get("block_timestamp", 0)

        # 過濾小額交易（0 值 approve、微額轉帳）
        if value < min_amount:
            continue

        if tx_to not in agg:
            agg[tx_to] = {
                "amount": 0.0,
                "tx_hashes": [],
                "earliest_ts": ts,
                "token": symbol,
            }

        agg[tx_to]["amount"] += value
        if tx_hash:
            agg[tx_to]["tx_hashes"].append(tx_hash)
        if ts and (agg[tx_to]["earliest_ts"] == 0 or ts < agg[tx_to]["earliest_ts"]):
            agg[tx_to]["earliest_ts"] = ts

    results = []
    for to_addr, data in agg.items():
        results.append({
            "to_address": to_addr,
            "amount": data["amount"],
            "token": data["token"],
            "tx_hash": data["tx_hashes"][0] if data["tx_hashes"] else "",
            "tx_hash_list": data["tx_hashes"],
            "timestamp": data["earliest_ts"] // 1000 if data["earliest_ts"] else 0,
            "label": "",
        })

    return results


def parse_trongrid_upstream(
    trc20_txs: list[dict],
    to_address: str,
    min_amount: float = 1.0,
) -> list[dict]:
    """從 TronGrid TRC20 轉帳紀錄中解析上游地址（to == current_addr 的交易）。

    min_amount: 最低金額門檻（預設 1.0），過濾 0 值及微額交易。
    """
    agg: dict[str, dict] = {}

    for tx in trc20_txs:
        tx_from = tx.get("from", "")
        tx_to = tx.get("to", "")

        if tx_to.lower() != to_address.lower():
            continue
        if not tx_from or tx_from.lower() == to_address.lower():
            continue

        token_info = tx.get("token_info", {})
        decimals = int(token_info.get("decimals", 6))
        symbol = token_info.get("symbol", "USDT")
        value = int(tx.get("value", "0")) / (10 ** decimals)
        tx_hash = tx.get("transaction_id", "")
        ts = tx.get("block_timestamp", 0)

        # 過濾小額交易
        if value < min_amount:
            continue

        if tx_from not in agg:
            agg[tx_from] = {
                "amount": 0.0,
                "tx_hashes": [],
                "earliest_ts": ts,
                "token": symbol,
            }

        agg[tx_from]["amount"] += value
        if tx_hash:
            agg[tx_from]["tx_hashes"].append(tx_hash)
        if ts and (agg[tx_from]["earliest_ts"] == 0 or ts < agg[tx_from]["earliest_ts"]):
            agg[tx_from]["earliest_ts"] = ts

    results = []
    for from_addr, data in agg.items():
        results.append({
            "from_address": from_addr,
            "amount": data["amount"],
            "token": data["token"],
            "tx_hash": data["tx_hashes"][0] if data["tx_hashes"] else "",
            "tx_hash_list": data["tx_hashes"],
            "timestamp": data["earliest_ts"] // 1000 if data["earliest_ts"] else 0,
            "label": "",
        })

    return results


def _parse_amount(value) -> float:
    """安全解析金額。"""
    try:
        if isinstance(value, str):
            value = value.replace(",", "")
        return float(value)
    except (ValueError, TypeError):
        return 0.0


# --- TRX 油費關聯分析 ---

def analyze_trx_gas(
    graph: FlowGraph,
    misttrack_client: MistTrackClient,
    trongrid_client=None,
) -> dict[str, str]:
    """查詢各非交易所地址的 TRX 入帳來源，回傳 {地址: TRX提供者地址} 的控制關係映射。

    TRX 油費提供者即可能為該錢包之實際持有人或上游控制者。
    若有 trongrid_client，使用 TronGrid 查詢 TRX 原生交易。
    """
    trx_providers: dict[str, str] = {}

    non_exchange_addrs = [
        addr for addr, node in graph.nodes.items()
        if not node.is_exchange
    ]

    print(f"[TRX Gas] 分析 {len(non_exchange_addrs)} 個非交易所地址的 TRX 入帳來源...")

    for addr in non_exchange_addrs:
        found = False

        # 優先使用 TronGrid 查詢 TRX 原生交易
        if trongrid_client and not found:
            trx_data = trongrid_client.get_trx_transfers(addr, limit=50)
            if trx_data and trx_data.get("data"):
                for tx in trx_data["data"]:
                    # TronGrid 原生交易格式：ret[0].contractRet == "SUCCESS"
                    ret = tx.get("ret", [{}])
                    if not ret or ret[0].get("contractRet") != "SUCCESS":
                        continue
                    contract = tx.get("raw_data", {}).get("contract", [{}])
                    if not contract:
                        continue
                    c = contract[0]
                    if c.get("type") != "TransferContract":
                        continue
                    param = c.get("parameter", {}).get("value", {})
                    to_hex = param.get("to_address", "")
                    owner_hex = param.get("owner_address", "")
                    amount_sun = param.get("amount", 0)
                    # 比對地址（TronGrid 原生交易使用 hex 地址）
                    # 需要轉換或使用 txID 中的資訊
                    # 簡化：直接用 MistTrack fallback（TRX 原生交易格式複雜）
                    pass

        # 使用 MistTrack 查詢 TRX 入帳
        if not found:
            tx_data = misttrack_client.get_transactions(addr, direction="in")
            time.sleep(RATE_LIMIT_DELAY)

            if not tx_data:
                continue

            in_list = tx_data.get("in", [])
            if not isinstance(in_list, list):
                continue

            for item in in_list:
                token = item.get("token", "")
                # TRX 入帳：token 為 TRX 或空（原生代幣）
                if token and token.upper() not in ("TRX", ""):
                    continue
                from_addr = item.get("address", "")
                if from_addr and from_addr != addr:
                    amount = _parse_amount(item.get("amount", 0))
                    if amount > 0:
                        trx_providers[addr] = from_addr
                        node = graph.nodes.get(addr)
                        alias = node.alias if node else addr[:12]
                        print(f"  {alias}: TRX 由 {from_addr[:12]}... 提供")
                        found = True
                        break

    print(f"[TRX Gas] 完成: 找到 {len(trx_providers)} 組 TRX 油費關聯")
    return trx_providers


def classify_wallets(graph: FlowGraph) -> None:
    """自動分類中繼/獲利錢包，寫入 FlowNode.wallet_type。

    分類規則：
    - 中繼錢包 (relay)：total_spent / total_received > 0.8 且同時有入帳和出帳邊
    - 獲利錢包 (profit)：有反向小額轉帳至上游層（即向較低 layer 地址轉帳）
    - 車手錢包 (mule)：Layer 0 起始地址（被害人轉匯之第一層收款錢包）
    """
    # 建立邊的方向索引
    outgoing: dict[str, set[str]] = {}  # addr -> {to_addrs}
    incoming: dict[str, set[str]] = {}  # addr -> {from_addrs}
    for edge in graph.edges:
        outgoing.setdefault(edge.from_address, set()).add(edge.to_address)
        incoming.setdefault(edge.to_address, set()).add(edge.from_address)

    for addr, node in graph.nodes.items():
        if node.is_exchange or node.layer == 0:
            continue

        has_in = addr in incoming
        has_out = addr in outgoing

        # 獲利錢包判定：有向上游層（layer 更小）的轉帳
        if has_out:
            for to_addr in outgoing[addr]:
                to_node = graph.nodes.get(to_addr)
                if to_node and to_node.layer < node.layer:
                    node.wallet_type = "profit"
                    break

        if node.wallet_type:
            continue

        # 中繼錢包判定：高比例轉出 + 雙向邊
        if has_in and has_out and node.total_received > 0:
            spend_ratio = node.total_spent / node.total_received
            if spend_ratio > 0.8:
                node.wallet_type = "relay"

    classified = sum(1 for n in graph.nodes.values() if n.wallet_type)
    print(f"[Classify] 自動分類完成: {classified} 個錢包已標註類型")
