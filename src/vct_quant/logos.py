"""Team logos and short tags (PRX, NRG, ...) for the web app.

Logos come from vlrggapi team payloads (``/v2/team?id=``) and from team blocks
inside archived match details. The cache lives at
``data/processed/team_logos.json`` as ``{team_id: {"name": ..., "logo": ..., "tag": ...}}``
and is only ever *read* by the dashboard; ``python -m vct_quant.logos`` refreshes
it (read-only against the DB and data/raw; writes only the JSON cache).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .config import PROCESSED_DIR, RAW_VLRGG_DIR

CACHE = PROCESSED_DIR / "team_logos.json"
# Local copies served by server.js at /logos/<team_id>.<ext>, so phones never
# depend on the third-party CDN (which refuses some browser requests).
LOGO_DIR = PROCESSED_DIR / "logos"
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/svg+xml": ".svg"}
MAX_BYTES = 512 * 1024
# vlr.gg's generic "no logo" placeholder is not a team logo.
PLACEHOLDER = re.compile(r"/img/vlr/tmp/vlr\.png$")


def clean_url(url: object) -> str | None:
    """Absolute https URL for a real logo, or None."""
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = "https://www.vlr.gg" + url
    if not url.startswith("https://") or PLACEHOLDER.search(url):
        return None
    return url


def clean_tag(value: object) -> str | None:
    """A short team tag like ``PRX``: 1-6 letters/digits (plus . or -), else None."""
    tag = str(value or "").strip()
    return tag if re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.\-]{0,5}", tag) else None


def _team_id(value: object) -> str | None:
    text = str(value or "").strip()
    return text if text.isdecimal() and int(text) > 0 else None


def _extract(payload: object, from_team_page: bool) -> dict[str, dict]:
    """Logos in one vlrggapi payload (a team page or a match-details page)."""
    found: dict[str, dict] = {}
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    segments = data.get("segments", [data]) if isinstance(data, dict) else []
    for seg in segments if isinstance(segments, list) else []:
        if not isinstance(seg, dict):
            continue
        blocks = ([seg] if from_team_page else []) + [t for t in seg.get("teams") or [] if isinstance(t, dict)]
        for block in blocks:
            key = _team_id(block.get("id"))
            if not key:
                continue
            entry = {}
            url = clean_url(block.get("logo"))
            if url:
                entry["logo"] = url
            tag = clean_tag(block.get("tag"))
            if tag:  # match-detail payloads carry empty tags; never erase a known one
                entry["tag"] = tag
            if entry:
                name = str(block.get("name") or "").strip()
                found[key] = {**found.get(key, {}), **({"name": name} if name else {}), **entry}
    return found


def harvest(raw_dir: Path = RAW_VLRGG_DIR) -> dict[str, dict]:
    """Latest logo per team id from archived team and match-detail payloads.

    Files are read in filename order (UTC fetch stamp), so a newer snapshot
    wins. Unreadable or malformed files are skipped. Read-only.
    """
    found: dict[str, dict] = {}
    for pattern, team_page in (("match_details_*.json", False), ("team_*.json", True)):
        for path in sorted(raw_dir.glob(pattern)):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            for key, entry in _extract(payload, team_page).items():
                found[key] = {**found.get(key, {}), **entry}
    return found


def _cache_entries(path: Path = CACHE) -> dict[str, dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return {str(k): v for k, v in raw.items() if _team_id(k) and isinstance(v, dict)} if isinstance(raw, dict) else {}


def load_logos(path: Path = CACHE, logo_dir: Path | None = None) -> dict[str, str]:
    """``{team_id: url}`` for the dashboard: the local ``/logos/...`` copy when
    downloaded, else the source URL; empty when the cache is absent."""
    logo_dir = LOGO_DIR if logo_dir is None else logo_dir
    out = {}
    for key, entry in _cache_entries(path).items():
        local = entry.get("file")
        if isinstance(local, str) and re.fullmatch(r"[0-9]+\.(png|jpg|webp|svg)", local) \
                and (logo_dir / local).is_file():
            out[key] = f"/logos/{local}"
            continue
        url = clean_url(entry.get("logo"))
        if url:
            out[key] = url
    return out


def load_tags(path: Path = CACHE) -> dict[str, str]:
    """``{team_id: tag}``; teams without a known tag are absent."""
    out = {}
    for key, entry in _cache_entries(path).items():
        tag = clean_tag(entry.get("tag"))
        if tag:
            out[key] = tag
    return out


def download(logos: dict[str, dict], logo_dir: Path = LOGO_DIR) -> int:
    """Store a local copy of each logo (skips ones already on disk). Returns new files."""
    import requests

    logo_dir.mkdir(parents=True, exist_ok=True)
    added = 0
    for key, entry in logos.items():
        url = clean_url(entry.get("logo"))
        if not url:
            continue
        if entry.get("file") and entry.get("source") == url and (logo_dir / entry["file"]).is_file():
            continue
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "vct-quant/1.0"})
            resp.raise_for_status()
            ext = IMAGE_TYPES.get(resp.headers.get("content-type", "").split(";")[0].strip())
            if not ext or not resp.content or len(resp.content) > MAX_BYTES:
                continue
            name = f"{key}{ext}"
            tmp = logo_dir / f".{name}.tmp"
            tmp.write_bytes(resp.content)
            tmp.replace(logo_dir / name)
            entry["file"], entry["source"] = name, url
            added += 1
        except Exception as exc:
            print(f"logo download failed for team {key}: {exc}")
    return added


def wanted_team_ids() -> set[str]:
    """Teams the web app shows: current rankings, upcoming fixtures, graded log."""
    import pandas as pd

    from .features.build import current_rankings

    ids: set[str] = set()
    ids.update(str(k) for k in current_rankings().get("team_key", []))
    for name, cols in (("upcoming_tier1.parquet", ["team_a_key", "team_b_key"]),
                       ("prediction_log.parquet", ["team_a_key", "team_b_key"])):
        path = PROCESSED_DIR / name
        if path.exists():
            frame = pd.read_parquet(path, columns=cols)
            for col in cols:
                ids.update(frame[col].dropna().astype(str))
    return {i for i in ids if _team_id(i)}


def refresh(fetch_missing: bool = True, limit: int = 120) -> dict[str, dict]:
    """Merge archived logos with the existing cache, fetch missing shown teams.

    Fetched team pages are NOT archived under data/raw (read-only); only the
    logo cache is written, atomically.
    """
    logos = _cache_entries()
    for key, entry in harvest().items():
        logos[key] = {**logos.get(key, {}), **entry}
    if fetch_missing:
        from .ingest import vlrgg

        # Team pages are the only source of tags, so fetch shown teams missing either.
        missing = sorted((k for k in wanted_team_ids()
                          if not logos.get(k, {}).get("logo") or not logos.get(k, {}).get("tag")),
                         key=int)[:limit]
        for team_id in missing:
            try:
                for key, entry in _extract(vlrgg.fetch_team(team_id, save=False), True).items():
                    logos[key] = {**logos.get(key, {}), **entry}
            except Exception as exc:  # one bad team must not stop the rest
                print(f"logo fetch failed for team {team_id}: {exc}")
    if fetch_missing:
        download(logos)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CACHE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(dict(sorted(logos.items(), key=lambda kv: int(kv[0]))), indent=1),
                   encoding="utf-8")
    tmp.replace(CACHE)
    return logos


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-fetch", action="store_true", help="only harvest archived payloads")
    parser.add_argument("--limit", type=int, default=120, help="max team pages to fetch")
    args = parser.parse_args()
    logos = refresh(fetch_missing=not args.no_fetch, limit=args.limit)
    wanted = wanted_team_ids()
    with_logo = {k for k, v in logos.items() if v.get("logo")}
    with_tag = {k for k, v in logos.items() if v.get("tag")}
    print(f"{len(logos)} teams cached; shown teams with logo {len(wanted & with_logo)}/{len(wanted)}, "
          f"with tag {len(wanted & with_tag)}/{len(wanted)}")


if __name__ == "__main__":
    main()
