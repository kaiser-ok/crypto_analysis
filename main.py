#!/usr/bin/env python3
"""主程式：串接抓取、擷取、驗證模組，輸出 CSV 與 HTML 報告。"""

import argparse
import csv
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # 載入 .env 檔案

import config
from scraper import Scraper
from extractor import extract_addresses
from validator import validate_addresses, ValidationResult


def write_csv(results: list[ValidationResult], output_path: str) -> None:
    """將驗證結果寫入 CSV 檔案。"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "案號",
            "法院",
            "原始地址",
            "是否有效",
            "錯誤類型",
            "建議修正",
            "前後文",
        ])
        for r in results:
            writer.writerow([
                r.case_id,
                r.court,
                r.address,
                "是" if r.is_valid else "否",
                r.error_type.value,
                " | ".join(r.suggestions) if r.suggestions else "",
                r.context,
            ])


def print_summary(results: list[ValidationResult]) -> None:
    """印出摘要統計。"""
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    invalid = total - valid
    with_suggestions = sum(1 for r in results if r.suggestions)

    print("\n" + "=" * 60)
    print(f"  擷取到的 TRON 地址總數：{total}")
    print(f"  有效地址：{valid}")
    print(f"  無效地址：{invalid}")
    print(f"  有修正建議的無效地址：{with_suggestions}")
    print("=" * 60)


def run_flow_report(args) -> None:
    """執行幣流分析報告生成。"""
    from misttrack import MistTrackClient
    from flow_tracer import trace_flow, CaseInfo
    from flow_report import generate_flow_report

    if not args.misttrack_key:
        print("[!] 幣流報告需要 --misttrack-key")
        sys.exit(1)

    if not args.source_address:
        print("[!] 幣流報告需要 --source-address")
        sys.exit(1)

    # 初始化 MistTrack
    mt_client = MistTrackClient(args.misttrack_key)

    # 初始化 Moralis（可選）
    moralis_client = None
    if args.moralis_key:
        from moralis import MoralisClient
        moralis_client = MoralisClient(args.moralis_key)

    # 初始化 TronGrid（預設啟用，無 key 也可使用）
    from trongrid import TronGridClient
    trongrid_client = TronGridClient(api_key=args.trongrid_key)

    # 案件資訊
    # 解析 analyst / reviewer（格式："職稱 姓名" 或 "姓名"）
    analyst_name, analyst_rank = _parse_person(args.analyst)
    reviewer_name, reviewer_rank = _parse_person(args.reviewer)

    case_info = CaseInfo(
        agency=args.agency,
        division=args.division,
        case_type=args.case_type,
        case_number=args.case_number,
        analyst_name=analyst_name,
        analyst_rank=analyst_rank,
        reviewer_name=reviewer_name,
        reviewer_rank=reviewer_rank,
        request_date=args.request_date or datetime.now().strftime("%Y年%m月%d日"),
        description=args.description,
        coin_type=args.coin,
        source_addresses=args.source_address,
    )

    # 時間範圍轉換
    min_timestamp = _date_to_ms_timestamp(args.start_date)
    max_timestamp = _date_to_ms_timestamp(args.end_date, end_of_day=True)
    target_exchange = args.target_exchange

    # 對每個起始地址追蹤
    for source_addr in args.source_address:
        print(f"\n{'='*60}")
        print(f"[FlowReport] 追蹤地址: {source_addr}")
        print(f"{'='*60}")

        # BFS 追蹤
        graph = trace_flow(
            source_address=source_addr,
            coin_type=args.coin,
            misttrack_client=mt_client,
            max_depth=args.max_depth,
            moralis_client=moralis_client,
            trongrid_client=trongrid_client,
            top_n=args.top_n,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            target_exchange=target_exchange,
        )

        # 產生報告
        timestamp = datetime.now().strftime("%Y%m%d")
        addr_short = source_addr[:8]
        output_path = os.path.join(
            config.OUTPUT_DIR,
            f"flow_report_{timestamp}_{addr_short}.html",
        )

        result_path = generate_flow_report(graph, case_info, output_path)
        print(f"\n[FlowReport] 報告已儲存至：{result_path}")
        print(f"  用瀏覽器開啟：file://{os.path.abspath(result_path)}")


def _date_to_ms_timestamp(date_str: str, end_of_day: bool = False) -> int:
    """將 YYYY-MM-DD 格式的日期轉為毫秒 Unix timestamp。

    end_of_day: True 時設為當天 23:59:59.999。
    回傳 0 表示輸入為空。
    """
    if not date_str:
        return 0
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
        return int(dt.timestamp() * 1000)
    except ValueError:
        print(f"[!] 日期格式錯誤：{date_str}，應為 YYYY-MM-DD")
        return 0


def run_exchange_report(args) -> None:
    """執行交易所調閱用幣流分析報告生成。"""
    from misttrack import MistTrackClient
    from flow_tracer import trace_flow, CaseInfo, analyze_trx_gas
    from exchange_report import generate_exchange_report

    if not args.misttrack_key:
        print("[!] 交易所調閱報告需要 --misttrack-key")
        sys.exit(1)

    if not args.source_address:
        print("[!] 交易所調閱報告需要 --source-address")
        sys.exit(1)

    # 時間範圍轉換
    min_timestamp = _date_to_ms_timestamp(args.start_date)
    max_timestamp = _date_to_ms_timestamp(args.end_date, end_of_day=True)
    target_exchange = args.target_exchange

    if min_timestamp or max_timestamp:
        print(f"[ExchangeReport] 犯罪時間範圍: {args.start_date or '不限'} ~ {args.end_date or '不限'}")
    if target_exchange:
        print(f"[ExchangeReport] 目標交易所: {target_exchange}")

    # 初始化 MistTrack
    mt_client = MistTrackClient(args.misttrack_key)

    # 初始化 Moralis（可選）
    moralis_client = None
    if args.moralis_key:
        from moralis import MoralisClient
        moralis_client = MoralisClient(args.moralis_key)

    # 初始化 TronGrid（預設啟用）
    from trongrid import TronGridClient
    trongrid_client = TronGridClient(api_key=args.trongrid_key)

    # 案件資訊
    analyst_name, analyst_rank = _parse_person(args.analyst)
    reviewer_name, reviewer_rank = _parse_person(args.reviewer)

    case_info = CaseInfo(
        agency=args.agency,
        division=args.division,
        case_type=args.case_type,
        case_number=args.case_number,
        analyst_name=analyst_name,
        analyst_rank=analyst_rank,
        reviewer_name=reviewer_name,
        reviewer_rank=reviewer_rank,
        request_date=args.request_date or datetime.now().strftime("%Y年%m月%d日"),
        description=args.description,
        coin_type=args.coin,
        source_addresses=args.source_address,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        target_exchange=target_exchange,
    )

    # 對每個起始地址追蹤
    for source_addr in args.source_address:
        print(f"\n{'='*60}")
        print(f"[ExchangeReport] 追蹤地址: {source_addr}")
        print(f"{'='*60}")

        # BFS 追蹤
        graph = trace_flow(
            source_address=source_addr,
            coin_type=args.coin,
            misttrack_client=mt_client,
            max_depth=args.max_depth,
            moralis_client=moralis_client,
            trongrid_client=trongrid_client,
            top_n=args.top_n,
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            target_exchange=target_exchange,
        )

        # TRX 油費關聯分析
        print(f"\n[ExchangeReport] 執行 TRX 油費關聯分析...")
        trx_providers = analyze_trx_gas(graph, mt_client, trongrid_client=trongrid_client)

        # 產生報告
        timestamp = datetime.now().strftime("%Y%m%d")
        addr_short = source_addr[:8]
        output_path = os.path.join(
            config.OUTPUT_DIR,
            f"exchange_report_{timestamp}_{addr_short}.html",
        )

        result_path = generate_exchange_report(
            graph, case_info, output_path, trx_providers=trx_providers,
        )
        print(f"\n[ExchangeReport] 報告已儲存至：{result_path}")
        print(f"  用瀏覽器開啟：file://{os.path.abspath(result_path)}")


def _parse_person(text: str) -> tuple[str, str]:
    """解析「職稱 姓名」格式，回傳 (name, rank)。"""
    if not text:
        return ("", "")
    parts = text.strip().split(None, 1)
    if len(parts) == 2:
        return (parts[1], parts[0])
    return (parts[0], "")


def main():
    parser = argparse.ArgumentParser(
        description="台灣詐欺案判決書加密貨幣帳號驗證工具",
    )

    # 模式選擇
    parser.add_argument(
        "--flow-report",
        action="store_true",
        help="幣流分析報告模式（需 --source-address, --misttrack-key）",
    )
    parser.add_argument(
        "--exchange-report",
        action="store_true",
        help="交易所調閱用幣流分析報告模式（需 --source-address, --misttrack-key）",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="啟動 Flask Web Server（http://localhost:5001）",
    )

    # --- 原有參數 ---
    parser.add_argument(
        "--date-start",
        default=config.DEFAULT_DATE_START,
        help=f"搜尋起始日期（民國年 YYYMMDD），預設 {config.DEFAULT_DATE_START}",
    )
    parser.add_argument(
        "--date-end",
        default=config.DEFAULT_DATE_END,
        help=f"搜尋結束日期（民國年 YYYMMDD），預設 {config.DEFAULT_DATE_END}",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=config.MAX_PAGES,
        help=f"最大抓取頁數，預設 {config.MAX_PAGES}",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=config.REQUEST_DELAY,
        help=f"請求間隔秒數，預設 {config.REQUEST_DELAY}",
    )
    parser.add_argument(
        "--output",
        default=os.path.join(config.OUTPUT_DIR, config.OUTPUT_CSV),
        help="輸出 CSV 路徑",
    )
    parser.add_argument(
        "--html",
        default=os.path.join(config.OUTPUT_DIR, "report.html"),
        help="輸出 HTML 報告路徑",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="不產生 HTML 報告（跳過 tron API 驗證）",
    )
    parser.add_argument(
        "--misttrack-key",
        default=os.environ.get("MISTTRACK_KEY", ""),
        help="MistTrack API key（用於風險分析與資金流向），可用環境變數 MISTTRACK_KEY",
    )

    # --- 幣流報告參數 ---
    parser.add_argument(
        "--source-address",
        nargs="+",
        default=[],
        help="起始追蹤地址（可多個）",
    )
    parser.add_argument(
        "--coin",
        default=config.FLOW_REPORT_DEFAULT_COIN,
        help=f"幣別，預設 {config.FLOW_REPORT_DEFAULT_COIN}",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=config.FLOW_REPORT_MAX_DEPTH,
        help=f"最大追蹤深度，預設 {config.FLOW_REPORT_MAX_DEPTH}",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=0,
        help="每個節點只追蹤金額/交易次數前 N 的下游地址（0=不限制），可大幅降低 API 成本",
    )
    parser.add_argument(
        "--start-date",
        default="",
        help="犯罪時間起始日（格式 YYYY-MM-DD），限縮起始地址的交易查詢範圍",
    )
    parser.add_argument(
        "--end-date",
        default="",
        help="犯罪時間結束日（格式 YYYY-MM-DD），限縮起始地址的交易查詢範圍",
    )
    parser.add_argument(
        "--target-exchange",
        default="",
        help="目標交易所關鍵字（如 maicoin、binance），僅保留通往該交易所的路徑",
    )
    parser.add_argument(
        "--moralis-key",
        default=os.environ.get("MORALIS_KEY", ""),
        help="Moralis API key（補充鏈上交易明細），可用環境變數 MORALIS_KEY",
    )
    parser.add_argument(
        "--trongrid-key",
        default=os.environ.get("TRONGRID_KEY", ""),
        help="TronGrid API key（可選，無 key 也可使用但有限速），可用環境變數 TRONGRID_KEY",
    )
    parser.add_argument(
        "--agency",
        default="",
        help="機關名稱（如：新北市政府警察局）",
    )
    parser.add_argument(
        "--division",
        default="",
        help="分局名稱（如：刑事警察大隊）",
    )
    parser.add_argument(
        "--case-type",
        default="詐欺",
        help="案類，預設「詐欺」",
    )
    parser.add_argument(
        "--case-number",
        default="",
        help="案號（如：113年度金訴字第1375號）",
    )
    parser.add_argument(
        "--analyst",
        default="",
        help="分析人員（格式：「職稱 姓名」如「偵查佐 王大明」）",
    )
    parser.add_argument(
        "--reviewer",
        default="",
        help="審核人員（格式：「職稱 姓名」如「隊長 李小華」）",
    )
    parser.add_argument(
        "--request-date",
        default="",
        help="申請日期（如：2024年03月15日），預設為今日",
    )
    parser.add_argument(
        "--description",
        default="",
        help="案件描述",
    )

    args = parser.parse_args()

    # 判斷執行模式
    if args.server:
        import server
        server.run()
        return

    if args.flow_report:
        run_flow_report(args)
        return

    if args.exchange_report:
        run_exchange_report(args)
        return

    # --- 原有流程：判決書抓取 + 驗證 ---

    # 1. 抓取判決書
    print("[1/4] 抓取判決書...")
    scraper = Scraper(
        date_start=args.date_start,
        date_end=args.date_end,
        max_pages=args.max_pages,
        delay=args.delay,
    )
    judgments = scraper.scrape()

    if not judgments:
        print("[!] 未找到任何判決書，結束。")
        sys.exit(0)

    # 2. 擷取 TRON 地址
    print("\n[2/4] 擷取 TRON 地址...")
    extracted = extract_addresses(judgments)
    print(f"  找到 {len(extracted)} 個疑似 TRON 地址")

    if not extracted:
        print("[!] 未找到任何 TRON 地址，結束。")
        sys.exit(0)

    # 3. 基本驗證 + CSV
    print("\n[3/4] 基本驗證（Base58Check）...")
    results = validate_addresses(extracted)
    write_csv(results, args.output)
    print(f"  CSV 報告已儲存至：{args.output}")
    print_summary(results)

    # 4. HTML 報告（整合 tron API）
    if not args.no_html:
        print(f"\n[4/4] 產生 HTML 報告（透過 tron-ocr-verify API 驗證）...")
        try:
            from report import verify_all, generate_html
            verified = verify_all(extracted, misttrack_api_key=args.misttrack_key)
            generate_html(verified, args.html)
            print(f"  HTML 報告已儲存至：{args.html}")
            print(f"  用瀏覽器開啟：file://{os.path.abspath(args.html)}")
        except Exception as e:
            print(f"  [!] HTML 報告產生失敗：{e}")
            print("  請確認 tron-ocr-verify API 已啟動 (npm start)")
    else:
        print("\n[4/4] 跳過 HTML 報告。")


if __name__ == "__main__":
    main()
