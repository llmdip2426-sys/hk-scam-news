#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日抓取：
1. unwire.hk 最新科技／手機新聞（最多5則）
2. 防騙／詐騙相關新聞（最多5則；不足則用治安／政府新聞補足）
"""

import json
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import urllib.request

HKT = timezone(timedelta(hours=8))

FEEDS = [
    {"name": "明報即時港聞", "url": "https://news.mingpao.com/rss/ins/s00001.xml", "type": "general"},
    {"name": "明報即時", "url": "https://news.mingpao.com/rss/ins/s00024.xml", "type": "general"},
    {"name": "明報港聞", "url": "https://news.mingpao.com/rss/pns/s00001.xml", "type": "general"},
    {"name": "RTHK本地", "url": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml", "type": "general"},
    {"name": "RTHK財經", "url": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml", "type": "general"},
    {"name": "政府新聞網-治安", "url": "https://www.news.gov.hk/tc/categories/law_order/html/articlelist.rss.xml", "type": "law"},
    {"name": "政府新聞網-主要", "url": "https://www.news.gov.hk/tc/common/html/topstories.rss.xml", "type": "general"},
    {"name": "新聞公報", "url": "https://www.info.gov.hk/gia/rss/general_zh.xml", "type": "general"},
    {"name": "unwire.hk", "url": "https://unwire.hk/feed/", "type": "unwire"},
    {"name": "Yahoo香港", "url": "https://hk.news.yahoo.com/rss/", "type": "general"},
]

KEYWORDS = [
    "騙", "假冒", "釣魚", "防騙", "詐騙", "短訊", "SMS",
    "WhatsApp", "騎劫", "偽基站", "假客服", "電話騙", "手機騙", "手機詐騙",
    "騙案", "騙徒", "騙款", "騙取", "騙走", "中伏", "網罪科", "貓池",
    "假短訊", "假網站", "假連結", "釣魚短訊", "帳戶騎劫",
    "Scameter", "守網者", "反詐", "18222", "防騙易"
]

MAX_UNWIRE = 5
MAX_SCAM = 5
MAX_AGE_DAYS = 30

def fetch_rss_via_rss2json(rss_url):
    api = "https://api.rss2json.com/v1/api.json?rss_url=" + quote(rss_url)
    try:
        with urllib.request.urlopen(api, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") != "ok":
            return []
        return data.get("items", [])
    except Exception as e:
        print(f"RSS failed: {rss_url} -> {e}")
        return []

def is_relevant(title, desc):
    text = ((title or "") + " " + (desc or "")).lower()
    return any(kw.lower() in text for kw in KEYWORDS)

def parse_date(date_str):
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

def within_days(pub, days):
    if not pub:
        return True
    try:
        age = (datetime.now(timezone.utc) - pub.astimezone(timezone.utc)).days
        return age <= days
    except Exception:
        return True

def clean_desc(desc):
    if not desc:
        return ""
    return re.sub(r"<[^>]+>", "", desc).replace("&nbsp;", " ").strip()[:300]

def main():
    unwire_items = []
    scam_items = []
    law_items = []
    seen = set()

    for feed in FEEDS:
        raw = fetch_rss_via_rss2json(feed["url"])
        for it in raw:
            title = (it.get("title") or "").strip()
            if not title or title in seen:
                continue
            desc = clean_desc(it.get("description") or "")
            pub = parse_date(it.get("pubDate"))
            if not within_days(pub, MAX_AGE_DAYS):
                continue

            item = {
                "title": title,
                "link": it.get("link") or "",
                "pubDate": it.get("pubDate") or "",
                "description": desc,
                "source": feed["name"]
            }
            seen.add(title)

            if feed["type"] == "unwire":
                unwire_items.append(item)
            elif feed["type"] == "law":
                law_items.append(item)
                if is_relevant(title, desc):
                    scam_items.append(item)
            else:
                if is_relevant(title, desc):
                    scam_items.append(item)

    # 排序：最新在上
    def sort_key(x):
        return x.get("pubDate") or ""

    unwire_items.sort(key=sort_key, reverse=True)
    scam_items.sort(key=sort_key, reverse=True)
    law_items.sort(key=sort_key, reverse=True)

    unwire_items = unwire_items[:MAX_UNWIRE]

    scam_is_fallback = False
    if len(scam_items) < MAX_SCAM:
        # 用治安／政府新聞補足
        existing_titles = {x["title"] for x in scam_items}
        for it in law_items:
            if it["title"] not in existing_titles:
                scam_items.append(it)
                existing_titles.add(it["title"])
            if len(scam_items) >= MAX_SCAM:
                break
        if not any(is_relevant(x["title"], x["description"]) for x in scam_items):
            scam_is_fallback = True
        elif len([x for x in scam_items if is_relevant(x["title"], x["description"])]) < MAX_SCAM:
            # 有部分相關，但用了補足
            pass

    scam_items = scam_items[:MAX_SCAM]

    # 若全部都係相關就唔標 fallback；若主要靠治安新聞就標
    relevant_count = sum(1 for x in scam_items if is_relevant(x["title"], x["description"]))
    if relevant_count == 0:
        scam_is_fallback = True

    result = {
        "updated_at": datetime.now(HKT).strftime("%Y-%m-%d %H:%M:%S"),
        "unwire": unwire_items,
        "scam": scam_items,
        "scam_is_fallback": scam_is_fallback,
        "unwire_count": len(unwire_items),
        "scam_count": len(scam_items)
    }

    with open("scam_news.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"unwire: {len(unwire_items)}, scam: {len(scam_items)}, fallback={scam_is_fallback}")

if __name__ == "__main__":
    main()
