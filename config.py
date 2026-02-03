"""設定檔：搜尋條件、日期範圍、關鍵字等。"""

from datetime import date

# --- 司法院裁判書查詢系統 ---
BASE_URL = "https://judgment.judicial.gov.tw/FJUD/"
SEARCH_URL = BASE_URL + "Default_AD.aspx"
QUERY_URL = BASE_URL + "FJUD_QRY.aspx"
DATA_URL = BASE_URL + "data.aspx"

# --- 搜尋條件 ---
JUD_SYS = "M"          # M = 刑事
JUD_TITLE = "詐欺"     # 案由
# 全文關鍵字清單：每個關鍵字會各執行一次搜尋（系統不支援 OR），結果自動合併去重
FULL_TEXT_KEYWORDS = [
    "USDT",
    "TRON",
    "TRC20",
    "泰達幣",
]

# --- 日期範圍（民國年） ---
def _default_date_range():
    """回傳近一年的民國年月日範圍 (start, end)，格式 YYYMMDD。"""
    today = date.today()
    roc_year_end = today.year - 1911
    roc_year_start = roc_year_end - 1
    start = f"{roc_year_start}{today.month:02d}{today.day:02d}"
    end = f"{roc_year_end}{today.month:02d}{today.day:02d}"
    return start, end

DEFAULT_DATE_START, DEFAULT_DATE_END = _default_date_range()

# --- 抓取控制 ---
MAX_PAGES = 5           # 每次抓取結果頁數上限
REQUEST_DELAY = 2.0     # 請求間隔（秒）

# --- 輸出 ---
OUTPUT_DIR = "output"
OUTPUT_CSV = "tron_addresses.csv"
CACHE_DIR = "output/cache"

# --- Moralis API ---
MORALIS_API_BASE = "https://deep-index.moralis.io/api/v2.2"

# --- TronGrid API ---
TRONGRID_API_BASE = "https://api.trongrid.io"
TRONGRID_RATE_LIMIT = 0.2
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# --- 幣流報告預設值 ---
FLOW_REPORT_MAX_DEPTH = 4
FLOW_REPORT_DEFAULT_COIN = "USDT-TRC20"
FLOW_REPORT_DEFAULT_TOP_N = 3  # 每個節點只展開前 N 個下游地址（0=不限制）

# --- 互動式探索器 ---
EXPLORER_SESSION_TIMEOUT = 3600  # 1 hour

# --- 案件分析 ---
CASES_DIR = "output/cases"

# --- LLM API（案情分析用） ---
import os as _os
LLM_API_BASE = _os.environ.get("LLM_API_BASE", "http://192.168.30.46:8000/v1")
LLM_MODEL = _os.environ.get("LLM_MODEL", "/models/gpt-oss-120b")
