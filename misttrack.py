"""MistTrack API 整合模組：風險評分、地址標籤、資金流向分析。"""

import time
from dataclasses import dataclass, field

import requests
from tqdm import tqdm

# TRON 的 coin 參數值（API 用 TRX）
COIN = "TRX"

API_BASE = "https://openapi.misttrack.io"
RATE_LIMIT_DELAY = 1.0  # 秒，避免 rate limit


class RateLimitError(Exception):
    """MistTrack API 每日額度超限。"""
    def __init__(self, msg: str = "ExceededDailyRateLimit", retry_after: int = 0):
        self.retry_after = retry_after
        super().__init__(f"{msg} (retry_after={retry_after}s)")


@dataclass
class MistTrackResult:
    """單一地址的 MistTrack 分析結果。"""
    address: str

    # address_labels
    label_list: list[str] = field(default_factory=list)
    label_type: str = ""

    # risk_score
    risk_score: int = 0
    risk_level: str = ""
    hacking_event: str = ""
    detail_list: list[str] = field(default_factory=list)
    risk_detail: list[dict] = field(default_factory=list)

    # address_overview
    balance: float = 0.0
    txs_count: int = 0
    first_seen: int = 0
    last_seen: int = 0
    total_received: float = 0.0
    total_spent: float = 0.0
    received_txs_count: int = 0
    spent_txs_count: int = 0

    # address_trace (profile)
    first_address: str = ""
    use_platform: dict = field(default_factory=dict)
    malicious_event: dict = field(default_factory=dict)

    error: str = ""


class MistTrackClient:
    """MistTrack API 客戶端（支援多 key round-robin + 自動切換）。

    api_key 可為單一 key 或逗號分隔的多個 key。
    每次請求使用當前 key；遇到 429 時自動切換到下一把，
    全部 key 都 429 才向上拋出 RateLimitError。
    """

    def __init__(self, api_key: str):
        # 支援逗號分隔多 key
        self._keys = [k.strip() for k in api_key.split(",") if k.strip()]
        if not self._keys:
            raise ValueError("至少需要一把 MistTrack API key")
        self._idx = 0  # 當前 round-robin 位置
        self._exhausted: set[int] = set()  # 已 429 的 key index
        self.session = requests.Session()

    @property
    def api_key(self) -> str:
        """當前使用的 key。"""
        return self._keys[self._idx]

    @property
    def key_count(self) -> int:
        return len(self._keys)

    def _rotate(self) -> bool:
        """切換到下一把可用 key。回傳 False 表示全部耗盡。"""
        self._exhausted.add(self._idx)
        for _ in range(len(self._keys)):
            self._idx = (self._idx + 1) % len(self._keys)
            if self._idx not in self._exhausted:
                return True
        return False

    def _advance_round_robin(self):
        """正常 round-robin：每次呼叫輪換 key 以平衡用量。"""
        if len(self._keys) > 1:
            start = self._idx
            for _ in range(len(self._keys)):
                self._idx = (self._idx + 1) % len(self._keys)
                if self._idx not in self._exhausted:
                    return
            # 全耗盡也回原位
            self._idx = start

    def _get(self, endpoint: str, params: dict) -> dict | None:
        last_retry = 0
        while True:
            params["api_key"] = self.api_key
            try:
                resp = self.session.get(
                    f"{API_BASE}{endpoint}",
                    params=params,
                    timeout=30,
                )
                if resp.status_code == 429:
                    data = resp.json() if resp.text else {}
                    last_retry = data.get("retry_after", 0)
                    key_label = self.api_key[:8] + "..."
                    # 嘗試切換到下一把 key
                    if self._rotate():
                        next_label = self.api_key[:8] + "..."
                        import logging
                        logging.getLogger(__name__).info(
                            f"Key {key_label} 額度耗盡，切換至 {next_label}")
                        continue  # 用新 key 重試
                    # 全部 key 都耗盡
                    raise RateLimitError(
                        data.get("msg", "AllKeysExhausted"),
                        retry_after=last_retry,
                    )
                resp.raise_for_status()
                data = resp.json()
                if data.get("success"):
                    self._advance_round_robin()
                    return data.get("data", {})
                # API 回傳 success=false，印出警告
                msg = data.get("msg", "UnknownError")
                import logging
                logging.getLogger(__name__).warning(
                    f"MistTrack API {endpoint} 失敗: {msg} "
                    f"(key={self.api_key[:8]}...)")
                self._advance_round_robin()
                return None
            except RateLimitError:
                raise
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    f"MistTrack API {endpoint} 例外: {exc}")
                self._advance_round_robin()
                return None

    def get_labels(self, address: str) -> dict:
        return self._get("/v1/address_labels", {"coin": COIN, "address": address}) or {}

    def get_risk_score(self, address: str) -> dict:
        return self._get("/v2/risk_score", {"coin": COIN, "address": address}) or {}

    def get_overview(self, address: str) -> dict:
        return self._get("/v1/address_overview", {"coin": COIN, "address": address}) or {}

    def get_profile(self, address: str) -> dict:
        return self._get("/v1/address_trace", {"coin": COIN, "address": address}) or {}

    def get_transactions(self, address: str, direction: str = "out") -> dict:
        """多層資金追蹤（transactions_investigation）。
        direction: "out" (下游) 或 "in" (上游)
        """
        return self._get("/v1/transactions_investigation", {
            "coin": COIN, "address": address, "type": direction,
        }) or {}

    def get_counterparty(self, address: str) -> dict:
        """交易對手辨識（address_counterparty）— 交易所名稱+金額。"""
        return self._get("/v1/address_counterparty", {
            "coin": COIN, "address": address,
        }) or {}

    def get_actions(self, address: str) -> dict:
        """交易分類（address_action）— Exchange/DEX/Mixer 等。"""
        return self._get("/v1/address_action", {
            "coin": COIN, "address": address,
        }) or {}

    def analyze(self, address: str) -> MistTrackResult:
        """完整分析一個地址。"""
        result = MistTrackResult(address=address)

        # 1. Labels
        labels = self.get_labels(address)
        time.sleep(RATE_LIMIT_DELAY)
        if labels:
            result.label_list = labels.get("label_list", [])
            result.label_type = labels.get("label_type", "")

        # 2. Risk Score
        risk = self.get_risk_score(address)
        time.sleep(RATE_LIMIT_DELAY)
        if risk:
            result.risk_score = risk.get("score", 0)
            result.risk_level = risk.get("risk_level", "")
            result.hacking_event = risk.get("hacking_event", "")
            result.detail_list = risk.get("detail_list", [])
            result.risk_detail = risk.get("risk_detail", [])

        # 3. Overview
        overview = self.get_overview(address)
        time.sleep(RATE_LIMIT_DELAY)
        if overview:
            result.balance = overview.get("balance", 0.0)
            result.txs_count = overview.get("txs_count", 0)
            result.first_seen = overview.get("first_seen", 0)
            result.last_seen = overview.get("last_seen", 0)
            result.total_received = overview.get("total_received", 0.0)
            result.total_spent = overview.get("total_spent", 0.0)
            result.received_txs_count = overview.get("received_txs_count", 0)
            result.spent_txs_count = overview.get("spent_txs_count", 0)

        # 4. Profile / Trace
        profile = self.get_profile(address)
        time.sleep(RATE_LIMIT_DELAY)
        if profile:
            result.first_address = profile.get("first_address", "")
            result.use_platform = profile.get("use_platform", {})
            result.malicious_event = profile.get("malicious_event", {})

        return result


def analyze_addresses(
    addresses: list[str],
    api_key: str,
) -> dict[str, MistTrackResult]:
    """批次分析多個地址，回傳 {address: MistTrackResult}。"""
    client = MistTrackClient(api_key)
    results: dict[str, MistTrackResult] = {}

    unique = list(dict.fromkeys(addresses))  # 去重保序
    print(f"[MistTrack] 分析 {len(unique)} 個不重複地址（{client.key_count} 把 API key round-robin）...")

    for addr in tqdm(unique, desc="MistTrack 分析"):
        results[addr] = client.analyze(addr)

    return results
