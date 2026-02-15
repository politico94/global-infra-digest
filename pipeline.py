#!/usr/bin/env python3
"""
Global Infrastructure Intelligence Digest — Free Pipeline
Center of Excellence: Policy, Finance & Delivery

Zero API costs. Fetches from 85+ global sources via RSS,
filters by keyword relevance, categorizes by rule-based matching,
and publishes a professional HTML digest.
"""

import os
import sys
import json
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict
from urllib.parse import urljoin

import yaml
import feedparser
import httpx
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent
SOURCES_FILE = ROOT / "sources.yaml"
TEMPLATE_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output"
ARCHIVE_DIR = ROOT / "archive"

OUTPUT_DIR.mkdir(exist_ok=True)
ARCHIVE_DIR.mkdir(exist_ok=True)

MAX_ITEMS_PER_SOURCE = 15
MAX_AGE_DAYS = 2
REQUEST_TIMEOUT = 20
MAX_ITEMS_PER_SECTION = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("infra-digest")

# ---------------------------------------------------------------------------
# SECTION CATEGORIZATION RULES
# ---------------------------------------------------------------------------

SECTION_RULES = {
    "multilateral_finance": {
        "source_hints": [
            "world bank", "ifc", "asian development bank", "african development bank",
            "aiib", "european investment bank", "ebrd", "new development bank",
            "oecd", "g20", "global infrastructure hub", "un-habitat",
        ],
        "keywords": [
            "world bank", "ifc ", "adb ", "aiib", "eib ", "ebrd", "ndb ",
            "oecd", "g20", "g7", "multilateral", "development bank",
            "development finance", "concessional", "sovereign guarantee",
            "global infrastructure hub", "un-habitat", "sdg", "mdb ",
            "international finance", "bilateral aid", "official development",
        ],
    },
    "major_economies": {
        "source_hints": [
            "us dot", "federal highway", "us epa", "army corps", "white house",
            "build america", "brookings", "eno center", "asce",
            "reason foundation", "national infrastructure commission",
            "infrastructure & projects authority", "european commission",
            "bruegel", "infrastructure intelligence", "new civil engineer",
            "france", "germany", "bmvi",
            "infrastructure australia", "infrastructure partnerships australia",
            "india", "gati shakti", "niti aayog", "belt and road",
            "japan", "south korea", "asean", "infrastructure asia",
        ],
        "keywords": [
            "united states", "us dot", "fhwa", "iija", "bipartisan infrastructure",
            "buy america", "european union", "ten-t", "investeu", "european commission",
            "united kingdom", "uk infrastructure", "national infrastructure commission",
            "india infrastructure", "gati shakti", "national infrastructure pipeline",
            "china infrastructure", "belt and road", "bri ", "australia infrastructure",
            "infrastructure australia", "japan infrastructure", "mlit",
            "south korea", "germany infrastructure", "france infrastructure",
            "gulf states", "saudi arabia", "neom", "uae infrastructure",
        ],
    },
    "canada_watch": {
        "source_hints": [
            "infrastructure canada", "canada infrastructure bank",
            "infrastructure ontario", "parliamentary budget officer",
            "ontario financial accountability", "c.d. howe",
            "federation of canadian municipalities", "canadian council for p3",
            "renew canada", "daily commercial news",
            "global affairs canada", "canada gazette",
        ],
        "keywords": [
            "canada", "canadian", "ontario", "quebec", "british columbia",
            "alberta", "infrastructure canada", "infrastructure ontario",
            "canada infrastructure bank", "cib ", "pbo ", "fao ",
            "fcm ", "municipal infrastructure", "provincial infrastructure",
            "ccppp", "p3 canada", "housing accelerator",
            "transit canada", "via rail", "metrolinx",
        ],
    },
    "project_finance_delivery": {
        "source_hints": [
            "world bank ppp", "global infrastructure investor",
            "ijglobal", "infrastructure investor", "preqin",
            "kpmg", "deloitte", "mckinsey",
        ],
        "keywords": [
            "public-private partnership", "ppp ", "p3 ", "concession",
            "design-build", "design build", "dbfm", "dbfom", "dbo ",
            "alliance contract", "progressive design", "project finance",
            "infrastructure fund", "infrastructure investor",
            "asset recycling", "toll road", "toll revenue",
            "procurement model", "delivery model", "risk allocation",
            "financial close", "bid ", "tender", "rfp ", "rfq ",
            "availability payment", "revenue risk",
            "lifecycle cost", "value for money", "vfm ",
        ],
    },
    "climate_sustainability": {
        "source_hints": [
            "climate bonds", "global commission on adaptation",
            "coalition for climate resilient", "unep",
            "green climate fund", "iea", "irena", "c40",
        ],
        "keywords": [
            "climate", "green bond", "green infrastructure",
            "resilience", "adaptation", "net zero", "net-zero",
            "renewable energy infrastructure", "clean energy",
            "carbon capture", "ccs ", "ccus", "hydrogen",
            "sustainable infrastructure", "nature-based",
            "flood", "wildfire", "extreme weather",
            "climate bond", "green finance", "esg ",
            "just transition", "energy transition",
            "circular economy", "embodied carbon",
        ],
    },
    "tech_innovation": {
        "source_hints": [
            "smart cities world", "digital twin consortium",
            "buildingsmart", "world economic forum",
            "mit senseable", "iot analytics",
        ],
        "keywords": [
            "digital twin", "bim ", "building information model",
            "smart city", "smart cities", "smart infrastructure",
            "iot ", "internet of things", "artificial intelligence",
            "ai infrastructure", "machine learning",
            "construction technology", "contech", "infratech",
            "govtech", "modular construction", "prefab",
            "3d printing construction", "robotics construction",
            "autonomous vehicle", "ev charging", "5g ",
            "fiber optic", "data center",
        ],
    },
}

# ---------------------------------------------------------------------------
# LOAD SOURCES
# ---------------------------------------------------------------------------

def load_sources() -> dict:
    with open(SOURCES_FILE) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# FETCH
# ---------------------------------------------------------------------------

def fetch_rss(source: dict) -> list[dict]:
    """Parse an RSS/Atom feed and return normalized items."""
    items = []
    try:
        feed_url = source.get("feed", source["url"])
        feed = feedparser.parse(feed_url)
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

        for entry in feed.entries[:MAX_ITEMS_PER_SOURCE]:
            published = None
            for date_field in ("published_parsed", "updated_parsed"):
                t = getattr(entry, date_field, None)
                if t:
                    from time import mktime
                    published = datetime.fromtimestamp(mktime(t), tz=timezone.utc)
                    break

            if published and published < cutoff:
                continue

            title = entry.get("title", "").strip()
            url = entry.get("link", "").strip()
            raw_summary = entry.get("summary", "") or entry.get("description", "")
            summary = _clean_html(raw_summary)

            if not title or len(title) < 10:
                continue

            items.append({
                "title": title,
                "url": url,
                "summary": summary,
                "published": published.isoformat() if published else None,
                "source": source["name"],
                "tier": source.get("tier", 3),
            })
    except Exception as e:
        log.warning(f"RSS fetch failed for {source['name']}: {e}")
    return items


def fetch_scrape(source: dict) -> list[dict]:
    """Scrape a webpage for recent links/headlines."""
    items = []
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Global Infrastructure Digest Bot; +https://politico94.github.io/global-infra-digest)"
        }
        r = httpx.get(source["url"], headers=headers, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        seen_urls = set()
        for tag in soup.find_all("a", href=True):
            title = tag.get_text(strip=True)
            href = tag["href"]

            if len(title) < 20 or len(title) > 300:
                continue
            if href.startswith("/"):
                href = urljoin(source["url"], href)
            if not href.startswith("http"):
                continue
            if href in seen_urls:
                continue

            # Skip navigation / boilerplate links
            skip_patterns = [
                "login", "sign-in", "subscribe", "cookie", "privacy",
                "terms", "contact", "about-us", "careers", "javascript:",
                "mailto:", "#", "facebook.com", "twitter.com", "linkedin.com",
            ]
            if any(p in href.lower() for p in skip_patterns):
                continue

            seen_urls.add(href)

            items.append({
                "title": title,
                "url": href,
                "summary": "",
                "published": None,
                "source": source["name"],
                "tier": source.get("tier", 3),
            })

            if len(items) >= MAX_ITEMS_PER_SOURCE:
                break

    except Exception as e:
        log.warning(f"Scrape failed for {source['name']}: {e}")
    return items


def fetch_source(source: dict) -> list[dict]:
    if source.get("type") == "rss":
        return fetch_rss(source)
    return fetch_scrape(source)


# ---------------------------------------------------------------------------
# FILTER & DEDUPLICATE
# ---------------------------------------------------------------------------

def _clean_html(text: str) -> str:
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=" ", strip=True)
    # Truncate to ~300 chars at a word boundary
    if len(clean) > 300:
        clean = clean[:300].rsplit(" ", 1)[0] + "…"
    return clean


def _item_hash(item: dict) -> str:
    raw = (item.get("title", "") + item.get("url", "")).lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()


def keyword_relevance(items: list[dict], config: dict) -> list[dict]:
    """Score items by infrastructure keyword relevance."""
    primary = [k.lower() for k in config.get("keywords", {}).get("primary", [])]
    secondary = [k.lower() for k in config.get("keywords", {}).get("secondary", [])]

    scored = []
    for item in items:
        text = f"{item['title']} {item.get('summary', '')}".lower()
        score = 0

        for kw in primary:
            if kw in text:
                score += 2
        for kw in secondary:
            if kw in text:
                score += 1

        # Tier boost — Tier 1 sources are almost always relevant
        if item.get("tier") == 1:
            score += 3
        elif item.get("tier") == 2:
            score += 1

        if score >= 2:
            item["relevance_score"] = score
            scored.append(item)

    return scored


def deduplicate(items: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in items:
        h = _item_hash(item)
        if h not in seen:
            seen.add(h)
            unique.append(item)
    return unique


# ---------------------------------------------------------------------------
# RULE-BASED CATEGORIZATION (NO AI)
# ---------------------------------------------------------------------------

def categorize_items(items: list[dict]) -> dict:
    """Categorize items into sections using rule-based matching."""
    sections = {section_id: [] for section_id in SECTION_RULES}
    used_urls = set()

    # Sort by relevance score descending
    items.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    for item in items:
        text = f"{item['title']} {item.get('summary', '')}".lower()
        source_lower = item.get("source", "").lower()

        best_section = None
        best_score = 0

        for section_id, rules in SECTION_RULES.items():
            score = 0

            # Source name matching (strong signal)
            for hint in rules["source_hints"]:
                if hint in source_lower:
                    score += 5
                    break

            # Keyword matching
            for kw in rules["keywords"]:
                if kw in text:
                    score += 1

            if score > best_score:
                best_score = score
                best_section = section_id

        if best_section and best_score >= 2 and item["url"] not in used_urls:
            if len(sections[best_section]) < MAX_ITEMS_PER_SECTION:
                # Assign significance based on tier + relevance
                total_score = item.get("relevance_score", 0) + best_score
                if total_score >= 10 or item.get("tier") == 1:
                    significance = "high"
                elif total_score >= 5:
                    significance = "medium"
                else:
                    significance = "low"

                sections[best_section].append({
                    "title": item["title"],
                    "url": item["url"],
                    "source": item["source"],
                    "summary": item.get("summary", ""),
                    "significance": significance,
                })
                used_urls.add(item["url"])

    return sections


def generate_pulse(sections: dict) -> str:
    """Generate a data-driven pulse summary from what's in today's digest."""
    total_items = sum(len(v) for v in sections.values())
    high_items = []
    for items in sections.values():
        for item in items:
            if item.get("significance") == "high":
                high_items.append(item["title"])

    active_sections = [sid for sid, items in sections.items() if items]
    section_labels = {
        "multilateral_finance": "multilateral development finance",
        "major_economies": "major economy infrastructure policy",
        "canada_watch": "Canadian infrastructure",
        "project_finance_delivery": "project finance and delivery",
        "climate_sustainability": "climate resilience and sustainability",
        "tech_innovation": "technology and innovation",
    }

    if total_items == 0:
        return "A quiet day across global infrastructure — no significant developments met our relevance threshold. Check back tomorrow."

    parts = [f"Today's digest tracks {total_items} developments across {len(active_sections)} domains."]

    if high_items:
        top = high_items[:3]
        if len(top) == 1:
            parts.append(f"Top story: {top[0]}.")
        else:
            headlines = "; ".join(top[:2])
            parts.append(f"Key developments include: {headlines}.")

    coverage = [section_labels.get(s, s) for s in active_sections[:4]]
    if coverage:
        parts.append(f"Coverage spans {', '.join(coverage[:-1])}, and {coverage[-1]}." if len(coverage) > 1 else f"Coverage focuses on {coverage[0]}.")

    return " ".join(parts)


def generate_outlook(sections: dict) -> str:
    """Generate a simple forward-looking note."""
    active = sum(1 for v in sections.values() if v)
    if active >= 5:
        return "Broad coverage across all six domains today suggests an active policy week ahead. Monitor multilateral announcements and national budget developments for signals on infrastructure spending trajectories. Subscribe via RSS or bookmark this page for tomorrow's edition."
    elif active >= 3:
        return "Moderate activity across infrastructure policy channels. Watch for follow-up developments on today's high-significance items, particularly any cross-border procurement or financing announcements. Tomorrow's digest will track continuations."
    else:
        return "A lighter day in infrastructure intelligence. Policy cycles often see surges around fiscal year milestones, parliamentary sessions, and multilateral convenings. Check back tomorrow for updated coverage."


# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------

def render_digest(sections: dict, pulse: str, outlook: str, config: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("digest.html")

    sections_config = {s["id"]: s for s in config.get("sections", [])}

    digest_data = {
        "pulse": pulse,
        "outlook": outlook,
        "sections": sections,
    }

    return template.render(
        digest=digest_data,
        sections_config=sections_config,
        generated_at=datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC"),
        date_display=datetime.now(timezone.utc).strftime("%A, %B %d, %Y"),
        total_sources=config.get("metadata", {}).get("total_sources", "85+"),
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    dry_run = "--dry-run" in sys.argv

    log.info("=" * 60)
    log.info("GLOBAL INFRASTRUCTURE INTELLIGENCE DIGEST")
    log.info("Free Edition — Zero API Costs")
    log.info("=" * 60)

    # 1. Load sources
    config = load_sources()
    log.info(f"Loaded {config['metadata']['total_sources']} sources across {config['metadata']['categories']} categories")

    # 2. Fetch from all source categories
    all_items = []
    source_categories = [
        "multilateral", "united_states", "europe_uk", "asia_pacific",
        "canada", "project_finance", "climate_resilience", "smart_infra",
    ]

    for cat_key in source_categories:
        category = config.get(cat_key, {})
        sources = category.get("sources", [])
        label = category.get("label", cat_key)
        log.info(f"\n--- {label} ({len(sources)} sources) ---")

        for source in sources:
            items = fetch_source(source)
            log.info(f"  {source['name']}: {len(items)} items")
            all_items.extend(items)

    log.info(f"\nTotal raw items: {len(all_items)}")

    # 3. Filter & deduplicate
    scored = keyword_relevance(all_items, config)
    log.info(f"After keyword filter: {len(scored)}")

    unique = deduplicate(scored)
    log.info(f"After dedup: {len(unique)}")

    if dry_run:
        log.info("\n--- DRY RUN: Top 25 items ---")
        unique.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        for item in unique[:25]:
            log.info(f"  [{item.get('relevance_score', 0)}] {item['source']}: {item['title'][:80]}")
        log.info(f"\nDry run complete. {len(unique)} items ready for categorization.")
        return

    # 4. Categorize (rule-based, no AI)
    log.info("\nCategorizing items (rule-based engine)...")
    sections = categorize_items(unique)

    for section_id, items in sections.items():
        log.info(f"  {section_id}: {len(items)} items")

    # 5. Generate pulse & outlook
    pulse = generate_pulse(sections)
    outlook = generate_outlook(sections)

    # 6. Render HTML
    html = render_digest(sections, pulse, outlook, config)
    output_path = OUTPUT_DIR / "index.html"
    output_path.write_text(html, encoding="utf-8")
    log.info(f"\nDigest written to {output_path}")

    # 7. Archive
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    archive_data = {
        "date": date_str,
        "pulse": pulse,
        "outlook": outlook,
        "sections": sections,
        "stats": {
            "raw_items": len(all_items),
            "filtered": len(scored),
            "unique": len(unique),
            "published": sum(len(v) for v in sections.values()),
        },
    }
    archive_path = ARCHIVE_DIR / f"digest-{date_str}.json"
    archive_path.write_text(json.dumps(archive_data, indent=2, default=str), encoding="utf-8")
    log.info(f"Archive written to {archive_path}")

    total_items = sum(len(v) for v in sections.values())
    log.info(f"\n✅ Digest complete: {total_items} items across {len(sections)} sections — $0.00 API cost")


if __name__ == "__main__":
    main()
