from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
# Fonts the top GTA Shorts use (research/viral-gta-shorts.md#fonts): name -> (file, variable-font instance)
FONTS = {
    "montserrat-black": ("Montserrat.ttf", "Black"),       # MrBossFTW hooks (51M views)
    "bebas": ("BebasNeue-Regular.ttf", None),              # Kai Cenat Live word captions (6.8M)
    "tiktok-bold": ("TikTokSans.ttf", "Bold"),             # RDCworld1 meme box (5M)
    "tiktok-semibold": ("TikTokSans.ttf", "SemiBold"),     # DarkViperAU labels / captions
    "luckiest": ("LuckiestGuy-Regular.ttf", None),         # Typical Gamer comic captions
}
SYSTEM_FALLBACK = ["/System/Library/Fonts/Supplemental/Arial Black.ttf",
                   "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                   "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]

CAPTION_STYLES = {
    "bold": {"font": "montserrat-black", "size": 84, "stroke": 8, "box": False},
    "boxed": {"font": "bebas", "size": 116, "stroke": 0, "box": True},
    "comic": {"font": "luckiest", "size": 96, "stroke": 11, "box": False},
}
# Each extra speaker gets its own colour and a different font so crosstalk is easy to follow.
SPEAKER_COLOURS = [((255, 255, 255), (255, 225, 60)), ((110, 215, 255), (255, 255, 255)),
                   ((255, 140, 205), (255, 255, 255)), ((150, 255, 140), (255, 255, 255))]
SPEAKER_FONTS = ["bebas", "luckiest", "tiktok-bold", "montserrat-black"]
FONT_SIZES = {"montserrat-black": 84, "bebas": 116, "luckiest": 96, "tiktok-bold": 90, "tiktok-semibold": 90}

HOOK_STYLES = {
    "bold": {"font": "montserrat-black", "size": 88, "upper": True, "fill": (255, 255, 255),
             "keyword": (255, 225, 60), "stroke": 3, "shadow": True, "box": False},
    "box": {"font": "tiktok-bold", "size": 66, "upper": False, "fill": (15, 15, 15),
            "keyword": (30, 120, 255), "stroke": 0, "shadow": False, "box": True},
    "label": {"font": "tiktok-semibold", "size": 70, "upper": False, "fill": (255, 255, 255),
              "keyword": (200, 90, 255), "stroke": 5, "shadow": False, "box": False},
}
# Vertical positions: "fit" = 16:9 game centred; "split" = facecam top 768px, game below.
# In split the hook sits on the seam so it never covers the streamer's face.
LAYOUTS = {"fit": {"hook_y": 400, "caption_y": 1420}, "split": {"hook_y": 768, "caption_y": 1380}}
_fonts = {}


def font(name, size):
    if (name, size) not in _fonts:
        file, instance = FONTS.get(name, FONTS["montserrat-black"])
        path = FONT_DIR / file
        if path.exists():
            f = ImageFont.truetype(str(path), size)
            if instance:
                f.set_variation_by_name(instance)
        else:
            f = next((ImageFont.truetype(p, size) for p in SYSTEM_FALLBACK if Path(p).exists()),
                     ImageFont.load_default(size))
        _fonts[(name, size)] = f
    return _fonts[(name, size)]


def chunk_words(words, max_words=3, max_gap=0.45):
    chunks, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if (len(cur) >= max_words or nxt is None or nxt["s"] - w["e"] > max_gap
                or w["w"].endswith((".", ",", "?", "!")) or w.get("label") or nxt.get("label")):
            chunks.append(cur)
            cur = []
    return chunks


def timeline(words, clip_start, clip_end, linger=0.5):
    """(t0, t1, chunk, active_index, chunk_words) per word, relative to the clip start."""
    inside = [w for w in words if w["s"] >= clip_start and w["e"] <= clip_end + 0.3]
    chunks = chunk_words(inside)
    dur = clip_end - clip_start
    out = []
    for ci, ch in enumerate(chunks):
        nxt_start = chunks[ci + 1][0]["s"] if ci + 1 < len(chunks) else None
        ch_end = min(ch[-1]["e"] + linger, nxt_start) if nxt_start else ch[-1]["e"] + linger
        for wi, w in enumerate(ch):
            t0 = w["s"] - clip_start
            t1 = (ch[wi + 1]["s"] if wi + 1 < len(ch) else ch_end) - clip_start
            t0, t1 = max(0.0, t0), min(dur, t1)
            if t1 - t0 >= 0.04:
                out.append((round(t0, 3), round(t1, 3), ci, wi, [x["w"] for x in ch]))
    return out


def caption_states(words, clip_start, clip_end):
    """[(t0, t1, ((speaker, words, active), ...))]: what's on screen when; overlapping speakers stack."""
    by_spk = {}
    for w in words:
        by_spk.setdefault(w.get("spk", 0), []).append(w)
    tls = {spk: timeline(ws, clip_start, clip_end) for spk, ws in by_spk.items()}
    dur = round(clip_end - clip_start, 3)
    cuts = sorted({0.0, dur} | {t for tl in tls.values() for e in tl for t in e[:2]})
    out = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 0.02:
            continue
        mid = (a + b) / 2
        state = tuple((spk, tuple(e[4]), e[3]) for spk, tl in sorted(tls.items())
                      for e in tl if e[0] <= mid < e[1])
        if out and out[-1][2] == state:
            out[-1] = (out[-1][0], b, state)
        else:
            out.append((a, b, state))
    return out


def _wrap(words, f, max_w):
    lines, cur = [], []
    for i, w in enumerate(words):
        test = " ".join(x for _, x in cur + [(i, w)])
        if cur and f.getlength(test) > max_w:
            lines.append(cur)
            cur = []
        cur.append((i, w))
    if cur:
        lines.append(cur)
    return lines


def speaker_look(spk, style, multi):
    """(font name, size, base colour, active colour) for a speaker."""
    st = CAPTION_STYLES.get(style, CAPTION_STYLES["bold"])
    base, active = SPEAKER_COLOURS[spk % len(SPEAKER_COLOURS)] if multi else SPEAKER_COLOURS[0]
    if not multi or spk == 0:
        return st["font"], st["size"], base, active
    others = [f for f in SPEAKER_FONTS if f != st["font"]]
    name = others[(spk - 1) % len(others)]
    return name, FONT_SIZES[name], base, active


def render_state(state, path, caption_y, multi, style="bold"):
    st = CAPTION_STYLES.get(style, CAPTION_STYLES["bold"])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    top = None
    for k, (spk, words, active) in enumerate(state):
        name, size, base, act = speaker_look(spk, style, multi)
        f = font(name, size)
        words = [w.upper().strip(",.") or w for w in words]
        lines = _wrap(words, f, 960)
        lh = int(size * 1.18)
        block = lh * len(lines)
        y = caption_y - block // 2 if k == 0 else top - 28 - block
        top = y
        space = f.getlength(" ")
        for line in lines:
            line_w = f.getlength(" ".join(w for _, w in line))
            x = (W - line_w) / 2
            if st["box"]:
                asc, desc = f.getmetrics()
                d.rectangle((x - 18, y - 6, x + line_w + 18, y + asc + desc - 4), fill=(0, 0, 0, 235))
            for i, w in line:
                kw = {"stroke_width": st["stroke"], "stroke_fill": (0, 0, 0)} if st["stroke"] else {}
                d.text((x, y), w, font=f, fill=act if i == active else base, **kw)
                x += f.getlength(w) + space
            y += lh
    img.save(path)


def parse_markup(text):
    """'I Can Play *GTA 6 NOW*' -> [(word, highlighted)]."""
    out, on = [], False
    for tok in text.split():
        body = tok.rstrip("?!.,;:…")  # "*THIS*?": the marker closes before trailing punctuation
        if body.startswith("*"):
            on = True
        clean = body.strip("*") + tok[len(body):]
        if clean:
            out.append((clean, on))
        if body.endswith("*") and (len(body) > 1 or not body.startswith("*")):
            on = False
    return out


def render_hook(text, path, style="box", layout="fit"):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    st = HOOK_STYLES.get(style)
    if st is None or not text.strip():
        img.save(path)
        return
    tokens = parse_markup(text)
    f = font(st["font"], st["size"])
    words = [w.upper() if st["upper"] else w for w, _ in tokens]
    lines = _wrap(words, f, 900)[:3]
    lh = int(st["size"] * 1.2)
    centre = LAYOUTS.get(layout, LAYOUTS["fit"])["hook_y"]
    box_h = lh * len(lines) + 50
    top = centre - box_h // 2
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    if st["box"]:
        d.rounded_rectangle((50, top, W - 50, top + box_h), radius=30, fill=(255, 255, 255, 248))
    y = top + 25
    space = f.getlength(" ")
    for line in lines:
        x = (W - f.getlength(" ".join(w for _, w in line))) / 2
        for i, w in line:
            colour = st["keyword"] if tokens[i][1] else st["fill"]
            kw = {"stroke_width": st["stroke"], "stroke_fill": (0, 0, 0)} if st["stroke"] else {}
            d.text((x, y), w, font=f, fill=colour, **kw)
            if st["shadow"]:
                sd.text((x + 5, y + 7), w, font=f, fill=(0, 0, 0, 200))
            x += f.getlength(w) + space
        y += lh
    if st["shadow"]:
        img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(5)))
    Image.alpha_composite(img, layer).save(path)


def write_overlay(words, clip_start, clip_end, out_dir, layout="fit", style="bold"):
    """Render caption PNGs and an FFmpeg concat list that shows each for as long as it's on screen."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    caption_y = LAYOUTS.get(layout, LAYOUTS["fit"])["caption_y"]
    multi = len({w.get("spk", 0) for w in words if clip_start <= w["s"] <= clip_end}) > 1
    cache, entries = {}, []
    for a, b, state in caption_states(words, clip_start, clip_end):
        if state not in cache:
            png = out_dir / f"cap_{len(cache):04d}.png"
            render_state(state, png, caption_y, multi, style)
            cache[state] = png
        entries.append((cache[state], b - a))
    lines = ["ffconcat version 1.0"]
    for png, dur in entries:
        lines += [f"file '{png.name}'", f"duration {dur:.3f}"]
    lines.append(f"file '{entries[-1][0].name}'")
    lst = out_dir / "captions.txt"
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lst
