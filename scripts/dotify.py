"""Turn a cut-out photo (PNG with transparent background) into a dot-matrix SVG.

Each grid cell becomes one dot: its colour comes from the photo, its size from
the tone at that spot (halftone). Background stays transparent. Halftone has to
flip per theme - on a dark page bright areas get the big dots - so it writes
two files, <out>-dark.svg and <out>-light.svg.

    pip install pillow numpy
    python scripts/dotify.py cutout.png -o assets/portrait --cols 110
"""

import argparse
from collections import defaultdict

import numpy as np
from PIL import Image, ImageOps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default="assets/portrait")
    ap.add_argument("--cols", type=int, default=110)
    ap.add_argument("--min-r", type=float, default=0.12)
    ap.add_argument("--max-r", type=float, default=0.5)
    a = ap.parse_args()

    img = Image.open(a.src).convert("RGBA")
    rows = round(a.cols * img.height / img.width)
    small = img.resize((a.cols, rows), Image.LANCZOS)
    rgb = np.asarray(small.convert("RGB"), dtype=float) / 255
    alpha = np.asarray(small.getchannel("A"), dtype=float) / 255

    # Equalize brightness inside the subject only, for the dot sizes.
    lum = np.asarray(ImageOps.equalize(small.convert("L"),
                                       mask=small.getchannel("A")), dtype=float) / 255

    for mode in ("dark", "light"):
        groups = defaultdict(list)
        for y in range(rows):
            for x in range(a.cols):
                if alpha[y, x] < 0.5:
                    continue
                tone = lum[y, x] if mode == "dark" else 1 - lum[y, x]
                lo = a.min_r if mode == "dark" else a.min_r + 0.1
                r = lo + (a.max_r - lo) * tone ** 0.9
                c = rgb[y, x]
                # Darks would vanish on a dark page, lights on a white one: push
                # the colours the opposite way with a gamma curve per theme.
                c = c ** 0.55 if mode == "dark" else c ** 1.7
                # Quantize so dots can share a <g fill>, which keeps the file small.
                key = "#%x%x%x" % tuple(int(round(min(v, 1) * 15)) for v in c)
                groups[key].append(f'<circle cx="{x + .5}" cy="{y + .5}" r="{r:.2f}"/>')

        body = "".join(f'<g fill="{k}">{"".join(v)}</g>' for k, v in groups.items())
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {a.cols} {rows}" '
               f'width="{a.cols * 3}" height="{rows * 3}" role="img" '
               f'aria-label="portrait as a dot matrix">{body}</svg>\n')
        out = f"{a.out}-{mode}.svg"
        with open(out, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {out}: {sum(map(len, groups.values()))} dots, {len(svg)//1024} KB")


if __name__ == "__main__":
    main()
