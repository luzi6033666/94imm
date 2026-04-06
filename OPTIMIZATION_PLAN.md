# mm187 Optimization Plan

## Goals

- Keep the `随便看看` feature intact.
- Prevent local disk usage from growing without bound.
- Improve page speed without breaking existing URLs.
- Keep the crawler stack stable and observable.

## Current Constraints

- All historical images must remain online because random browsing can hit any old page.
- `/mnt/onedrive` is an `rclone mount` of OneDrive and is not suitable as the primary online image store.
- The image corpus is already large enough that direct full-size image use in list pages is wasteful.

## Recommended Path

### Phase 1: Low-risk speed improvements

1. Generate thumbnail files for page cards.
2. Use thumbnails only on:
   - home page
   - category pages
   - sort pages
   - related cards
   - random cards
3. Keep original images for article detail pages.
4. Preload or directly render the first 2 to 3 detail images, lazy-load the rest.

### Phase 2: Storage discipline

1. Keep all images online.
2. Use OneDrive only as backup or archive copy.
3. Do not serve public traffic directly from `/mnt/onedrive`.
4. Add scheduled backup:
   - local images to OneDrive
   - database dump to OneDrive

### Phase 3: Proper image hosting

1. Move the full image corpus to a real online storage target:
   - Cloudflare R2
   - Tencent COS
   - Aliyun OSS
   - Backblaze B2
   - or a separate static-file server with a large disk
2. Put a CDN in front of image delivery.
3. Keep the Django app responsible only for HTML and application logic.

### Phase 4: Format optimization

1. Preserve originals.
2. Generate `webp` thumbnails for list views.
3. Optionally generate medium-size detail derivatives later.

## What Not To Do

- Do not use OneDrive `rclone mount` as the main live image source.
- Do not remove old images from online storage while `随便看看` still relies on all historical pages.
- Do not switch detail pages to only compressed derivatives before validating visual quality.

## Implementation Order

1. Thumbnail generation and template switch.
2. Backup jobs to OneDrive.
3. CDN plan.
4. Remote image storage migration.

## Notes

- The crawler layer already supports multiple sources and deduplication.
- Media integrity cleanup should remain as a maintenance task because historical bad image files exist.
