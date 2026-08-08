# Plan: fix `fetch_news(action='since_update')` pacman log parsing

**Status:** proposed
**Date:** 2026-08-08
**Branch context:** `harden/security`
**Component:** `src/arch_ops_server/news.py` → `get_news_since_last_update` (line 200),
reached via `fetch_news(action='since_update')`

## Context

`fetch_news(action='since_update')` fails on every current Arch system:

```json
{"error": true, "type": "NotFound",
 "message": "Could not determine last system update timestamp from pacman log"}
```

Found while running the `update-arch-system` skill against a live system. The skill degraded
to its CLI fallback and the news gate still worked, so nothing was missed — but the tool is
inert, and a caller without a fallback would get nothing.

## Root cause

`news.py:234` expects a log timestamp format pacman no longer writes:

```python
match = re.match(r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})\]', line)
```

That matches `[2025-11-08 10:01]`. Since pacman 5.2 (2019) the log is ISO-8601:

```
[2026-08-08T16:50:25+0200] [PACMAN] starting full system upgrade
```

The `T` separator defeats `\s+`, so the regex never matches, `last_update` stays `None`, and
the function returns `NotFound`. Measured on a real log:

| Lines matching the expected legacy format | **0** |
| Lines in ISO-8601 format | **32,306** |

The log on that machine has been ISO-8601 back to its first entry in 2024-11-19. This is not
an edge case; the function has been dead for every user since pacman 5.2.

## Why the test suite does not catch it

`tests/test_news.py:205` feeds a fixture written in the **legacy** format:

```
[2025-11-08 10:01] [ALPM] upgraded linux (6.6.1-1 -> 6.6.2-1)
[2025-11-09 15:30] [ALPM] installed test-package (1.0-1)
```

The fixture matches the buggy regex, so `test_get_news_since_last_update_success` passes
against input no real system produces. Its assertions do not constrain the result either —
`assert result["news_count"] >= 0` cannot fail for any non-negative count.

**Fixing the regex without replacing this fixture leaves the test validating dead
behaviour.** The fixture is the defect, as much as the regex is.

## The three defects behind this one

Fixing only the regex is not safe, because it converts a **loud** failure into a **silent**
one. The current bug announces itself with an error. The defects below all fail by making
the news window too narrow, which returns "no news since your update" — indistinguishable
from a genuine all-clear, on a check whose only job is to stop an unprepared upgrade. Fix
them in the same change.

### 1. The timezone is discarded and replaced with UTC

`news.py:236` rebuilds the timestamp and hardcodes an offset:

```python
date_str = f"{match.group(1)}T{match.group(2)}:00+00:00"
```

The real stamp carries `+0200`. On a UTC+2 machine this places the last update two hours
later than it happened, so any announcement published in that window is judged "before your
update" and dropped. Any approach that reconstructs the string instead of parsing the
original reintroduces this.

### 2. A single package install counts as a system update

`news.py:232` accepts three markers:

```python
if " upgraded " in line or " installed " in line or "starting full system upgrade" in line:
```

The loop keeps the last match, so installing one package — `pacman -S pacman-contrib` —
moves `last_update` to today even if the last full upgrade was weeks ago. Every announcement
in between is then filtered out. For this tool's purpose only `starting full system upgrade`
marks the boundary the user actually crossed.

### 3. A broad `except` will mask the next failure

`news.py:282` catches `Exception` and reports a generic `NewsError`. If a fix yields a naive
datetime — which the legacy format does, see below — then `published > last_update` at
line 267 raises `TypeError: can't compare offset-naive and offset-aware datetimes`, and that
surfaces as an unrelated message. Narrow the catch, or handle the naive case explicitly.

## The fix

On Python ≥ 3.11 — the project floor per `pyproject.toml:30` — `datetime.fromisoformat`
parses both log formats, so capturing the whole bracketed stamp handles modern and legacy
logs with one expression. Verified:

```
'2026-08-08T16:50:25+0200'  -> 2026-08-08 16:50:25+02:00   tz-aware
'2025-11-08 10:01'          -> 2025-11-08 10:01:00         naive
```

The legacy form returns naive, so it must be given a timezone before comparison.

```python
# pacman has logged ISO-8601 timestamps since 5.2 (2019):
#   [2026-08-08T16:50:25+0200] [PACMAN] starting full system upgrade
# Capture the whole stamp and let fromisoformat read the offset rather than
# rebuilding the string, which is how the timezone was previously lost.
PACMAN_LOG_TIMESTAMP = re.compile(r"^\[([^\]]+)\]")

# Only a full system upgrade marks the boundary the user actually crossed.
# " installed "/" upgraded " would let a single-package install shrink the
# window and hide announcements.
FULL_UPGRADE_MARKER = "starting full system upgrade"

last_update = None
with open(pacman_log) as f:
    for line in f:
        if FULL_UPGRADE_MARKER not in line:
            continue
        match = PACMAN_LOG_TIMESTAMP.match(line)
        if not match:
            continue
        try:
            stamp = datetime.fromisoformat(match.group(1))
        except ValueError:
            continue
        # Legacy log lines parse naive; treat them as local time so the
        # comparison against tz-aware feed dates is well defined.
        last_update = stamp if stamp.tzinfo else stamp.astimezone()
```

### Fail toward more news, not less

When no full-upgrade line is found — a fresh install, or a rotated log where the entry now
lives in `pacman.log.1` — do not return `NotFound`. Return every recent item and say the
boundary is unknown. Over-reporting costs the user a moment's reading; under-reporting is
the failure this whole feature exists to prevent.

```python
if last_update is None:
    return {
        "last_update": None,
        "boundary_known": False,
        "note": (
            "No full system upgrade found in /var/log/pacman.log; the log may be "
            "rotated. Reporting all recent news rather than filtering."
        ),
        "news_count": len(news_items),
        "has_news": bool(news_items),
        "news": news_items,
    }
```

Add `"boundary_known": True` to the normal return so callers can tell the two apart without
inspecting `last_update` for `None`.

## Tests

Replace the legacy fixture in `tests/test_news.py` rather than adding beside it, then cover:

- **ISO-8601 fixture in the real format**, including a `+0200` offset: `last_update` matches
  the last `starting full system upgrade` line, and only later news is returned.
- **Timezone is honoured**: an item published between the local and the naive-UTC reading of
  the same stamp is classified correctly. This test fails against the current
  hardcoded-`+00:00` code and is the regression guard for defect 1.
- **A later `installed` line does not move the boundary**: log ends with a single-package
  install after an older full upgrade; `last_update` stays at the full upgrade. Regression
  guard for defect 2.
- **Legacy space-separated fixture** still parses, landing tz-aware so the comparison works.
- **No full-upgrade line**: returns `boundary_known: False` with all news, not an error.
- Replace `assert result["news_count"] >= 0` with an assertion on the actual expected count
  and titles.

## Verification

1. `uv run pytest tests/test_news.py tests/test_news_fetch.py`, then the full suite.
2. Live check on a real Arch machine — this is what the unit tests missed, so it is the one
   that matters:

   ```bash
   grep 'starting full system upgrade' /var/log/pacman.log | tail -1
   ```

   `fetch_news(action='since_update')` must report a `last_update` equal to that timestamp,
   offset included, and must not return `NotFound`.
3. Cross-check against `fetch_news(action='critical')`: any critical item published after
   `last_update` must also appear in the `since_update` result.
4. Confirm the `update-arch-system` skill now takes the arch-mcp path for this step instead
   of falling back, and that its report says so.

## Out of scope

- Reading rotated logs (`pacman.log.1`, `.gz`). The `boundary_known: False` path handles
  their absence honestly; following them is a separate feature.
- Reverse-scanning the log for speed. 32k lines parse trivially, and a forward scan keeping
  the last match is easier to read.
- The feed length ceiling of roughly ten items, which bounds how far back any news check can
  see regardless of this fix.
