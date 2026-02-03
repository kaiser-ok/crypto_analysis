"""案情分析模組：從判決書提取被害人/嫌犯帳號及案件資訊。

使用 regex 提取固定格式欄位，再透過 LLM 分析案情語境，
混合產生結構化的案件分析結果。
"""

import hashlib
import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from openai import OpenAI

import config

log = logging.getLogger("case_analyzer")


# --- 資料結構 ---

@dataclass
class CaseAnalysis:
    """案情分析結果。"""
    case_id: str = ""                # 裁判字號
    court: str = ""                  # 法院
    judgment_date: str = ""          # 裁判日期
    case_type: str = ""              # 案由
    defendants: list[dict] = field(default_factory=list)   # [{"name": "...", "role": "被告"}]
    victims: list[dict] = field(default_factory=list)      # [{"name": "...", "role": "告訴人"}]
    wallets: list[dict] = field(default_factory=list)      # [{"address": "T...", "role": "victim|suspect|unknown", "label": "", "owner_name": "", "context": ""}]
    transactions: list[dict] = field(default_factory=list)  # [{"amount": 6634.0, "currency": "USDT", "date": "..."}]
    coin_type: str = "USDT-TRC20"
    crime_start_date: str = ""       # 犯罪時間起始日（ISO 格式 YYYY-MM-DD 或描述文字）
    crime_end_date: str = ""         # 犯罪時間結束日
    description: str = ""            # LLM 生成的案件摘要
    analyzed_at: str = ""            # ISO timestamp


# --- 路徑管理 ---

def _case_dir(case_id: str) -> str:
    """取得案件分析目錄路徑（使用 MD5 hash，與 scraper.py 一致）。"""
    case_hash = hashlib.md5(case_id.encode()).hexdigest()
    return os.path.join(config.CASES_DIR, case_hash)


def has_case_analysis(case_id: str) -> bool:
    """檢查案件是否已分析。"""
    path = os.path.join(_case_dir(case_id), "case_info.json")
    return os.path.isfile(path)


def load_case_analysis(case_id: str) -> CaseAnalysis | None:
    """載入已存在的案件分析結果。"""
    path = os.path.join(_case_dir(case_id), "case_info.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 過濾掉不屬於 CaseAnalysis 的欄位，避免舊檔案欄位不匹配
    valid_fields = {f.name for f in CaseAnalysis.__dataclass_fields__.values()}
    data = {k: v for k, v in data.items() if k in valid_fields}
    return CaseAnalysis(**data)


def save_case_analysis(analysis: CaseAnalysis) -> str:
    """儲存案件分析結果，回傳檔案路徑。"""
    case_dir = _case_dir(analysis.case_id)
    os.makedirs(case_dir, exist_ok=True)
    path = os.path.join(case_dir, "case_info.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(analysis), f, ensure_ascii=False, indent=2)
    return path


# --- Regex 提取 ---

def _extract_metadata_regex(text: str) -> dict:
    """從判決書全文中用 regex 提取固定格式欄位。"""
    metadata = {
        "case_id": "",
        "judgment_date": "",
        "case_type": "",
    }

    # 裁判字號
    m = re.search(r'裁判字號[：:]\s*\n?\s*(.+?)(?:\n|$)', text)
    if m:
        metadata["case_id"] = m.group(1).strip()

    # 裁判日期（民國年）
    m = re.search(r'裁判日期[：:]\s*\n?\s*民國\s*(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日', text)
    if m:
        roc_y, mon, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        metadata["judgment_date"] = f"民國{roc_y}年{mon}月{day}日"

    # 案由
    m = re.search(r'裁判案由[：:]\s*\n?\s*(.+?)(?:\n|$)', text)
    if m:
        metadata["case_type"] = m.group(1).strip()

    return metadata


def _extract_persons_regex(text: str) -> tuple[list[dict], list[dict]]:
    """從判決書全文中用 regex 提取被告和告訴人/被害人。"""
    defendants = []
    victims = []
    seen_defendants = set()
    seen_victims = set()

    # 被告
    for m in re.finditer(r'被\s*告\s+(\S{2,4})', text):
        name = m.group(1).strip()
        if name not in seen_defendants:
            defendants.append({"name": name, "role": "被告"})
            seen_defendants.add(name)

    # 告訴人 / 被害人
    for m in re.finditer(r'(?:告訴人|被害人)[　\s]*(\S{2,4})', text):
        name = m.group(1).strip()
        if name not in seen_victims:
            victims.append({"name": name, "role": "告訴人"})
            seen_victims.add(name)

    return defendants, victims


def _extract_addresses_from_text(text: str) -> list[dict]:
    """從判決書全文中提取 TRON 地址及其前後文。"""
    from extractor import _LOOSE_PATTERN, CONTEXT_CHARS

    addresses = []
    seen = set()

    for m in _LOOSE_PATTERN.finditer(text):
        addr = m.group(0)
        if addr in seen:
            continue
        seen.add(addr)

        start = max(0, m.start() - CONTEXT_CHARS)
        end = min(len(text), m.end() + CONTEXT_CHARS)
        ctx = text[start:end].replace("\n", " ").strip()
        if start > 0:
            ctx = "..." + ctx
        if end < len(text):
            ctx = ctx + "..."

        addresses.append({
            "address": addr,
            "context": ctx,
        })

    return addresses


# --- LLM 分析 ---

def _analyze_with_llm(
    text: str,
    addresses: list[dict],
    metadata: dict,
    defendants: list[dict],
    victims: list[dict],
) -> dict:
    """透過 LLM 分析判決書案情語境。

    回傳 dict 包含：
    - wallets: 每個地址的 role/owner_name 補充
    - description: 案件摘要
    - transactions: 交易金額與日期
    """
    addr_list_text = "\n".join(
        f"  - {a['address']} (前後文: {a['context']})"
        for a in addresses
    )
    defendant_names = ", ".join(d["name"] for d in defendants) if defendants else "未知"
    victim_names = ", ".join(v["name"] for v in victims) if victims else "未知"

    prompt = f"""你是一個台灣法律案件分析助理。請以繁體中文回覆。請分析以下詐欺案判決書，提取虛擬通貨相關資訊。

## 已知資訊
- 案由：{metadata.get("case_type", "未知")}
- 被告：{defendant_names}
- 告訴人/被害人：{victim_names}

## 判決書中提取到的 TRON 地址
{addr_list_text if addr_list_text else "（無地址）"}

## 判決書全文
{text[:8000]}

## 請以 JSON 格式回傳分析結果

```json
{{
  "wallets": [
    {{
      "address": "T...",
      "role": "victim 或 suspect 或 unknown",
      "owner_name": "對應的持有人姓名（若能從判決書判斷）",
      "label": "簡短標籤描述（如：被告收款錢包、被害人入金錢包等）"
    }}
  ],
  "transactions": [
    {{
      "amount": 6634.0,
      "currency": "USDT",
      "date": "日期描述",
      "description": "交易簡述"
    }}
  ],
  "crime_start_date": "犯罪行為最早發生日期（YYYY-MM-DD 格式，如 2025-08-26）",
  "crime_end_date": "犯罪行為最晚發生日期（YYYY-MM-DD 格式）",
  "description": "案件摘要（100-200字，描述詐欺手法、涉案金額、虛擬通貨使用方式）"
}}
```

注意：
1. role 判斷：若地址出現在被害人轉帳的語境中，標為 victim；若為被告/嫌犯控制的收款地址，標為 suspect
2. 若無法確定角色，標為 unknown
3. 請從判決書敘述中提取具體的交易金額和日期
4. 所有文字內容請使用繁體中文
5. 只回傳 JSON，不要其他文字
6. crime_start_date / crime_end_date：從判決書事實描述中找出犯罪行為的最早與最晚日期，用西元 YYYY-MM-DD 格式。若判決書中用民國紀年，請轉換為西元（如民國114年 → 2025年）。若無法確定，留空字串"""

    try:
        client = OpenAI(
            base_url=config.LLM_API_BASE,
            api_key="not-needed",
        )
        response = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        content = response.choices[0].message.content.strip()

        # 解析 JSON（可能被包在 ```json ... ``` 中）
        json_match = re.search(r'```json\s*\n?(.*?)\n?\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)

        result = json.loads(content)
        return result

    except Exception as e:
        log.error(f"LLM 分析失敗: {e}")
        return {
            "wallets": [],
            "transactions": [],
            "description": f"LLM 分析失敗: {e}",
        }


# --- 主要入口 ---

def analyze_case(
    case_id: str,
    court: str = "",
    address_corrections: dict[str, str] | None = None,
) -> CaseAnalysis:
    """分析案件判決書，回傳 CaseAnalysis。

    address_corrections: {原始地址: 修正後地址} 對應表，
        用於將判決書中 OCR 錯誤的地址替換為驗證後的正確地址。
    若已分析過，直接回傳快取結果。
    """
    # 檢查快取
    existing = load_case_analysis(case_id)
    if existing:
        return existing

    # 載入判決書全文
    cache_hash = hashlib.md5(case_id.encode()).hexdigest()
    cache_path = os.path.join(config.CACHE_DIR, f"{cache_hash}.txt")

    if not os.path.isfile(cache_path):
        raise FileNotFoundError(f"找不到判決書快取: {case_id}")

    with open(cache_path, "r", encoding="utf-8") as f:
        text = f.read()

    # Step 1: Regex 提取固定格式欄位
    metadata = _extract_metadata_regex(text)
    defendants, victims = _extract_persons_regex(text)
    addresses = _extract_addresses_from_text(text)

    # Step 2: LLM 分析案情語境
    llm_result = _analyze_with_llm(text, addresses, metadata, defendants, victims)

    # Step 3: 合併結果
    # 建立 LLM wallet 結果的 lookup
    llm_wallets = {w["address"]: w for w in llm_result.get("wallets", []) if "address" in w}

    # 套用地址修正（OCR 錯誤地址 → 驗證後正確地址）
    corrections = address_corrections or {}

    wallets = []
    for addr_info in addresses:
        raw_addr = addr_info["address"]
        # 優先使用修正後地址
        corrected_addr = corrections.get(raw_addr, raw_addr)
        llm_w = llm_wallets.get(raw_addr, {})
        wallets.append({
            "address": corrected_addr,
            "role": llm_w.get("role", "unknown"),
            "label": llm_w.get("label", ""),
            "owner_name": llm_w.get("owner_name", ""),
            "context": addr_info["context"],
        })

    analysis = CaseAnalysis(
        case_id=case_id,
        court=court or metadata.get("court", ""),
        judgment_date=metadata.get("judgment_date", ""),
        case_type=metadata.get("case_type", ""),
        defendants=defendants,
        victims=victims,
        wallets=wallets,
        transactions=llm_result.get("transactions", []),
        coin_type="USDT-TRC20",
        crime_start_date=llm_result.get("crime_start_date", ""),
        crime_end_date=llm_result.get("crime_end_date", ""),
        description=llm_result.get("description", ""),
        analyzed_at=datetime.now().isoformat(),
    )

    # 儲存
    path = save_case_analysis(analysis)
    log.info(f"案情分析完成: {case_id} → {path}")

    return analysis
