#!/usr/bin/env python3
import json
import os
import shutil

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from django.conf import settings
from django.core.cache import cache

from images.models import Image, Page, Tag, Video

BLOCKED_CONTENT_KEYWORDS = (
    "伪娘",
    "男娘",
    "女装大佬",
    "男扮女装",
    "扶她",
    "futanari",
    "cd变装",
)
INDEX_PATH = os.path.join(settings.BASE_DIR, "cache", "crawler_dedupe_index.json")


def _tag_names(raw_tag_ids, tag_map):
    names = []
    for part in (raw_tag_ids or "").replace("[", "").replace("]", "").split(","):
        part = part.strip()
        if part.isdigit():
            tag_name = tag_map.get(int(part))
            if tag_name:
                names.append(tag_name)
    return names


def _find_blocked_keyword(title, tag_names):
    haystack = " ".join([title or ""] + list(tag_names or [])).lower()
    for keyword in BLOCKED_CONTENT_KEYWORDS:
        if keyword.lower() in haystack:
            return keyword
    return ""


def _local_media_path(media_url):
    if not media_url or not media_url.startswith("/static/"):
        return ""
    return os.path.join(settings.BASE_DIR, media_url.lstrip("/"))


def _remove_media_files(image_urls):
    removed_files = 0
    checked_dirs = set()
    for image_url in image_urls:
        media_path = _local_media_path(image_url)
        if not media_path:
            continue
        checked_dirs.add(os.path.dirname(media_path))
        if os.path.exists(media_path):
            try:
                os.remove(media_path)
                removed_files += 1
            except OSError:
                continue

    for directory in sorted(checked_dirs, key=len, reverse=True):
        try:
            if os.path.isdir(directory) and not os.listdir(directory):
                os.rmdir(directory)
        except OSError:
            continue

    return removed_files


def _blocked_pages():
    tag_map = dict(Tag.objects.values_list("id", "tag"))
    blocked = []
    for page in Page.objects.all().only("id", "title", "tagid", "firstimg"):
        keyword = _find_blocked_keyword(page.title, _tag_names(page.tagid, tag_map))
        if keyword:
            blocked.append((page, keyword))
    return blocked


def _blocked_videos():
    blocked = []
    for video in Video.objects.all().only("id", "v_name"):
        keyword = _find_blocked_keyword(video.v_name, [])
        if keyword:
            blocked.append((video, keyword))
    return blocked


def purge_blocked_content():
    page_matches = _blocked_pages()
    video_matches = _blocked_videos()

    summary = {
        "pages_deleted": 0,
        "page_ids": [],
        "videos_deleted": 0,
        "video_ids": [],
        "files_removed": 0,
    }

    for page, keyword in page_matches:
        image_urls = list(Image.objects.filter(pageid=page.id).values_list("imageurl", flat=True))
        if page.firstimg:
            image_urls.append(page.firstimg)
        summary["files_removed"] += _remove_media_files(sorted(set(image_urls)))
        Image.objects.filter(pageid=page.id).delete()
        summary["page_ids"].append({"id": page.id, "title": page.title, "keyword": keyword})
        page.delete()
        summary["pages_deleted"] += 1

    for video, keyword in video_matches:
        summary["video_ids"].append({"id": video.id, "name": video.v_name, "keyword": keyword})
        video.delete()
        summary["videos_deleted"] += 1

    cache.clear()
    if os.path.exists(INDEX_PATH):
        try:
            os.remove(INDEX_PATH)
        except OSError:
            pass

    return summary


def main():
    summary = purge_blocked_content()
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
