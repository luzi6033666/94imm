#!/opt/mm187/.venv/bin/python
import datetime
import os
import re
import sys
from urllib.parse import urlparse

from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from django.db import transaction

from common import build_session, download_file, fetch
from images.models import Image, Page, Tag


BASE_URL = "https://www.06se.com"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}
IMAGE_REQUEST_HEADERS = {
    key: value for key, value in REQUEST_HEADERS.items() if key.lower() != "referer"
}
PAGE_LIMIT = max(int(os.environ.get("CRAWLER_06SE_PAGES", "1")), 1)
POST_LIMIT = max(int(os.environ.get("CRAWLER_06SE_POST_LIMIT", "2")), 1)
SCAN_LIMIT = max(int(os.environ.get("CRAWLER_06SE_SCAN_LIMIT", str(POST_LIMIT * 3))), POST_LIMIT)
SOURCE_PATHS = [item.strip() for item in os.environ.get("CRAWLER_06SE_PATHS", "/,/cos").split(",") if item.strip()]


def normalize_title(title):
    return re.sub(r"\s+", " ", (title or "").strip())


def infer_type_id(title, keywords, source_path):
    text = " ".join([title, source_path] + keywords).lower()
    if source_path == "/cos" or "cosplay" in text or "cos" in text:
        return 6
    if any(keyword in text for keyword in ("丝袜", "黑丝", "白丝", "肉丝", "吊袜", "连裤袜")):
        return 3
    if any(keyword in text for keyword in ("美腿", "长腿", "玉腿")):
        return 4
    if any(keyword in text for keyword in ("美胸", "巨乳", "爆乳", "豪乳", "大胸", "酥胸")):
        return 5
    if any(keyword in text for keyword in ("清纯", "萝莉", "少女", "学妹")):
        return 2
    return 1


def get_or_create_tag_ids(keywords):
    tag_ids = []
    seen = set()
    for keyword in keywords:
        tag_name = keyword.strip()
        if not tag_name or tag_name in seen:
            continue
        seen.add(tag_name)
        tag, _ = Tag.objects.get_or_create(tag=tag_name[:200])
        tag_ids.append(tag.id)
    return tag_ids


def build_list_url(source_path, page_number):
    if source_path == "/":
        return BASE_URL if page_number == 1 else "{}/page/{}".format(BASE_URL, page_number)
    base = BASE_URL + source_path
    return base if page_number == 1 else "{}/page/{}".format(base, page_number)


def extract_post_id(post_url):
    match = re.search(r"/(\d+)\.html$", post_url)
    return int(match.group(1)) if match else 0


def collect_post_urls(session, source_path):
    seen = set()
    post_urls = []

    for page_number in range(1, PAGE_LIMIT + 1):
        list_url = build_list_url(source_path, page_number)
        response = fetch(session, list_url, headers=REQUEST_HEADERS)
        if response is None:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        for anchor in soup.select("h2.item-heading a[href], .item-thumbnail a[href]"):
            url = anchor.get("href", "").strip()
            if not url.startswith(BASE_URL) or not url.endswith(".html"):
                continue
            if url in seen:
                continue
            seen.add(url)
            post_urls.append(url)

    post_urls.sort(key=extract_post_id, reverse=True)
    return post_urls[:SCAN_LIMIT]


def parse_detail(session, detail_url, source_path):
    response = fetch(session, detail_url, headers=REQUEST_HEADERS, referer=BASE_URL)
    if response is None:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    title_node = soup.select_one("h1.article-title a, h1.article-title")
    if not title_node:
        print("详情页结构异常：" + detail_url)
        return None

    title = normalize_title(title_node.get_text(" ", strip=True))
    keywords_meta = soup.find("meta", attrs={"name": "keywords"})
    keywords = [item.strip() for item in (keywords_meta.get("content", "") if keywords_meta else "").split(",") if item.strip()]

    date_node = soup.select_one(".item-meta item[title]")
    send_date = datetime.date.today()
    if date_node and date_node.get("title"):
        send_date = datetime.date.fromisoformat(date_node["title"][:10])

    image_urls = []
    seen_images = set()
    for image in soup.select(".article-content img[data-src], .article-content img[src]"):
        image_url = image.get("data-src") or image.get("src") or ""
        image_url = image_url.strip()
        if not image_url.startswith("http"):
            continue
        if image_url in seen_images:
            continue
        seen_images.add(image_url)
        image_urls.append(image_url)

    if not image_urls:
        print("详情页无图片：" + detail_url)
        return None

    return {
        "title": title,
        "keywords": keywords,
        "send_date": send_date,
        "image_urls": image_urls,
        "type_id": infer_type_id(title, keywords, source_path),
    }


def download_and_store(session, detail_url, source_path):
    parsed = parse_detail(session, detail_url, source_path)
    if not parsed:
        return False

    if Page.objects.filter(title=parsed["title"]).exists():
        print("已采集：" + parsed["title"])
        return False

    tag_ids = get_or_create_tag_ids(parsed["keywords"])
    source_id = os.path.basename(urlparse(detail_url).path).split(".")[0]
    date_dir = datetime.date.today().strftime("%Y%m%d")
    target_dir = os.path.join("..", "static", "images", date_dir, source_id)
    os.makedirs(target_dir, exist_ok=True)

    downloaded_images = []
    for index, image_url in enumerate(parsed["image_urls"], start=1):
        image_ext = os.path.splitext(urlparse(image_url).path)[1].lower() or ".jpg"
        if image_ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            image_ext = ".jpg"
        file_name = "{:03d}{}".format(index, image_ext)
        absolute_path = os.path.join(target_dir, file_name)
        relative_path = "/static/images/{}/{}/{}".format(date_dir, source_id, file_name)
        # 06se uses a CDN that intermittently rejects hotlink-style Referer headers.
        # Downloading the same asset without Referer is more reliable from the gray host.
        if download_file(session, image_url, absolute_path, headers=IMAGE_REQUEST_HEADERS):
            downloaded_images.append(relative_path)

    if not downloaded_images:
        print("图片下载失败：" + detail_url)
        return False

    with transaction.atomic():
        page = Page.objects.create(
            typeid=parsed["type_id"],
            sendtime=parsed["send_date"],
            title=parsed["title"][:200],
            firstimg=downloaded_images[0],
            tagid=str(tag_ids),
            hot=0,
        )
        Image.objects.bulk_create(
            [Image(pageid=page.id, imageurl=image_url) for image_url in downloaded_images],
            batch_size=200,
        )

    print("采集完成：{} images={}".format(parsed["title"], len(downloaded_images)))
    return True


def main():
    session = build_session(headers=REQUEST_HEADERS, retries=1)
    total_created = 0

    for source_path in SOURCE_PATHS:
        post_urls = collect_post_urls(session, source_path)
        if not post_urls:
            print("未获取到可用列表，跳过 {}".format(source_path))
            continue

        created_for_source = 0
        for post_url in post_urls:
            if download_and_store(session, post_url, source_path):
                total_created += 1
                created_for_source += 1
                if created_for_source >= POST_LIMIT:
                    break

    print("created_pages={}".format(total_created))


if __name__ == "__main__":
    main()
