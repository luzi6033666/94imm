#!/usr/bin/env python3
import io
import os
import re
import sys
from urllib.parse import urlparse

from bs4 import BeautifulSoup

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from common import build_session, fetch
from gallery_source import download_and_store_gallery, parse_date, run_source_paths


BASE_URL = "https://www.miaohuaying.com"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}
PAGE_LIMIT = max(int(os.environ.get("CRAWLER_MIAOHUAYING_PAGES", "1")), 1)
POST_LIMIT = max(int(os.environ.get("CRAWLER_MIAOHUAYING_POST_LIMIT", "1")), 1)
SCAN_LIMIT = max(int(os.environ.get("CRAWLER_MIAOHUAYING_SCAN_LIMIT", str(POST_LIMIT * 3))), POST_LIMIT)
SOURCE_PATHS = [
    item.strip()
    for item in os.environ.get("CRAWLER_MIAOHUAYING_PATHS", "/cosplay/").split(",")
    if item.strip()
]
IMAGE_HOST_ALLOWLIST = ("img.miaohuaying.com",)


def normalize_title(title):
    return re.sub(r"\s*[–-]\s*喵画影\s*$", "", (title or "").strip())
def build_list_url(source_path, page_number):
    base = BASE_URL + source_path.rstrip("/") + "/"
    return base if page_number == 1 else "{}page/{}/".format(base, page_number)


def collect_post_urls(session, source_path):
    seen = set()
    post_urls = []

    for page_number in range(1, PAGE_LIMIT + 1):
        list_url = build_list_url(source_path, page_number)
        response = fetch(session, list_url, headers=REQUEST_HEADERS)
        if response is None:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.select(".post-list-item .post-info h2 a[href], .post-list-item .thumb-link[href], article h2 a[href]"):
            href = anchor.get("href", "").strip()
            if not href.startswith(BASE_URL):
                continue
            if href in seen:
                continue
            seen.add(href)
            post_urls.append(href)

    return post_urls[:SCAN_LIMIT]


def parse_detail(session, detail_url, source_path):
    response = fetch(session, detail_url, headers=REQUEST_HEADERS, referer=BASE_URL)
    if response is None:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    title = normalize_title(
        (soup.select_one("meta[property='og:title']") or {}).get("content", "")
        if soup.select_one("meta[property='og:title']")
        else (soup.title.get_text(" ", strip=True) if soup.title else "")
    )
    if not title:
        print("详情页结构异常：" + detail_url)
        return None

    date_node = soup.select_one("meta[property='og:updated_time']")
    send_date = parse_date(date_node.get("content", "")) if date_node else datetime.date.today()

    keywords_meta = soup.find("meta", attrs={"name": "keywords"})
    tags = [source_path.strip("/").split("/")[-1] or "cosplay"]
    if keywords_meta and keywords_meta.get("content"):
        tags.extend([item.strip() for item in keywords_meta["content"].split(",") if item.strip()])

    image_urls = []
    seen_images = set()
    for image in soup.select(".entry-content img[data-src], .entry-content img[src], .article-content img[data-src], .article-content img[src]"):
        image_url = image.get("data-src") or image.get("src") or ""
        image_url = image_url.strip()
        if not image_url.startswith("http"):
            continue
        if urlparse(image_url).netloc not in IMAGE_HOST_ALLOWLIST:
            continue
        if image_url in seen_images:
            continue
        seen_images.add(image_url)
        image_urls.append(image_url)

    if len(image_urls) < 3:
        print("详情页图片不足：" + detail_url)
        return None

    return {
        "title": title,
        "send_date": send_date,
        "tags": tags,
        "type_id": 6,
        "image_urls": image_urls,
    }


def download_and_store(session, detail_url, source_path):
    parsed = parse_detail(session, detail_url, source_path)
    if not parsed:
        return False

    return download_and_store_gallery(session, detail_url, parsed, REQUEST_HEADERS)


def main():
    session = build_session(headers=REQUEST_HEADERS, retries=1)
    run_source_paths(
        SOURCE_PATHS,
        lambda source_path: collect_post_urls(session, source_path),
        lambda post_url, source_path: download_and_store(session, post_url, source_path),
        POST_LIMIT,
    )


if __name__ == "__main__":
    main()
