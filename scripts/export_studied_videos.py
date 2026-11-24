# One-off: merge every competitor-video dataset (research/*.json + the raw study data in viral/) into one workbook,
# exports/research/studied-videos.xlsx, one row per video. Needs openpyxl: python3 scripts/export_studied_videos.py
import argparse
import csv
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
RES, VIRAL = ROOT / "research", ROOT / "viral"
OUT_DIR = ROOT / "exports" / "research"
OUT = OUT_DIR / "studied-videos.xlsx"
OUT_CSV = OUT_DIR / "studied-videos.csv"     # only with --csv
CACHE = OUT_DIR / ".cache"
YTDLP_CACHE = CACHE / "ytdlp.json"            # channel listings and channel subs, so a rerun never re-fetches
ABOUT_CACHE = CACHE / "about.json"            # {id: {"about", "source"}} written from transcripts / first lines
ABOUT_TODO = CACHE / "about-todo.jsonl"       # rows that have spoken text but no written "about" yet

COLUMNS = ["rank", "video_id", "url", "channel", "subs", "title", "spoken_hook", "onscreen_hook", "about",
           "about_source", "views", "likes", "comments", "published", "duration_s", "outlier_score", "score_basis",
           "group", "niche_query", "source_files"]
SCORES = ("x", "lift", "views/norm", "views/subs")

# Per-field preference when files overlap: direct API stats first, title-only collections last.
PRIO = {"viral/longform/long.json": 1, "viral/videos.json": 2, "research/gaming-shorts-outliers.json": 3,
        "research/long-form-outliers.json": 4, "research/clip-hooks-500k.json": 5, "research/hits-vs-flops.json": 6,
        "research/moment-pairs.json": 7, "research/long-form-streamers-2026-11.json": 8, "viral/openings.json": 9,
        "viral/labels.json": 10, "viral/ab.json": 11, "research/gaming-shorts-titles.json": 12,
        "research/open-loop-titles.json": 13, "yt-dlp": 20}
NOT_VIDEO_DATA = {"hook-strategy.json", "own-stats.json"}


def ckey(name):
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def tkey(title):
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def num(v):
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def day(v):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v or ""))
    return m.group(1) if m else None


def first_line(words, max_gap=0.7, max_words=14):  # same rule as clipper.pairs.first_line, for [w, s, e] words
    out = []
    for w, s, e in words:
        if out and (s - out[-1][2] > max_gap or len(out) >= max_words):
            break
        out.append((w, s, e))
    return " ".join(w for w, _, _ in out)


def clean_captions(text):
    return re.sub(r"\s+", " ", re.sub(r"\[[^\]]*\]|>>", " ", text or "")).strip()


def title_sentence(title):
    """A title as a plain sentence: hashtags, emoji and decoration dropped, nothing added."""
    t = re.sub(r"#\S+", " ", title or "")
    t = "".join(c for c in t if c.isalnum() or c.isspace() or c in "'’\".,!?:;-&$%()/+")
    t = re.sub(r"\s+", " ", t).strip(" -|:;,/")
    if not re.search(r"[A-Za-z0-9]", t):
        return ""
    return t if t[-1] in ".!?" else t + "."


class Store:
    def __init__(self):
        self.rows = {}

    def row(self, key):
        return self.rows.setdefault(key, {"fields": {}, "files": set(), "scores": {}, "niche": [], "id": None})

    def add(self, key, src, **fields):
        r = self.row(key)
        r["files"].add(src)
        for k, v in fields.items():
            if v is None or v == "":
                continue
            if k == "niche":
                if v not in r["niche"]:
                    r["niche"].append(v)
            elif k in SCORES:
                r["scores"].setdefault(k, (PRIO[src], v, src))
                if PRIO[src] < r["scores"][k][0]:
                    r["scores"][k] = (PRIO[src], v, src)
            elif k not in r["fields"] or PRIO[src] < r["fields"][k][0]:
                r["fields"][k] = (PRIO[src], v)
        return r

    def get(self, r, k):
        return r["fields"].get(k, (0, None))[1]


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def own_filter():
    """Our video IDs, channel IDs and channel names (own-stats.json, own-uploads*.json, viral 'own' rows)."""
    ids, chans, names = set(), set(), set()
    for p in [RES / "own-stats.json", *sorted(RES.glob("own-uploads*.json"))]:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict):
                names.add(ckey(d.get("channel")))
                d = d.get("uploads") or []
            ids |= {u.get("id") for u in d if isinstance(u, dict) and u.get("id")}
    if (VIRAL / "videos.json").exists():
        for v in load("viral/videos.json"):
            if v.get("source") == "own":
                ids.add(v["id"])
                chans.add(v.get("channel_id"))
    names.discard("")
    return ids, {c for c in chans if c}, names


def channel_names():
    """channel_id -> (name, subs) from every channel list we have."""
    out = {}
    for line in (RES / "viral-channels.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("UC"):
            cid, name = line.split(" ", 1)
            out[cid] = (name.strip(), None)
    for rel in ("viral/longform/candidates.json", "viral/longform/channels.json"):
        if (ROOT / rel).exists():
            for cid, c in load(rel).items():
                out[cid] = (c.get("name") or out.get(cid, (None,))[0], num(c.get("subs")) or (out.get(cid) or (0, None))[1])
    for c in load("research/long-form-streamers-2026-11.json")["meta"]["channels"]:
        out[c["id"]] = (c["name"], num(c.get("subs")) or (out.get(c["id"]) or (0, None))[1])
    return out


def collect(store, own_ids, own_chans, own_names, chans):
    used, skipped = Counter(), Counter()
    title_rows = []                                   # (src, ch, t, fields) from files with no video IDs
    name_subs = {}                                    # ckey(channel name) -> subs, for rows with names only

    def keep(src, vid, ch=None, cid=None):
        if vid in own_ids or (cid and cid in own_chans) or ckey(ch) in own_names:
            skipped[src] += 1
            return False
        return True

    for cid, (name, subs) in chans.items():
        if subs:
            name_subs.setdefault(ckey(name), subs)

    # viral/longform/long.json: the 3,461 long videos the 2026-11 long-form study measured (vision.json = that set)
    if (VIRAL / "longform" / "long.json").exists():
        studied = set(load("viral/longform/vision.json")) if (VIRAL / "longform" / "vision.json").exists() else None
        src = "viral/longform/long.json"
        for v in load(src):
            if studied is not None and v["id"] not in studied:
                continue
            if keep(src, v["id"], v.get("channel"), v.get("channel_id")):
                store.add(v["id"], src, channel=v.get("channel"), channel_id=v.get("channel_id"), title=v.get("title"),
                          views=num(v.get("views")), likes=num(v.get("likes")), comments=num(v.get("comments")),
                          published=day(v.get("published")), duration_s=num(v.get("duration")), x=num(v.get("x")),
                          subs=(chans.get(v.get("channel_id")) or (None, None))[1],
                          group="top" if v.get("outlier") else None,
                          niche=" / ".join(x for x in (v.get("lean"), v.get("kind")) if x) or None)

    # viral/videos.json: the streamer-clip Shorts collected for the outlier study
    if (VIRAL / "videos.json").exists():
        src = "viral/videos.json"
        for v in load(src):
            name, subs = chans.get(v.get("channel_id"), (None, None))
            ch = name or (v.get("source") if v.get("source") != "own" else None)
            if keep(src, v["id"], ch, v.get("channel_id")):
                store.add(v["id"], src, channel=ch, channel_id=v.get("channel_id"), title=v.get("title"),
                          views=num(v.get("views")), likes=None if v.get("likes_hidden") else num(v.get("likes")),
                          published=day(v.get("published")), duration_s=num(v.get("duration")), subs=subs)

    src = "research/gaming-shorts-outliers.json"
    for v in load(src):
        if keep(src, v["id"], v.get("ch")):
            store.add(v["id"], src, channel=v.get("ch"), title=v.get("t"), views=num(v.get("views")),
                      likes=num(v.get("likes")), comments=num(v.get("comments")), duration_s=num(v.get("dur")),
                      x=num(v.get("x")), subs=num(v.get("subs")), spoken_hook=v.get("first_line"), niche=v.get("q"))

    src = "research/long-form-outliers.json"
    lfo = load(src)
    for c in lfo["channels"]:
        if num(c.get("subs")):
            name_subs.setdefault(ckey(c["ch"]), num(c["subs"]))
    for v in lfo["outliers"]:
        if keep(src, v["id"], v.get("ch")):
            store.add(v["id"], src, channel=v.get("ch"), title=v.get("t"), views=num(v.get("views")),
                      likes=num(v.get("likes")), comments=num(v.get("comments")), published=day(v.get("pub")),
                      duration_s=num(v.get("dur")), x=num(v.get("x")), group="top")

    src = "research/clip-hooks-500k.json"
    for v in load(src):
        if keep(src, v["id"], v.get("ch")):
            store.add(v["id"], src, channel=v.get("ch"), title=v.get("t"), views=num(v.get("views")),
                      published=day(v.get("pub")), duration_s=num(v.get("duration")),
                      onscreen_hook=v.get("banner_text"))

    src = "research/hits-vs-flops.json"
    for v in load(src):
        if keep(src, v["id"], v.get("ch")):
            store.add(v["id"], src, channel=v.get("ch"), title=v.get("t"), views=num(v.get("views")),
                      duration_s=num(v.get("duration")), lift=num(v.get("lift")), group=v.get("group"))

    src = "research/moment-pairs.json"
    transcripts = {}
    for p in load(src):
        for side, group in (("hit", "top"), ("flop", "bottom")):
            v = p[side]
            if keep(src, v["id"], v.get("ch")):
                words = v.get("words") or []
                store.add(v["id"], src, channel=v.get("ch"), title=v.get("t"), views=num(v.get("views")),
                          lift=num(v.get("lift")), group=group, spoken_hook=first_line(words) or None)
                if words:
                    transcripts[v["id"]] = " ".join(w[0] for w in words)

    src = "research/long-form-streamers-2026-11.json"
    lfs = load(src)
    for v in lfs["coded_titles"]:
        if keep(src, v["id"], v.get("channel")):
            store.add(v["id"], src, channel=v.get("channel"), title=v.get("title"), views=num(v.get("views")),
                      duration_s=num(v.get("duration")), x=num(v.get("x")), group="top" if v.get("outlier") else None)
    for v in lfs["closeups"]:
        if keep(src, v["id"], v.get("channel")):
            caps = clean_captions(v.get("first30s_captions"))
            store.add(v["id"], src, channel=v.get("channel"), title=v.get("title"), views=num(v.get("views")),
                      duration_s=num(v.get("dur_s")), x=num(v.get("x")), niche=v.get("lean"),
                      spoken_hook=" ".join(caps.split()[:14]) or None)
            if caps:
                transcripts[v["id"]] = caps        # first 30 s only; the title covers the rest

    # enrichment for videos already listed above (openings: OCR + first 5 s; labels: title-based premise;
    # ab: Gemini watched the video and described its premise)
    if (VIRAL / "openings.json").exists():
        src = "viral/openings.json"
        for vid, o in load(src).items():
            if vid in store.rows and keep(src, vid):
                store.add(vid, src, spoken_hook=o.get("transcript_0_5") or None,
                          onscreen_hook=o.get("ocr_0_3") if o.get("hook_text") else None)
    premise = {}
    if (VIRAL / "labels.json").exists():
        for vid, lab in load("viral/labels.json").items():
            if vid in store.rows and lab.get("premise"):
                premise[vid] = lab["premise"]
                store.rows[vid]["files"].add("viral/labels.json")
    watched = {}
    if (VIRAL / "ab.json").exists():
        src = "viral/ab.json"
        for a in load(src).values():
            reply = a.get("reply") if isinstance(a.get("reply"), dict) else {}
            for vid, group in ((a.get("outlier"), "top"), (a.get("average"), None)):
                side = "A" if a.get("A") == vid else "B"
                if vid in store.rows and keep(src, vid):
                    store.add(vid, src, group=group)
                    if (reply.get(side) or {}).get("premise"):
                        watched[vid] = reply[side]["premise"]

    # title-only collections: no video IDs in the file
    for src, field in (("research/gaming-shorts-titles.json", "niche"), ("research/open-loop-titles.json", "set")):
        for v in load(src):
            if keep(src, None, v.get("ch")):
                title_rows.append((src, v["ch"], v["t"], {"views": num(v.get("views")), "lift": num(v.get("lift")),
                                                         "niche": v.get(field)}))
    return used, skipped, title_rows, name_subs, transcripts, premise, watched


# ---------- yt-dlp (metadata only, cached) ----------

def ytdlp_json(url, end):
    cmd = ["yt-dlp", "--ignore-config", "--flat-playlist", "-J", "--no-warnings", "--skip-download",
           "--playlist-end", str(end), "--sleep-requests", "0.5", url]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if res.returncode != 0 or not res.stdout.strip():
        raise RuntimeError((res.stderr or "no output").strip().splitlines()[-1][:200])
    return json.loads(res.stdout)


def resolve_channel(name, titles, cache, refresh, end):
    """List a channel's Shorts and accept it only if enough of our titles are on it. Candidates: the
    channel's @handle, then YouTube's channel search for the name."""
    chans = cache.setdefault("channels", {})
    if name in chans and not refresh:
        return chans[name]
    want = {tkey(t) for t in titles}
    tried, best = [], None
    handle = re.sub(r"[^A-Za-z0-9_.-]", "", name)
    candidates = [f"https://www.youtube.com/@{handle}"] if handle else []
    try:
        found = ytdlp_json(f"https://www.youtube.com/results?search_query={quote(name)}&sp=EgIQAg%253D%253D", 3)
        candidates += [e.get("url") for e in found.get("entries") or [] if e.get("url")]
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        tried.append(f"search: {e}")
    for base in dict.fromkeys(candidates):
        try:
            d = ytdlp_json(base.rstrip("/") + "/shorts", end)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            tried.append(f"{base}: {e}")
            continue
        entries = {tkey(e.get("title")): e["id"] for e in d.get("entries") or [] if e.get("id")}
        hit = len(want & set(entries))
        info = {"url": base, "channel": d.get("channel"), "channel_id": d.get("channel_id"),
                "subs": num(d.get("channel_follower_count")), "ids": entries, "matched": hit, "wanted": len(want),
                "fetched_at": time.time()}
        if best is None or hit > best["matched"]:
            best = info
        if hit >= max(3, 0.3 * len(want)):
            break
    if best is None or best["matched"] < max(3, 0.3 * len(want)):
        best = {"unresolved": True, "tried": tried, "best": {k: v for k, v in (best or {}).items() if k != "ids"},
                "fetched_at": time.time()}
    chans[name] = best
    return best


def channel_subs(cid, cache, refresh):
    subs = cache.setdefault("subs", {})
    if cid not in subs or refresh:
        try:
            d = ytdlp_json(f"https://www.youtube.com/channel/{cid}/videos", 1)
            subs[cid] = {"subs": num(d.get("channel_follower_count")), "channel": d.get("channel"),
                         "fetched_at": time.time()}
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            subs[cid] = {"subs": None, "error": str(e), "fetched_at": time.time()}
    return subs[cid]


def video_subs(vid, cache, refresh):
    vids = cache.setdefault("videos", {})
    if vid not in vids or refresh:
        try:
            res = subprocess.run(["yt-dlp", "--ignore-config", "-J", "--no-warnings", "--skip-download",
                                  f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, timeout=120)
            d = json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else {}
            vids[vid] = {"subs": num(d.get("channel_follower_count")), "channel_id": d.get("channel_id"),
                         "error": None if d else (res.stderr or "no output").strip()[-200:], "fetched_at": time.time()}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            vids[vid] = {"subs": None, "error": str(e), "fetched_at": time.time()}
    return vids[vid]


NOTES = [
    ("rank", "1 = highest outlier_score; rows with no score last"),
    ("video_id / url", "blank when the source file had only channel + title and the ID couldn't be found"),
    ("subs", "channel subscribers: from our channel lists, else yt-dlp channel metadata"),
    ("spoken_hook", "first spoken line (transcript), verbatim from speech recognition"),
    ("onscreen_hook", "text on screen at the start (banner_text, or Apple OCR at 0.3 s)"),
    ("about", "one sentence on what happens, written only from the data in about_source"),
    ("about_source", "transcript = speech transcript + title; video = Gemini watched the video (viral/ab.json); "
                     "first_line = first spoken line + title; title_only = the title alone"),
    ("outlier_score", "x or lift = views vs the channel's normal; views/subs only when neither exists (different "
                      "scale); score_basis names it and its file"),
    ("group", "top / bottom where a study grouped the video (hits vs flops, moment pairs, outliers)"),
    ("source_files", "every file this row's fields came from; yt-dlp = ID or subs backfilled from YouTube metadata"),
]


def write_xlsx(rows, path, summary):
    try:
        from openpyxl import Workbook
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        sys.exit("openpyxl is needed for the .xlsx: run with python3 (it has openpyxl), or pass --csv")
    widths = {"rank": 7, "video_id": 14, "url": 16, "channel": 20, "subs": 11, "title": 50, "spoken_hook": 40,
              "onscreen_hook": 30, "about": 60, "about_source": 12, "views": 13, "likes": 11, "comments": 10,
              "published": 11, "duration_s": 10, "outlier_score": 12, "score_basis": 30, "group": 8,
              "niche_query": 22, "source_files": 45}
    wb = Workbook()
    ws = wb.active
    ws.title = "videos"
    ws.append(COLUMNS)
    for c in ws[1]:
        c.font = Font(bold=True)
    for row in rows:
        ws.append([None if row.get(k) in (None, "") else row[k] for k in COLUMNS])
        for c in ws[ws.max_row]:
            if isinstance(c.value, str):
                c.value = ILLEGAL_CHARACTERS_RE.sub("", c.value)
                c.data_type = "s"                 # a title starting with "=" stays text, not a formula
        url = ws.cell(ws.max_row, COLUMNS.index("url") + 1)
        if url.value:
            url.hyperlink = url.value
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    for i, k in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(k, 12)
    notes = wb.create_sheet("notes")
    notes.append(["column", "meaning"])
    for pair in NOTES:
        notes.append(list(pair))
    notes.append([])
    notes.append(["rows", summary["rows"]])
    notes.append(["with a video ID", summary["with_video_id"]])
    notes.append(["rows per file", "(a row can come from several files)"])
    for f, n in summary["rows_per_file"].items():
        notes.append([f, n])
    for title in ("about_source", "score_basis"):
        notes.append([title, ""])
        for k, n in summary[title].items():
            notes.append([f"  {k}", n])
    notes.append(["our videos skipped", sum(summary["own_rows_skipped"].values())])
    for c in notes[1]:
        c.font = Font(bold=True)
    notes.column_dimensions["A"].width, notes.column_dimensions["B"].width = 45, 110
    tmp = path.with_suffix(".tmp.xlsx")
    wb.save(tmp)
    tmp.replace(path)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-ytdlp", action="store_true", help="use cached yt-dlp data only")
    ap.add_argument("--refresh", action="store_true", help="re-fetch yt-dlp data even when cached")
    ap.add_argument("--playlist-end", type=int, default=600, help="Shorts listed per channel to find IDs")
    ap.add_argument("--csv", action="store_true", help="also write studied-videos.csv")
    args = ap.parse_args()

    extra = sorted(p.name for p in RES.glob("*.json") if p.name not in NOT_VIDEO_DATA
                   and not p.name.startswith("own-uploads") and f"research/{p.name}" not in PRIO)
    if extra:
        sys.exit(f"new per-video file(s) in research/ that this script doesn't read yet: {extra}")

    own_ids, own_chans, own_names = own_filter()
    chans = channel_names()
    store = Store()
    _, skipped, title_rows, name_subs, transcripts, premise, watched = collect(store, own_ids, own_chans,
                                                                              own_names, chans)

    # title-only rows: find the ID in data we hold (same channel + title), else in the channel's Shorts listing
    local = {}
    for key, r in store.rows.items():
        ch, t = store.get(r, "channel"), store.get(r, "title")
        if ch and t:
            local.setdefault((ckey(ch), tkey(t)), key)
    cache = json.loads(YTDLP_CACHE.read_text(encoding="utf-8")) if YTDLP_CACHE.exists() else {}
    need = defaultdict(list)
    for src, ch, t, f in title_rows:
        if (ckey(ch), tkey(t)) not in local:
            need[ch].append(t)
    via_ytdlp = {}
    for i, (ch, titles) in enumerate(sorted(need.items()), 1):
        if args.no_ytdlp and ch not in cache.get("channels", {}):
            continue
        fresh = args.refresh or ch not in cache.get("channels", {})
        info = resolve_channel(ch, titles, cache, args.refresh and not args.no_ytdlp, args.playlist_end)
        save_json(YTDLP_CACHE, cache)
        state = "unresolved" if info.get("unresolved") else f"{info['matched']}/{info['wanted']} titles found"
        if fresh:
            print(f"[yt-dlp] {i}/{len(need)} {ch}: {state}", file=sys.stderr)
        if not info.get("unresolved"):
            via_ytdlp[ckey(ch)] = info
            if info.get("subs"):
                name_subs.setdefault(ckey(ch), info["subs"])
    unresolved_titles = 0
    for src, ch, t, f in title_rows:
        key = local.get((ckey(ch), tkey(t)))
        info = via_ytdlp.get(ckey(ch))
        if key is None and info and tkey(t) in info["ids"]:
            key = info["ids"][tkey(t)]
            if key in own_ids:
                skipped[src] += 1
                continue
            store.add(key, "yt-dlp", channel_id=info.get("channel_id"), subs=info.get("subs"))
        if key is None:
            key = f"title:{ckey(ch)}|{tkey(t)}"
            unresolved_titles += 1
        store.add(key, src, channel=ch, title=t, **f)
        local.setdefault((ckey(ch), tkey(t)), key)

    # subs: channel lists we hold, then the channel page via yt-dlp
    for r in store.rows.values():
        if store.get(r, "subs") is None and name_subs.get(ckey(store.get(r, "channel"))):
            r["fields"]["subs"] = (PRIO["yt-dlp"], name_subs[ckey(store.get(r, "channel"))])
    missing = Counter(store.get(r, "channel_id") for r in store.rows.values()
                      if store.get(r, "subs") is None and store.get(r, "channel_id"))
    for cid in sorted(missing):
        if args.no_ytdlp and cid not in cache.get("subs", {}):
            continue
        s = channel_subs(cid, cache, args.refresh and not args.no_ytdlp)
        save_json(YTDLP_CACHE, cache)
        if s.get("subs") is not None:
            for key, r in store.rows.items():
                if store.get(r, "channel_id") == cid and store.get(r, "subs") is None:
                    store.add(key, "yt-dlp", subs=s["subs"])

    for key, r in store.rows.items():
        if store.get(r, "subs") is None and not key.startswith("title:"):
            if args.no_ytdlp and key not in cache.get("videos", {}):
                continue
            v = video_subs(key, cache, args.refresh and not args.no_ytdlp)
            save_json(YTDLP_CACHE, cache)
            if v.get("subs") is not None:
                store.add(key, "yt-dlp", subs=v["subs"], channel_id=v.get("channel_id"))

    # about: written sentences from transcripts / first lines (cache), Gemini's premise from watching the video,
    # else the title (the blind title label's premise, or the title itself as a sentence)
    about_cache = json.loads(ABOUT_CACHE.read_text(encoding="utf-8")) if ABOUT_CACHE.exists() else {}
    todo, rows = [], []
    for key, r in store.rows.items():
        vid = None if key.startswith("title:") else key
        title, spoken = store.get(r, "title"), store.get(r, "spoken_hook")
        written = about_cache.get(vid) if vid else None
        if vid in transcripts and not (written and written.get("source") == "transcript"):
            todo.append({"id": vid, "source": "transcript", "title": title, "text": transcripts[vid][:6000]})
        elif vid and spoken and vid not in transcripts and vid not in watched and not written:
            todo.append({"id": vid, "source": "first_line", "title": title, "text": spoken})
        if written and written.get("source") == "transcript":
            about, about_src = written["about"], "transcript"
        elif vid in watched:
            about, about_src = watched[vid], "video"
        elif written and written.get("source") == "first_line":  # a line like "Uh" adds nothing: the title wrote it
            about = written["about"]
            about_src = "first_line" if len(re.findall(r"[A-Za-z']+", spoken or "")) >= 4 else "title_only"
        else:
            about = premise.get(vid) or title_sentence(title)
            about_src = "title_only" if about else ""
        scores = r["scores"]
        views, subs = store.get(r, "views"), store.get(r, "subs")
        if "x" in scores or "lift" in scores:
            k = "x" if "x" in scores else "lift"
            score, basis = scores[k][1], f"{k} ({scores[k][2].split('/')[-1]})"
        elif views is not None and subs:
            score, basis = round(views / subs, 4), "views/subs"
        else:
            score, basis = None, ""
        rows.append({"video_id": vid or "", "url": f"https://www.youtube.com/watch?v={vid}" if vid else "",
                     "channel": store.get(r, "channel"), "subs": subs, "title": title, "spoken_hook": spoken,
                     "onscreen_hook": store.get(r, "onscreen_hook"), "about": about, "about_source": about_src,
                     "views": views, "likes": store.get(r, "likes"), "comments": store.get(r, "comments"),
                     "published": store.get(r, "published"), "duration_s": store.get(r, "duration_s"),
                     "outlier_score": score, "score_basis": basis, "group": store.get(r, "group"),
                     "niche_query": "; ".join(r["niche"]),
                     "source_files": "; ".join(sorted(r["files"], key=lambda f: (PRIO.get(f, 99), f)))})
    rows.sort(key=lambda x: (x["outlier_score"] is None, -(x["outlier_score"] or 0), -(x["views"] or 0)))
    for i, row in enumerate(rows, 1):
        row["rank"] = i

    assert len({r["video_id"] for r in rows if r["video_id"]}) == sum(1 for r in rows if r["video_id"])
    assert not {r["video_id"] for r in rows} & own_ids
    CACHE.mkdir(parents=True, exist_ok=True)
    with ABOUT_TODO.open("w", encoding="utf-8") as fh:
        for t in todo:
            fh.write(json.dumps(t, ensure_ascii=False) + "\n")

    per_file = Counter(f for r in rows for f in r["source_files"].split("; ") if f)
    summary = {
        "xlsx": str(OUT.relative_to(ROOT)), "rows": len(rows), "with_video_id": sum(1 for r in rows if r["video_id"]),
        "title_rows_without_id": unresolved_titles,
        "rows_per_file": dict(sorted(per_file.items(), key=lambda kv: PRIO.get(kv[0], 99))),
        "own_rows_skipped": dict(skipped),
        "spoken_hook": sum(1 for r in rows if r["spoken_hook"]), "onscreen_hook": sum(1 for r in rows if r["onscreen_hook"]),
        "about_source": dict(Counter(r["about_source"] or "(none)" for r in rows)),
        "score_basis": dict(Counter(r["score_basis"].split(" ")[0] or "(none)" for r in rows)),
        "missing": {k: sum(1 for r in rows if r[k] in (None, "")) for k in ("subs", "views", "published", "duration_s")},
        "about_todo": len(todo),
    }
    write_xlsx(rows, OUT, summary)
    if args.csv:
        with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow({k: "" if row.get(k) is None else row[k] for k in COLUMNS})
        summary["csv"] = str(OUT_CSV.relative_to(ROOT))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
