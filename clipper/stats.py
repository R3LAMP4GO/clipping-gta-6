"""Our own uploads' results, joined to what the clipper knew when it rendered them (upload.json), so picking rules are
judged on our channel instead of a manual study. Read-only: YouTube Data + Analytics with the OAuth refresh token in
.env (YOUTUBE_OAUTH_CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN)."""
import http.client
import json
import os
import re
import statistics as st
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

from .config import ROOT

EXPORTS = ROOT / "exports"
STATS = ROOT / "research" / "own-stats.json"
API = "https://www.googleapis.com/youtube/v3"
ANALYTICS = "https://youtubeanalytics.googleapis.com/v2/reports"
SETTLE_HOURS = 48  # YouTube's first test audience is still being served before this
NEIGHBOURS = 15    # each side, like the 3,481-Short study: lift = views / median of the uploads around it


def access_token():
    keys = ("YOUTUBE_OAUTH_CLIENT_ID", "YOUTUBE_OAUTH_CLIENT_SECRET", "YOUTUBE_OAUTH_REFRESH_TOKEN")
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"[stats] missing {', '.join(missing)} in .env (the read-only YouTube OAuth token)")
    data = urllib.parse.urlencode({"client_id": os.environ[keys[0]], "client_secret": os.environ[keys[1]],
                                   "refresh_token": os.environ[keys[2]], "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data, timeout=30) as r:
        return json.load(r)["access_token"]


TRANSIENT = (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError)


def get(url, token, tries=3, wait=2.0, **params):
    """GET with retries: one dropped connection out of ~80 calls used to end the whole run."""
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"Authorization": f"Bearer {token}"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429 or attempt == tries - 1:
                raise
        except TRANSIENT:
            if attempt == tries - 1:
                raise
        time.sleep(wait * (attempt + 1))


def seconds(iso):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else None


def fetch_uploads(token):
    ch = get(f"{API}/channels", token, part="contentDetails,snippet", mine="true")["items"][0]
    playlist, ids, page = ch["contentDetails"]["relatedPlaylists"]["uploads"], [], None
    while True:
        r = get(f"{API}/playlistItems", token, part="contentDetails", playlistId=playlist, maxResults=50,
                **({"pageToken": page} if page else {}))
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        page = r.get("nextPageToken")
        if not page:
            break
    rows = []
    for i in range(0, len(ids), 50):
        for v in get(f"{API}/videos", token, part="snippet,statistics,contentDetails,status", id=",".join(ids[i:i + 50]))["items"]:
            if v["status"]["privacyStatus"] != "public":
                continue
            rows.append({"id": v["id"], "t": v["snippet"]["title"], "published": v["snippet"]["publishedAt"],
                         "duration": seconds(v["contentDetails"]["duration"]),
                         "views": int(v["statistics"].get("viewCount", 0))})
    return ch["snippet"]["title"], rows


def fetch_analytics(token, rows, start="2020-01-01"):
    """Engaged-view share, average % viewed and shares per video, plus the watch ratio at the halfway point."""
    end = date.today().isoformat()
    r = get(ANALYTICS, token, ids="channel==MINE", startDate=start, endDate=end, dimensions="video", maxResults=200,
            metrics="views,engagedViews,averageViewPercentage,shares,subscribersGained", sort="-views")
    cols = [c["name"] for c in r["columnHeaders"]]
    by = {d["video"]: d for d in (dict(zip(cols, x)) for x in r.get("rows") or [])}
    for row in rows:
        d = by.get(row["id"])
        if d and d["views"]:
            row.update(engaged=round(d["engagedViews"] / d["views"], 3), avg_pct=round(d["averageViewPercentage"], 1),
                       shares=d["shares"], subs=d["subscribersGained"])
        if d:
            try:
                curve = get(ANALYTICS, token, ids="channel==MINE", startDate=start, endDate=end,
                            metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                            filters=f"video=={row['id']}").get("rows") or []
            except TRANSIENT:  # one video's curve is optional; its views and engaged share are already in
                curve = []
            if curve:
                row["ret50"] = round(min(curve, key=lambda p: abs(p[0] - 0.5))[1], 3)
    return rows


def norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def local_manifests(root=EXPORTS):
    """{video id or normalized title: upload.json / long.json entry + its profile} for every rendered MP4. A poster
    that writes `youtube_id` into the manifest makes the match exact; otherwise the posted title must still equal ours."""
    out = {}
    files = sorted(root.glob("*/*/*/upload.json")) + sorted(root.glob("*/*/*/long.json"))
    for f in files:
        profile = f.parent.parent.parent.name
        data = json.loads(f.read_text(encoding="utf-8"))
        for e in data if isinstance(data, list) else [data]:
            if f.name == "upload.json":
                e = {"kind": "short", **e}  # renders before 2026-11-23 didn't record it
            if e.get("youtube_id"):
                out.setdefault(e["youtube_id"], {**e, "profile": profile})
            if e.get("title"):
                out.setdefault(norm_title(e["title"]), {**e, "profile": profile})
    return out


def add_lift(rows):
    """Views over the median of the NEIGHBOURS uploads posted either side (publish order), so growth cancels out."""
    rows = sorted(rows, key=lambda r: r["published"])
    for i, r in enumerate(rows):
        nb = [x["views"] for x in rows[max(0, i - NEIGHBOURS):i + NEIGHBOURS + 1] if x is not r]
        r["lift"] = round(r["views"] / max(st.median(nb), 1), 3) if nb else None
    return rows


def join(rows, manifests, now=None):
    now = now or datetime.now(timezone.utc)
    for r in rows:
        m = manifests.get(r["id"]) or manifests.get(norm_title(r["t"]))
        r["settled"] = now - datetime.fromisoformat(r["published"].replace("Z", "+00:00")) >= timedelta(hours=SETTLE_HOURS)
        if m:
            r.update({k: m.get(k) for k in ("profile", "clip_type", "arm", "hook", "hook_type", "turn", "cold_premise",
                                            "loop", "predicted", "angle_arm", "hook_angle", "premise_type",
                                            "selection_score", "kind", "question", "category", "decision",
                                            "moment_score", "packaging_score", "profile_match", "principles",
                                            "experiment", "experiment_arm", "review", "verdict_on", "contrast_type")})
        from .hooks import loop_frame
        r["title_frame"] = loop_frame(r["t"])  # the posted title, matched or not: every upload counts here
    return rows


def _summary(group):
    def med(k):
        v = [r[k] for r in group if r.get(k) is not None]
        return round(st.median(v), 3) if v else None
    return {"n": len(group), "views": med("views"), "lift": med("lift"), "engaged": med("engaged"), "ret50": med("ret50")}


def report(rows):
    """Medians per what the clipper decided, over settled uploads only."""
    ok = [r for r in rows if r.get("settled")]
    groups = {"all settled": ok, "matched to an upload.json": [r for r in ok if r.get("profile")]}
    for key, name in (("profile", "profile"), ("kind", "shape"), ("question", "question type"), ("clip_type", "clip type"), ("arm", "hook arm"), ("hook_type", "hook type"),
                      ("title_frame", "title frame"), ("angle_arm", "hook angle (assigned)"),
                      ("hook_angle", "hook angle (posted)"), ("premise_type", "premise type"),
                      ("category", "category"), ("contrast_type", "contrast"), ("decision", "decision"),
                      ("principles", "principles mode")):
        for v in sorted({r.get(key) for r in ok if r.get(key)}):
            groups[f"{name}: {v}"] = [r for r in ok if r.get(key) == v]
    for r in ok:  # one experiment at a time: group by its arm
        if r.get("experiment") and r.get("experiment_arm"):
            groups.setdefault(f"experiment {r['experiment']}: {r['experiment_arm']}", []).append(r)
    for key, name, cuts in (("moment_score", "moment score", (60, 70, 80)), ("profile_match", "profile match",
                                                                            (0.34, 0.67))):
        scored = [r for r in ok if r.get(key) is not None]
        for lo, hi in zip((None,) + cuts, cuts + (None,)):
            band = [r for r in scored if (lo is None or r[key] >= lo) and (hi is None or r[key] < hi)]
            if band:
                groups[f"{name} {'<' + str(hi) if lo is None else str(lo) + '+' if hi is None else f'{lo}-{hi}'}"] = band
    with_turn = [r for r in ok if r.get("profile") and r.get("turn")]
    if with_turn:
        groups["turn named"] = with_turn
        groups["no turn named"] = [r for r in ok if r.get("profile") and not r.get("turn")]
    return {k: _summary(v) for k, v in groups.items() if v}


def own_uploads(rows):
    """Rows for simulate's `own` scope, per profile: {profile: [{niche, ch, t, views, lift}]}."""
    out = {}
    for r in rows:
        if r.get("settled") and r.get("profile") and r.get("lift") is not None and r.get("kind", "short") == "short":
            out.setdefault(r["profile"], []).append({"niche": "own", "ch": "own", "t": r["t"], "views": r["views"],
                                                     "lift": r["lift"]})
    return out


def format_report(channel, rep):
    lines = [f"# {channel}: settled uploads (>= {SETTLE_HOURS} h)", "",
             "| group | n | median views | lift | engaged share | watch ratio at 50% |", "|---|---|---|---|---|---|"]
    for k, s in rep.items():
        lines.append(f"| {k} | {s['n']} | {s['views']} | {s['lift']} | {s['engaged']} | {s['ret50']} |")
    return "\n".join(lines)


CALIBRATE_MIN = 60     # scored posts needed before rank correlations mean anything
TRACKING_RHO = 0.15    # |rho| below this: the score isn't tracking views


def calibrate(rows, weights=None, min_n=CALIBRATE_MIN):
    """Each review criterion's and total's rank correlation with views on settled scored uploads, and suggested
    weights (current weight x (1 + 2 rho), floored at a quarter). Read-only: weights live in watchlist.yaml."""
    from .hooks import REVIEW, review_weights
    from .viral import spearman
    w = weights or review_weights(None)
    scored = [r for r in rows if r.get("settled") and isinstance(r.get("review"), dict) and r.get("views") is not None]
    out = {"n": len(scored), "min_n": min_n, "criteria": {}, "totals": {}, "suggested": {}}
    views = [r["views"] for r in scored]
    for part, cs in REVIEW.items():
        for c in cs:
            xs = [((r["review"].get(part) or {}).get(c)) for r in scored]
            rho = spearman(xs, views)
            out["criteria"][f"{part}.{c}"] = round(rho, 3) if rho is not None else None
            if rho is not None and len(scored) >= min_n:
                out["suggested"].setdefault(part, {})[c] = round(max(0.25, w[part][c] * (1 + 2 * rho)), 2)
    for key in ("moment_score", "packaging_score", "profile_match"):
        rho = spearman([r.get(key) for r in scored], views)
        out["totals"][key] = round(rho, 3) if rho is not None else None
    return out


def format_calibration(c):
    lines = [f"# Calibration: {c['n']} settled scored uploads (needs {c['min_n']})"]
    if c["n"] < c["min_n"]:
        lines.append(f"too few scored posts: {c['n']} of {c['min_n']}; correlations below are not reliable")
    for k, rho in {**c["totals"], **c["criteria"]}.items():
        flag = " not tracking views" if rho is not None and abs(rho) < TRACKING_RHO else ""
        lines.append(f"- {k}: rho {rho}{flag}")
    if c["suggested"]:
        lines += ["", "Suggested review_weights (copy into watchlist.yaml by hand; nothing was written):"]
        for part, ws in c["suggested"].items():
            lines.append(f"  {part}: " + ", ".join(f"{k}: {v}" for k, v in ws.items()))
    return "\n".join(lines)


def run_calibrate(cfg=None):
    """Read research/own-stats.json (written by `clipper stats`) and print the calibration; never writes."""
    from .hooks import review_weights
    rows = json.loads(STATS.read_text(encoding="utf-8")).get("uploads", []) if STATS.exists() else []
    return format_calibration(calibrate(rows, review_weights(cfg)))


def run(save=True):
    token = access_token()
    channel, rows = fetch_uploads(token)
    rows = join(add_lift(fetch_analytics(token, rows)), local_manifests())
    rep = report(rows)
    if save:
        from .simulate import own_data
        STATS.write_text(json.dumps({"channel": channel, "fetched": date.today().isoformat(), "uploads": rows},
                                    indent=1, ensure_ascii=False), encoding="utf-8")
        for profile, own in own_uploads(rows).items():
            if len(own) >= 10:  # simulate needs >=10 Shorts with a feature before it trusts an effect anyway
                own_data(profile).write_text(json.dumps(own, indent=1, ensure_ascii=False), encoding="utf-8")
    return format_report(channel, rep)
