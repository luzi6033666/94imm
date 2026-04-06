#!/opt/mm187/.venv/bin/python
import argparse
import datetime
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from images.models import Image, Page, Video


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_IMAGES_DIR = os.path.join(BASE_DIR, "static", "images")
STATIC_VIDEOS_DIR = os.path.join(BASE_DIR, "static", "videos")
PAGE_BATCH_SIZE = 500
VIDEO_BATCH_SIZE = 500
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO_EXTENSIONS = (".mp4", ".m3u8", ".mov", ".webm")
GENERIC_PAGE_TITLE_REGEX = r"^图集 [0-9]+$"


def _iter_image_pages():
    if not os.path.isdir(STATIC_IMAGES_DIR):
        return

    for date_name in sorted(os.listdir(STATIC_IMAGES_DIR)):
        date_dir = os.path.join(STATIC_IMAGES_DIR, date_name)
        if not os.path.isdir(date_dir):
            continue
        try:
            send_date = datetime.datetime.strptime(date_name, "%Y%m%d").date()
        except ValueError:
            continue

        for page_name in sorted(os.listdir(date_dir)):
            page_dir = os.path.join(date_dir, page_name)
            if not os.path.isdir(page_dir) or not page_name.isdigit():
                continue

            image_names = [
                file_name for file_name in sorted(os.listdir(page_dir))
                if file_name.lower().endswith(IMAGE_EXTENSIONS)
            ]
            if not image_names:
                continue

            page_id = int(page_name)
            firstimg = "/static/images/{}/{}/{}".format(date_name, page_name, image_names[0])
            yield Page(
                id=page_id,
                typeid=1,
                sendtime=send_date,
                title="图集 {}".format(page_id),
                firstimg=firstimg,
                tagid="[]",
                hot=0,
            )


def _page_image_urls(date_name, page_name, page_dir):
    image_urls = []
    for file_name in sorted(os.listdir(page_dir)):
        if file_name.lower().endswith(IMAGE_EXTENSIONS):
            image_urls.append("/static/images/{}/{}/{}".format(date_name, page_name, file_name))
    return image_urls


def rebuild_pages():
    existing_ids = set(Page.objects.values_list("id", flat=True))
    seen_ids = set(existing_ids)
    batch = []
    created = 0

    for page in _iter_image_pages() or []:
        if page.id in seen_ids:
            continue
        seen_ids.add(page.id)
        batch.append(page)
        if len(batch) >= PAGE_BATCH_SIZE:
            Page.objects.bulk_create(batch, batch_size=PAGE_BATCH_SIZE, ignore_conflicts=True)
            created += len(batch)
            batch = []

    if batch:
        Page.objects.bulk_create(batch, batch_size=PAGE_BATCH_SIZE, ignore_conflicts=True)
        created += len(batch)

    return created


def repair_page_images():
    repaired_pages = 0
    repaired_images = 0

    if not os.path.isdir(STATIC_IMAGES_DIR):
        return repaired_pages, repaired_images

    page_dirs = {}
    for date_name in sorted(os.listdir(STATIC_IMAGES_DIR)):
        date_dir = os.path.join(STATIC_IMAGES_DIR, date_name)
        if not os.path.isdir(date_dir):
            continue
        for page_name in sorted(os.listdir(date_dir)):
            page_dir = os.path.join(date_dir, page_name)
            if os.path.isdir(page_dir) and page_name.isdigit():
                page_dirs[int(page_name)] = (date_name, page_name, page_dir)

    for page_id, (date_name, page_name, page_dir) in page_dirs.items():
        image_urls = _page_image_urls(date_name, page_name, page_dir)
        if not image_urls:
            continue

        page = Page.objects.filter(id=page_id).first()
        if not page:
            continue

        page_updated = False
        if page.firstimg != image_urls[0]:
            page.firstimg = image_urls[0]
            page.save(update_fields=["firstimg"])
            page_updated = True

        existing_urls = set(Image.objects.filter(pageid=page_id).values_list("imageurl", flat=True))
        missing_urls = [image_url for image_url in image_urls if image_url not in existing_urls]
        if missing_urls:
            Image.objects.bulk_create(
                [Image(pageid=page_id, imageurl=image_url) for image_url in missing_urls],
                batch_size=PAGE_BATCH_SIZE,
            )
            repaired_images += len(missing_urls)
            page_updated = True

        if page_updated:
            repaired_pages += 1

    return repaired_pages, repaired_images


def rebuild_videos():
    existing_paths = set(Video.objects.values_list("v_path", flat=True))
    existing_urls = set(Video.objects.values_list("url", flat=True))
    batch = []
    created = 0

    if not os.path.isdir(STATIC_VIDEOS_DIR):
        return created

    for file_name in sorted(os.listdir(STATIC_VIDEOS_DIR)):
        if not file_name.lower().endswith(VIDEO_EXTENSIONS):
            continue
        v_path = file_name[:50]
        video_url = "/static/videos/{}".format(file_name)
        if v_path in existing_paths or video_url in existing_urls:
            continue

        batch.append(
            Video(
                url=video_url,
                user_id="local",
                date_time="",
                v_name=file_name,
                v_path=v_path,
                source="local",
            )
        )
        existing_paths.add(v_path)
        existing_urls.add(video_url)

        if len(batch) >= VIDEO_BATCH_SIZE:
            Video.objects.bulk_create(batch, batch_size=VIDEO_BATCH_SIZE)
            created += len(batch)
            batch = []

    if batch:
        Video.objects.bulk_create(batch, batch_size=VIDEO_BATCH_SIZE)
        created += len(batch)

    return created


def purge_generic_pages():
    page_ids = list(Page.objects.filter(title__regex=GENERIC_PAGE_TITLE_REGEX).values_list("id", flat=True))
    if not page_ids:
        return 0, 0

    image_count = Image.objects.filter(pageid__in=page_ids).count()
    Image.objects.filter(pageid__in=page_ids).delete()
    page_count = Page.objects.filter(id__in=page_ids).count()
    Page.objects.filter(id__in=page_ids).delete()
    return page_count, image_count


def purge_shadow_local_videos():
    keep_urls = set(Video.objects.exclude(source="local").values_list("url", flat=True))
    qs = Video.objects.filter(source="local", url__in=keep_urls)
    removed = qs.count()
    qs.delete()
    return removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-pages", action="store_true")
    parser.add_argument("--rebuild-videos", action="store_true")
    parser.add_argument("--purge-generic-pages", action="store_true")
    parser.add_argument("--purge-shadow-local-videos", action="store_true")
    args = parser.parse_args()

    purged_pages = 0
    purged_images = 0
    purged_videos = 0
    if args.purge_generic_pages:
        purged_pages, purged_images = purge_generic_pages()
    if args.purge_shadow_local_videos:
        purged_videos = purge_shadow_local_videos()

    page_count = rebuild_pages() if args.rebuild_pages else 0
    repaired_pages, repaired_images = repair_page_images()
    video_count = rebuild_videos() if args.rebuild_videos else 0
    print("pages_purged={}".format(purged_pages))
    print("images_purged={}".format(purged_images))
    print("videos_purged={}".format(purged_videos))
    print("pages_created={}".format(page_count))
    print("pages_repaired={}".format(repaired_pages))
    print("images_repaired={}".format(repaired_images))
    print("videos_created={}".format(video_count))
    print("pages_total={}".format(Page.objects.count()))
    print("images_total={}".format(Image.objects.count()))
    print("videos_total={}".format(Video.objects.count()))


if __name__ == "__main__":
    main()
