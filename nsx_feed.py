#!/usr/bin/env python3
"""
Pre-Facelift NA2 Acura NSX feed aggregator
===========================================
Scrapes public listing sites for 1997-2001 Acura NSX / NSX-T listings
(the "manual NA2" window: 3.2L C32B engine, 6-speed manual, pop-up
headlights) and writes a combined RSS 2.0 feed to docs/feed.xml.

Point any RSS reader at the published feed URL (see README.md for how
to host this for free on GitHub Pages) and you'll get new matching
listings show up as unread items automatically.

SOURCES
-------
Wired up and verified against a live fetch on 2026-09-21:
  - Classics on Autotrader (classics.autotrader.com)

Stubbed out — the site doesn't expose a simple public search-results
page I could verify, so these need someone to inspect the real markup
before they're safe to rely on. See CONTRIBUTING a source below.
  - ClassicCars.com
  - Hemmings

Deliberately NOT scraped — use their native alerts instead (see
README.md "Sources this script does NOT cover" section for why):
  - Bring a Trailer
  - Classic.com
  - Cars & Bids / PCARMARKET / Collecting Cars

FILTERING
---------
"Manual NA2 pre-facelift" isn't always a labeled field on a search
results page, so this script uses a conservative heuristic: it only
EXCLUDES a listing when the page text explicitly says "automatic".
Anything ambiguous is left IN the feed — you'll see the occasional
automatic car you have to skip past, but you won't silently miss a
real manual listing because of a parsing miss. Adjust is_manual_text()
if you want it stricter.
"""

import re
import sys
import html
import hashlib
import time
from datetime import datetime, timezone
from email.utils import format_datetime

import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; NSXFeedBot/1.0; +personal, low-frequency use)"
TARGET_YEARS = range(1997, 2002)  # 1997-2001 inclusive
TIMEOUT = 20
REQUEST_DELAY = 1.5  # seconds between requests — be polite, this is a rare/low-volume search


def fetch(url):
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    resp.raise_for_status()
    time.sleep(REQUEST_DELAY)
    return resp.text


def is_manual_text(*texts):
    blob = " ".join(t for t in texts if t).lower()
    if "automatic" in blob or "auto trans" in blob or "sportshift" in blob:
        return False
    return True


# ---------------------------------------------------------------------------
# Source: Classics on Autotrader
# ---------------------------------------------------------------------------
def scrape_autotrader_classics():
    """
    URL pattern (confirmed live):
      https://classics.autotrader.com/classic-cars-for-sale/modern_performance-{year}-acura-nsx-for-sale

    Listing cards link to /classic-cars/{year}/acura/nsx/{id}. Matching on
    that URL pattern (rather than a CSS class) is deliberately resilient to
    Autotrader restyling the page — it'll keep working even if their HTML
    changes, as long as the URL scheme doesn't.
    """
    results = []
    for year in TARGET_YEARS:
        url = (
            "https://classics.autotrader.com/classic-cars-for-sale/"
            f"modern_performance-{year}-acura-nsx-for-sale"
        )
        try:
            page = fetch(url)
        except requests.RequestException as e:
            print(f"[autotrader] {year}: fetch failed ({e})", file=sys.stderr)
            continue

        soup = BeautifulSoup(page, "html.parser")
        seen_ids = set()
        href_pattern = re.compile(rf"/classic-cars/{year}/acura/nsx/(\d+)")

        for a in soup.find_all("a", href=href_pattern):
            href = a.get("href", "")
            m = href_pattern.search(href)
            if not m:
                continue
            listing_id = m.group(1)
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            full_url = href if href.startswith("http") else (
                "https://classics.autotrader.com" + href
            )
            card_text = a.get_text(" ", strip=True)
            container = a.find_parent(["div", "li", "article"]) or a
            context_text = container.get_text(" ", strip=True)[:400]

            if not is_manual_text(card_text, context_text):
                continue

            results.append({
                "id": f"autotrader-{listing_id}",
                "title": f"{year} Acura NSX — Classics on Autotrader",
                "url": full_url,
                "source": "Classics on Autotrader",
                "summary": context_text or card_text,
            })
    return results


# ---------------------------------------------------------------------------
# Add more sources here. Each function should return a list of dicts with
# keys: id, title, url, source, summary. Then add it to SOURCES below.
#
# def scrape_classiccars_com():
#     ...
#
# def scrape_hemmings():
#     ...
# ---------------------------------------------------------------------------

SOURCES = [
    scrape_autotrader_classics,
]


def build_rss(items, feed_path):
    now = format_datetime(datetime.now(timezone.utc))
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel>',
        "<title>Pre-Facelift NA2 NSX Watch (1997-2001, manual)</title>",
        "<link>https://github.com/</link>",
        "<description>Auto-generated feed of matching Acura NSX listings. "
        "Edit the &lt;link&gt; above to your GitHub Pages URL.</description>",
        f"<lastBuildDate>{now}</lastBuildDate>",
    ]
    for it in items:
        guid = hashlib.sha1(it["id"].encode()).hexdigest()
        parts.append("<item>")
        parts.append(f"<title>{html.escape(it['title'])}</title>")
        parts.append(f"<link>{html.escape(it['url'])}</link>")
        parts.append(f'<guid isPermaLink="false">{guid}</guid>')
        parts.append(f"<description>{html.escape(it['summary'])}</description>")
        parts.append(f"<pubDate>{now}</pubDate>")
        parts.append("</item>")
    parts.append("</channel></rss>")

    with open(feed_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def main():
    all_items = []
    for source_fn in SOURCES:
        try:
            found = source_fn()
            print(f"[{source_fn.__name__}] {len(found)} matching listings")
            all_items.extend(found)
        except Exception as e:
            print(f"[error] {source_fn.__name__} failed: {e}", file=sys.stderr)

    seen = set()
    deduped = []
    for it in all_items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        deduped.append(it)

    build_rss(deduped, feed_path="docs/feed.xml")
    print(f"Wrote {len(deduped)} total listings to docs/feed.xml")


if __name__ == "__main__":
    main()
