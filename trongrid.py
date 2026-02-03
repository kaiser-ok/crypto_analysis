"""TronGrid API 整合模組：TRON 鏈上交易資料查詢（完整鏈上數據）。"""

import logging
import time

import requests

TRONGRID_API_BASE = "https://api.trongrid.io"
RATE_LIMIT_DELAY = 0.2
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

log = logging.getLogger(__name__)


class TronGridClient:
    """TronGrid API 客戶端 — 用於取得完整 TRON 鏈上交易數據。

    TronGrid 為 TRON 官方提供的免費 API，無 key 限制 15 req/s，有 key 可提高至 50 req/s。
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.session = requests.Session()
        headers = {"Accept": "application/json"}
        if api_key:
            headers["TRON-PRO-API-KEY"] = api_key
        self.session.headers.update(headers)

    def _get(self, path: str, params: dict | None = None) -> dict | None:
        """發送 GET 請求至 TronGrid API。"""
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = self.session.get(
                f"{TRONGRID_API_BASE}{path}",
                params=params or {},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            log.warning(f"TronGrid API {path} 例外: {exc}")
            return None

    def get_account(self, address: str) -> dict | None:
        """取得帳戶基本資訊（TRX 餘額等）。"""
        return self._get(f"/v1/accounts/{address}")

    def get_trc20_transfers(
        self,
        address: str,
        contract_address: str | None = None,
        limit: int = 200,
        fingerprint: str | None = None,
        min_timestamp: int | None = None,
        max_timestamp: int | None = None,
    ) -> dict | None:
        """取得 TRC20 代幣轉帳紀錄。

        contract_address: 指定合約地址僅查單一代幣（如 USDT），None 查全部 TRC20 代幣。
        fingerprint: 分頁游標，由前一頁回傳。
        """
        params: dict = {"limit": limit, "order_by": "block_timestamp,asc"}
        if contract_address:
            params["contract_address"] = contract_address
        if fingerprint:
            params["fingerprint"] = fingerprint
        if min_timestamp:
            params["min_timestamp"] = min_timestamp
        if max_timestamp:
            params["max_timestamp"] = max_timestamp
        return self._get(f"/v1/accounts/{address}/transactions/trc20", params)

    def get_trx_transfers(
        self,
        address: str,
        limit: int = 200,
        fingerprint: str | None = None,
    ) -> dict | None:
        """取得 TRX 原生交易紀錄。"""
        params: dict = {"limit": limit, "order_by": "block_timestamp,asc"}
        if fingerprint:
            params["fingerprint"] = fingerprint
        return self._get(f"/v1/accounts/{address}/transactions", params)

    def get_all_trc20_transfers(
        self,
        address: str,
        contract_address: str | None = None,
        max_pages: int = 50,
        min_timestamp: int | None = None,
        max_timestamp: int | None = None,
    ) -> list[dict]:
        """分頁取得完整 TRC20 轉帳歷史。

        contract_address: None 查全部 TRC20 代幣，指定合約則僅查該幣。
        min_timestamp / max_timestamp: 毫秒 Unix timestamp，TronGrid 伺服器端過濾。
        回傳每筆交易包含 token_info.symbol 和 token_info.decimals。
        """
        all_transfers: list[dict] = []
        fingerprint = None

        for page in range(max_pages):
            result = self.get_trc20_transfers(
                address,
                contract_address=contract_address,
                fingerprint=fingerprint,
                min_timestamp=min_timestamp,
                max_timestamp=max_timestamp,
            )
            if not result:
                break

            transfers = result.get("data", [])
            if not transfers:
                break

            all_transfers.extend(transfers)
            log.info(f"  [TronGrid] {address[:12]}... 第 {page + 1} 頁: "
                     f"{len(transfers)} 筆 (累計 {len(all_transfers)})")

            # 分頁: TronGrid 使用 meta.fingerprint
            meta = result.get("meta", {})
            fingerprint = meta.get("fingerprint")
            if not fingerprint:
                break

        return all_transfers
