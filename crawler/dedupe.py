#!/opt/mm187/.venv/bin/python
import hashlib
import json
import os
import unicodedata

from django.conf import settings

from images.models import Page


INDEX_PATH = os.path.join(settings.BASE_DIR, "cache", "crawler_dedupe_index.json")


def _ensure_cache_dir():
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)


def _local_media_path(media_url):
    if not media_url or not media_url.startswith("/static/"):
        return ""
    return os.path.join(settings.BASE_DIR, media_url.lstrip("/"))


def normalize_title(title):
    normalized = []
    for char in (title or "").strip().lower():
        category = unicodedata.category(char)
        if category.startswith("P") or category.startswith("Z"):
            continue
        normalized.append(char)
    return "".join(normalized)


def sha1_file(file_path):
    digest = hashlib.sha1()
    with open(file_path, "rb") as input_file:
        while True:
            chunk = input_file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def build_index():
    title_keys = {}
    cover_hashes = {}

    for page_id, title, firstimg in Page.objects.values_list("id", "title", "firstimg"):
        title_key = normalize_title(title)
        if title_key and title_key not in title_keys:
            title_keys[title_key] = page_id

        media_path = _local_media_path(firstimg)
        if media_path and os.path.exists(media_path):
            try:
                cover_hashes.setdefault(sha1_file(media_path), page_id)
            except OSError:
                continue

    payload = {
        "page_count": Page.objects.count(),
        "title_keys": title_keys,
        "cover_hashes": cover_hashes,
    }
    _ensure_cache_dir()
    with open(INDEX_PATH, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, separators=(",", ":"))
    return payload


def load_index():
    if not os.path.exists(INDEX_PATH):
        return build_index()

    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as input_file:
            payload = json.load(input_file)
    except (OSError, json.JSONDecodeError):
        return build_index()

    if payload.get("page_count") != Page.objects.count():
        return build_index()
    return payload


def find_duplicate_page_id(title, cover_path=None):
    payload = load_index()

    title_key = normalize_title(title)
    if title_key:
        page_id = payload.get("title_keys", {}).get(title_key)
        if page_id:
            return page_id

    if cover_path and os.path.exists(cover_path):
        try:
            cover_hash = sha1_file(cover_path)
        except OSError:
            return None
        return payload.get("cover_hashes", {}).get(cover_hash)

    return None


def register_page(page_id, title, cover_path):
    payload = load_index()

    title_key = normalize_title(title)
    if title_key:
        payload.setdefault("title_keys", {})[title_key] = page_id

    if cover_path and os.path.exists(cover_path):
        try:
            cover_hash = sha1_file(cover_path)
        except OSError:
            cover_hash = ""
        if cover_hash:
            payload.setdefault("cover_hashes", {})[cover_hash] = page_id

    payload["page_count"] = Page.objects.count()
    _ensure_cache_dir()
    with open(INDEX_PATH, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, ensure_ascii=False, separators=(",", ":"))
