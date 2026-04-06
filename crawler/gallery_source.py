import datetime
import os
import shutil
from urllib.parse import urlparse

from django.db import transaction

from common import download_file
from dedupe import find_duplicate_page_id, register_page
from images.models import Image, Page, Tag

BLOCKED_CONTENT_KEYWORDS = (
    "伪娘",
    "男娘",
    "女装大佬",
    "男扮女装",
    "扶她",
    "futanari",
    "cd变装",
)


def parse_date(value):
    try:
        return datetime.datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return datetime.date.today()


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


def find_blocked_keyword(title, tag_names):
    haystack = " ".join([title or ""] + list(tag_names or [])).lower()
    for keyword in BLOCKED_CONTENT_KEYWORDS:
        if keyword.lower() in haystack:
            return keyword
    return ""


def download_and_store_gallery(session, detail_url, parsed, request_headers):
    blocked_keyword = find_blocked_keyword(parsed["title"], parsed.get("tags", []))
    if blocked_keyword:
        print("关键词过滤跳过：{} keyword={}".format(parsed["title"], blocked_keyword))
        return False

    duplicate_page_id = find_duplicate_page_id(parsed["title"])
    if duplicate_page_id:
        print("重复资源，跳过：{} duplicate_page_id={}".format(parsed["title"], duplicate_page_id))
        return False

    tag_ids = get_or_create_tag_ids(parsed["tags"])
    source_id = urlparse(detail_url).path.strip("/").replace("/", "_")
    date_dir = datetime.date.today().strftime("%Y%m%d")
    target_dir = os.path.join("..", "static", "images", date_dir, source_id)
    os.makedirs(target_dir, exist_ok=True)

    downloaded_images = []
    cover_path = ""
    for index, image_url in enumerate(parsed["image_urls"], start=1):
        image_ext = os.path.splitext(urlparse(image_url).path)[1].lower() or ".jpg"
        if image_ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            image_ext = ".jpg"
        file_name = "{:03d}{}".format(index, image_ext)
        absolute_path = os.path.join(target_dir, file_name)
        relative_path = "/static/images/{}/{}/{}".format(date_dir, source_id, file_name)
        if download_file(session, image_url, absolute_path, headers=request_headers, referer=detail_url):
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


def run_source_paths(source_paths, collect_post_urls, process_post, post_limit):
    total_created = 0

    for source_path in source_paths:
        post_urls = collect_post_urls(source_path)
        if not post_urls:
            print("未获取到可用列表，跳过 {}".format(source_path))
            continue

        created_for_source = 0
        for post_url in post_urls:
            if process_post(post_url, source_path):
                total_created += 1
                created_for_source += 1
                if created_for_source >= post_limit:
                    break

    print("created_pages={}".format(total_created))
