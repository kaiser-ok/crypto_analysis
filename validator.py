"""TRON 地址驗證與修正建議模組。"""

from dataclasses import dataclass, field
from enum import Enum

import base58

from extractor import ExtractedAddress, is_strict_tron_format

_BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# 非 Base58 字元的常見替換映射
_CHAR_SUBSTITUTIONS: dict[str, list[str]] = {
    "0": ["o", "D"],
    "O": ["o"],
    "I": ["1", "i"],
    "l": ["1", "L"],
}


class ErrorType(Enum):
    NONE = "無"
    LENGTH = "長度錯誤"
    INVALID_CHARS = "含非 Base58 字元"
    CHECKSUM = "Checksum 錯誤"
    VERSION_BYTE = "Version byte 錯誤"


@dataclass
class ValidationResult:
    """驗證結果。"""
    address: str
    case_id: str
    court: str
    context: str
    is_valid: bool
    error_type: ErrorType
    suggestions: list[str] = field(default_factory=list)


def _is_valid_tron(address: str) -> tuple[bool, ErrorType]:
    """驗證 TRON 地址，回傳 (是否有效, 錯誤類型)。"""
    if len(address) != 34:
        return False, ErrorType.LENGTH

    if not address.startswith("T"):
        return False, ErrorType.INVALID_CHARS

    # 檢查是否有非 Base58 字元
    if not is_strict_tron_format(address):
        return False, ErrorType.INVALID_CHARS

    try:
        decoded = base58.b58decode_check(address)
    except ValueError:
        return False, ErrorType.CHECKSUM

    # TRON 地址解碼後應為 21 bytes，第一個 byte 為 0x41
    if len(decoded) != 21:
        return False, ErrorType.VERSION_BYTE
    if decoded[0] != 0x41:
        return False, ErrorType.VERSION_BYTE

    return True, ErrorType.NONE


def _check_candidate(candidate: str) -> bool:
    """快速檢查候選地址是否有效。"""
    if len(candidate) != 34 or not candidate.startswith("T"):
        return False
    try:
        decoded = base58.b58decode_check(candidate)
        return len(decoded) == 21 and decoded[0] == 0x41
    except (ValueError, Exception):
        return False


def _suggest_corrections(address: str) -> list[str]:
    """對無效地址嘗試推測可能的正確地址。"""
    suggestions: set[str] = set()

    # --- 策略 1：替換非 Base58 字元的常見替換 ---
    non_b58_positions = []
    for i, ch in enumerate(address):
        if ch in _CHAR_SUBSTITUTIONS:
            non_b58_positions.append(i)

    if non_b58_positions:
        # 遞迴替換所有非 Base58 字元組合
        candidates = [address]
        for pos in non_b58_positions:
            ch = address[pos]
            new_candidates = []
            for cand in candidates:
                for repl in _CHAR_SUBSTITUTIONS[ch]:
                    new_cand = cand[:pos] + repl + cand[pos + 1:]
                    new_candidates.append(new_cand)
            candidates = new_candidates
        for cand in candidates:
            if len(cand) == 34 and _check_candidate(cand):
                suggestions.add(cand)

    # --- 策略 2：單字元替換暴力搜尋 ---
    if len(address) == 34:
        for i in range(len(address)):
            original_char = address[i]
            for ch in _BASE58_CHARS:
                if ch == original_char:
                    continue
                candidate = address[:i] + ch + address[i + 1:]
                if _check_candidate(candidate):
                    suggestions.add(candidate)

    # --- 策略 3：相鄰字元對調 (transposition) ---
    if len(address) == 34:
        for i in range(len(address) - 1):
            swapped = address[:i] + address[i + 1] + address[i] + address[i + 2:]
            if _check_candidate(swapped):
                suggestions.add(swapped)

    return sorted(suggestions)


def validate_addresses(
    extracted: list[ExtractedAddress],
) -> list[ValidationResult]:
    """驗證所有擷取出的地址，回傳驗證結果列表。"""
    results: list[ValidationResult] = []

    for item in extracted:
        is_valid, error_type = _is_valid_tron(item.address)

        suggestions: list[str] = []
        if not is_valid:
            suggestions = _suggest_corrections(item.address)

        results.append(ValidationResult(
            address=item.address,
            case_id=item.case_id,
            court=item.court,
            context=item.context,
            is_valid=is_valid,
            error_type=error_type,
            suggestions=suggestions,
        ))

    return results
