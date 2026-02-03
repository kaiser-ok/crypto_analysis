"""TRON (TRC-20) 地址擷取模組。"""

import re
from dataclasses import dataclass

from scraper import Judgment

# Base58 字元集（不含 0, O, I, l）
_BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# 嚴格的 TRON 地址正規表達式：T 開頭 + 33 個 Base58 字元 = 34 字元
_STRICT_PATTERN = re.compile(r"T[" + re.escape(_BASE58_CHARS) + r"]{33}")

# 寬鬆模式：T 開頭 + 32~34 個英數字（可能包含非 Base58 字元如 0, O, I, l）
_LOOSE_PATTERN = re.compile(r"T[A-Za-z0-9]{32,34}")

CONTEXT_CHARS = 40  # 前後文擷取字元數


@dataclass
class ExtractedAddress:
    """擷取出的地址資訊。"""
    address: str        # 原始地址字串
    case_id: str        # 所在判決書案號
    court: str          # 法院
    context: str        # 前後文摘錄


def extract_addresses(judgments: list[Judgment]) -> list[ExtractedAddress]:
    """從判決書列表中擷取所有疑似 TRON 地址。"""
    results: list[ExtractedAddress] = []
    seen: set[tuple[str, str]] = set()  # (address, case_id) 去重

    for jud in judgments:
        text = jud.full_text

        # 先用寬鬆模式找所有候選
        for m in _LOOSE_PATTERN.finditer(text):
            addr = m.group(0)
            key = (addr, jud.case_id)
            if key in seen:
                continue
            seen.add(key)

            # 擷取前後文
            start = max(0, m.start() - CONTEXT_CHARS)
            end = min(len(text), m.end() + CONTEXT_CHARS)
            ctx = text[start:end].replace("\n", " ").strip()
            if start > 0:
                ctx = "..." + ctx
            if end < len(text):
                ctx = ctx + "..."

            results.append(ExtractedAddress(
                address=addr,
                case_id=jud.case_id,
                court=jud.court,
                context=ctx,
            ))

    return results


def is_strict_tron_format(address: str) -> bool:
    """檢查是否嚴格符合 TRON 地址格式（34 字元、T 開頭、全 Base58 字元）。"""
    return bool(_STRICT_PATTERN.fullmatch(address))
