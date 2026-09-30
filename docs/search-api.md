# Search API contract

`GET /api/search` serves the processed Tier-1/Tier-2 team, player, and event index. It is read-only and does not trigger upstream requests.

## Requests

- `GET /api/search` returns the full index for compatibility. The response has `teams`, `players`, and `events` arrays.
- `GET /api/search?q=<query>` searches all three categories. `q` is trimmed and must contain 1–100 characters. The query is Unicode-normalized (NFKD), diacritics are removed, and matching is case-insensitive; Turkish dotless `ı` folds to `i`.
- `limit` is optional only when `q` is present. It must be an integer from 1 through 50; the default is 20. The cap applies independently to each category, so the response can contain up to three times that many rows.
- Each category ranks exact field matches before prefix matches, then substring matches. Ties preserve source-index order. Teams match `id`, `name`, and `tag`; players match `id`, `handle`, `real_name`, and latest recorded `team_name`; events match `id` and `name`.
- Empty/whitespace queries, oversized queries, malformed limits, `limit` without `q`, or repeated `q`/`limit` parameters return HTTP 400. A nonblank query that normalizes to empty returns empty arrays.

## Responses and caching

- Search results are JSON. The full index may be gzip-compressed when accepted by the request; clients should let the HTTP stack handle `Accept-Encoding` rather than manually decoding it. `Vary: Accept-Encoding` is set.
- Successful responses use `Cache-Control: no-cache` and a SHA-256 ETag for the exact representation bytes. Gzip and identity variants have different ETags.
- Send the received ETag in `If-None-Match` on revalidation. Matching strong, weak, or wildcard validators return HTTP 304 with an empty body; otherwise the route returns HTTP 200 and the representation.
- The server reloads the processed index when its mtime/size stamp changes. A missing or invalid index returns HTTP 503 with a fixed error payload; clients can retry after the next matchday refresh.

This contract describes the backend behavior; it does not prescribe UI layout or client-side ranking.
