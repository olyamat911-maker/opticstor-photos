#!/usr/bin/env python3
"""Generate vertical TikTok videos (1080x1920, 30fps) from the OpticStor photos.

Usage:  python3 tiktok/make_videos.py            # all videos
        python3 tiktok/make_videos.py 2 4        # only videos #2 and #4
Requires: Pillow, numpy, ffmpeg in PATH.
"""
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tiktok", "videos")
W, H, FPS = 1080, 1920, 30
FONT_DIR = "/usr/share/fonts/opentype/inter"
F_BLACK = os.path.join(FONT_DIR, "InterDisplay-Black.otf")
F_BOLD = os.path.join(FONT_DIR, "InterDisplay-Bold.otf")
YELLOW = (255, 196, 0)

_cache = {}


def img(name, box=None):
    key = (name, box)
    if key not in _cache:
        im = Image.open(os.path.join(ROOT, name)).convert("RGB")
        if box:
            im = im.crop(box)
        _cache[key] = im
    return _cache[key]


def font(path, size):
    key = (path, size)
    if key not in _cache:
        _cache[key] = ImageFont.truetype(path, size)
    return _cache[key]


# ---------- easing ----------
def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = max(0.0, min(1.0, t))
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ---------- background / image layers ----------
def blurred_bg(src):
    key = ("bg", id(src))
    if key not in _cache:
        s = max(W / src.width, H / src.height)
        b = src.resize((int(src.width * s) + 1, int(src.height * s) + 1))
        b = b.crop(((b.width - W) // 2, (b.height - H) // 2, (b.width - W) // 2 + W, (b.height - H) // 2 + H))
        b = b.filter(ImageFilter.GaussianBlur(40))
        b = Image.blend(b, Image.new("RGB", (W, H), (0, 0, 0)), 0.45)
        _cache[key] = b
    return _cache[key].copy()


def render_photo(src, zoom=1.0, fill=False, dx=0.0, dy=0.0, cy=0.5):
    """Photo on blurred bg. fill=True covers the whole frame (crop), else fit width."""
    frame = blurred_bg(src)
    if fill:
        s = max(W / src.width, H / src.height) * zoom
    else:
        s = min(W / src.width, 1500 / src.height) * zoom
    nw, nh = int(src.width * s), int(src.height * s)
    p = src.resize((nw, nh), Image.BILINEAR)
    x = (W - nw) // 2 + int(dx)
    y = int(H * cy - nh / 2 + dy)
    if fill:
        x = min(0, max(W - nw, x))
        y = min(0, max(H - nh, y))
    frame.paste(p, (x, y))
    return frame


# ---------- text ----------
def caption(frame, text, y, size=72, style="box", t=1.0, color=(0, 0, 0), bg=(255, 255, 255), fnt=F_BLACK):
    """TikTok-style caption. style: box (white pill), outline (white text, black stroke), yellow."""
    if t <= 0:
        return frame
    f = font(fnt, size)
    lines = text.split("\n")
    d0 = ImageDraw.Draw(frame)
    sizes = [d0.textbbox((0, 0), ln, font=f) for ln in lines]
    lh = int(size * 1.22)
    pad_x, pad_y = int(size * 0.38), int(size * 0.2)
    layer = Image.new("RGBA", (W, lh * len(lines) + pad_y * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, (ln, bb) in enumerate(zip(lines, sizes)):
        tw = bb[2] - bb[0]
        x = (W - tw) // 2
        yy = pad_y + i * lh
        if style == "box" or style == "yellow":
            fill_bg = YELLOW if style == "yellow" else bg
            d.rounded_rectangle((x - pad_x, yy - pad_y // 2, x + tw + pad_x, yy + lh - pad_y // 2 + 4),
                                radius=int(size * 0.28), fill=fill_bg + (255,))
            d.text((x - bb[0], yy + (lh - size) // 2 - bb[1] // 2), ln, font=f, fill=color + (255,))
        else:
            d.text((x - bb[0], yy + (lh - size) // 2 - bb[1] // 2), ln, font=f, fill=(255, 255, 255, 255),
                   stroke_width=max(4, size // 12), stroke_fill=(0, 0, 0, 255))
    # pop-in animation
    sc = 0.6 + 0.4 * ease_back(t)
    if sc != 1.0:
        layer = layer.resize((max(1, int(layer.width * sc)), max(1, int(layer.height * sc))), Image.BILINEAR)
    alpha = min(1.0, t * 3)
    if alpha < 1:
        a = layer.split()[3].point(lambda v: int(v * alpha))
        layer.putalpha(a)
    frame.paste(layer, ((W - layer.width) // 2, int(y - layer.height / 2)), layer)
    return frame


def progress_bar(frame, frac):
    d = ImageDraw.Draw(frame)
    d.rectangle((0, 0, int(W * frac), 10), fill=YELLOW)
    return frame


def flash(frame, k):
    if k <= 0:
        return frame
    return Image.blend(frame, Image.new("RGB", (W, H), (255, 255, 255)), min(1.0, k))


def logo_end(t, line1="opticstor.com.ua", line2="+380 (68) 128-13-19"):
    lg = img("logo/opticstor-logo-card-tall.jpg")
    frame = Image.new("RGB", (W, H), (0, 0, 0))
    s = 1000 / lg.width * (0.9 + 0.1 * ease_out(t * 2))
    p = lg.resize((int(lg.width * s), int(lg.height * s)), Image.BILINEAR)
    frame.paste(p, ((W - p.width) // 2, 330 + (1125 - p.height) // 2))
    caption(frame, "Пиши нам у Direct", 230, 70, "yellow", ease_out(t * 3))
    caption(frame, line1, 1560, 58, "outline", ease_out(t * 3 - 0.3), fnt=F_BOLD)
    caption(frame, line2, 1650, 50, "outline", ease_out(t * 3 - 0.5), fnt=F_BOLD)
    return frame


# ---------- writer ----------
def write(name, frame_fn, seconds):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    n = int(seconds * FPS)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
           "-shortest", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        fr = frame_fn(i / FPS, i / n)
        pr.stdin.write(fr.convert("RGB").tobytes())
    pr.stdin.close()
    pr.wait()
    print("wrote", path, f"{seconds:.1f}s")


def scenes_video(name, scenes, end_sec=2.5, bar=True):
    """scenes: list of dicts {src, dur, caps:[(text,y,size,style,start)], fill, zoom:(a,b), pan:(dx,dy), shake}"""
    starts, acc = [], 0.0
    for s in scenes:
        starts.append(acc)
        acc += s["dur"]
    total = acc + end_sec

    def fn(t, frac):
        if t >= acc:
            return logo_end((t - acc) / end_sec)
        i = max(k for k, st in enumerate(starts) if st <= t)
        s = scenes[i]
        lt = t - starts[i]
        u = lt / s["dur"]
        z0, z1 = s.get("zoom", (1.0, 1.08))
        z = z0 + (z1 - z0) * ease_out(u) if s.get("ease", True) else z0 + (z1 - z0) * u
        # punch-in on cut
        if lt < 0.12 and i > 0:
            z *= 1 + 0.08 * (1 - lt / 0.12)
        px, py = s.get("pan", (0, 0))
        dx, dy = px * u, py * u
        if s.get("shake") and lt < 0.25:
            dx += math.sin(lt * 90) * 14 * (1 - lt / 0.25)
        frame = render_photo(s["src"], z, s.get("fill", False), dx, dy, s.get("cy", 0.5))
        for c in s.get("caps", []):
            text, y, size, style, st = c[:5]
            caption(frame, text, y, size, style, (lt - st) / 0.35)
        if lt < 0.08 and i > 0 and s.get("flash", True):
            frame = flash(frame, 0.7 * (1 - lt / 0.08))
        if bar:
            progress_bar(frame, t / acc)
        return frame

    write(name, fn, total)


# =====================================================================
# 1) "3-в-1" магнітні накладки — день / сонце / ніч (hook + reveal)
# =====================================================================
def v1():
    q = lambda c, r: img("0947.jpg", (c * 800, r * 800, c * 800 + 800, r * 800 + 800))
    scenes = [
        dict(src=q(0, 0), dur=2.2, zoom=(1.25, 1.35), caps=[
            ("1 оправа =\n3 пари окулярів?", 360, 88, "box", 0.0),
            ("Дивись до кінця", 1420, 56, "yellow", 0.8)]),
        dict(src=img("0947.jpg", (0, 270, 800, 540)), dur=1.6, zoom=(1.0, 1.06), caps=[
            ("для зору — щодня", 420, 76, "box", 0.05)]),
        dict(src=img("0947.jpg", (0, 0, 800, 270)), dur=1.6, zoom=(1.0, 1.06), caps=[
            ("+ поляризаційна\nсонцезахисна накладка", 420, 70, "box", 0.05)]),
        dict(src=img("0947.jpg", (0, 530, 800, 800)), dur=1.6, zoom=(1.0, 1.06), caps=[
            ("+ жовта нічна\nдля водіїв", 420, 76, "yellow", 0.05)]),
        dict(src=q(1, 0), dur=1.4, fill=True, zoom=(1.0, 1.08), shake=True, caps=[
            ("На магнітах", 380, 84, "box", 0.05),
            ("клац — і готово", 520, 64, "outline", 0.4)]),
        dict(src=q(0, 1), dur=1.3, fill=True, zoom=(1.0, 1.1), caps=[
            ("Одягаєш за 1 секунду", 380, 72, "box", 0.05)]),
        dict(src=q(1, 1), dur=1.8, fill=True, zoom=(1.05, 1.15), caps=[
            ("3 в 1 за ціною\nоднієї пари", 380, 84, "yellow", 0.05),
            ("Зберігай, щоб не загубити", 1420, 54, "box", 0.6)]),
    ]
    scenes_video("01_3v1_magnitni_nakladky.mp4", scenes)


# =====================================================================
# 2) "Rate my frames / Обери свій номер" — швидкий photo-dump 1–8
# =====================================================================
def v2():
    picks = [("19169.jpg", None), ("8019.jpg", None), ("2570.jpg", (0, 0, 690, 560)),
             ("6022.jpg", (0, 0, 700, 847)), ("213.jpg", None), ("6030.jpg", (0, 0, 700, 954)),
             ("99196.jpg", None), ("2687.jpg", (0, 0, 700, 924))]
    scenes = [dict(src=img("6032.jpg"), dur=1.8, zoom=(1.0, 1.1), caps=[
        ("Обери свої окуляри\nі напиши номер", 330, 76, "box", 0.0),
        ("Я першою кажу — №3", 1450, 54, "yellow", 0.7)])]
    for n, (f, box) in enumerate(picks, 1):
        tall = img(f, box).height > img(f, box).width * 1.3
        scenes.append(dict(src=img(f, box), dur=1.05, fill=tall, zoom=(1.02, 1.1), caps=[
            (f"№{n}", 300, 150, "outline", 0.0)]))
    scenes.append(dict(src=img("6032.jpg"), dur=1.6, zoom=(1.1, 1.2), caps=[
        ("Пиши номер у коментарі", 330, 72, "box", 0.0),
        ("— відповім з ціною", 450, 60, "yellow", 0.3)]))
    scenes_video("02_obery_nomer.mp4", scenes)


# =====================================================================
# 3) "POV: ти весь день за компʼютером" — захист від синього світла
# =====================================================================
def v3():
    scenes = [
        dict(src=img("6022.jpg", (0, 0, 700, 847)), dur=2.0, zoom=(1.0, 1.08), caps=[
            ("POV: ти 8 годин\nдивишся в екран", 350, 80, "box", 0.0),
            ("а ввечері болять очі", 1420, 56, "yellow", 0.7)]),
        dict(src=img("1731.jpg", (0, 0, 680, 948)), dur=1.7, zoom=(1.0, 1.1), caps=[
            ("Рішення — лінзи\nз фільтром синього світла", 360, 66, "box", 0.05)]),
        dict(src=img("2570.jpg", (0, 0, 690, 560)), dur=1.5, zoom=(1.05, 1.18), caps=[
            ("Шукай цей значок", 380, 76, "yellow", 0.05)]),
        dict(src=img("2687.jpg", (0, 0, 700, 924)), dur=1.4, zoom=(1.0, 1.1), caps=[
            ("Круглі", 330, 110, "outline", 0.05)]),
        dict(src=img("2134.jpg", (0, 0, 680, 953)), dur=1.4, zoom=(1.0, 1.1), caps=[
            ("Геометрія", 330, 110, "outline", 0.05)]),
        dict(src=img("6030.jpg", (0, 0, 700, 954)), dur=1.4, zoom=(1.0, 1.1), caps=[
            ("Авіатори", 330, 110, "outline", 0.05)]),
        dict(src=img("5002.jpg", (0, 0, 700, 630)), dur=1.4, zoom=(1.0, 1.1), caps=[
            ("Класика", 330, 110, "outline", 0.05)]),
        dict(src=img("2007.jpg", (0, 0, 690, 1036)), dur=1.9, zoom=(1.0, 1.1), caps=[
            ("Можна з діоптріями\nабо без", 360, 76, "box", 0.05),
            ("Відправ тому, хто не відлипає від ноута", 1430, 44, "yellow", 0.6)]),
    ]
    scenes_video("03_pov_ekran_syne_svitlo.mp4", scenes)


# =====================================================================
# 4) "Підбираю окуляри на складі" — behind the scenes / day in the life
# =====================================================================
def v4():
    scenes = [
        dict(src=img("020.jpg"), dur=2.0, fill=True, zoom=(1.0, 1.08), caps=[
            ("Збираю ваше\nзамовлення", 360, 84, "box", 0.0),
            ("наш склад окулярів", 1420, 56, "yellow", 0.6)]),
        dict(src=img("8097.jpg"), dur=1.5, fill=True, zoom=(1.0, 1.1), caps=[
            ("Шукаю потрібну\nдіоптрію", 360, 80, "box", 0.05)]),
        dict(src=img("99196.jpg"), dur=1.5, fill=True, zoom=(1.0, 1.1), caps=[
            ("+1.0 … +6.0", 360, 100, "outline", 0.05)]),
        dict(src=img("19169.jpg"), dur=1.5, fill=True, zoom=(1.0, 1.1), caps=[
            ("Перевіряю оправу", 360, 80, "box", 0.05)]),
        dict(src=img("8019.jpg"), dur=1.5, fill=True, zoom=(1.0, 1.1), caps=[
            ("і лінзи", 360, 90, "box", 0.05)]),
        dict(src=img("213.jpg"), dur=1.5, fill=True, zoom=(1.0, 1.1), caps=[
            ("Ще одна пара\nв дорогу", 360, 80, "box", 0.05)]),
        dict(src=img("6032.jpg"), dur=2.0, fill=True, zoom=(1.0, 1.12), caps=[
            ("Відправляємо\nпо всій Україні", 360, 80, "yellow", 0.05),
            ("Нова пошта · Укрпошта", 1430, 54, "box", 0.5)]),
    ]
    scenes_video("04_zbyrayu_zamovlennya.mp4", scenes)


# =====================================================================
# 5) "Це знак купити нові окуляри" — trend text-reveal + style grid
# =====================================================================
def v5():
    tiles = [img("19169.jpg"), img("8019.jpg"), img("6032.jpg"), img("213.jpg"),
             img("2687.jpg", (0, 0, 700, 924)), img("99196.jpg")]
    hook_dur, grid_dur, bad_dur = 2.4, 3.6, 1.8

    def thumb(src, w, h):
        s = max(w / src.width, h / src.height)
        r = src.resize((int(src.width * s) + 1, int(src.height * s) + 1), Image.BILINEAR)
        return r.crop(((r.width - w) // 2, (r.height - h) // 2, (r.width - w) // 2 + w, (r.height - h) // 2 + h))

    gw, gh = 470, 430
    thumbs = [thumb(s, gw, gh) for s in tiles]
    total_main = hook_dur + bad_dur + grid_dur

    def fn(t, frac):
        if t < hook_dur:
            frame = render_photo(img("8019.jpg"), 1.0 + 0.05 * t / hook_dur, fill=True)
            frame = Image.blend(frame, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
            caption(frame, "Якщо ти бачиш це відео —", 700, 62, "outline", t / 0.35, fnt=F_BOLD)
            caption(frame, "це знак", 860, 120, "yellow", (t - 0.7) / 0.35)
            caption(frame, "оновити окуляри", 1020, 84, "box", (t - 1.3) / 0.35)
        elif t < hook_dur + bad_dur:
            lt = t - hook_dur
            frame = render_photo(img("0947.jpg", (0, 270, 800, 540)), 1.0 + 0.05 * lt, fill=False)
            caption(frame, "Подряпані лінзи?", 420, 76, "box", lt / 0.3)
            caption(frame, "Зламана дужка?", 560, 76, "box", (lt - 0.5) / 0.3)
            caption(frame, "Стара оправа?", 700, 76, "box", (lt - 1.0) / 0.3)
            if lt < 0.08:
                frame = flash(frame, 0.7 * (1 - lt / 0.08))
        elif t < total_main:
            lt = t - hook_dur - bad_dur
            frame = Image.new("RGB", (W, H), (12, 12, 12))
            caption(frame, "Обирай свій стиль", 220, 72, "yellow", lt / 0.3)
            for k, th in enumerate(thumbs):
                appear = ease_back((lt - 0.15 * k) / 0.4)
                if appear <= 0:
                    continue
                c, r = k % 2, k // 2
                sc = max(0.05, appear)
                tt = th.resize((int(gw * sc), int(gh * sc)), Image.BILINEAR)
                cx = (W // 2 - gw // 2 - 8) if c == 0 else (W // 2 + gw // 2 + 8)
                cy = 320 + r * (gh + 16) + gh // 2
                frame.paste(tt, (cx - tt.width // 2, cy - tt.height // 2))
            caption(frame, "Яка пара твоя? Пиши в коментарі", 1700, 48, "box", (lt - 1.5) / 0.3)
            if lt < 0.08:
                frame = flash(frame, 0.7 * (1 - lt / 0.08))
        else:
            return logo_end((t - total_main) / 2.5)
        progress_bar(frame, min(1, t / total_main))
        return frame

    write("05_tse_znak.mp4", fn, total_main + 2.5)


VIDEOS = {1: v1, 2: v2, 3: v3, 4: v4, 5: v5}

if __name__ == "__main__":
    which = [int(a) for a in sys.argv[1:]] or list(VIDEOS)
    for k in which:
        VIDEOS[k]()
