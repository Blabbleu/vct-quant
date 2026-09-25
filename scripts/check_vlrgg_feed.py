"""Validate a vlrggapi source response on stdin before matchday writes anything.

HTTP 200 is insufficient: the API can return an error envelope or malformed
segments. This checker performs no network access or writes.
"""
from __future__ import annotations

import json
import sys


def valid_feed(payload: object) -> bool:
    if not isinstance(payload, dict) or payload.get("status") != "success":
        return False
    data = payload.get("data")
    return (isinstance(data, dict) and data.get("status") == 200
            and isinstance(data.get("segments"), list)
            and all(isinstance(row, dict) for row in data["segments"]))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (ValueError, UnicodeError):
        return 1
    return 0 if valid_feed(payload) else 1


if __name__ == "__main__":
    sys.exit(main())
