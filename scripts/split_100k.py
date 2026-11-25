# One-off: the 100K+ split from exports/research/studied-videos.xlsx (scripts/export_studied_videos.py) ->
# research/100k-split-2026-11.json. High = 100K+ views and 5x+ the channel's normal; low = under 100K and under 1x;
# both from the watched streamer-clip channels (research/viral-channels.txt), on a channel-relative lift, keeping only
# channels with both. Our own uploads ride along with their first-day numbers. Needs openpyxl.
import json
import sys
from datetime import datetime
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
BOOK = ROOT / "exports" / "research" / "studied-videos.xlsx"
OUT = ROOT / "research" / "100k-split-2026-11.json"
LIFT_BASIS = ("lift (open-loop-titles.json)", "lift (moment-pairs.json)")
HIGH_VIEWS, HIGH_LIFT, LOW_LIFT = 100_000, 5.0, 1.0
KEEP = {"video_id": "id", "channel": "ch", "subs": "subs", "B Title": "t", "E Views": "views", "E Outlier score": "lift",
        "C Duration (s)": "dur", "D Upload time (UTC)": "published", "D Posting frequency (uploads/day)": "freq",
        "E Likes per 1,000 views": "likes_k", "E Comments per 1,000 views": "comments_k",
        "E Views measured at age (days)": "age_d", "B Spoken hook": "spoken_hook", "B On-screen hook": "screen_hook",
        "B Hook type": "hook_type", "C Dead space (s)": "dead_s", "C Cuts per minute": "cuts_min",
        "A Streamer(s)": "streamers"}
OWN = {"video_id": "id", "B Title": "t", "C Duration (s)": "dur", "D Upload time (UTC)": "published",
       "E Views": "views", "E Views after 24 hours": "views_24h", "E Views after 72 hours": "views_72h",
       "E Viewed vs swiped away (stayed %)": "stayed", "E First 3-second retention": "r3s",
       "E Likes per 1,000 views": "likes_k", "B Hook type": "hook_type", "B On-screen hook": "screen_hook",
       "A Moment type": "moment_type", "A Streamer(s)": "streamers"}


def clean(v):
    return v.isoformat(timespec="seconds") if isinstance(v, datetime) else v


def sheet(wb, name):
    rows = wb[name].iter_rows(values_only=True)
    head = next(rows)
    return [dict(zip(head, r)) for r in rows]


def watched(path=ROOT / "research" / "viral-channels.txt"):
    return {ln.split(" ", 1)[1].strip() for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")}


def split(videos, channels):
    rows = [v for v in videos if v["E Score basis"] in LIFT_BASIS and v["channel"] in channels
            and isinstance(v["E Views"], (int, float)) and isinstance(v["E Outlier score"], (int, float))]
    high = [v for v in rows if v["E Views"] >= HIGH_VIEWS and v["E Outlier score"] >= HIGH_LIFT]
    low = [v for v in rows if v["E Views"] < HIGH_VIEWS and v["E Outlier score"] < LOW_LIFT]
    both = {v["channel"] for v in high} & {v["channel"] for v in low}
    return high, low, both


def main():
    wb = openpyxl.load_workbook(BOOK, read_only=True)
    high, low, both = split(sheet(wb, "videos"), watched())
    out = [{"group": g, **{k: clean(v[c]) for c, k in KEEP.items() if v.get(c) is not None}}
           for g, rows in (("high", high), ("low", low)) for v in rows if v["channel"] in both]
    own = [{k: clean(o[c]) for c, k in OWN.items() if o.get(c) is not None}
           for o in sheet(wb, "own channel") if o["kind"] == "short"]
    data = {"built_from": BOOK.name, "rule": {"high": "views >= 100K and lift >= 5", "low": "views < 100K and lift < 1",
                                              "channels": "research/viral-channels.txt, with both groups",
                                              "lift": list(LIFT_BASIS)},
            "all_high": len(high), "all_low": len(low), "channels": sorted(both), "videos": out, "own": own}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0))
    print(f"high {len(high)} / low {len(low)} on the watched channels; {len(both)} channels with both: "
          f"{sum(r['group'] == 'high' for r in out)} high, {sum(r['group'] == 'low' for r in out)} low; own {len(own)}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
