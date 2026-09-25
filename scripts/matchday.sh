#!/usr/bin/env bash
# Matchday refresh: vct update, then grade. Scheduled from blabbleu's crontab.
#
#   scripts/matchday.sh            # one refresh; output appended to data/interim/matchday.log
#
# DuckDB is single-writer. flock stops refreshes from overlapping, and one retry
# covers the desk server holding a read connection at the wrong moment.
set -u
cd "$(dirname "$0")/.."
LOG=data/interim/matchday.log
STOP_AFTER=${VCT_MATCHDAY_UNTIL:-2027-12-31}   # through the 2027 season (Kickoff qualifiers start Nov 2026)

mkdir -p data/interim
exec >>"$LOG" 2>&1
echo "=== $(date -u +%FT%TZ)"

if [ "$(date -u +%s)" -gt "$(date -u -d "$STOP_AFTER" +%s)" ]; then
  echo "past $STOP_AFTER; not refreshing (remove the crontab line)"
  exit 0
fi

if ! curl -sf -m 10 -o /dev/null http://127.0.0.1:3001/; then
  echo "vlrggapi on :3001 is down; skipping (start it in tmux session vlrggapi)"
  exit 1
fi

exec 9>data/interim/matchday.lock
if ! flock -n 9; then
  echo "previous refresh still running; skipping"
  exit 0
fi

# The API root can be healthy while the vlr.gg upstream circuit is open.
# Check both sources before any ingest/write; do not retry a known source outage.
for endpoint in 'events?page=1' 'match?q=upcoming'; do
  if ! curl -sf -m 10 -o /dev/null "http://127.0.0.1:3001/v2/$endpoint"; then
    case "$endpoint" in
      events*) echo "events feed unavailable; skipping update" ;;
      *) echo "upcoming feed unavailable; skipping update" ;;
    esac
    exit 1
  fi
done

. .venv/bin/activate
for attempt in 1 2; do
  if vct update; then
    python scripts/grade_predictions.py
    exit 0
  fi
  echo "vct update failed (attempt $attempt)"
  [ "$attempt" = 1 ] && sleep 60
done
exit 1
