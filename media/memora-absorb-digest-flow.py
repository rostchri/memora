#!/usr/bin/env python3

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

W, H = 1200, 675
FPS = 16
DURATION = 6.0
N = int(FPS * DURATION)
OUT = Path(__file__).with_name("memora-absorb-digest-flow.gif")

FONT = "/System/Library/Fonts/SFNS.ttf"
MONO = "/System/Library/Fonts/SFNSMono.ttf"


def font(size):
    return ImageFont.truetype(FONT, size)


def mono(size):
    return ImageFont.truetype(MONO, size)


F = {
    "brand": font(52),
    "h1": font(31),
    "h2": font(22),
    "body": font(18),
    "small": font(15),
    "mono": mono(18),
    "mono_small": mono(14),
}

C = {
    "bg": (10, 14, 18),
    "bg2": (14, 20, 26),
    "panel": (22, 29, 36),
    "panel2": (27, 36, 45),
    "line": (60, 74, 88),
    "text": (232, 238, 244),
    "muted": (139, 154, 169),
    "green": (72, 211, 137),
    "teal": (57, 184, 210),
    "yellow": (237, 191, 89),
    "purple": (169, 107, 226),
    "red": (232, 100, 104),
}


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def alpha_between(t, a, b):
    return smooth((t - a) / (b - a))


def lerp(a, b, x):
    return a + (b - a) * x


def mix(c1, c2, x):
    return tuple(int(lerp(a, b, x)) for a, b in zip(c1, c2))


def rounded(draw, xy, r, fill, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=width)


def text(draw, xy, s, fill, fnt, anchor=None):
    draw.text(xy, s, fill=fill, font=fnt, anchor=anchor)


def line_alpha(draw, pts, fill, width=3, alpha=255):
    color = fill + (int(alpha),)
    draw.line(pts, fill=color, width=width, joint="curve")


def paste_layer(base, layer, alpha=1.0):
    if alpha >= 0.999:
        base.alpha_composite(layer)
    elif alpha > 0:
        a = layer.getchannel("A").point(lambda p: int(p * alpha))
        layer.putalpha(a)
        base.alpha_composite(layer)


def draw_layer(base, alpha, fn, *args):
    if alpha <= 0:
        return
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fn(ImageDraw.Draw(layer), *args)
    paste_layer(base, layer, alpha)


def draw_header(draw):
    text(draw, (56, 49), "memora", C["text"], F["brand"])
    text(draw, (58, 101), "absorb -> graph memory -> digest", C["muted"], F["h2"])
    rounded(draw, (918, 44, 1128, 90), 10, (18, 30, 34), (48, 114, 100), 1)
    text(draw, (940, 58), "source-backed context", C["green"], F["body"])


def panel(draw, xy, title, subtitle, accent):
    x0, y0, x1, y1 = xy
    rounded(draw, (x0, y0 + 8, x1, y1 + 8), 14, (0, 0, 0, 72), None, 1)
    rounded(draw, xy, 14, C["panel"], mix(C["line"], accent, 0.35), 2)
    rounded(draw, (x0, y0, x1, y0 + 54), 14, C["panel2"], None, 1)
    draw.rectangle((x0, y0 + 28, x1, y0 + 54), fill=C["panel2"])
    text(draw, (x0 + 24, y0 + 18), title, C["text"], F["h2"])
    text(draw, (x0 + 24, y0 + 58), subtitle, C["muted"], F["small"])


def dot(draw, x, y, r, color, outline=None):
    draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=outline or color, width=2)


def arrow(draw, x0, y0, x1, y1, color, progress=1.0, alpha=1.0):
    p = smooth(progress)
    if p <= 0:
        return
    xm = lerp(x0, x1, p)
    ym = lerp(y0, y1, p)
    rgba = color + (int(230 * clamp(alpha)),)
    draw.line((x0, y0, xm, ym), fill=rgba, width=4)
    if p > 0.18:
        ang = math.atan2(y1 - y0, x1 - x0)
        back = 17
        half = 7
        bx = xm - math.cos(ang) * back
        by = ym - math.sin(ang) * back
        nx = -math.sin(ang)
        ny = math.cos(ang)
        draw.polygon(
            [
                (xm, ym),
                (bx + nx * half, by + ny * half),
                (bx - nx * half, by - ny * half),
            ],
            fill=rgba,
        )


def draw_terminal(draw, t):
    x0, y0, x1, y1 = 64, 166, 360, 536
    panel(draw, (x0, y0, x1, y1), "agent session", "facts, decisions, TODOs", C["teal"])
    rows = [
        ("decision", "bus is the contract"),
        ("issue", "prompt-submit race"),
        ("todo", "tighten MCP reconnect"),
        ("note", "Pi: maintainer online"),
    ]
    y = y0 + 98
    for i, (kind, body) in enumerate(rows):
        p = alpha_between(t, 0.35 + i * 0.22, 0.85 + i * 0.22)
        if p <= 0:
            continue
        color = [C["teal"], C["green"], C["yellow"], C["red"], C["purple"]][i]
        row_y = y + int(lerp(10, 0, p))
        dot(draw, x0 + 27, row_y + 10, 4, mix(C["panel2"], color, p))
        text(draw, (x0 + 42, row_y), kind, mix(C["muted"], color, p), F["mono_small"])
        text(draw, (x0 + 42, row_y + 22), body, mix(C["muted"], C["text"], p), F["small"])
        y += 55
    if t > 0.8:
        pulse = 0.5 + 0.5 * math.sin(t * 7)
        text(draw, (x0 + 24, y1 - 37), "memora_absorb(...)", mix(C["green"], C["text"], pulse * 0.35), F["mono"])


def draw_graph(draw, t):
    x0, y0, x1, y1 = 430, 166, 770, 536
    panel(draw, (x0, y0, x1, y1), "memory graph", "dedupe, merge, relate", C["green"])

    cx, cy = (x0 + x1) / 2, y0 + 236
    nodes = [
        (cx - 88, cy - 82, "issue", C["red"]),
        (cx + 64, cy - 78, "decision", C["green"]),
        (cx - 22, cy + 10, "context", C["teal"]),
        (cx - 104, cy + 102, "todo", C["yellow"]),
        (cx + 106, cy + 91, "repo", C["purple"]),
    ]
    node_progress = [alpha_between(t, 1.35 + i * 0.16, 1.95 + i * 0.16) for i in range(len(nodes))]
    edge_progress = alpha_between(t, 2.15, 2.9)
    for i, a in enumerate(nodes):
        for j, b in enumerate(nodes):
            if j <= i or (i + j) % 2:
                continue
            e = min(node_progress[i], node_progress[j]) * edge_progress
            if e <= 0.02:
                continue
            x_a, y_a, _, _ = a
            x_b, y_b, _, _ = b
            line_color = mix(C["line"], C["green"], 0.62)
            draw.line((x_a, y_a, x_b, y_b), fill=line_color + (int(185 * e),), width=2)
    for i, (x, y, label, color) in enumerate(nodes):
        p = node_progress[i]
        if p <= 0.02:
            continue
        rr = int(lerp(2, 27, p))
        glow = int(lerp(0, 6, p) * (0.65 + 0.35 * math.sin(t * 5 + i)))
        if glow:
            dot(draw, x, y, rr + glow, mix(C["bg"], color, 0.35), None)
        dot(draw, x, y, rr, mix(C["panel2"], color, p), C["bg"])
        if p > 0.7:
            text(draw, (x, y - 7), label, C["bg"], F["small"], anchor="mm")

    badge = alpha_between(t, 2.65, 3.1)
    if badge > 0:
        rounded(draw, (x0 + 32, y1 - 70, x1 - 32, y1 - 25), 9, (19, 37, 32), mix(C["line"], C["green"], badge), 1)
        text(draw, (x0 + 50, y1 - 57), "dedupe -> update -> link", mix(C["muted"], C["green"], badge), F["small"])


def draw_digest(draw, t):
    x0, y0, x1, y1 = 840, 166, 1136, 536
    panel(draw, (x0, y0, x1, y1), "memory_digest", "answer with raw sources", C["purple"])
    q = alpha_between(t, 3.15, 3.9)
    if q > 0:
        rounded(draw, (x0 + 24, y0 + 92, x1 - 24, y0 + 145), 9, (18, 26, 36), mix(C["purple"], C["line"], 0.2), 1)
        text(draw, (x0 + 41, y0 + 106), "topic: prompt hanging", mix(C["muted"], C["text"], q), F["mono_small"])

    rows = [
        ("active_hits", "[602, 799, 800]"),
        ("open_issues", "2 relevant"),
        ("related", "32 edges"),
    ]
    y = y0 + 174
    for i, (k, v) in enumerate(rows):
        p = alpha_between(t, 3.8 + i * 0.26, 4.35 + i * 0.26)
        if p <= 0:
            continue
        color = [C["green"], C["red"], C["teal"], C["yellow"]][i]
        row_y = y + int(lerp(10, 0, p))
        dot(draw, x0 + 35, row_y + 11, 4, mix(C["panel2"], color, p))
        text(draw, (x0 + 52, row_y), k, mix(C["muted"], C["text"], p * 0.65), F["small"])
        text(draw, (x0 + 52, row_y + 22), v, mix(C["muted"], C["text"], p), F["mono_small"])
        y += 54

    final = alpha_between(t, 5.0, 5.45)
    if final > 0:
        rounded(draw, (x0 + 24, y1 - 67, x1 - 24, y1 - 23), 9, (33, 38, 22), mix(C["line"], C["yellow"], final * 0.8), 1)
        text(draw, (x0 + 42, y1 - 54), "context > guesses", mix(C["muted"], C["yellow"], final), F["small"])


def draw_footer(draw, t):
    x0, y0, x1, y1 = 270, 584, 930, 626
    rounded(draw, (x0, y0, x1, y1), 12, (17, 23, 29), (42, 54, 67), 1)
    labels = [
        ("absorb", 0.15, 1.8, C["teal"]),
        ("consolidate", 1.75, 3.25, C["green"]),
        ("digest", 3.2, 5.25, C["purple"]),
        ("handoff", 5.0, 6.0, C["yellow"]),
    ]
    x = x0 + 28
    for label, a, b, color in labels:
        active = alpha_between(t, a, b) * (1 - alpha_between(t, b, b + 0.35))
        dot(draw, x, y0 + 21, 5 + int(active * 5), mix(C["line"], color, active))
        text(draw, (x + 16, y0 + 11), label, mix(C["muted"], C["text"], active), F["small"])
        x += 150


def make_frame(i):
    t = i / FPS
    img = Image.new("RGBA", (W, H), C["bg"] + (255,))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        r = y / H
        col = mix(C["bg"], C["bg2"], r)
        draw.line((0, y, W, y), fill=col)

    # Subtle background grid, not decorative blobs.
    for x in range(0, W, 40):
        draw.line((x, 0, x, H), fill=(17, 24, 31), width=1)
    for y in range(0, H, 40):
        draw.line((0, y, W, y), fill=(17, 24, 31), width=1)

    draw_header(draw)
    draw_layer(img, alpha_between(t, 0.05, 0.35), draw_terminal, t)
    draw_layer(img, alpha_between(t, 1.1, 1.55), draw_graph, t)
    draw_layer(img, alpha_between(t, 3.05, 3.45), draw_digest, t)

    arrow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    arrow_draw = ImageDraw.Draw(arrow_layer)
    arrow(arrow_draw, 363, 345, 424, 345, C["teal"], alpha_between(t, 1.55, 2.1), alpha_between(t, 1.35, 1.75))
    arrow(arrow_draw, 774, 345, 834, 345, C["purple"], alpha_between(t, 3.45, 4.0), alpha_between(t, 3.25, 3.65))
    img.alpha_composite(arrow_layer)

    draw_footer(draw, t)
    return img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)


def main():
    frames = [make_frame(i) for i in range(N)]
    durations = [int(1000 / FPS)] * N
    durations[-1] = 1200
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(OUT)
    print(OUT.stat().st_size)


if __name__ == "__main__":
    main()
