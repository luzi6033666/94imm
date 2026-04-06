#!/opt/mm187/.venv/bin/python
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "silumz.settings")

import django

django.setup()

from django.core.cache import cache

from images.models import Image, Page


def purge_empty_pages():
    page_ids_with_images = set(Image.objects.values_list("pageid", flat=True))
    queryset = Page.objects.filter(firstimg="")
    page_ids = [page_id for page_id in queryset.values_list("id", flat=True) if page_id not in page_ids_with_images]
    if not page_ids:
        return 0

    deleted_count = Page.objects.filter(id__in=page_ids).count()
    Page.objects.filter(id__in=page_ids).delete()
    cache.clear()
    return deleted_count


def main():
    deleted_count = purge_empty_pages()
    print("pages_purged={}".format(deleted_count))
    print("pages_total={}".format(Page.objects.count()))


if __name__ == "__main__":
    main()
