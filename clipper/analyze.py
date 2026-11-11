import json
import subprocess

import numpy as np

from . import candidates as cand
from . import hooks, playbook, signals, transcribe
from . import config


def fmt(t):
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def contact_sheet(src, start, end, out):
    dur = max(1.0, end - start)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}",
                    "-i", str(src), "-vf", f"fps=6/{dur:.2f},scale=480:-2,tile=3x2",
                    "-frames:v", "1", "-q:v", "4", str(out)], check=True)


def grid_frame(job, seconds):
    """Full frame at `seconds` with a labelled 10% grid, for reading facecam coordinates."""
    from PIL import Image, ImageDraw, ImageFont
    out = job / "review" / f"frame_{int(seconds)}.jpg"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{seconds:.2f}", "-i", str(job / "source.mp4"),
                    "-frames:v", "1", "-vf", "scale=1280:-2", str(out)], check=True)
    img = Image.open(out).convert("RGB")
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(str(config.ROOT / "assets" / "fonts" / "TikTokSans.ttf"), 18)
    for k in range(1, 10):
        x, y = img.width * k // 10, img.height * k // 10
        d.line((x, 0, x, img.height), fill=(255, 0, 0), width=1)
        d.line((0, y, img.width, y), fill=(255, 0, 0), width=1)
        d.text((x + 3, 3), f".{k}", font=f, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0))
        d.text((3, y + 3), f".{k}", font=f, fill=(255, 255, 0), stroke_width=2, stroke_fill=(0, 0, 0))
    img.save(out, quality=88)
    return out


def analyze(job, cfg, fast=False, force=False):
    meta = json.loads((job / "job.json").read_text(encoding="utf-8"))
    info = json.loads((job / "source.info.json").read_text(encoding="utf-8"))
    src, wav = job / "source.mp4", job / "audio.wav"
    if force or not wav.exists():
        transcribe.extract_audio(src, wav)

    tpath = job / "transcript.json"
    if force or not tpath.exists():
        print(f"[analyze] transcribing locally ({cfg.get('asr', 'parakeet')}) ...", flush=True)
        words, events, model = transcribe.transcribe(wav, job / "whisper", cfg, fast)
        tpath.write_text(json.dumps({"model": model, "words": words, "events": events}), encoding="utf-8")
    t = json.loads(tpath.read_text(encoding="utf-8"))
    words, events = transcribe.drop_repeats(t["words"]), t["events"]
    sentences = transcribe.group_sentences(words)

    print("[analyze] measuring loudness ...", flush=True)
    lufs = signals.loudness_per_second(wav)
    n = len(lufs)
    duration = float(n)
    loud = signals.norm_spikes(lufs)
    heat = signals.heatmap_per_second(info, n)
    kw, kw_hits = signals.keywords_per_second(words, events, set(cfg.get("hype_words", [])), n)
    rate = signals.speech_rate_per_second(words, n)
    jump, jump_raw = signals.jump_per_second(lufs)
    w = dict(cfg.get("weights", {}))
    if not heat.any():  # no "Most replayed" data: share its weight with the other signals
        extra = w.pop("heatmap", 0)
        rest = sum(w.values()) or 1
        w = {k: v + extra * v / rest for k, v in w.items()}
    score = (w.get("loudness", 0) * loud + w.get("jump", 0) * jump + w.get("heatmap", 0) * heat
             + w.get("keywords", 0) * kw + w.get("speech_rate", 0) * rate)

    hype_total = sum(len(h) for h in kw_hits)
    profile, spread = cand.clip_profile(lufs, events, meta.get("title", ""), hype_total / max(1.0, duration / 60))
    lengths = dict(cand.PROFILES[profile])
    for key, cfg_key in (("target", "target_seconds"), ("min", "min_seconds"), ("max", "max_seconds")):
        if isinstance(cfg.get(cfg_key), (int, float)):
            lengths[key] = cfg[cfg_key]
    count = cfg.get("max_candidates", "auto")
    count = cand.auto_candidate_count(duration) if count == "auto" else int(count)
    picks = cand.pick_windows(score, sentences, duration, lengths["target"], lengths["min"], lengths["max"], count)
    review = job / "review"
    review.mkdir(exist_ok=True)
    out = []
    for i, c in enumerate(picks, 1):
        s, e = c["start"], c["end"]
        sents = [x for x in sentences if x["e"] > s and x["s"] < e]
        hits = sorted({h for sec in range(int(s), min(int(e) + 1, n)) for h in kw_hits[sec]})
        ev_hits = [h for h in hits if h.startswith("(")]
        jump_lu = float(jump_raw[int(s):int(e) + 1].max())
        heat_max = float(heat[int(s):int(e) + 1].max()) if heat.any() else 0.0
        worth = cand.tier(c["score"], jump_lu, len(hits) - len(ev_hits), len(ev_hits), heat_max)

        def energy(x):
            a, b = int(x["s"]), max(int(x["s"]) + 1, int(x["e"]) + 1)
            return float(score[a:b].max()) if a < n else 0.0

        hook = " ".join(max(sents, key=energy)["text"].split()[:12]) if sents else ""
        sheet = review / f"cand_{i:02d}.jpg"
        contact_sheet(src, s, e, sheet)
        abs_s = s + meta.get("offset", 0)
        out.append({
            "id": i, "start": s, "end": e, "duration": round(e - s, 1), "score": c["score"], "tier": worth,
            "peak": c["peak"], "timestamp": f"{fmt(abs_s)}-{fmt(e + meta.get('offset', 0))}",
            "link": config.timestamp_link(meta['url'], abs_s),
            "signals": {
                "peak_lufs": round(max(lufs[int(s):int(e) + 1]), 1),
                "typical_lufs": round(float(np.median(lufs)), 1),
                "jump_lu": round(jump_lu, 1),
                "most_replayed": round(float(heat[int(s):int(e) + 1].max()), 2) if heat.any() else None,
                "hype_hits": hits,
            },
            "hook": hook[:120],
            "first_line": sents[0]["text"][:120] if sents else "",
            "opens_with": hooks.opening_type(sents[0]["text"]) if sents else "no speech",
            "transcript": " ".join(x["text"] for x in sents),
            "contact_sheet": str(sheet.relative_to(job)),
        })
    scenarios = []
    for i, c in enumerate(cand.scenario_windows(sentences, duration, [(o["start"], o["end"]) for o in out]), 1):
        s, e = c["start"], c["end"]
        sents = [x for x in sentences if x["e"] > s and x["s"] < e]
        sheet = review / f"scen_{i:02d}.jpg"
        contact_sheet(src, s, e, sheet)
        abs_s = s + meta.get("offset", 0)
        scenarios.append({"id": f"S{i}", "start": s, "end": e, "duration": round(e - s, 1), "cue": c["cue"],
                          "timestamp": f"{fmt(abs_s)}-{fmt(e + meta.get('offset', 0))}",
                          "link": config.timestamp_link(meta['url'], abs_s),
                          "transcript": " ".join(x["text"] for x in sents),
                          "contact_sheet": str(sheet.relative_to(job))})
    recommended = cand.recommend([c["tier"] for c in out], duration)
    loud_events = any(h.startswith("(") for sec in kw_hits for h in sec)
    clip_type = playbook.guess_type(meta.get("title", ""), profile, len(words) / max(1.0, duration / 60), loud_events)
    result = {"video": meta, "weights": {k: round(v, 3) for k, v in w.items()}, "has_heatmap": bool(heat.any()),
              "profile": profile, "loudness_spread_lu": spread, "clip_length": lengths,
              "recommended": recommended, "clip_type": clip_type, "hook_plan": playbook.plan_text(clip_type, playbook.for_profile(cfg)),
              "candidates": out, "scenarios": scenarios}
    (job / "candidates.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (job / "candidates.md").write_text(to_markdown(result), encoding="utf-8")
    return result


def to_markdown(r):
    v = r["video"]
    lines = [f"# Clip candidates: {v['title']}", "",
             f"{v['channel']} · {v['url']} · most-replayed data: {'yes' if r['has_heatmap'] else 'no'}", "",
             f"**Worth exporting: {r['recommended']} video(s)** · content: {r['profile']} "
             f"(loudness spread {r['loudness_spread_lu']} LU) · clip length {r['clip_length']['min']}–"
             f"{r['clip_length']['max']}s, aim {r['clip_length']['target']}s", "",
             f"**Suggested clip type → hook plan:** {r.get('hook_plan', '')}",
             "(Confirm the type per clip from the contact sheet and transcript. A reaction stream can still contain a "
             "comedy bit; set `clip_type` in picks.json.)", "",
             "| # | Tier | Timestamp | Len | Score | Volume jump | Peak / typical loudness | Hype signals |",
             "|---|---|---|---|---|---|---|---|"]
    for c in r["candidates"]:
        s = c["signals"]
        lines.append(f"| {c['id']} | {c['tier']} | [{c['timestamp']}]({c['link']}) | {c['duration']:.0f}s | {c['score']} "
                     f"| +{s['jump_lu']} LU | {s['peak_lufs']} / {s['typical_lufs']} LUFS "
                     f"| {', '.join(s['hype_hits'][:6]) or '-'} |")
    for c in r["candidates"]:
        lines += ["", f"## #{c['id']} · {c['tier']} · {c['timestamp']} · score {c['score']}",
                  f"Contact sheet: `{c['contact_sheet']}`", "",
                  f"**Opens with:** {c.get('opens_with', '?')}: \"{c.get('first_line', '')}\"", "",
                  f"**Suggested hook:** {c['hook']}", "",
                  f"> {c['transcript'][:900]}"]
    if r.get("scenarios"):
        lines += ["", "## Scenario candidates (quiet premise → payoff; not loudness-ranked)",
                  "Each opens on a cue that something new is being made, found, tried or shown. Take one only if it "
                  "opens a curiosity gap (\"he made a new WHAT?\"), builds, and pays off with a reveal or a face; "
                  "`clip_type: scenario`."]
        for c in r["scenarios"]:
            lines += ["", f"### {c['id']} · {c['timestamp']} · {c['duration']:.0f}s · cue \"{c['cue']}\"",
                      f"Contact sheet: `{c['contact_sheet']}`", "", f"> {c['transcript'][:900]}"]
    return "\n".join(lines) + "\n"
