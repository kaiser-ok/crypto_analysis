# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Taiwan court judgment cryptocurrency address forensics tool. Scrapes fraud case judgments from judicial.gov.tw, extracts/validates TRON addresses, performs AML risk analysis via MistTrack, and generates flow tracing reports for law enforcement.

## Tech Stack

- Python 3.11+
- Flask (web server)
- MistTrack API (AML/risk analysis, multi-key round-robin support)
- TronGrid API (primary chain data source)
- Moralis API (supplementary chain data)
- OpenAI-compatible LLM API (case analysis)
- External dependency: tron-ocr-verify Node.js API at localhost:3000

## Key Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Default mode: scrape judgments + validate addresses + generate HTML report
python main.py

# Start web server at http://localhost:5001
python main.py --server

# Generate flow report (police format)
python main.py --flow-report --source-address <TRON_ADDR> --misttrack-key <KEY>

# Generate exchange inquiry report (A4 print-optimized)
python main.py --exchange-report --source-address <TRON_ADDR> --misttrack-key <KEY> \
    --agency "新北市政府警察局" --analyst "偵查佐 王大明"

# With time window and target exchange filtering
python main.py --flow-report --source-address <ADDR> --misttrack-key <KEY> \
    --start-date 2024-01-01 --end-date 2024-06-30 --target-exchange maicoin

# Run server standalone
python server.py
```

## Environment Variables

Set in `.env`:
- `MISTTRACK_KEY` — MistTrack API key(s), comma-separated for round-robin (required for flow tracing)
- `MORALIS_KEY` — Moralis API key (optional)
- `TRONGRID_KEY` — TronGrid API key (optional, improves rate limits)
- `LLM_API_BASE` — OpenAI-compatible endpoint for case analysis (default: http://192.168.30.46:8000/v1)
- `LLM_MODEL` — Model name for case analysis

## Architecture

### Data Flow Pipeline

```
judicial.gov.tw → scraper.py → extractor.py → validator.py → report.py (HTML)
                                                    ↓
                              flow_tracer.py (BFS) → flow_report.py / exchange_report.py
```

### Core Modules

| Module | Purpose |
|--------|---------|
| `flow_tracer.py` | BFS fund flow tracing engine with FlowNode/FlowEdge/FlowGraph data structures |
| `exchange_report.py` | Police A4 report: cover, wallet overview, flow diagrams, TRX gas analysis |
| `flow_report.py` | Police-format SVG flow diagrams with auto-generated Chinese narrative |
| `server.py` | Flask server with background job tracking for async flow analysis |
| `misttrack.py` | MistTrack client with multi-key round-robin on 429 errors |
| `trongrid.py` | TronGrid client with pagination (fingerprint cursor) and time filtering |

### Key Algorithms

**BFS Tracing** (`flow_tracer.trace_flow`):
- Layer 0 = source address (alias "A"), expands to B1/B2/C1/C2 by timestamp order
- Data source priority: TronGrid → MistTrack fallback
- Stops at exchange addresses (terminal nodes)
- Optional `top_n` filtering to limit downstream per node
- Optional `target_exchange` for path pruning via reverse BFS

**Wallet Classification** (`flow_tracer.classify_wallets`):
- **Relay**: `total_spent / total_received > 0.8` with both in/out edges
- **Profit**: Has outgoing edge to upstream layer (backward transfer)

**TRX Gas Analysis** (`flow_tracer.analyze_trx_gas`):
- Identifies TRX providers to each wallet → control/sponsorship relationship

## Code Conventions

- Language: Python docstrings and comments in Traditional Chinese
- Date format: ROC calendar (民國年 YYYMMDD) for court system queries
- Timestamps: milliseconds for API queries, seconds for storage
- HTML: Generated as Python f-strings, no template engine
- Rate limiting: 0.2s TronGrid, 1.0s MistTrack, 0.3s Moralis

## Server Routes

- `GET /` — Main HTML report
- `GET /explorer` — Interactive fund flow explorer
- `GET /exchange-report` — Exchange report form
- `POST /api/flow-report` — Async fund flow tracing (returns job_id)
- `GET /api/judgment?case_id=X` — Cached judgment text

## 幣流分析

參考文件：/Users/chunwencheng/Downloads/1-幣流分析報告.pdf /Users/chunwencheng/Downloads/4-幣流分析報告.pdf /Users/chunwencheng/Downloads/3-.幣流分析報告.pdf

1. 案件分析功能：由每個案子判決書，分析的被害人的貨幣帳號以及嫌犯的帳號資料，產生分析前的虛擬貨幣案件基本資料，存在案件的目錄下。
如果沒分析過，web UI 顯示'案情分析'按鈕,如果已經分析好了，可以在網頁上查看結果。
這部份如同參考文件的'一、 案件資訊', 我們希望從先前蒐集到的判決書去推出'案件資訊'
2.有了基本資料後，透過API 去分析實際幣流，並產生幣流分析圖。此分析圖，最大預設5層，與案件資訊無關的帳號，不必放進來

## exchange_report.py 演算法

### 報告結構

交易所調閱用報告 (`generate_exchange_report`) 產生 A4 列印最佳化 HTML，結構如下：

1. **封面** — 機關名稱、案號、案類、分析/審核人員、ROC 日期
2. **目錄 + 免責聲明** — 來自 `templates/disclaimer.py`
3. **一、案件資訊** — 承辦單位、幣別、時間範圍、錢包地址清單（含層別與角色）、交易序號列表
4. **錢包概況表** — 每個地址的餘額、首次/最近交易時間、收入/支出總額與次數
5. **二、分析情形**
   - （一）幣流視覺化圖 — SVG 圖 + 自動生成中文敘述
   - （二）各錢包態樣分析 — 每個錢包的角色、收支比例、風險等級
   - （三）錢包間關聯繫屬及支配情形 — TRX 油費關聯分析 + 資金流向從屬關係
   - （四）結論研判 — 統計總金額、中繼/獲利錢包、交易所流入情況
6. **三、結論及建議事項** — 摘要 + 建議向交易所調閱 KYC 資料
7. **四、名詞解釋** — 來自 `templates/glossary.py`

### 核心演算法

#### 錢包自動分類 (`classify_wallets` in `flow_tracer.py`)

對 FlowGraph 中每個非交易所、非 Layer 0 的節點，依以下規則分類：

1. **獲利錢包 (profit)**：有出帳邊指向 layer 更小（上游）的地址 → 反向小額轉帳行為
2. **中繼錢包 (relay)**：同時有入帳和出帳邊，且 `total_spent / total_received > 0.8` → 高比例轉出，用於中轉分散資金
3. 未符合以上條件者不標註

#### 敘述自動生成 (`_generate_narrative`)

1. 將所有邊按 `(from_address, to_address)` 聚合 → 合併金額、計算筆數、取最早/最晚時間
2. 按 `from_node.layer` → `earliest_timestamp` 排序
3. 逐對產生中文敘述段落，含：地址別名、縮寫地址、時間描述、金額、交易筆數、交易所標籤、錢包類型標籤

#### 關聯分析 (`_generate_association_text`)

1. 建立出帳邊索引 `outgoing: {addr -> [FlowEdge]}`
2. 按 layer 順序走訪非交易所節點
3. 列出每個節點的資金流出目標，推斷從屬關係

#### TRX 油費關聯分析 (`analyze_trx_gas` in `flow_tracer.py`)

1. 對每個非交易所地址，查詢 TRX（原生代幣）入帳來源
2. 優先用 TronGrid 查詢原生交易，備用 MistTrack `transactions_investigation(direction=in)`
3. 找到 TRX 提供者 → 回傳 `{地址: TRX提供者地址}` 映射，代表控制關係

#### 路徑剪枝 (`_prune_to_exchange` in `flow_tracer.py`)

當指定 `target_exchange` 時：
1. 找出所有 `is_exchange` 且 labels 包含目標關鍵字的終端節點
2. 從終端節點 BFS 反向回溯，標記所有祖先為「路徑上」
3. 刪除不在路徑上的節點和邊，重建 layers

#### 錢包角色描述 (`_wallet_role_description`)

- `is_exchange` → 交易所地址（含交易所名稱）
- `layer == 0` → 起始追蹤地址（被告/涉嫌人轉幣錢包）
- `wallet_type == "relay"` → 中繼錢包（用於中轉、分散資金）
- `wallet_type == "profit"` → 獲利錢包（向被害人發送假獲利）
- 其他 → 犯嫌收款錢包

## flow_tracer.py 演算法

### 資料結構

- **FlowNode** — 幣流圖節點，欄位：address, layer (0=A,1=B,2=C...), alias, labels, risk_score/risk_level, balance, total_received/total_spent, is_exchange, first_seen/last_seen, txs_count, received_txs_count/spent_txs_count, wallet_type ("relay"/"profit"/"")
- **FlowEdge** — 幣流圖邊，欄位：tx_hash, from_address, to_address, amount, token, timestamp
- **FlowGraph** — 完整幣流圖，欄位：source_address, coin_type, nodes (dict), edges (list), layers (dict[int, list[str]]), alias_map (dict)
- **CaseInfo** — 案件資訊，含 agency, division, case_type, case_number, analyst/reviewer, min/max_timestamp, target_exchange 等

### BFS 追蹤引擎 (`trace_flow`)

主要入口函式，從起始地址向外 BFS 追蹤資金流向。

**參數：**
- `source_address` — 起始 TRON 地址
- `coin_type` — 幣種（如 "USDT-TRC20"）
- `max_depth` — 最大追蹤深度（預設 4 層）
- `top_n` — 每個節點展開時只取前 N 個下游地址（0=不限制）
- `min_timestamp / max_timestamp` — 毫秒 Unix timestamp，所有層的查詢都套用時間窗口過濾
- `target_exchange` — 目標交易所關鍵字，BFS 完成後剪枝只保留通往該交易所的路徑

**演算法流程：**

```
1. 初始化起始節點為 Layer 0 (alias "A")
   - 呼叫 fetch_node_info() 取得標籤、風險分數、鏈上數據
   - 若有 min/max_timestamp，起始節點的 TronGrid 查詢會套用時間範圍

2. BFS 迴圈（queue 存放 (address, current_layer)）：
   a. 若 current_layer >= max_depth → 跳過
   b. 取得下游交易：
      - 優先 TronGrid: get_all_trc20_transfers() → parse_trongrid_downstream()
      - 備用 MistTrack: get_transactions(direction="out") → parse_downstream()
   c. top_n 篩選（若啟用）：
      - 依金額排序取 top_n 個地址
      - 依交易次數排序取 top_n 個地址
      - 取兩者聯集
   d. 建立 FlowEdge：
      - 若有 tx_hash_list → 每筆 hash 各建一條邊（金額平均分攤）
      - 若無 hash → 建一條邊
   e. 新節點收集（排除已 visited 的地址）
   f. 按 timestamp 排序 → 分配 alias（如 B1, B2, C1...）
   g. 對每個新節點呼叫 fetch_node_info() 取得資訊
   h. 若非交易所 → 加入 BFS queue 繼續遞迴
      若是交易所 → 標記為終端節點，不再遞迴

3. 路徑剪枝（若指定 target_exchange）：
   _prune_to_exchange() 反向 BFS 只保留通往目標交易所的路徑
```

### 節點資訊查詢 (`fetch_node_info`)

對每個地址查詢完整資訊，資料來源分層：

| 資料項目 | 主要來源 | 備用來源 |
|---------|---------|---------|
| 標籤 (labels) | MistTrack `get_labels()` | — |
| 風險分數 (risk_score) | MistTrack `get_risk_score()` | — |
| 鏈上數據 (餘額/交易統計) | TronGrid `get_account()` + `get_all_trc20_transfers()` | MistTrack `get_overview()` |

TronGrid 鏈上統計流程 (`_fetch_trongrid_overview`)：
1. `get_account()` 取即時 USDT-TRC20 餘額（從 trc20 陣列中找 USDT 合約地址）
2. `get_all_trc20_transfers()` 取全部 TRC20 交易歷史（可套用時間窗口）
3. 逐筆遍歷：累計收入/支出金額與次數、記錄 first_seen/last_seen
4. TronGrid 回傳毫秒 timestamp → 轉為秒級存入

### 交易所辨識 (`_is_exchange_label`)

預設交易所關鍵字清單：binance, bitopro, maicoin, max, okx, huobi, htx, bybit, kucoin, gate.io, kraken, coinbase, bitfinex, poloniex, bitstamp, gemini, ace, bito

匹配邏輯：完全比對 + 部分比對（如 "Binance Hot Wallet" 會匹配 "binance"）

### Alias 命名規則 (`_make_alias`)

- Layer 0 → "A"（固定，起始地址）
- Layer 1 → "B1", "B2", "B3"...（按 timestamp 排序）
- Layer 2 → "C1", "C2", "C3"...
- Layer N → 取 `LAYER_LETTERS[N]` + 序號（ABCDEFG...Z，超過 26 層用 L{N}）

### 下游交易解析

#### `parse_downstream` (MistTrack)

解析 MistTrack `transactions_investigation(type=out)` 回傳資料：
- 主要格式：`{"out": [{"address", "amount", "tx_hash_list", "token", "timestamp", "label"}]}`
- 備用格式：`{"receive": [...]}`
- 按 to_address 去重

#### `parse_trongrid_downstream` (TronGrid)

解析 TronGrid TRC20 轉帳紀錄（`from == current_addr` 的交易）：
1. 過濾：`from` 必須為當前地址、排除自轉、金額 >= `min_amount`（預設 1.0，過濾 0 值 approve 及微塵交易）
2. 按 `to_address` 聚合：累加金額、收集 tx_hash 列表、取最早 timestamp
3. 回傳格式與 `parse_downstream()` 相同

#### `parse_upstream` / `parse_trongrid_upstream`

與 downstream 對稱，用於反向追蹤上游來源（`analyze_trx_gas` 等場景使用）

### 路徑剪枝 (`_prune_to_exchange`)

當指定 `target_exchange` 時，原地修改 graph：
1. 掃描所有節點，找出 `is_exchange=True` 且 labels 含目標關鍵字的終端節點
2. 建立反向邊索引：`to_addr -> {from_addrs}`
3. 從終端節點 BFS 反向回溯，標記所有祖先為 `on_path`
4. 起始地址強制保留
5. 刪除不在 `on_path` 中的節點、alias_map 項目、邊
6. 重建 `graph.layers`

### TRX 油費關聯分析 (`analyze_trx_gas`)

識別各錢包的 TRX 手續費提供者（即可能的實際控制者）：
1. 篩選所有非交易所地址
2. 對每個地址嘗試：
   - TronGrid: `get_trx_transfers()` 查詢原生 TRX 交易（目前 pass，格式複雜待完善）
   - MistTrack fallback: `get_transactions(direction=in)` 找 token 為 TRX 或空的入帳
3. 找到第一筆金額 > 0 的 TRX 入帳 → 記錄提供者地址
4. 回傳 `{地址: TRX提供者地址}` 映射

### 錢包自動分類 (`classify_wallets`)

對 FlowGraph 中每個非交易所、非 Layer 0 的節點：

1. 建立邊方向索引：`outgoing[addr] -> {to_addrs}`、`incoming[addr] -> {from_addrs}`
2. **獲利錢包 (profit)** 判定（優先）：出帳目標中存在 layer 更小的節點 → 反向轉帳行為
3. **中繼錢包 (relay)** 判定：同時有入帳和出帳邊 + `total_spent / total_received > 0.8`
