"""Cache bounded exact-ID player avatars from the local vlr.gg API.

Only processed caches are written. Raw API archives and the canonical database
are read-only; downloaded media is restricted to the known avatar CDN.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .config import PROCESSED_DIR

CACHE = PROCESSED_DIR / "player_photos.json"
PHOTO_DIR = PROCESSED_DIR / "players"
MAX_BYTES = 512 * 1024
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
PLACEHOLDER = re.compile(r"/img/base/ph/sil\.png$")


def clean_avatar_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    url = value.strip()
    if not url.startswith("https://") or PLACEHOLDER.search(url):
        return None
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.username is not None or parsed.password is not None or parsed.port is not None:
            return None
    except ValueError:
        return None
    return url if host == "owcdn.net" or host.endswith(".owcdn.net") else None


def _player_id(value: object) -> str | None:
    text = str(value or "").strip()
    if not text.isascii() or not text.isdecimal() or len(text) > 16:
        return None
    try:
        return text if 0 < int(text) <= 9_007_199_254_740_991 else None
    except ValueError:
        return None


def _has_roster(payload: object) -> bool:
    """Return whether a team response has the expected roster shape."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return False
    segments = data.get("segments", [data])
    return isinstance(segments, list) and any(
        isinstance(segment, dict) and isinstance(segment.get("roster"), list)
        for segment in segments
    )


def extract_roster(payload: object) -> dict[str, dict]:
    """Extract valid avatar records from a team-page response."""
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    segments = data.get("segments", [data]) if isinstance(data, dict) else []
    result: dict[str, dict] = {}
    for segment in segments if isinstance(segments, list) else []:
        roster = segment.get("roster", []) if isinstance(segment, dict) else []
        for player in roster if isinstance(roster, list) else []:
            if not isinstance(player, dict):
                continue
            key = _player_id(player.get("id"))
            avatar = clean_avatar_url(player.get("avatar"))
            if key and avatar:
                handle = str(player.get("name") or "").strip()
                result[key] = {"avatar": avatar, **({"handle": handle} if handle else {})}
    return result


def _cache(path: Path = CACHE) -> dict[str, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for raw_key, value in data.items()
            if (key := _player_id(raw_key)) and isinstance(value, dict)}


def _checked_teams(path: Path = CACHE) -> set[str]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    values = raw.get("_teams_checked", []) if isinstance(raw, dict) else []
    return {key for value in values if (key := _player_id(value))} if isinstance(values, list) else set()


def local_photo(player_id: object, cache: dict[str, dict] | None = None,
                photo_dir: Path | None = None) -> str | None:
    key = _player_id(player_id)
    photo_dir = PHOTO_DIR if photo_dir is None else photo_dir
    entry = (cache if cache is not None else _cache()).get(key, {}) if key else {}
    filename = entry.get("file") if isinstance(entry, dict) else None
    if not isinstance(filename, str) or not re.fullmatch(r"[1-9][0-9]*\.(png|jpg|webp)", filename):
        return None
    return f"/players/{filename}" if (photo_dir / filename).is_file() else None


def local_photos(player_ids, cache: dict[str, dict] | None = None,
                 photo_dir: Path | None = None) -> dict[str, str | None]:
    """Resolve many local photos while parsing the cache only once."""
    cache = _cache() if cache is None else cache
    result = {}
    for player_id in player_ids:
        key = _player_id(player_id)
        if key:
            result[key] = local_photo(key, cache=cache, photo_dir=photo_dir)
    return result


def download(records: dict[str, dict], photo_dir: Path = PHOTO_DIR) -> int:
    import requests

    photo_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    for raw_player_id, entry in records.items():
        player_id = _player_id(raw_player_id)
        if not player_id or not isinstance(entry, dict):
            continue
        source = clean_avatar_url(entry.get("avatar"))
        if not source:
            continue
        existing = entry.get("file")
        if entry.get("source") == source and isinstance(existing, str) \
                and re.fullmatch(r"[1-9][0-9]*\.(png|jpg|webp)", existing) \
                and (photo_dir / existing).is_file():
            continue
        try:
            response = requests.get(source, timeout=15, headers={"User-Agent": "vct-quant/1.0"},
                                   allow_redirects=False, stream=True)
            try:
                response.raise_for_status()
                if clean_avatar_url(response.url) is None:
                    continue
                extension = IMAGE_TYPES.get(response.headers.get("content-type", "").split(";")[0].strip().lower())
                if not extension:
                    continue
                content_length = response.headers.get("content-length", "")
                if content_length.isdecimal() and int(content_length) > MAX_BYTES:
                    continue
                content = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(content) + len(chunk) > MAX_BYTES:
                        break
                    content.extend(chunk)
                else:
                    if not content:
                        continue
                    filename = f"{player_id}{extension}"
                    temporary = photo_dir / f".{filename}.tmp"
                    temporary.write_bytes(content)
                    temporary.replace(photo_dir / filename)
                    entry["file"], entry["source"] = filename, source
                    added += 1
            finally:
                response.close()
        except Exception as exc:
            print(f"player photo download failed for {player_id}: {exc}")
    return added


def refresh(*, limit: int = 150, player_limit: int = 150) -> dict[str, dict]:
    """Refresh bounded wanted-team rosters and missing historical player IDs."""
    from . import logos
    from .ingest import vlrgg
    from .recent_lineup import recent_lineup

    records = _cache()
    checked = _checked_teams()
    targets = sorted(logos.wanted_team_ids(), key=int)
    for team_id in [key for key in targets if key not in checked][:limit]:
        try:
            response = vlrgg.fetch_team(team_id, save=False)
            if not _has_roster(response):
                print(f"player roster response malformed for team {team_id}; will retry")
                continue
            records.update({key: {**records.get(key, {}), **value}
                            for key, value in extract_roster(response).items()})
            checked.add(team_id)
        except Exception as exc:
            print(f"player roster fetch failed for team {team_id}: {exc}")
    missing: set[str] = set()
    for team_id in targets:
        try:
            missing.update(str(row["player_id"]) for row in recent_lineup(int(team_id))["players"]
                           if _player_id(row.get("player_id"))
                           and not records.get(str(row["player_id"]), {}).get("avatar"))
        except Exception as exc:
            print(f"player history lookup failed for team {team_id}: {exc}")
    for player_id in sorted(missing, key=int)[:player_limit]:
        try:
            data = vlrgg.fetch_player(player_id, save=False)
            payload = data.get("data", {}) if isinstance(data, dict) else {}
            segments = payload.get("segments", [payload]) if isinstance(payload, dict) else []
            for segment in segments if isinstance(segments, list) else []:
                if not isinstance(segment, dict) or _player_id(segment.get("id")) != player_id:
                    continue
                avatar = clean_avatar_url(segment.get("avatar"))
                if avatar:
                    records[player_id] = {**records.get(player_id, {}), "avatar": avatar,
                                          **({"handle": str(segment.get("name")).strip()}
                                             if segment.get("name") else {})}
        except Exception as exc:
            print(f"player photo lookup failed for {player_id}: {exc}")
    download(records)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE.with_suffix(".json.tmp")
    serializable = dict(sorted(records.items(), key=lambda pair: int(pair[0])))
    serializable["_teams_checked"] = sorted(checked, key=int)
    temporary.write_text(json.dumps(serializable, indent=1), encoding="utf-8")
    temporary.replace(CACHE)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=150, help="max team roster requests")
    parser.add_argument("--player-limit", type=int, default=150, help="max individual player requests")
    args = parser.parse_args()
    records = refresh(limit=max(0, args.limit), player_limit=max(0, args.player_limit))
    print(f"{len(records)} player avatars cached; {sum(local_photo(k, records) is not None for k in records)} local photos")


if __name__ == "__main__":
    main()
