#!/opt/mm187/.venv/bin/python
import datetime
import os
import re
import shutil
import sys
from urllib.parse import urlparse

from bs4 import BeautifulSoup

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from django.db import transaction

from common import build_session, download_file, fetch
from dedupe import find_duplicate_page_id, register_page
from gallery_source import find_blocked_keyword
from images.models import Image, Page, Tag


BASE_URL = "https://www.huotumao.com"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL,
}
PAGE_LIMIT = max(int(os.environ.get("CRAWLER_HUOTUMAO_PAGES", "1")), 1)
POST_LIMIT = max(int(os.environ.get("CRAWLER_HUOTUMAO_POST_LIMIT", "1")), 1)
SOURCE_PATHS = [
    item.strip()
    for item in os.environ.get("CRAWLER_HUOTUMAO_PATHS", "/info/coser").split(",")
    if item.strip()
]
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def normalize_title(title):
    return re.sub(r"\s+", " ", (title or "").strip())


def infer_type_id(title, tags, source_path):
    text = " ".join([title, source_path] + tags).lower()
    if "cos" in text or "coser" in text or "cosplay" in text:
        return 6
    if any(keyword in text for keyword in ("丝袜", "黑丝", "白丝", "肉丝", "吊袜", "连体丝袜")):
        return 3
    if any(keyword in text for keyword in ("美腿", "长腿", "玉腿")):
        return 4
    if any(keyword in text for keyword in ("美胸", "巨乳", "爆乳", "豪乳", "大胸", "酥胸")):
        return 5
    if any(keyword in text for keyword in ("清纯", "萝莉", "少女", "学妹")):
        return 2
    return 1


def get_or_create_tag_ids(tag_names):
    tag_ids = []
    seen = set()
    for tag_name in tag_names:
        value = tag_name.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        tag = Tag.objects.filter(tag=value[:200]).order_by("id").first()
        if tag is None:
            tag = Tag.objects.create(tag=value[:200])
        tag_ids.append(tag.id)
    return tag_ids


def build_list_url(source_path, page_number):
    base = BASE_URL + source_path
    return base if page_number == 1 else "{}/page/{}".format(base, page_number)


def extract_post_id(post_url):
    match = re.search(r"/info/(\d+)\.html$", post_url)
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
        for anchor in soup.select("a[href^='https://www.huotumao.com/info/'], a[href^='/info/']"):
            href = anchor.get("href", "").strip()
            if not href:
                continue
            url = href if href.startswith("http") else BASE_URL + href
            if not re.search(r"/info/\d+\.html$", url):
                continue
            if url in seen:
                continue
            seen.add(url)
            post_urls.append(url)

    post_urls.sort(key=extract_post_id, reverse=True)
    return post_urls[:POST_LIMIT]


def parse_detail(session, detail_url, source_path):
    response = fetch(session, detail_url, headers=REQUEST_HEADERS, referer=BASE_URL)
    if response is None:
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    title_node = soup.select_one("h1.post-title")
    article_node = soup.select_one("article.post-content")
    if not title_node or not article_node:
        print("详情页结构异常：" + detail_url)
        return None

    title = normalize_title(title_node.get_text(" ", strip=True))
    date_node = soup.select_one(".meta-date")
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", date_node.get_text(" ", strip=True) if date_node else "")
    send_date = datetime.date.fromisoformat(date_match.group(0)) if date_match else datetime.date.today()

    tags = [anchor.get_text(" ", strip=True) for anchor in soup.select(".meta-cat-dot a, .article-tags a")]
    image_urls = []
    seen_images = set()
    for image in article_node.select("img[src]"):
        image_url = image.get("src", "").strip()
        if not image_url.startswith("http"):
            continue
        lower_url = image_url.lower()
        if not any(lower_url.endswith(ext) for ext in IMAGE_EXTENSIONS):
            continue
        if "/wp-content/uploads/" not in lower_url:
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
        "type_id": infer_type_id(title, tags, source_path),
        "image_urls": image_urls,
    }


def download_and_store(session, detail_url, source_path):
    parsed = parse_detail(session, detail_url, source_path)
    if not parsed:
        return False

    blocked_keyword = find_blocked_keyword(parsed["title"], parsed.get("tags", []))
    if blocked_keyword:
        print("关键词过滤跳过：{} keyword={}".format(parsed["title"], blocked_keyword))
        return False

    duplicate_page_id = find_duplicate_page_id(parsed["title"])
    if duplicate_page_id:
        print("重复资源，跳过：{} duplicate_page_id={}".format(parsed["title"], duplicate_page_id))
        return False

    tag_ids = get_or_create_tag_ids(parsed["tags"])
    source_id = os.path.basename(urlparse(detail_url).path).split(".")[0]
    date_dir = datetime.date.today().strftime("%Y%m%d")
    target_dir = os.path.join("..", "static", "images", date_dir, source_id)
    os.makedirs(target_dir, exist_ok=True)

    downloaded_images = []
    cover_path = ""
    for index, image_url in enumerate(parsed["image_urls"], start=1):
        image_ext = os.path.splitext(urlparse(image_url).path)[1].lower() or ".jpg"
        if image_ext not in IMAGE_EXTENSIONS:
            image_ext = ".jpg"
        file_name = "{:03d}{}".format(index, image_ext)
        absolute_path = os.path.join(target_dir, file_name)
        relative_path = "/static/images/{}/{}/{}".format(date_dir, source_id, file_name)
        if download_file(session, image_url, absolute_path, headers=REQUEST_HEADERS, referer=detail_url):
            if not cover_path:
                cover_path = absolute_path
                duplicate_page_id = find_duplicate_page_id(parsed["title"], cover_path=cover_path)
                if duplicate_page_id:
                    shutil.rmtree(target_dir, ignore_errors=True)
                    print("重复资源，跳过：{} duplicate_page_id={}".format(parsed["title"], duplicate_page_id))
                    return False
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

    register_page(page.id, parsed["title"], cover_path)
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

        for post_url in post_urls:
            if download_and_store(session, post_url, source_path):
                total_created += 1

    print("created_pages={}".format(total_created))


if __name__ == "__main__":
    main()
