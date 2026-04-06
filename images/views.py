import random
from collections import Counter
import glob
import os
import re

from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from django.conf import settings
from django.core.cache import cache
from django.core.paginator import EmptyPage, Paginator
from django.db.models import F
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from config import description, email, friendly_link, key_word, site_name, site_url
from images.models import Image, Page, Tag, Type, Video

HOME_RANDOM_POOL_SIZE = 500
HOME_RANDOM_LIMIT = 50
SIMILAR_PAGE_POOL_SIZE = 80
SIMILAR_PAGE_LIMIT = 20
SEARCH_QUERY_MAX_LENGTH = 50
TYPE_CACHE_KEY = "images:type_list:v2"
TYPE_CACHE_TIMEOUT = 300
HOT_TAG_CACHE_KEY = "images:hot_tag:v2"
HOT_TAG_CACHE_TIMEOUT = 300
PAGE_SIZE = 10
PAGE_MEDIA_CACHE_KEY_TEMPLATE = "images:page_media:v3:{}"
PAGE_MEDIA_CACHE_TIMEOUT = 300
CARD_IMAGE_CACHE_KEY_TEMPLATE = "images:card_image:v3:{}"
CARD_IMAGE_CACHE_TIMEOUT = 300
MEDIA_VALID_CACHE_KEY_TEMPLATE = "images:media_valid:v1:{}"
MEDIA_VALID_CACHE_TIMEOUT = 3600
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
CARD_IMAGE_PLACEHOLDER = "/static/imeizi.png"
GENERIC_PAGE_TITLE_REGEX = r"^图集 [0-9]+$"


def _site_context(**kwargs):
    context = {
        "siteName": site_name,
        "keyWord": key_word,
        "description": description,
        "siteUrl": site_url,
        "email": email,
        "friendly_link": friendly_link,
    }
    context.update(kwargs)
    return context


def _page_value_fields():
    return ("id", "title", "firstimg", "sendtime", "hot", "typeid", "tagid")


def _parse_tag_ids(raw_tag_ids):
    tag_ids = []
    if not raw_tag_ids:
        return tag_ids

    for item in raw_tag_ids.replace("[", "").replace("]", "").split(","):
        item = item.strip()
        if item.isdigit():
            tag_ids.append(int(item))
    return tag_ids


def _page_card(page_row, type_dict):
    type_id = page_row["typeid"]
    resolved_image = _resolve_card_image(page_row["id"], page_row["firstimg"])
    if resolved_image == CARD_IMAGE_PLACEHOLDER:
        return None
    return {
        "pid": page_row["id"],
        "firstimg": resolved_image,
        "title": page_row["title"],
        "sendtime": page_row["sendtime"],
        "hot": page_row["hot"],
        "type": type_dict.get(type_id, ""),
        "type_id": type_id,
    }


def _page_cards(page_rows, type_dict):
    cards = []
    for page_row in page_rows:
        card = _page_card(page_row, type_dict)
        if card is not None:
            cards.append(card)
    return cards


def _random_sample(rows, limit):
    rows = list(rows)
    if len(rows) <= limit:
        return rows
    return random.sample(rows, limit)


def _normalize_video_url(raw_url):
    if not raw_url:
        return ""

    url = raw_url.strip()
    if url.startswith("/"):
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url.lstrip("/")


def _visible_pages_queryset():
    return Page.objects.exclude(title__regex=GENERIC_PAGE_TITLE_REGEX)


def _local_media_path(media_url):
    if not media_url or not media_url.startswith("/static/"):
        return ""
    return os.path.join(settings.BASE_DIR, media_url.lstrip("/"))


def _is_valid_local_image(media_path):
    cache_key = MEDIA_VALID_CACHE_KEY_TEMPLATE.format(media_path)
    cached_value = cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    is_valid = False
    if media_path and os.path.exists(media_path):
        try:
            with open(media_path, "rb") as image_file:
                header = image_file.read(256).lstrip().lower()
            if not (header.startswith(b"<!doctype html") or header.startswith(b"<html")):
                with PILImage.open(media_path) as image:
                    image.verify()
                is_valid = True
        except (OSError, UnidentifiedImageError, SyntaxError, ValueError):
            is_valid = False

    cache.set(cache_key, is_valid, MEDIA_VALID_CACHE_TIMEOUT)
    return is_valid


def _media_exists(media_url):
    if not media_url:
        return False
    if media_url.startswith(("http://", "https://", "//")):
        return True
    media_path = _local_media_path(media_url)
    return bool(media_path and _is_valid_local_image(media_path))


def _page_images_from_filesystem(firstimg):
    if not firstimg or not firstimg.startswith("/static/images/"):
        return []

    relative_dir = os.path.dirname(firstimg.lstrip("/"))
    absolute_dir = os.path.join(settings.BASE_DIR, relative_dir)
    if not os.path.isdir(absolute_dir):
        return []

    file_stem = os.path.splitext(os.path.basename(firstimg))[0]
    image_path_parts = firstimg.lstrip("/").split("/")[2:]
    prefix = ""
    if (
        len(image_path_parts) == 3
        and len(image_path_parts[0]) == 4
        and len(image_path_parts[1]) == 2
        and image_path_parts[0].isdigit()
        and image_path_parts[1].isdigit()
    ):
        prefix = re.sub(r"\d+$", "", file_stem)

    image_urls = []
    for file_name in sorted(os.listdir(absolute_dir)):
        if not file_name.lower().endswith(IMAGE_EXTENSIONS):
            continue
        if prefix:
            candidate_stem = os.path.splitext(file_name)[0]
            if not candidate_stem.startswith(prefix):
                continue
        image_urls.append("/" + os.path.join(relative_dir, file_name).replace(os.sep, "/"))
    return image_urls


def _page_images_from_page_id(page_id):
    image_urls = []
    pattern = os.path.join(settings.BASE_DIR, "static", "images", "*", str(page_id))
    for absolute_dir in sorted(glob.glob(pattern)):
        if not os.path.isdir(absolute_dir):
            continue
        relative_dir = os.path.relpath(absolute_dir, settings.BASE_DIR)
        for file_name in sorted(os.listdir(absolute_dir)):
            if file_name.lower().endswith(IMAGE_EXTENSIONS):
                image_urls.append("/" + os.path.join(relative_dir, file_name).replace(os.sep, "/"))
        if image_urls:
            break
    return image_urls


def _page_images(page_id, firstimg):
    cache_key = PAGE_MEDIA_CACHE_KEY_TEMPLATE.format(page_id)
    cached_value = cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    image_urls = [
        image_url
        for image_url in Image.objects.filter(pageid=page_id).order_by("id").values_list("imageurl", flat=True)
        if _media_exists(image_url)
    ]
    if not image_urls:
        image_urls = [image_url for image_url in _page_images_from_filesystem(firstimg) if _media_exists(image_url)]
    if not image_urls:
        image_urls = [image_url for image_url in _page_images_from_page_id(page_id) if _media_exists(image_url)]

    cache.set(cache_key, image_urls, PAGE_MEDIA_CACHE_TIMEOUT)
    return image_urls


def _resolve_card_image(page_id, firstimg):
    cache_key = CARD_IMAGE_CACHE_KEY_TEMPLATE.format(page_id)
    cached_value = cache.get(cache_key)
    if cached_value is not None:
        return cached_value

    resolved_image = firstimg if _media_exists(firstimg) else ""
    if not resolved_image:
        image_urls = _page_images(page_id, firstimg)
        if image_urls:
            resolved_image = image_urls[0]
    if not resolved_image:
        resolved_image = CARD_IMAGE_PLACEHOLDER

    cache.set(cache_key, resolved_image, CARD_IMAGE_CACHE_TIMEOUT)
    return resolved_image


def _pagination_pages(page_obj, edge_count=1, around_count=2):
    total_pages = page_obj.paginator.num_pages
    current_page = page_obj.number
    visible_pages = set()

    for page_number in range(1, min(edge_count, total_pages) + 1):
        visible_pages.add(page_number)
    for page_number in range(max(1, total_pages - edge_count + 1), total_pages + 1):
        visible_pages.add(page_number)
    for page_number in range(
        max(1, current_page - around_count),
        min(total_pages, current_page + around_count) + 1,
    ):
        visible_pages.add(page_number)

    ordered_pages = []
    previous_page = None
    for page_number in sorted(visible_pages):
        if previous_page is not None and page_number - previous_page > 1:
            ordered_pages.append(None)
        ordered_pages.append(page_number)
        previous_page = page_number
    return ordered_pages


def _paginate_items(request, items, per_page=PAGE_SIZE):
    paginator = Paginator(items, per_page)
    requested_page = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(requested_page)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    except Exception:
        page_obj = paginator.page(1)

    query_params = request.GET.copy()
    query_params.pop("page", None)
    return {
        "data": list(page_obj.object_list),
        "page_obj": page_obj,
        "is_paginated": paginator.num_pages > 1,
        "pagination_pages": _pagination_pages(page_obj),
        "pagination_query": query_params.urlencode(),
    }


def _get_random_video():
    count = Video.objects.count()
    if count == 0:
        return None

    offset = random.randint(0, count - 1)
    return Video.objects.order_by("id").values(
        "url",
        "user_id",
        "date_time",
        "v_name",
        "source",
    )[offset]


def _get_hot_tags():
    cached_value = cache.get(HOT_TAG_CACHE_KEY)
    if cached_value is not None:
        return cached_value

    tag_dict = dict(Tag.objects.values_list("id", "tag"))
    counter = Counter()
    for raw_tag_ids in Page.objects.values_list("tagid", flat=True).iterator():
        counter.update(_parse_tag_ids(raw_tag_ids))

    return_list = []
    for tag_id, view_count in counter.most_common():
        tag_name = tag_dict.get(tag_id)
        if tag_name and view_count > 20:
            return_list.append({"tid": str(tag_id), "tag": tag_name, "viwe": view_count})

    cache.set(HOT_TAG_CACHE_KEY, return_list, HOT_TAG_CACHE_TIMEOUT)
    return return_list


@require_GET
def index(request):
    type_dict, typelist = type_list()
    candidate_pages = list(
        _visible_pages_queryset().order_by("-id").values(*_page_value_fields())[:HOME_RANDOM_POOL_SIZE]
    )
    imgs = _page_cards(_random_sample(candidate_pages, HOME_RANDOM_LIMIT), type_dict)
    return render(
        request,
        "index.html",
        _site_context(typelist=typelist, **_paginate_items(request, imgs)),
    )


@require_GET
def page(request, i_id):
    page_row = Page.objects.filter(id=i_id).values(*_page_value_fields()).first()
    if not page_row:
        raise Http404("page not found")

    type_dict, typelist = type_list()
    Page.objects.filter(id=i_id).update(hot=F("hot") + 1)

    type_id = page_row["typeid"]
    tag_ids = _parse_tag_ids(page_row["tagid"])
    tag_dict = dict(Tag.objects.filter(id__in=tag_ids).values_list("id", "tag"))
    tags = [{"tname": tag_dict[tag_id], "tid": str(tag_id)} for tag_id in tag_ids if tag_id in tag_dict]
    if len(tags) > 4:
        tags = random.sample(tags, 4)

    imgs = _page_images(i_id, page_row["firstimg"])
    type_name = type_dict.get(type_id, "")

    return render(
        request,
        "page.html",
        _site_context(
            data=imgs,
            has_images=bool(imgs),
            tag=tags,
            title=page_row["title"],
            type=type_name,
            typeid=str(type_id),
            time=page_row["sendtime"],
            similar=page_similar(type_id, page_row["id"], type_name),
            typelist=typelist,
            pageid=i_id,
            typeName=type_name,
        ),
    )


@require_GET
def tag(request, tid):
    tid_int = int(tid)
    type_dict, typelist = type_list()
    candidate_pages = list(
        _visible_pages_queryset()
        .filter(tagid__contains=str(tid_int))
        .order_by("-id")
        .values(*_page_value_fields())
    )
    matched_pages = [
        page_row for page_row in candidate_pages if tid_int in _parse_tag_ids(page_row["tagid"])
    ]
    imgs = _page_cards(matched_pages, type_dict)
    return render(
        request,
        "index.html",
        _site_context(typelist=typelist, **_paginate_items(request, imgs)),
    )


@require_GET
def type(request, typeid):
    type_dict, typelist = type_list()
    page_list = list(
        _visible_pages_queryset().filter(typeid=typeid).order_by("-id").values(*_page_value_fields())
    )
    imgs = _page_cards(page_list, type_dict)
    return render(
        request,
        "category.html",
        _site_context(typeid=str(typeid), typelist=typelist, **_paginate_items(request, imgs)),
    )


def page_similar(type_id, exclude_page_id, type_name):
    similar_pages = list(
        _visible_pages_queryset()
        .filter(typeid=type_id)
        .exclude(id=exclude_page_id)
        .order_by("-hot", "-id")
        .values(*_page_value_fields())[:SIMILAR_PAGE_POOL_SIZE]
    )
    similar_pages = _random_sample(similar_pages, SIMILAR_PAGE_LIMIT)

    similar_list = []
    for page_row in similar_pages:
        resolved_image = _resolve_card_image(page_row["id"], page_row["firstimg"])
        if resolved_image == CARD_IMAGE_PLACEHOLDER:
            continue
        similar_list.append(
            {
                "stitle": page_row["title"],
                "tid": page_row["typeid"],
                "pid": page_row["id"],
                "firstimg": resolved_image,
                "sendtime": page_row["sendtime"],
                "hot": page_row["hot"],
                "type": type_name,
                "type_id": page_row["typeid"],
            }
        )
    return similar_list


@require_GET
def search(request):
    type_dict, typelist = type_list()
    context = request.GET.get("s", "").strip()[:SEARCH_QUERY_MAX_LENGTH]
    imgs = []
    if context:
        page_list = list(
            _visible_pages_queryset()
            .filter(title__icontains=context)
            .order_by("-id")
            .values(*_page_value_fields())
        )
        imgs = _page_cards(page_list, type_dict)

    return render(
        request,
        "index.html",
        _site_context(typelist=typelist, **_paginate_items(request, imgs)),
    )


@require_GET
def HotTag(request):
    _, typelist = type_list()
    return_list = _get_hot_tags()
    return render(
        request,
        "tag.html",
        _site_context(data=return_list, typelist=typelist, keyword=return_list[0:10]),
    )


@require_GET
def SortBy(request, method):
    if method not in ("new", "hot"):
        raise Http404("sort method not found")

    if method == "new":
        page_list = list(_visible_pages_queryset().order_by("-id").values(*_page_value_fields())[:100])
    else:
        page_list = list(_visible_pages_queryset().order_by("-hot", "-id").values(*_page_value_fields())[:100])

    type_dict, typelist = type_list()
    imgs = _page_cards(page_list, type_dict)
    return render(
        request,
        "sort.html",
        _site_context(method=method, typelist=typelist, **_paginate_items(request, imgs)),
    )


@require_GET
def getVideo(request):
    video_info = _get_random_video()
    if video_info is None:
        return JsonResponse({"detail": "video not found"}, status=404)

    return JsonResponse(
        {
            "url": _normalize_video_url(video_info["url"]),
            "user_id": video_info["user_id"],
            "source": video_info["source"],
        }
    )


@require_GET
def mVideo(request):
    video_info = _get_random_video()
    if video_info is None:
        raise Http404("video not found")

    return render(
        request,
        "mVideo.html",
        _site_context(
            url=_normalize_video_url(video_info["url"]),
            user_id=video_info["user_id"],
            date_time=video_info["date_time"],
            v_name=video_info["v_name"],
            source=video_info["source"],
        ),
    )


@require_GET
def pVideo(request):
    _, typelist = type_list()
    video_info = _get_random_video()
    if video_info is None:
        raise Http404("video not found")

    return render(
        request,
        "video.html",
        _site_context(
            url=_normalize_video_url(video_info["url"]),
            user_id=video_info["user_id"],
            date_time=video_info["date_time"],
            v_name=video_info["v_name"],
            source=video_info["source"],
            typelist=typelist,
        ),
    )


def type_list():
    cached_value = cache.get(TYPE_CACHE_KEY)
    if cached_value is not None:
        return cached_value

    type_rows = list(Type.objects.order_by("id").values_list("id", "type"))
    type_dict = {type_id: type_name for type_id, type_name in type_rows}
    typelist = [{"type": type_name, "type_id": str(type_id)} for type_id, type_name in type_rows]
    cache_value = (type_dict, typelist)
    cache.set(TYPE_CACHE_KEY, cache_value, TYPE_CACHE_TIMEOUT)
    return cache_value
