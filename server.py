"""Flask Web Server — 提供地址驗證報告 + 幣流報告 API + 互動式探索器。"""

import hashlib
import logging
import os
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, request, send_from_directory

load_dotenv()

import config

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
log = logging.getLogger("server")

app = Flask(__name__)

OUTPUT_DIR = os.path.abspath(config.OUTPUT_DIR)

# 背景任務追蹤: job_id -> {"status": "running"|"done"|"error", "url": ..., "error": ...}
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()

# 互動式探索器 session 狀態
_explorer_sessions: dict[str, dict] = {}
_explorer_lock = threading.Lock()


@app.route("/")
def index():
    """提供主報告頁面。"""
    return send_from_directory(OUTPUT_DIR, "report.html")


@app.route("/output/<path:filename>")
def serve_output(filename):
    """提供 output/ 下的靜態檔案。"""
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/explorer")
def explorer_page():
    """提供互動式幣流探索器頁面。"""
    from explorer import generate_explorer_html
    resp = make_response(generate_explorer_html())
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@app.route("/exchange-report")
def exchange_report_page():
    """提供交易所調閱報告前端頁面。"""
    from exchange_report_page import generate_exchange_report_page_html
    resp = make_response(generate_exchange_report_page_html())
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


@app.route("/api/judgment", methods=["GET"])
def judgment_api():
    """根據 case_id 回傳快取的判決書全文。"""
    case_id = request.args.get("case_id", "").strip()
    if not case_id:
        return jsonify({"error": "缺少 case_id 參數"}), 400

    cache_hash = hashlib.md5(case_id.encode()).hexdigest()
    cache_path = os.path.join(config.CACHE_DIR, f"{cache_hash}.txt")

    if not os.path.isfile(cache_path):
        return jsonify({"error": "找不到此判決書快取"}), 404

    with open(cache_path, "r", encoding="utf-8") as f:
        text = f.read()

    return jsonify({"case_id": case_id, "text": text})


@app.route("/api/flow-report", methods=["POST"])
def flow_report_api():
    """接收地址資訊，背景執行幣流追蹤，立即回傳 job_id。"""
    data = request.get_json(force=True)
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"error": "缺少 address 參數"}), 400

    misttrack_key = os.environ.get("MISTTRACK_KEY", "")
    if not misttrack_key:
        return jsonify({"error": "伺服器未設定 MISTTRACK_KEY 環境變數"}), 500

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}

    # 啟動背景執行緒
    t = threading.Thread(
        target=_run_flow_job,
        args=(job_id, address, data, misttrack_key),
        daemon=True,
    )
    t.start()

    return jsonify({"status": "accepted", "job_id": job_id})


@app.route("/api/flow-report/<job_id>", methods=["GET"])
def flow_report_status(job_id):
    """查詢背景任務狀態。"""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "找不到此任務"}), 404
    return jsonify(job)


# ============================================================
# 案情分析 API
# ============================================================

@app.route("/api/case-analysis", methods=["POST"])
def case_analysis_api():
    """執行案情分析（若已分析則回傳快取結果）。"""
    from case_analyzer import analyze_case
    from dataclasses import asdict

    data = request.get_json(force=True)
    case_id = data.get("case_id", "").strip()
    court = data.get("court", "").strip()

    if not case_id:
        return jsonify({"error": "缺少 case_id 參數"}), 400

    address_corrections = data.get("address_corrections", {})

    try:
        analysis = analyze_case(case_id, court=court, address_corrections=address_corrections)
        return jsonify(asdict(analysis))
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        log.error(f"案情分析失敗: {e}")
        log.error(traceback.format_exc())
        return jsonify({"error": f"案情分析失敗: {e}"}), 500


@app.route("/api/case-analysis", methods=["GET"])
def case_analysis_get():
    """查詢已存在的案情分析結果。"""
    from case_analyzer import load_case_analysis
    from dataclasses import asdict

    case_id = request.args.get("case_id", "").strip()
    if not case_id:
        return jsonify({"error": "缺少 case_id 參數"}), 400

    analysis = load_case_analysis(case_id)
    if not analysis:
        return jsonify({"error": "此案件尚未分析"}), 404

    return jsonify(asdict(analysis))


@app.route("/api/case-flow-report", methods=["POST"])
def case_flow_report_api():
    """基於案情分析結果，執行案件幣流追蹤（背景任務）。"""
    data = request.get_json(force=True)
    case_id = data.get("case_id", "").strip()
    address = data.get("address", "").strip()

    if not case_id:
        return jsonify({"error": "缺少 case_id 參數"}), 400
    if not address:
        return jsonify({"error": "缺少 address 參數"}), 400

    misttrack_key = os.environ.get("MISTTRACK_KEY", "")
    if not misttrack_key:
        return jsonify({"error": "伺服器未設定 MISTTRACK_KEY 環境變數"}), 500

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}

    t = threading.Thread(
        target=_run_case_flow_job,
        args=(job_id, case_id, address, data, misttrack_key),
        daemon=True,
    )
    t.start()

    return jsonify({"status": "accepted", "job_id": job_id})


# ============================================================
# 交易所調閱報告 API
# ============================================================

@app.route("/api/exchange-report", methods=["POST"])
def exchange_report_api():
    """接收地址/案件參數，背景執行 trace + TRX 分析 + 生成交易所調閱報告。"""
    data = request.get_json(force=True)
    address = data.get("address", "").strip()
    if not address:
        return jsonify({"error": "缺少 address 參數"}), 400

    misttrack_key = os.environ.get("MISTTRACK_KEY", "")
    if not misttrack_key:
        return jsonify({"error": "伺服器未設定 MISTTRACK_KEY 環境變數"}), 500

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}

    t = threading.Thread(
        target=_run_exchange_report_job,
        args=(job_id, address, data, misttrack_key),
        daemon=True,
    )
    t.start()

    return jsonify({"status": "accepted", "job_id": job_id})


@app.route("/api/exchange-report/<job_id>", methods=["GET"])
def exchange_report_status(job_id):
    """查詢交易所調閱報告任務狀態。"""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "找不到此任務"}), 404
    return jsonify(job)


# ============================================================
# 互動式探索器 API
# ============================================================

@app.route("/api/explorer/start", methods=["POST"])
def explorer_start():
    """建立探索 session，查詢根節點資訊。"""
    from misttrack import MistTrackClient
    from flow_tracer import (
        FlowGraph, FlowNode, fetch_node_info, _is_exchange_label, _make_alias,
    )

    data = request.get_json(force=True)
    address = data.get("address", "").strip()
    coin = data.get("coin", config.FLOW_REPORT_DEFAULT_COIN)

    if not address:
        return jsonify({"error": "缺少 address 參數"}), 400

    misttrack_key = os.environ.get("MISTTRACK_KEY", "")
    if not misttrack_key:
        return jsonify({"error": "伺服器未設定 MISTTRACK_KEY 環境變數"}), 500

    from misttrack import RateLimitError

    mt_client = MistTrackClient(misttrack_key)

    # 查詢節點資訊 (3 API calls: labels + risk_score + overview)
    try:
        info = fetch_node_info(address, mt_client)
    except RateLimitError as e:
        return jsonify({"error": f"MistTrack API 每日額度已用完，請 {e.retry_after // 60} 分鐘後再試"}), 429

    # 建立 FlowGraph 並加入根節點
    graph = FlowGraph(source_address=address, coin_type=coin)
    source_node = FlowNode(
        address=address, layer=0, alias="A",
        labels=info["labels"], risk_score=info["risk_score"],
        risk_level=info["risk_level"], balance=info["balance"],
        total_received=info["total_received"], total_spent=info["total_spent"],
        is_exchange=info["is_exchange"],
    )
    graph.nodes[address] = source_node
    graph.layers[0] = [address]
    graph.alias_map[address] = "A"

    # 查詢 overview 取得額外欄位
    try:
        overview = mt_client.get_overview(address) or {}
    except RateLimitError:
        overview = {}

    # 建立 session
    session_id = uuid.uuid4().hex[:12]
    with _explorer_lock:
        _cleanup_expired_sessions()
        _explorer_sessions[session_id] = {
            "graph": graph,
            "client": mt_client,
            "coin": coin,
            "created_at": time.time(),
            "alias_counters": {0: 1},  # layer -> next index
        }

    node_info = {
        "address": address,
        "alias": "A",
        "labels": info["labels"],
        "risk_score": info["risk_score"],
        "risk_level": info["risk_level"],
        "balance": info["balance"],
        "total_received": info["total_received"],
        "total_spent": info["total_spent"],
        "is_exchange": info["is_exchange"],
        "first_seen": overview.get("first_seen", 0),
        "last_seen": overview.get("last_seen", 0),
        "txs_count": overview.get("txs_count", 0),
        "received_txs_count": overview.get("received_txs_count", 0),
        "spent_txs_count": overview.get("spent_txs_count", 0),
    }

    log.info(f"[Explorer] 新 session {session_id}: {address[:16]}... "
             f"risk={info['risk_score']} labels={info['labels']}")

    return jsonify({"session_id": session_id, "node_info": node_info})


@app.route("/api/explorer/expand", methods=["POST"])
def explorer_expand():
    """展開某節點的 IN 或 OUT 交易對手方。"""
    from misttrack import RATE_LIMIT_DELAY, RateLimitError
    from flow_tracer import (
        FlowNode, FlowEdge, parse_downstream, parse_upstream,
        _is_exchange_label, _make_alias,
    )

    data = request.get_json(force=True)
    session_id = data.get("session_id", "")
    address = data.get("address", "").strip()
    direction = data.get("direction", "out")

    if direction not in ("in", "out"):
        return jsonify({"error": "direction 須為 'in' 或 'out'"}), 400

    session = _get_session(session_id)
    if not session:
        return jsonify({"error": "session 不存在或已過期"}), 404

    graph = session["graph"]
    client = session["client"]
    coin = session["coin"]
    alias_counters = session["alias_counters"]

    # 呼叫 MistTrack transactions_investigation (1 API call)
    try:
        tx_data = client.get_transactions(address, direction=direction)
    except RateLimitError as e:
        return jsonify({"error": f"MistTrack API 每日額度已用完，請 {e.retry_after // 60} 分鐘後再試"}), 429
    time.sleep(RATE_LIMIT_DELAY)

    counterparties = []

    if direction == "out":
        parsed = parse_downstream(tx_data, address, coin)
        # parsed: [{"to_address", "amount", "token", "tx_hash_list", "timestamp", "label"}]
        # 按金額排序（大到小）
        parsed.sort(key=lambda x: x["amount"], reverse=True)

        parent_node = graph.nodes.get(address)
        parent_layer = parent_node.layer if parent_node else 0
        child_layer = parent_layer + 1

        for item in parsed:
            to_addr = item["to_address"]
            label = item.get("label", "")
            labels = [label] if label else []
            is_exchange = _is_exchange_label(labels)

            # 分配 alias（若尚未存在）
            if to_addr not in graph.nodes:
                idx = alias_counters.get(child_layer, 0)
                alias = _make_alias(child_layer, idx)
                alias_counters[child_layer] = idx + 1

                node = FlowNode(
                    address=to_addr, layer=child_layer, alias=alias,
                    labels=labels, is_exchange=is_exchange,
                )
                graph.nodes[to_addr] = node
                graph.layers.setdefault(child_layer, []).append(to_addr)
                graph.alias_map[to_addr] = alias
            else:
                node = graph.nodes[to_addr]
                # 更新 labels（如果之前沒有）
                if labels and not node.labels:
                    node.labels = labels
                    node.is_exchange = is_exchange

            # 記錄 edges
            tx_hash_list = item.get("tx_hash_list", [])
            if tx_hash_list:
                for txh in tx_hash_list:
                    graph.edges.append(FlowEdge(
                        tx_hash=txh, from_address=address, to_address=to_addr,
                        amount=item["amount"] / len(tx_hash_list),
                        token=item["token"], timestamp=item["timestamp"],
                    ))
            else:
                graph.edges.append(FlowEdge(
                    tx_hash=item.get("tx_hash", ""), from_address=address,
                    to_address=to_addr, amount=item["amount"],
                    token=item["token"], timestamp=item["timestamp"],
                ))

            counterparties.append({
                "address": to_addr,
                "alias": graph.alias_map.get(to_addr, ""),
                "labels": graph.nodes[to_addr].labels,
                "is_exchange": graph.nodes[to_addr].is_exchange,
                "amount": item["amount"],
                "token": item["token"],
                "tx_count": len(tx_hash_list) or 1,
                "tx_hash_list": tx_hash_list,
                "timestamp": item["timestamp"],
            })

    else:  # direction == "in"
        parsed = parse_upstream(tx_data, address, coin)
        parsed.sort(key=lambda x: x["amount"], reverse=True)

        parent_node = graph.nodes.get(address)
        parent_layer = parent_node.layer if parent_node else 0
        child_layer = parent_layer + 1

        for item in parsed:
            from_addr = item["from_address"]
            label = item.get("label", "")
            labels = [label] if label else []
            is_exchange = _is_exchange_label(labels)

            if from_addr not in graph.nodes:
                idx = alias_counters.get(child_layer, 0)
                alias = _make_alias(child_layer, idx)
                alias_counters[child_layer] = idx + 1

                node = FlowNode(
                    address=from_addr, layer=child_layer, alias=alias,
                    labels=labels, is_exchange=is_exchange,
                )
                graph.nodes[from_addr] = node
                graph.layers.setdefault(child_layer, []).append(from_addr)
                graph.alias_map[from_addr] = alias
            else:
                node = graph.nodes[from_addr]
                if labels and not node.labels:
                    node.labels = labels
                    node.is_exchange = is_exchange

            # 記錄 edges (from → to=address)
            tx_hash_list = item.get("tx_hash_list", [])
            if tx_hash_list:
                for txh in tx_hash_list:
                    graph.edges.append(FlowEdge(
                        tx_hash=txh, from_address=from_addr, to_address=address,
                        amount=item["amount"] / len(tx_hash_list),
                        token=item["token"], timestamp=item["timestamp"],
                    ))
            else:
                graph.edges.append(FlowEdge(
                    tx_hash=item.get("tx_hash", ""), from_address=from_addr,
                    to_address=address, amount=item["amount"],
                    token=item["token"], timestamp=item["timestamp"],
                ))

            counterparties.append({
                "address": from_addr,
                "alias": graph.alias_map.get(from_addr, ""),
                "labels": graph.nodes[from_addr].labels,
                "is_exchange": graph.nodes[from_addr].is_exchange,
                "amount": item["amount"],
                "token": item["token"],
                "tx_count": len(tx_hash_list) or 1,
                "tx_hash_list": tx_hash_list,
                "timestamp": item["timestamp"],
            })

    log.info(f"[Explorer] expand {address[:12]}... {direction}: "
             f"{len(counterparties)} counterparties")

    return jsonify({"counterparties": counterparties})


@app.route("/api/explorer/node-detail", methods=["POST"])
def explorer_node_detail():
    """延遲載入：查詢某節點的詳細資訊（risk + overview）。"""
    from misttrack import RATE_LIMIT_DELAY, RateLimitError
    from flow_tracer import fetch_node_info, _is_exchange_label

    data = request.get_json(force=True)
    session_id = data.get("session_id", "")
    address = data.get("address", "").strip()

    session = _get_session(session_id)
    if not session:
        return jsonify({"error": "session 不存在或已過期"}), 404

    client = session["client"]
    graph = session["graph"]

    # 3 API calls: labels + risk_score + overview
    try:
        info = fetch_node_info(address, client)
    except RateLimitError as e:
        return jsonify({"error": f"MistTrack API 每日額度已用完，請 {e.retry_after // 60} 分鐘後再試"}), 429

    # 更新 graph 中的節點
    node = graph.nodes.get(address)
    if node:
        node.labels = info["labels"] or node.labels
        node.risk_score = info["risk_score"]
        node.risk_level = info["risk_level"]
        node.balance = info["balance"]
        node.total_received = info["total_received"]
        node.total_spent = info["total_spent"]
        node.is_exchange = info["is_exchange"] or node.is_exchange

    # 取得 overview 額外欄位
    try:
        overview = client.get_overview(address) or {}
    except RateLimitError:
        overview = {}
    time.sleep(RATE_LIMIT_DELAY)

    result = {
        "address": address,
        "labels": info["labels"],
        "risk_score": info["risk_score"],
        "risk_level": info["risk_level"],
        "balance": info["balance"],
        "total_received": info["total_received"],
        "total_spent": info["total_spent"],
        "is_exchange": info["is_exchange"],
        "first_seen": overview.get("first_seen", 0),
        "last_seen": overview.get("last_seen", 0),
        "txs_count": overview.get("txs_count", 0),
        "received_txs_count": overview.get("received_txs_count", 0),
        "spent_txs_count": overview.get("spent_txs_count", 0),
    }

    log.info(f"[Explorer] node-detail {address[:12]}... "
             f"risk={info['risk_score']} labels={info['labels']}")

    return jsonify(result)


@app.route("/api/explorer/report", methods=["POST"])
def explorer_report():
    """使用 session 中的 FlowGraph 產生警用報告。"""
    from flow_tracer import CaseInfo

    data = request.get_json(force=True)
    session_id = data.get("session_id", "")

    session = _get_session(session_id)
    if not session:
        return jsonify({"error": "session 不存在或已過期"}), 404

    graph = session["graph"]

    analyst_name, analyst_rank = _parse_person(data.get("analyst", ""))
    reviewer_name, reviewer_rank = _parse_person(data.get("reviewer", ""))

    case_info = CaseInfo(
        agency=data.get("agency", ""),
        division=data.get("division", ""),
        case_number=data.get("case_number", ""),
        analyst_name=analyst_name,
        analyst_rank=analyst_rank,
        reviewer_name=reviewer_name,
        reviewer_rank=reviewer_rank,
        request_date=datetime.now().strftime("%Y年%m月%d日"),
        coin_type=session["coin"],
        source_addresses=[graph.source_address],
    )

    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {"status": "running"}

    t = threading.Thread(
        target=_run_explorer_report_job,
        args=(job_id, graph, case_info),
        daemon=True,
    )
    t.start()

    return jsonify({"status": "accepted", "job_id": job_id})


def _run_explorer_report_job(job_id: str, graph, case_info):
    """背景產生探索器報告。"""
    log.info(f"[Explorer Report {job_id}] 開始產生報告...")
    try:
        from flow_report import generate_flow_report

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        addr_short = graph.source_address[:8]
        filename = f"flow_report_{timestamp}_{addr_short}.html"
        output_path = os.path.join(config.OUTPUT_DIR, filename)

        generate_flow_report(graph, case_info, output_path)

        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done",
                "filename": filename,
                "url": f"/output/{filename}",
            }
        log.info(f"[Explorer Report {job_id}] 完成: {filename}")

    except Exception as e:
        log.error(f"[Explorer Report {job_id}] 失敗: {e}")
        log.error(traceback.format_exc())
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "error": str(e)}


# ============================================================
# Explorer session helpers
# ============================================================

def _get_session(session_id: str) -> dict | None:
    """取得 session，若過期則移除並回傳 None。"""
    with _explorer_lock:
        session = _explorer_sessions.get(session_id)
        if not session:
            return None
        if time.time() - session["created_at"] > config.EXPLORER_SESSION_TIMEOUT:
            del _explorer_sessions[session_id]
            return None
        return session


def _cleanup_expired_sessions():
    """清理過期 session（須在 _explorer_lock 內呼叫）。"""
    now = time.time()
    expired = [
        sid for sid, s in _explorer_sessions.items()
        if now - s["created_at"] > config.EXPLORER_SESSION_TIMEOUT
    ]
    for sid in expired:
        del _explorer_sessions[sid]
        log.info(f"[Explorer] 清理過期 session: {sid}")


# ============================================================
# 原有 flow report helpers
# ============================================================

def _run_flow_job(job_id: str, address: str, data: dict, misttrack_key: str):
    """背景執行幣流追蹤 + 報告產生。"""
    log.info(f"[Job {job_id}] 開始: address={address[:16]}...")
    try:
        from misttrack import MistTrackClient
        from flow_tracer import trace_flow, CaseInfo
        from flow_report import generate_flow_report

        coin = data.get("coin", config.FLOW_REPORT_DEFAULT_COIN)
        max_depth = int(data.get("max_depth", config.FLOW_REPORT_MAX_DEPTH))

        log.info(f"[Job {job_id}] 初始化 API clients...")
        mt_client = MistTrackClient(misttrack_key)

        from trongrid import TronGridClient
        tg_client = TronGridClient(api_key=os.environ.get("TRONGRID_KEY", ""))

        analyst_name, analyst_rank = _parse_person(data.get("analyst", ""))
        reviewer_name, reviewer_rank = _parse_person(data.get("reviewer", ""))

        case_info = CaseInfo(
            agency=data.get("agency", ""),
            division=data.get("division", ""),
            case_number=data.get("case_number", ""),
            analyst_name=analyst_name,
            analyst_rank=analyst_rank,
            reviewer_name=reviewer_name,
            reviewer_rank=reviewer_rank,
            request_date=datetime.now().strftime("%Y年%m月%d日"),
            coin_type=coin,
            source_addresses=[address],
        )

        top_n = int(data.get("top_n", 0))
        log.info(f"[Job {job_id}] 開始 BFS trace_flow (max_depth={max_depth}, top_n={top_n})...")
        graph = trace_flow(
            source_address=address,
            coin_type=coin,
            misttrack_client=mt_client,
            max_depth=max_depth,
            trongrid_client=tg_client,
            top_n=top_n,
        )
        log.info(f"[Job {job_id}] trace_flow 完成: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        addr_short = address[:8]
        filename = f"flow_report_{timestamp}_{addr_short}.html"
        output_path = os.path.join(config.OUTPUT_DIR, filename)

        log.info(f"[Job {job_id}] 產生報告 → {filename}")
        generate_flow_report(graph, case_info, output_path)

        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done",
                "filename": filename,
                "url": f"/output/{filename}",
            }
        log.info(f"[Job {job_id}] 完成!")

    except Exception as e:
        log.error(f"[Job {job_id}] 失敗: {e}")
        log.error(traceback.format_exc())
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "error": str(e)}


def _run_exchange_report_job(
    job_id: str, address: str, data: dict, misttrack_key: str,
):
    """背景執行幣流追蹤 + TRX 分析 + 交易所調閱報告產生。"""
    log.info(f"[ExchangeReport {job_id}] 開始: address={address[:16]}...")
    try:
        from misttrack import MistTrackClient
        from flow_tracer import trace_flow, CaseInfo, analyze_trx_gas, prune_to_any_exchange
        from exchange_report import generate_exchange_report

        coin = data.get("coin", config.FLOW_REPORT_DEFAULT_COIN)
        max_depth = int(data.get("max_depth", config.FLOW_REPORT_MAX_DEPTH))

        mt_client = MistTrackClient(misttrack_key)

        from trongrid import TronGridClient
        tg_client = TronGridClient(api_key=os.environ.get("TRONGRID_KEY", ""))

        analyst_name, analyst_rank = _parse_person(data.get("analyst", ""))
        reviewer_name, reviewer_rank = _parse_person(data.get("reviewer", ""))

        top_n = int(data.get("top_n", 0))
        min_timestamp = int(data.get("min_timestamp", 0))
        max_timestamp = int(data.get("max_timestamp", 0))
        target_exchange = data.get("target_exchange", "")

        case_info = CaseInfo(
            agency=data.get("agency", ""),
            division=data.get("division", ""),
            case_number=data.get("case_number", ""),
            case_type=data.get("case_type", "詐欺"),
            analyst_name=analyst_name,
            analyst_rank=analyst_rank,
            reviewer_name=reviewer_name,
            reviewer_rank=reviewer_rank,
            request_date=datetime.now().strftime("%Y年%m月%d日"),
            description=data.get("description", ""),
            coin_type=coin,
            source_addresses=[address],
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            target_exchange=target_exchange,
        )

        log.info(f"[ExchangeReport {job_id}] BFS trace_flow (max_depth={max_depth}, top_n={top_n}, "
                 f"time={min_timestamp}~{max_timestamp}, target={target_exchange or '全部'})...")
        graph = trace_flow(
            source_address=address,
            coin_type=coin,
            misttrack_client=mt_client,
            max_depth=max_depth,
            trongrid_client=tg_client,
            top_n=top_n,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            target_exchange=target_exchange,
        )
        log.info(f"[ExchangeReport {job_id}] trace_flow 完成: "
                 f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # 交易所報告用途：即使未指定特定交易所，也剪枝只保留通往交易所的路徑
        if not target_exchange:
            log.info(f"[ExchangeReport {job_id}] 剪枝：只保留通往交易所的路徑...")
            prune_to_any_exchange(graph)
            log.info(f"[ExchangeReport {job_id}] 剪枝後: "
                     f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # TRX 油費關聯分析
        log.info(f"[ExchangeReport {job_id}] TRX 油費關聯分析...")
        trx_providers = analyze_trx_gas(graph, mt_client, trongrid_client=tg_client)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        addr_short = address[:8]
        filename = f"exchange_report_{timestamp}_{addr_short}.html"
        output_path = os.path.join(config.OUTPUT_DIR, filename)

        log.info(f"[ExchangeReport {job_id}] 產生報告 → {filename}")
        generate_exchange_report(graph, case_info, output_path, trx_providers=trx_providers)

        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done",
                "filename": filename,
                "url": f"/output/{filename}",
            }
        log.info(f"[ExchangeReport {job_id}] 完成!")

    except Exception as e:
        log.error(f"[ExchangeReport {job_id}] 失敗: {e}")
        log.error(traceback.format_exc())
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "error": str(e)}


def _run_case_flow_job(
    job_id: str, case_id: str, address: str, data: dict, misttrack_key: str,
):
    """背景執行案件幣流追蹤 + 報告產生。"""
    log.info(f"[CaseFlow {job_id}] 開始: case={case_id}, address={address[:16]}...")
    try:
        from case_analyzer import load_case_analysis
        from misttrack import MistTrackClient
        from flow_tracer import trace_flow, CaseInfo, prune_to_case_addresses
        from flow_report import generate_flow_report

        # 載入案情分析結果
        analysis = load_case_analysis(case_id)
        if not analysis:
            raise ValueError(f"案件 {case_id} 尚未進行案情分析")

        coin = data.get("coin", config.FLOW_REPORT_DEFAULT_COIN)
        max_depth = int(data.get("max_depth", 5))

        mt_client = MistTrackClient(misttrack_key)

        from trongrid import TronGridClient
        tg_client = TronGridClient(api_key=os.environ.get("TRONGRID_KEY", ""))

        # 收集案件相關地址
        case_addresses = set()
        for w in analysis.wallets:
            case_addresses.add(w["address"])

        log.info(f"[CaseFlow {job_id}] BFS trace_flow (max_depth={max_depth})...")
        graph = trace_flow(
            source_address=address,
            coin_type=coin,
            misttrack_client=mt_client,
            max_depth=max_depth,
            trongrid_client=tg_client,
        )
        log.info(f"[CaseFlow {job_id}] trace_flow 完成: "
                 f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # 剪枝：只保留案件相關地址的路徑
        if case_addresses:
            prune_to_case_addresses(graph, case_addresses)
            log.info(f"[CaseFlow {job_id}] 剪枝後: "
                     f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # 建立 CaseInfo
        analyst_name, analyst_rank = _parse_person(data.get("analyst", ""))
        reviewer_name, reviewer_rank = _parse_person(data.get("reviewer", ""))

        case_info = CaseInfo(
            agency=analysis.court,
            case_type=analysis.case_type or "詐欺",
            case_number=case_id,
            analyst_name=analyst_name,
            analyst_rank=analyst_rank,
            reviewer_name=reviewer_name,
            reviewer_rank=reviewer_rank,
            request_date=datetime.now().strftime("%Y年%m月%d日"),
            description=analysis.description,
            coin_type=coin,
            source_addresses=[address],
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        addr_short = address[:8]
        filename = f"case_flow_{timestamp}_{addr_short}.html"
        output_path = os.path.join(config.OUTPUT_DIR, filename)

        log.info(f"[CaseFlow {job_id}] 產生報告 → {filename}")
        generate_flow_report(graph, case_info, output_path)

        with _jobs_lock:
            _jobs[job_id] = {
                "status": "done",
                "filename": filename,
                "url": f"/output/{filename}",
            }
        log.info(f"[CaseFlow {job_id}] 完成!")

    except Exception as e:
        log.error(f"[CaseFlow {job_id}] 失敗: {e}")
        log.error(traceback.format_exc())
        with _jobs_lock:
            _jobs[job_id] = {"status": "error", "error": str(e)}


def _parse_person(text: str) -> tuple[str, str]:
    """解析「職稱 姓名」格式，回傳 (name, rank)。"""
    if not text:
        return ("", "")
    parts = text.strip().split(None, 1)
    if len(parts) == 2:
        return (parts[1], parts[0])
    return (parts[0], "")


def run(host="127.0.0.1", port=8888, debug=False):
    """啟動 Flask 伺服器。"""
    print(f"[Server] 啟動 http://{host}:{port}")
    print(f"[Server] 報告目錄：{OUTPUT_DIR}")
    print(f"[Server] 探索器: http://{host}:{port}/explorer")
    print(f"[Server] 交易所調閱報告: http://{host}:{port}/exchange-report")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run(debug=True)
