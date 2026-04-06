#!/opt/mm187/.venv/bin/python
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from django.core.cache import cache

from images.models import Image, Page


SMALL_IMAGE_THRESHOLD = 300
LARGE_IMAGE_THRESHOLD = 800
SCAN_LIMIT = 24


def local_media_path(media_url):
    if not media_url or not media_url.startswith("/static/"):
        return ""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), media_url.lstrip("/"))


def inspect_media(media_url):
    media_path = local_media_path(media_url)
    if not media_path or not os.path.exists(media_path):
        return {"valid": False, "width": 0, "height": 0, "reason": "missing"}

    try:
        with open(media_path, "rb") as image_file:
            header = image_file.read(256).lstrip().lower()
        if header.startswith(b"<!doctype html") or header.startswith(b"<html"):
            return {"valid": False, "width": 0, "height": 0, "reason": "html"}

        with PILImage.open(media_path) as image:
            width, height = image.size
            image.verify()
        return {"valid": True, "width": width, "height": height, "reason": "ok"}
    except (OSError, UnidentifiedImageError, SyntaxError, ValueError):
        return {"valid": False, "width": 0, "height": 0, "reason": "corrupt"}


def repair_pages():
    stats = {
        "pages_checked": 0,
        "pages_updated": 0,
        "image_rows_deleted": 0,
        "pages_emptied": 0,
        "small_junk_removed": 0,
        "invalid_removed": 0,
    }

    for page in Page.objects.order_by("id").iterator():
        rows = list(Image.objects.filter(pageid=page.id).order_by("id").values("id", "imageurl")[:SCAN_LIMIT])
        if not rows and not page.firstimg:
            continue

        stats["pages_checked"] += 1
        inspected_rows = []
        large_valid_count = 0
        for row in rows:
            meta = inspect_media(row["imageurl"])
            if meta["valid"] and meta["width"] >= LARGE_IMAGE_THRESHOLD and meta["height"] >= LARGE_IMAGE_THRESHOLD:
                large_valid_count += 1
            inspected_rows.append((row, meta))

        keep_urls = []
        delete_ids = []
        page_changed = False

        for row, meta in inspected_rows:
            if not meta["valid"]:
                delete_ids.append(row["id"])
                stats["invalid_removed"] += 1
                page_changed = True
                continue

            if (
                large_valid_count >= 3
                and meta["width"] <= SMALL_IMAGE_THRESHOLD
                and meta["height"] <= SMALL_IMAGE_THRESHOLD
            ):
                delete_ids.append(row["id"])
                stats["small_junk_removed"] += 1
                page_changed = True
                continue

            keep_urls.append(row["imageurl"])

        if delete_ids:
            Image.objects.filter(id__in=delete_ids).delete()
            stats["image_rows_deleted"] += len(delete_ids)

        new_firstimg = keep_urls[0] if keep_urls else ""
        first_meta = inspect_media(page.firstimg) if page.firstimg else {"valid": False, "width": 0, "height": 0}
        if page.firstimg != new_firstimg and (keep_urls or not first_meta["valid"]):
            page.firstimg = new_firstimg
            page.save(update_fields=["firstimg"])
            page_changed = True
            if not new_firstimg:
                stats["pages_emptied"] += 1

        if page_changed:
            stats["pages_updated"] += 1

    cache.clear()
    return stats


def main():
    stats = repair_pages()
    for key, value in stats.items():
        print("{}={}".format(key, value))


if __name__ == "__main__":
    main()
