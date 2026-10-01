"""Download and serve-ready cache of playable VALORANT agent icons.

The source is valorant-api.com; only processed image/cache files are written.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .config import PROCESSED_DIR

CACHE = PROCESSED_DIR / "agent_icons.json"
ICON_DIR = PROCESSED_DIR / "agents"
MAX_BYTES = 512 * 1024
MAX_CATALOG_BYTES = 256 * 1024
API_URL = "https://valorant-api.com/v1/agents?isPlayableCharacter=true"
ALLOWED_IMAGE_HOST = "media.valorant-api.com"
IMAGE_TYPE = "image/png"


def slug(value: object) -> str | None:
    """Normalize VLR and Valorant API names to a conservative local slug."""
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-z]", "", value.lower())
    return normalized if re.fullmatch(r"[a-z]{2,16}", normalized) else None


def _icon_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.hostname != ALLOWED_IMAGE_HOST
            or port not in (None, 443) or parsed.username is not None
            or parsed.password is not None):
        return None
    return value


def _catalog(payload: object) -> dict[str, dict[str, str]]:
    rows = payload.get("data") if isinstance(payload, dict) else None
    found: dict[str, dict[str, str]] = {}
    if not isinstance(rows, list):
        return found
    for row in rows:
        if not isinstance(row, dict) or row.get("isPlayableCharacter") is not True:
            continue
        name = row.get("displayName")
        key = slug(name)
        url = _icon_url(row.get("displayIcon"))
        if key and isinstance(name, str) and url:
            found[key] = {"name": name, "url": url}
    return found


def refresh(*, session=None, cache: Path = CACHE, icon_dir: Path = ICON_DIR) -> dict[str, dict[str, str]]:
    """Fetch the official agent catalog and atomically cache PNG icons."""
    import requests

    session = session or requests.Session()
    response = session.get(API_URL, timeout=30, headers={"User-Agent": "vct-quant/1.0"},
                           stream=True, allow_redirects=False)
    try:
        response.raise_for_status()
        content_length = response.headers.get("content-length", "")
        if content_length.isdecimal():
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = None
            if declared_length is not None and declared_length > MAX_CATALOG_BYTES:
                raise ValueError(f"VALORANT API catalog exceeds {MAX_CATALOG_BYTES} bytes")
        body = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            if len(body) + len(chunk) > MAX_CATALOG_BYTES:
                raise ValueError(f"VALORANT API catalog exceeds {MAX_CATALOG_BYTES} bytes")
            body.extend(chunk)
        payload = json.loads(body)
    finally:
        response.close()
    catalog = _catalog(payload)
    if not catalog:
        raise ValueError("VALORANT API returned no playable agent icons")
    try:
        previous = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    icon_dir.mkdir(parents=True, exist_ok=True)
    for key, item in catalog.items():
        cached = previous.get(key) if isinstance(previous, dict) else None
        cached_file = cached.get("file") if isinstance(cached, dict) else None
        if isinstance(cached_file, str) and cached_file == f"{key}.png":
            existing = icon_dir / cached_file
            try:
                if existing.is_file() and 0 < existing.stat().st_size <= MAX_BYTES:
                    item["file"] = cached_file
                    continue
            except OSError:
                pass
        try:
            image = session.get(item["url"], timeout=30,
                                headers={"User-Agent": "vct-quant/1.0"}, stream=True,
                                allow_redirects=False)
            try:
                image.raise_for_status()
                final_url = getattr(image, "url", item["url"])
                if _icon_url(final_url) is None:
                    print(f"agent icon skipped for {item['name']}: response URL authority is untrusted")
                    continue
                content_type = image.headers.get("content-type", "").split(";")[0].strip().lower()
                if content_type != IMAGE_TYPE:
                    print(f"agent icon skipped for {item['name']}: content type {content_type or 'missing'}")
                    continue
                content_length = image.headers.get("content-length", "")
                if content_length.isdecimal() and int(content_length) > MAX_BYTES:
                    print(f"agent icon skipped for {item['name']}: image exceeds {MAX_BYTES} bytes")
                    continue
                content = bytearray()
                for chunk in image.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(content) + len(chunk) > MAX_BYTES:
                        print(f"agent icon skipped for {item['name']}: image exceeds {MAX_BYTES} bytes")
                        break
                    content.extend(chunk)
                else:
                    if not content:
                        print(f"agent icon skipped for {item['name']}: empty image")
                        continue
                    name = f"{key}.png"
                    tmp = icon_dir / f".{name}.tmp"
                    tmp.write_bytes(content)
                    tmp.replace(icon_dir / name)
                    item["file"] = name
            finally:
                image.close()
        except Exception as exc:
            print(f"agent icon download failed for {item['name']}: {exc}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp_cache = cache.with_suffix(".json.tmp")
    tmp_cache.write_text(json.dumps(dict(sorted(catalog.items())), indent=1), encoding="utf-8")
    tmp_cache.replace(cache)
    return catalog


def main() -> None:
    catalog = refresh()
    available = sum("file" in item for item in catalog.values())
    print(f"{len(catalog)} playable agents cached; {available} local icons")


if __name__ == "__main__":
    main()
