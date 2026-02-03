# 虛擬通貨幣流分析 — 程式邏輯說明

## 概述

本文件說明幣流分析的兩大核心模組：

- **`flow_tracer.py`** — 多層資金流向追蹤引擎，以 BFS 演算法從起始地址向外追蹤虛擬通貨幣流，產生 `FlowGraph` 幣流圖資料結構。
- **`exchange_report.py`** — 交易所調閱用報告生成器，將 `FlowGraph` 轉換為 A4 列印最佳化 HTML，結構對齊警方內部報告範本，包含封面、案件資訊、錢包概況、幣流視覺化、關聯分析、結論建議及名詞解釋共七大章節。

---

# Part A：幣流追蹤引擎（flow_tracer.py）

---

## A-1、資料結構

### FlowNode — 幣流圖節點

| 欄位 | 型別 | 說明 |
|------|------|------|
| `address` | `str` | TRON 地址 |
| `layer` | `int` | 層級（0=A, 1=B, 2=C...） |
| `alias` | `str` | 別名（"A", "B1", "C2"...） |
| `labels` | `list[str]` | MistTrack 標籤（如交易所名稱） |
| `risk_score` | `int` | MistTrack 風險分數 |
| `risk_level` | `str` | 風險等級（Low/Moderate/High/Severe） |
| `balance` | `float` | USDT 餘額 |
| `total_received` | `float` | 總收入金額 |
| `total_spent` | `float` | 總支出金額 |
| `is_exchange` | `bool` | 是否為交易所地址 |
| `first_seen` | `int` | 首次交易 Unix timestamp（秒） |
| `last_seen` | `int` | 最近交易 Unix timestamp（秒） |
| `txs_count` | `int` | 總交易次數 |
| `received_txs_count` | `int` | 入帳次數 |
| `spent_txs_count` | `int` | 出帳次數 |
| `wallet_type` | `str` | `"relay"`（中繼）/ `"profit"`（獲利）/ `""`（未分類） |

### FlowEdge — 幣流圖邊

| 欄位 | 型別 | 說明 |
|------|------|------|
| `tx_hash` | `str` | 交易雜湊 |
| `from_address` | `str` | 來源地址 |
| `to_address` | `str` | 目標地址 |
| `amount` | `float` | 金額 |
| `token` | `str` | 幣種（"USDT", "TRX"） |
| `timestamp` | `int` | 交易時間 Unix timestamp |

### FlowGraph — 完整幣流圖

| 欄位 | 型別 | 說明 |
|------|------|------|
| `source_address` | `str` | 起始追蹤地址 |
| `coin_type` | `str` | 幣種（如 "USDT-TRC20"） |
| `nodes` | `dict[str, FlowNode]` | 地址 → 節點映射 |
| `edges` | `list[FlowEdge]` | 所有交易邊 |
| `layers` | `dict[int, list[str]]` | 層級 → 地址列表 |
| `alias_map` | `dict[str, str]` | 地址 → 別名 |

### CaseInfo — 案件資訊

| 欄位 | 型別 | 說明 |
|------|------|------|
| `agency` | `str` | 機關名稱 |
| `division` | `str` | 分局名稱 |
| `case_type` | `str` | 案類（預設「詐欺」） |
| `case_number` | `str` | 案號 |
| `analyst_name` / `analyst_rank` | `str` | 分析人員姓名/職稱 |
| `reviewer_name` / `reviewer_rank` | `str` | 審核人員姓名/職稱 |
| `request_date` | `str` | 申請日期 |
| `description` | `str` | 案件描述 |
| `coin_type` | `str` | 幣種（預設 "USDT-TRC20"） |
| `source_addresses` | `list[str]` | 起始地址列表 |
| `min_timestamp` / `max_timestamp` | `int` | 犯罪時間起訖（毫秒 Unix timestamp） |
| `target_exchange` | `str` | 目標交易所關鍵字 |

---

## A-2、Alias 命名規則（`_make_alias`）

| 層級 | 別名格式 | 範例 |
|------|---------|------|
| Layer 0 | 固定 `"A"` | A |
| Layer 1 | `B` + 序號 | B1, B2, B3 |
| Layer 2 | `C` + 序號 | C1, C2 |
| Layer N (N<26) | `LAYER_LETTERS[N]` + 序號 | D1, E1 |
| Layer N (N≥26) | `L{N}` + 序號 | L26_1 |

同一層內的節點按**最早交易時間排序**分配序號。

---

## A-3、交易所辨識（`_is_exchange_label`）

### 預設交易所關鍵字

```
binance, bitopro, maicoin, max, okx, huobi, htx, bybit, kucoin,
gate.io, kraken, coinbase, bitfinex, poloniex, bitstamp, gemini, ace, bito
```

### 匹配邏輯

對節點的每個 label：
1. **完全比對**：`label.lower() == keyword`
2. **部分比對**：`keyword in label.lower()`（如 `"Binance Hot Wallet"` 匹配 `"binance"`）

任一 label 匹配即判定為交易所。

---

## A-4、BFS 追蹤引擎（`trace_flow`）

### 函式簽章

```python
def trace_flow(
    source_address: str,        # 起始 TRON 地址
    coin_type: str,             # 幣種（如 "USDT-TRC20"）
    misttrack_client,           # MistTrack API 客戶端
    max_depth: int = 4,         # 最大追蹤深度
    moralis_client=None,        # Moralis 客戶端（可選）
    trongrid_client=None,       # TronGrid 客戶端（可選）
    top_n: int = 0,             # 每節點展開前 N 個地址（0=不限）
    min_timestamp: int = 0,     # 時間窗口起始（毫秒）
    max_timestamp: int = 0,     # 時間窗口結束（毫秒）
    target_exchange: str = "",  # 目標交易所（BFS 後剪枝）
) -> FlowGraph:
```

### 完整演算法流程

```
1. 初始化起始節點為 Layer 0（alias "A"）
   └─ fetch_node_info() 取得標籤/風險/鏈上數據
   └─ 若有時間窗口，TronGrid 查詢套用 min/max_timestamp

2. BFS 迴圈（queue 存放 (address, current_layer)）
   │
   ├─ 若 current_layer >= max_depth → 跳過
   │
   ├─ 取得下游交易（二擇一）
   │   ├─ 優先 TronGrid: get_all_trc20_transfers()
   │   │   → parse_trongrid_downstream()
   │   │   Layer 0: max_pages=50；深層: max_pages=10
   │   └─ 備用 MistTrack: get_transactions(direction="out")
   │       → parse_downstream()
   │
   ├─ top_n 篩選（若 top_n > 0 且下游數 > top_n）
   │   ├─ 依金額排序取前 N 個地址
   │   ├─ 依交易次數排序取前 N 個地址
   │   └─ 取兩者聯集
   │
   ├─ 建立 FlowEdge
   │   ├─ 有 tx_hash_list → 每筆 hash 各建一條邊
   │   │   └─ 同對地址最多 MAX_EDGES_PER_PAIR = 10 條
   │   │   └─ 金額平均分攤，最後一條承接剩餘
   │   └─ 無 hash → 建一條邊
   │
   ├─ 新節點收集（排除已 visited）
   │   ├─ 按 timestamp 排序 → 分配 alias
   │   └─ fetch_node_info() 取得資訊
   │
   └─ 節點分流
       ├─ 非交易所 → 加入 BFS queue 繼續遞迴
       └─ 交易所 → 標記為終端，不再遞迴

3. 路徑剪枝（若指定 target_exchange）
   └─ _prune_to_exchange() 反向 BFS 只保留通往目標交易所的路徑
```

---

## A-5、節點資訊查詢（`fetch_node_info`）

對每個地址查詢完整資訊，資料來源分層：

| 資料項目 | 主要來源 | 備用來源 |
|---------|---------|---------|
| 標籤 (labels) | MistTrack `get_labels()` | — |
| 風險分數 (risk_score) | MistTrack `get_risk_score()` | — |
| 鏈上數據（餘額/交易統計） | TronGrid `get_account()` + `get_all_trc20_transfers()` | MistTrack `get_overview()` |

### TronGrid 鏈上統計（`_fetch_trongrid_overview`）

1. `get_account()` — 取即時 USDT-TRC20 餘額
   - 從 `trc20` 陣列中找 USDT 合約地址（`USDT_TRC20_CONTRACT`）
   - 原始值除以 `1_000_000`
2. `get_all_trc20_transfers()` — 取全部 TRC20 交易歷史
   - 可套用 `min_timestamp` / `max_timestamp` 時間窗口
3. 逐筆遍歷交易：
   - 依 `from`/`to` 判斷收入或支出
   - 累加金額與次數
   - 記錄 `first_seen` / `last_seen`
4. TronGrid 回傳毫秒 timestamp → 除以 1000 轉為秒級存入

### 交易所跳過優化

若 `is_exchange == True`，跳過鏈上交易歷史查詢（交易所地址為終端節點，不需統計）。

---

## A-6、下游交易解析

### `parse_downstream`（MistTrack 來源）

解析 `transactions_investigation(type=out)` 回傳資料：

- 主要格式：`{"out": [{"address", "amount", "tx_hash_list", "token", "timestamp", "label"}]}`
- 備用格式：`{"receive": [...]}`
- 排除自轉（`to_addr == from_addr`）
- 按 `to_address` 去重

### `parse_trongrid_downstream`（TronGrid 來源）

解析 TronGrid TRC20 轉帳紀錄（`from == current_addr` 的交易）：

1. **過濾**：
   - `from` 必須為當前地址
   - 排除自轉
   - 金額 >= `min_amount`（預設 1.0，過濾 0 值 approve 及微塵交易）
2. **聚合**：按 `to_address` 分組
   - 累加金額
   - 收集 `tx_hash` 列表
   - 取最早 `timestamp`
3. **輸出**：格式與 `parse_downstream()` 相同

### `parse_upstream` / `parse_trongrid_upstream`

與 downstream 對稱，用於反向追蹤上游來源（`analyze_trx_gas` 等場景）。

---

## A-7、路徑剪枝

### `_prune_to_exchange`（指定交易所剪枝）

當指定 `target_exchange` 時，原地修改 graph：

```
1. 掃描所有節點，找出 is_exchange=True 且 labels 含目標關鍵字的終端節點
    │
    ▼
2. 建立反向邊索引：to_addr → {from_addrs}
    │
    ▼
3. 從終端節點 BFS 反向回溯，標記所有祖先為 on_path
    │
    ▼
4. 起始地址強制保留
    │
    ▼
5. 刪除不在 on_path 中的節點、alias_map、邊
    │
    ▼
6. 重建 graph.layers
```

### `prune_to_any_exchange`（通用交易所剪枝）

與 `_prune_to_exchange` 相同邏輯，但不限定特定交易所——只要路徑終端是任意交易所就保留。適用於交易所調閱報告場景。

### `prune_to_case_addresses`（案件地址剪枝）

保留連接案件相關地址的路徑，使用**雙向 BFS**：

```
1. 目標節點 = case_addresses ∩ graph.nodes + 所有交易所節點
    │
    ▼
2. 反向 BFS：從目標節點回溯到 source
   → backward_reachable
    │
    ▼
3. 正向 BFS：從 source 出發可到達的節點
   → forward_reachable
    │
    ▼
4. 取交集：on_path = forward_reachable ∩ backward_reachable
    │
    ▼
5. 刪除非 on_path 節點/邊，重建 layers
```

---

## A-8、TRX 油費關聯分析（`analyze_trx_gas`）

### 原理

TRON 鏈上執行交易需要 TRX 作為手續費（油費）。提供 TRX 的地址通常為該錢包的實際持有者或上游控制者。

### 流程

```
1. 篩選所有非交易所地址
    │
    ▼
2. 對每個地址查詢 TRX 入帳來源
   ├─ 優先 TronGrid: get_trx_transfers()
   │   （目前 pass，原生交易格式複雜待完善）
   └─ 備用 MistTrack: get_transactions(direction=in)
       └─ 過濾 token 為 TRX 或空（原生代幣）
    │
    ▼
3. 找到第一筆金額 > 0 的 TRX 入帳
   → 記錄提供者地址
    │
    ▼
4. 回傳 { 地址: TRX提供者地址 } 映射
```

---

## A-9、錢包自動分類（`classify_wallets`）

對 FlowGraph 中**每個非交易所、非 Layer 0 的節點**進行分類：

### 分類規則

```
步驟 1: 建立邊方向索引
    outgoing = { addr → {to_addrs} }
    incoming = { addr → {from_addrs} }

步驟 2: 獲利錢包判定（優先）
    條件：有出帳邊指向 layer 更小（上游）的節點
    意義：反向小額轉帳行為（向被害人發送假獲利）
    → wallet_type = "profit"

步驟 3: 中繼錢包判定
    條件：同時有入帳和出帳邊 + total_spent / total_received > 0.8
    意義：高比例轉出，用於中轉分散資金
    → wallet_type = "relay"
```

| 類型 | 條件 | 意義 |
|------|------|------|
| `profit`（獲利） | 有出帳邊指向 layer 更小的節點 | 反向轉帳，製造假獲利 |
| `relay`（中繼） | 有入有出 + 轉出比 > 80% | 中轉站，分散資金流向 |
| `""`（未分類） | 以上皆不符合 | 犯嫌收款錢包 |

---

## A-10、完整追蹤流程圖

```
起始地址 (source_address)
    │
    ▼
┌──────────────────────────────┐
│ fetch_node_info()               │  MistTrack 標籤/風險
│   ├─ get_labels()               │  + TronGrid 鏈上數據
│   ├─ get_risk_score()           │
│   └─ _fetch_trongrid_overview() │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ BFS 迴圈                       │
│  ┌─────────────────────────┐ │
│  │ 取得下游交易               │ │
│  │  ├─ TronGrid (優先)       │ │
│  │  └─ MistTrack (備用)      │ │
│  └───────────┬─────────────┘ │
│              ▼                 │
│  ┌─────────────────────────┐ │
│  │ top_n 篩選（可選）         │ │
│  │  金額 top_n ∪ 次數 top_n  │ │
│  └───────────┬─────────────┘ │
│              ▼                 │
│  ┌─────────────────────────┐ │
│  │ 建立 FlowEdge             │ │
│  │  每筆 tx_hash 各一條邊    │ │
│  │  MAX_EDGES_PER_PAIR = 10  │ │
│  └───────────┬─────────────┘ │
│              ▼                 │
│  ┌─────────────────────────┐ │
│  │ 新節點: fetch_node_info() │ │
│  │  按 timestamp 排序分配    │ │
│  │  alias (B1, B2, C1...)    │ │
│  └───────────┬─────────────┘ │
│              ▼                 │
│  交易所? ─── 是 → 終端節點    │
│         └── 否 → 加入 queue   │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ 路徑剪枝（可選）                │
│  ├─ _prune_to_exchange()       │  指定交易所
│  ├─ prune_to_any_exchange()    │  任意交易所
│  └─ prune_to_case_addresses()  │  案件地址
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ classify_wallets()              │  中繼/獲利分類
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ analyze_trx_gas()               │  油費控制關係
└──────────┬───────────────────┘
           │
           ▼
      FlowGraph 完成
      → 交由 exchange_report.py 產生報告
```

---

# Part B：交易所調閱報告生成器（exchange_report.py）

---

## 一、報告生成入口（`generate_exchange_report`）

### 函式簽章

```python
def generate_exchange_report(
    graph: FlowGraph,        # 幣流圖（由 flow_tracer.py 產生）
    case_info: CaseInfo,     # 案件資訊
    output_path: str,        # HTML 輸出路徑
    trx_providers: dict[str, str] | None = None,  # TRX 油費提供者映射
) -> str:
```

### 執行流程

```
輸入: FlowGraph + CaseInfo
    │
    ▼
1. classify_wallets(graph)     ← 自動分類錢包（中繼/獲利）
    │
    ▼
2. 計算民國年日期              ← 西元年 - 1911
    │
    ▼
3. 去重收集交易 hash           ← graph.edges 中所有 tx_hash
    │
    ▼
4. _generate_flow_svg(graph)   ← SVG 幣流圖（來自 flow_report.py）
    │
    ▼
5. _build_exchange_html(...)   ← 組裝完整 HTML
    │
    ▼
6. 寫入檔案
```

---

## 二、HTML 報告結構

### 章節組成

| 順序 | 章節 | 建構函式 | 說明 |
|------|------|---------|------|
| 1 | 封面 | `_build_cover()` | 機關名稱、案號、案類、分析/審核人員、民國日期 |
| 2 | 目錄 + 免責聲明 | `_build_toc_and_disclaimer()` | 五節目錄 + 免責條款（`templates/disclaimer.py`） |
| 3 | 一、案件資訊 | `_build_section1_case_info()` | 承辦表格 + 錢包清單 + 交易序號 |
| 4 | 錢包概況表 | `_build_wallet_overview()` | 每個地址的餘額與交易統計 |
| 5 | 二、分析情形 | `_build_section2_analysis()` | 含 (一)~(四) 四個子節 |
| 6 | 三、結論及建議事項 | `_build_section3_conclusion()` | 摘要 + 建議調閱 KYC + 簽章欄 |
| 7 | 四、名詞解釋 | `_build_section4_glossary()` | 專有名詞定義（`templates/glossary.py`） |

每個章節以 `page-break-after` CSS 分頁，列印時自動換頁。

---

## 三、封面（`_build_cover`）

顯示內容：

- 機關名稱（`case_info.agency`）+ 承辦單位（`case_info.division`）
- 報告標題：「虛擬通貨幣流分析報告」
- 案號 + 案類 + 案件說明
- 分析人員、審核人員（職等 + 姓名）
- 民國年月日

---

## 四、一、案件資訊（`_build_section1_case_info`）

### 案件資訊表格

列出承辦單位、承辦人員、申請日期、案類、幣別、案號，以及可選的追蹤時間範圍和目標交易所。

### 錢包地址清單

按 layer 順序列出所有節點：

| 欄位 | 說明 |
|------|------|
| 層別 | 節點的 alias（如 A, B1, C2） |
| 地址 | 完整 TRON 地址 |
| 角色說明 | 由 `_wallet_role_description()` 產生 + 類型徽章 |

### 類型徽章

| 類型 | 顏色 | CSS 類別 |
|------|------|---------|
| 交易所 | 綠色 | `badge-exchange` |
| 中繼錢包 | 藍色 | `badge-relay` |
| 獲利錢包 | 橘色 | `badge-profit` |
| 車手錢包 | 紅色 | `badge-mule` |

### 交易序號列表

去重列出所有 `edge.tx_hash`，以編號列表顯示。

---

## 五、錢包概況表（`_build_wallet_overview`）

按 layer 順序對每個地址產生一列：

| 欄位 | 來源 |
|------|------|
| 別名 | `node.alias` |
| 地址 | 縮寫顯示（`_short_addr`） |
| 餘額 | `node.balance` |
| 首次交易 | `node.first_seen` |
| 最近交易 | `node.last_seen` |
| 收入總額 | `node.total_received` |
| 收入次數 | `node.received_txs_count` |
| 支出總額 | `node.total_spent` |
| 支出次數 | `node.spent_txs_count` |
| 總交易次數 | `node.txs_count` |

---

## 六、二、分析情形（`_build_section2_analysis`）

### （一）幣流視覺化圖

1. 插入由 `_generate_flow_svg()` 產生的 SVG 幣流圖
2. 呼叫 `_generate_narrative()` 產生中文敘述（詳見第八節）

### （二）各錢包態樣分析（`_build_wallet_analysis`）

按 layer 順序走訪每個節點，每個錢包產生一張卡片（藍色左邊框），內容包含：

- 角色描述 + 標籤（如交易所名稱）
- 累計收入/支出金額
- 轉出比例（`total_spent / total_received * 100%`，非交易所節點）
- 風險等級與分數

### （三）錢包間關聯繫屬及支配情形（`_build_association_analysis`）

包含兩部分：

#### TRX 油費關聯分析

若傳入 `trx_providers` 映射（由 `flow_tracer.analyze_trx_gas()` 產生），以表格顯示：

| 錢包別名 | 錢包地址 | TRX 提供者別名 | TRX 提供者地址 |
|---------|---------|--------------|--------------|

原理：TRON 鏈上執行交易需要 TRX 作為手續費（油費），提供 TRX 的地址通常為該錢包的實際持有者或上游控制者。

#### 資金流向關聯

呼叫 `_generate_association_text()` 產生從屬關係敘述（詳見第九節）。

### （四）結論研判（`_build_analysis_conclusion`）

自動統計並輸出：

1. 總金額、節點數、邊數摘要
2. 中繼錢包列表（`wallet_type == "relay"`）— 用於中轉分散資金
3. 獲利錢包列表（`wallet_type == "profit"`）— 曾向上游反向發送小額虛擬貨幣
4. 資金流入的交易所名稱與地址，建議調閱 KYC
5. 若無交易所節點，建議擴大追蹤深度

---

## 七、三、結論及建議事項（`_build_section3_conclusion`）

### 摘要

自動組合以下資訊為中文段落：

- 起始地址（縮寫）
- 追蹤時間範圍（若有設定 `min_timestamp` / `max_timestamp`）
- 相關地址數、交易筆數、總金額
- 目標交易所篩選說明（若有設定 `target_exchange`）

### 建議事項

對每個偵測到的交易所，自動產生一條建議：

```
1. 經追蹤，犯罪時間 YYYY-MM-DD ~ YYYY-MM-DD 期間，從起始地址轉出之
   XXX USDT 經中繼後流入 Binance，建議向 Binance 調閱地址 B1、B2 之
   註冊帳戶資料（含 KYC 身分資訊）及相關交易紀錄，以釐清資金實際受益人身分。
```

末尾附加固定建議：幣流圖及錢包概況表可匯出為圖檔或 CSV 作為偵查卷證附件。

### 簽章欄

顯示報告日期、分析人員、審核人員，供列印後簽章用。

---

## 八、敘述自動生成演算法（`_generate_narrative`）

### 流程

```
graph.edges
    │
    ▼
步驟 1: 按 (from_address, to_address) 聚合
    ├─ 加總金額 (total_amount)
    ├─ 計算筆數 (tx_count)
    ├─ 取最早時間 (earliest_ts)
    └─ 取最晚時間 (latest_ts)
    │
    ▼
步驟 2: 排序
    ├─ 主鍵: from_node.layer（按層順序）
    └─ 次鍵: earliest_ts（按時間順序）
    │
    ▼
步驟 3: 逐對產生中文段落
```

### 段落格式

每對 (from, to) 產生一段敘述，包含：

- 來源地址別名 + 縮寫地址
- 時間描述（單筆：「於 YYYY-MM-DD HH:MM」；多筆：「於 ... 至 ... 期間」）
- 金額 + 幣種
- 目標地址別名 + 縮寫地址
- 交易筆數（多筆時顯示）
- 交易所標籤（若目標為交易所：「經查地址 X 為 Binance 之地址」）
- 錢包類型標籤（若有分類：「經研判為中繼錢包」）

### 範例輸出

> 地址 A（TLa3...xYz）於 2024-01-15 10:30 將 5,000.00 USDT 轉出至地址 B1（TQr7...aBc）（共 3 筆交易）。經查地址 B1 為 Binance 之地址（經研判為中繼錢包）。

---

## 九、關聯分析演算法（`_generate_association_text`）

### 流程

```
graph.edges
    │
    ▼
步驟 1: 建立出帳邊索引
    outgoing = { from_addr: [FlowEdge, ...] }
    │
    ▼
步驟 2: 按 layer 順序走訪非交易所節點
    │
    ▼
步驟 3: 對每個節點列出資金轉出目標
    ├─ 去重取 unique targets
    └─ 產生從屬關係判斷
```

### 輸出格式

> 地址 A 將資金轉出至 B1、B2，研判 A 與 B1、B2 間具有資金從屬關係。

---

## 十、錢包角色判定（`_wallet_role_description`）

依以下優先順序判定錢包角色：

| 優先序 | 條件 | 角色描述 |
|--------|------|---------|
| 1 | `node.is_exchange == True` | 交易所地址（含交易所名稱） |
| 2 | `node.layer == 0` | 起始追蹤地址（被告/涉嫌人轉幣錢包） |
| 3 | `node.wallet_type == "relay"` | 中繼錢包（用於中轉、分散資金） |
| 4 | `node.wallet_type == "profit"` | 獲利錢包（向被害人發送假獲利） |
| 5 | 以上皆非 | 犯嫌收款錢包 |

`wallet_type` 由 `flow_tracer.classify_wallets()` 在報告生成前自動計算：

- **中繼錢包 (relay)**：同時有入帳和出帳，且 `total_spent / total_received > 0.8`
- **獲利錢包 (profit)**：有出帳邊指向 layer 更小（上游）的節點

---

## 十一、外部依賴

| 模組 | 引用項目 | 用途 |
|------|---------|------|
| `flow_tracer.py` | `FlowGraph`, `FlowNode`, `FlowEdge`, `CaseInfo`, `LAYER_LETTERS`, `classify_wallets`, `analyze_trx_gas` | 資料結構 + 分類 + 油費分析 |
| `flow_report.py` | `_esc`, `_short_addr`, `_ts_to_str`, `_ts_to_date`, `_format_amount`, `_tronscan_addr_link`, `_tronscan_tx_link`, `_generate_flow_svg` | HTML 工具函式 + SVG 生成 |
| `templates/disclaimer.py` | `EXCHANGE_REPORT_DISCLAIMER_ITEMS` | 免責聲明條款列表 |
| `templates/glossary.py` | `EXCHANGE_REPORT_GLOSSARY_ITEMS` | 名詞解釋條目列表 |

---

## 十二、CSS 與列印設計

### A4 列印最佳化

```css
@page { size: A4; margin: 20mm 18mm 25mm 18mm; }
```

- 每個章節以 `page-break-after: always` 分頁
- 螢幕預覽：`max-width: 900px` + 陰影模擬紙張效果
- 列印時：移除 padding 限制、頁尾固定於底部

### 視覺設計

| 元素 | 設計 |
|------|------|
| 封面標題 | 28pt 粗體、底線、字距 8px |
| 資料表格 | 灰底表頭、1px 邊框、等寬字型顯示地址 |
| 錢包卡片 | 藍色左邊框（`3px solid #1976D2`）+ 淺灰底 |
| 敘述段落 | 首行縮排 2em、兩端對齊 |
| 徽章配色 | 中繼=藍、獲利=橘、車手=紅、交易所=綠 |
| 交易 hash | 8pt 等寬字型、淺灰底、允許斷行 |
| 簽章欄 | 上方分隔線、雙欄排列（分析人員/審核人員） |

---

## 十三、完整報告生成流程圖

```
FlowGraph + CaseInfo
    │
    ▼
┌─────────────────────────┐
│ classify_wallets(graph)    │  自動分類中繼/獲利錢包
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ _generate_flow_svg(graph)  │  產生 SVG 幣流圖
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────────────────────┐
│ _build_exchange_html()                     │
│                                            │
│  ┌─ _build_cover()              封面       │
│  ├─ _build_toc_and_disclaimer() 目錄+免責  │
│  ├─ _build_section1_case_info() 案件資訊   │
│  │   └─ 錢包清單 + 交易序號               │
│  ├─ _build_wallet_overview()    錢包概況表 │
│  ├─ _build_section2_analysis()  分析情形   │
│  │   ├─ (一) SVG 圖 + _generate_narrative()│
│  │   ├─ (二) _build_wallet_analysis()      │
│  │   ├─ (三) _build_association_analysis() │
│  │   │   ├─ TRX 油費關聯表                │
│  │   │   └─ _generate_association_text()   │
│  │   └─ (四) _build_analysis_conclusion()  │
│  ├─ _build_section3_conclusion() 結論建議  │
│  │   └─ 摘要 + 建議 + 簽章欄             │
│  └─ _build_section4_glossary()  名詞解釋   │
└───────────┬─────────────────────────────┘
            │
            ▼
      寫入 HTML 檔案
```
