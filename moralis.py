"""Moralis API 整合模組：TRON 鏈上交易資料查詢。"""

import time

import requests

MORALIS_API_BASE = "https://deep-index.moralis.io/api/v2.2"
RATE_LIMIT_DELAY = 0.3


class MoralisClient:
    """Moralis Web3 API 客戶端 — 用於 TRON 鏈交易明細補充。"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "X-API-Key": api_key,
        })

    def _get(self, path: str, params: dict | None = None) -> dict | list | None:
        try:
            resp = self.session.get(
                f"{MORALIS_API_BASE}{path}",
                params=params or {},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def get_trc20_transfers(
        self,
        address: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict | None:
        """取得 TRC20 代幣轉帳紀錄（主要用於 USDT）。"""
        params: dict = {"chain": "tron", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        time.sleep(RATE_LIMIT_DELAY)
        return self._get(f"/{address}/erc20/transfers", params)

    def get_native_balance(self, address: str) -> dict | None:
        """取得原生代幣（TRX）餘額。"""
        time.sleep(RATE_LIMIT_DELAY)
        return self._get(f"/{address}/balance", {"chain": "tron"})

    def get_transactions(
        self,
        address: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict | None:
        """取得原生交易紀錄。"""
        params: dict = {"chain": "tron", "limit": limit}
        if cursor:
            params["cursor"] = cursor
        time.sleep(RATE_LIMIT_DELAY)
        return self._get(f"/{address}", params)

    def get_all_trc20_transfers(
        self,
        address: str,
        max_pages: int = 5,
    ) -> list[dict]:
        """分頁取得所有 TRC20 轉帳紀錄。"""
        all_transfers: list[dict] = []
        cursor = None

        for _ in range(max_pages):
            result = self.get_trc20_transfers(address, cursor=cursor)
            if not result:
                break
            transfers = result.get("result", [])
            if not transfers:
                break
            all_transfers.extend(transfers)
            cursor = result.get("cursor")
            if not cursor:
                break

        return all_transfers
