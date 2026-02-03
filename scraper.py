"""司法院裁判書查詢系統抓取模組。"""

import hashlib
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

import config


@dataclass
class Judgment:
    """一筆判決書資料。"""
    case_id: str        # 案號
    court: str          # 法院
    full_text: str      # 判決書全文
    url: str            # 原始網址


def _cache_path(case_id: str) -> str:
    """根據案號產生快取檔案路徑。"""
    safe = hashlib.md5(case_id.encode()).hexdigest()
    return os.path.join(config.CACHE_DIR, f"{safe}.txt")


def _load_cache(case_id: str) -> str | None:
    path = _cache_path(case_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def _save_cache(case_id: str, text: str) -> None:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    with open(_cache_path(case_id), "w", encoding="utf-8") as f:
        f.write(text)


def _extract_hidden_fields(html: str) -> dict[str, str]:
    """擷取 ASP.NET hidden fields（__VIEWSTATE 等）及其他 hidden inputs。"""
    soup = BeautifulSoup(html, "lxml")
    fields = {}
    for tag in soup.find_all("input", {"type": "hidden"}):
        name = tag.get("name", "")
        if name:
            fields[name] = tag.get("value", "")
    return fields


class Scraper:
    """司法院判決書抓取器。"""

    RESULT_LIST_URL = config.BASE_URL + "qryresultlst.aspx"

    def __init__(
        self,
        date_start: str = config.DEFAULT_DATE_START,
        date_end: str = config.DEFAULT_DATE_END,
        max_pages: int = config.MAX_PAGES,
        delay: float = config.REQUEST_DELAY,
    ):
        self.date_start = date_start
        self.date_end = date_end
        self.max_pages = max_pages
        self.delay = delay

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })

    def _sleep(self):
        time.sleep(self.delay)

    # ------------------------------------------------------------------
    # Step 1: 取得搜尋頁面的 hidden fields
    # ------------------------------------------------------------------
    def _get_search_page(self) -> dict[str, str]:
        """GET 搜尋頁面，回傳 hidden fields。"""
        resp = self.session.get(config.SEARCH_URL, timeout=30)
        resp.raise_for_status()
        return _extract_hidden_fields(resp.text)

    # ------------------------------------------------------------------
    # Step 2: POST 搜尋表單，取得 query ID
    # ------------------------------------------------------------------
    def _post_search(self, keyword: str) -> tuple[str, int]:
        """送出搜尋表單（單一關鍵字），回傳 (QID, 結果數量)。"""
        # 每次搜尋前重新取得 hidden fields（VIEWSTATE 會過期）
        hidden = self._get_search_page()

        # 日期格式為 YYYMMDD，月日固定各 2 碼，年份為剩餘前段
        dy1 = self.date_start[:-4]
        dm1 = self.date_start[-4:-2]
        dd1 = self.date_start[-2:]
        dy2 = self.date_end[:-4]
        dm2 = self.date_end[-4:-2]
        dd2 = self.date_end[-2:]

        data = {
            **hidden,
            "jud_sys": config.JUD_SYS,
            "jud_title": config.JUD_TITLE,
            "jud_kw": keyword,
            "dy1": dy1,
            "dm1": dm1,
            "dd1": dd1,
            "dy2": dy2,
            "dm2": dm2,
            "dd2": dd2,
            "jud_court": "",
            "jud_year": "",
            "jud_case": "",
            "jud_no": "",
            "jud_no_end": "",
            "jud_jmain": "",
            "KbStart": "",
            "KbEnd": "",
            "ctl00$cp_content$btnQry": "送出查詢",
        }
        self._sleep()
        resp = self.session.post(config.SEARCH_URL, data=data, timeout=30)
        resp.raise_for_status()

        # 從結果頁擷取 QID 與結果數量
        soup = BeautifulSoup(resp.text, "lxml")
        qid_input = soup.find("input", {"name": "hidQID"})
        if not qid_input:
            raise RuntimeError("無法取得查詢 ID (hidQID)，搜尋可能失敗")
        qid = qid_input.get("value", "")

        count = 0
        count_div = soup.find("div", {"id": "result-count"})
        if count_div:
            badge = count_div.find("span", class_="badge")
            if badge:
                try:
                    count = int(badge.get_text(strip=True))
                except ValueError:
                    pass

        return qid, count

    # ------------------------------------------------------------------
    # Step 3: 從結果列表頁擷取判決書連結
    # ------------------------------------------------------------------
    def _fetch_result_list(self, qid: str, page: int = 1) -> str:
        """取得指定頁數的結果列表 HTML。"""
        url = f"{self.RESULT_LIST_URL}?ty=JUDBOOK&q={qid}&page={page}"
        self._sleep()
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def _parse_result_links(self, html: str) -> list[tuple[str, str, str]]:
        """從結果列表頁擷取 (case_id, court, detail_url) 清單。"""
        soup = BeautifulSoup(html, "lxml")
        results = []
        for a_tag in soup.select("a[href*='data.aspx']"):
            href = a_tag.get("href", "")
            if "ty=JD" not in href and "ty=jd" not in href.lower():
                continue
            url = urljoin(config.BASE_URL, href)
            text = a_tag.get_text(strip=True)
            # 格式: "臺灣臺北地方法院 113 年度 訴 字第 582 號刑事判決"
            court = ""
            case_id = text
            m = re.match(r"^([\u4e00-\u9fff]+(?:法院))\s*(.+)$", text)
            if m:
                court = m.group(1)
                case_id = m.group(2)
            results.append((case_id, court, url))
        return results

    def _has_next_page(self, html: str) -> bool:
        """檢查是否有下一頁。"""
        soup = BeautifulSoup(html, "lxml")
        for a_tag in soup.find_all("a"):
            text = a_tag.get_text(strip=True)
            if "下一頁" in text:
                return True
        return False

    # ------------------------------------------------------------------
    # Step 4: 抓取判決書全文
    # ------------------------------------------------------------------
    def _fetch_judgment_text(self, url: str) -> str:
        """抓取單一判決書全文。"""
        self._sleep()
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        # 判決書全文通常在特定容器中
        for selector in [
            ("div", {"id": "jud_body"}),
            ("div", {"class": "jud-body"}),
            ("div", {"id": "jud"}),
            ("pre", {}),
        ]:
            body = soup.find(selector[0], selector[1])
            if body:
                return body.get_text("\n", strip=True)
        # fallback: 取整頁文字
        body = soup.find("body")
        return body.get_text("\n", strip=True) if body else ""

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def _collect_links_for_keyword(self, keyword: str) -> list[tuple[str, str, str]]:
        """對單一關鍵字執行搜尋並收集所有結果連結。"""
        print(f"\n[*] 搜尋關鍵字：{keyword}")
        qid, count = self._post_search(keyword)
        print(f"  結果：{count} 筆 (QID: {qid})")

        if count == 0:
            return []

        links: list[tuple[str, str, str]] = []
        for page_num in range(1, self.max_pages + 1):
            print(f"  取得列表第 {page_num} 頁...")
            list_html = self._fetch_result_list(qid, page=page_num)
            page_links = self._parse_result_links(list_html)
            if not page_links:
                break
            links.extend(page_links)
            print(f"    找到 {len(page_links)} 筆")

            if not self._has_next_page(list_html):
                break

        return links

    def scrape(self) -> list[Judgment]:
        """執行完整抓取流程，回傳判決書列表。"""
        # 對每個關鍵字分別搜尋，合併去重（以 URL 為 key）
        all_links: dict[str, tuple[str, str, str]] = {}  # url -> (case_id, court, url)

        for keyword in config.FULL_TEXT_KEYWORDS:
            links = self._collect_links_for_keyword(keyword)
            for case_id, court, url in links:
                if url not in all_links:
                    all_links[url] = (case_id, court, url)

        unique_links = list(all_links.values())
        print(f"\n[*] 合併去重後共 {len(unique_links)} 筆判決書，開始抓取全文...")

        judgments: list[Judgment] = []
        for case_id, court, url in tqdm(unique_links, desc="抓取判決書"):
            # 檢查快取
            cached = _load_cache(case_id)
            if cached:
                full_text = cached
            else:
                try:
                    full_text = self._fetch_judgment_text(url)
                    _save_cache(case_id, full_text)
                except Exception as e:
                    print(f"\n  [!] 抓取失敗: {case_id} — {e}")
                    continue

            if full_text:
                judgments.append(Judgment(
                    case_id=case_id,
                    court=court,
                    full_text=full_text,
                    url=url,
                ))

        print(f"[*] 成功取得 {len(judgments)} 筆判決書全文")
        return judgments
