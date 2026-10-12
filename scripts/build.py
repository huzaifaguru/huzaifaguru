"""Generate every SVG the profile README uses, straight into assets/.

No third-party stats services (github-readme-stats etc. are shared public
instances that rate-limit and go down). Standard library only.

    GITHUB_TOKEN=... python scripts/build.py [username]
"""

import datetime as dt
import json
import math
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
USER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PROFILE_USER", "huzaifaguru")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

# Notebook byte counts are mostly embedded outputs/images, so they swamp
# the language breakdown. Leave them out of the language cards.
IGNORED_LANGS = {"Jupyter Notebook"}

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", text="#e6edf3", muted="#8b949e",
                 accent="#39d353", grid="#21262d", fill="#39d35333"),
    "light": dict(bg="#ffffff", border="#d0d7de", text="#1f2328", muted="#59636e",
                  accent="#1a7f37", grid="#eaeef2", fill="#1a7f3726"),
}

LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "HTML": "#e34c26", "CSS": "#663399", "C++": "#f34b7d", "C": "#555555",
    "PHP": "#4F5D95", "C#": "#178600", "Shell": "#89e051", "Java": "#b07219",
    "Jupyter Notebook": "#DA5B0B", "SCSS": "#c6538c", "Dockerfile": "#384d54",
}
FONT = "font-family=\"'Segoe UI',Ubuntu,'Helvetica Neue',sans-serif\""
MONO = "font-family=\"'JetBrains Mono',Consolas,'Courier New',monospace\""


# ---------------------------------------------------------------- API

def api(path, body=None):
    url = path if path.startswith("http") else f"https://api.github.com/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-builder")
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch():
    user = api(f"users/{USER}")
    repos = [r for r in api(f"users/{USER}/repos?per_page=100&type=owner")
             if not r["fork"]]
    langs = {}
    for r in repos:
        for name, size in api(r["languages_url"]).items():
            if name not in IGNORED_LANGS:
                langs[name] = langs.get(name, 0) + size

    q = """query($login:String!){ user(login:$login){
      contributionsCollection{
        totalCommitContributions totalPullRequestContributions
        totalIssueContributions restrictedContributionsCount
        contributionCalendar{ totalContributions
          weeks{ contributionDays{ date contributionCount } } } } } }"""
    cc = api("graphql", {"query": q, "variables": {"login": USER}})
    cc = cc["data"]["user"]["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return dict(user=user, repos=repos, langs=langs, cc=cc, days=days)


def streaks(days):
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    # Today not having a contribution yet should not break the streak.
    i = len(counts) - 1
    if counts and counts[i] == 0:
        i -= 1
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    return current, longest


# ---------------------------------------------------------------- helpers

def svg(w, h, body, t=None, title=""):
    bg = (f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" '
          f'fill="{t["bg"]}" stroke="{t["border"]}"/>') if t else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}">'
            f'<title>{escape(title)}</title>{bg}{body}</svg>\n')


def wrap(text, width):
    lines, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def write(name, content):
    (ASSETS / name).write_text(content, encoding="utf-8")
    print("wrote", name)


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


# ---------------------------------------------------------------- cards

def stats_card(d, t):
    cc, user = d["cc"], d["user"]
    cur, longest = streaks(d["days"])
    core = [
        ("Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
        ("Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("Public repos", user["public_repos"]),
        ("Languages used", len(d["langs"])),
    ]
    # Only show these once they are non-zero, so a new profile does not look empty.
    optional = [
        ("Pull requests", cc["totalPullRequestContributions"]),
        ("Issues", cc["totalIssueContributions"]),
        ("Stars earned", sum(r["stargazers_count"] for r in d["repos"])),
        ("Followers", user["followers"]),
    ]
    rows = (core + [r for r in optional if r[1]])[:6]
    w, h = 480, 210
    body = [f'<text x="24" y="38" {MONO} font-size="15" font-weight="700" fill="{t["accent"]}">'
            f'$ gh stats {escape(USER)}</text>']
    for i, (label, val) in enumerate(rows):
        y = 70 + i * 22
        body.append(f'<text x="24" y="{y}" {FONT} font-size="13" fill="{t["muted"]}">{label}</text>'
                    f'<text x="262" y="{y}" {MONO} font-size="13" font-weight="700" '
                    f'fill="{t["text"]}" text-anchor="end">{fmt(val)}</text>')
    # streak block on the right
    cx = 380
    body.append(f'<line x1="292" y1="58" x2="292" y2="186" stroke="{t["border"]}"/>')
    for i, (label, val) in enumerate([("current streak", cur), ("longest streak", longest)]):
        y = 92 + i * 64
        body.append(f'<text x="{cx}" y="{y}" {MONO} font-size="28" font-weight="700" '
                    f'fill="{t["accent"]}" text-anchor="middle">{val}</text>'
                    f'<text x="{cx}" y="{y+20}" {FONT} font-size="12" fill="{t["muted"]}" '
                    f'text-anchor="middle">{label} (days)</text>')
    return svg(w, h, "".join(body), t, f"{USER} GitHub statistics")


def langs_card(d, t, top=6):
    total = sum(d["langs"].values()) or 1
    items = [kv for kv in sorted(d["langs"].items(), key=lambda kv: -kv[1])
             if kv[1] / total >= 0.005][:top]
    w, h = 480, 78 + 24 * math.ceil(len(items) / 2)
    body = [f'<text x="24" y="36" {MONO} font-size="15" font-weight="700" fill="{t["accent"]}">'
            f'$ most used languages</text>',
            f'<clipPath id="bar"><rect x="24" y="50" width="{w-48}" height="10" rx="5"/></clipPath>'
            f'<g clip-path="url(#bar)">']
    x = 24.0
    shown = sum(v for _, v in items)
    for name, v in items:
        bw = (w - 48) * v / shown
        body.append(f'<rect x="{x:.2f}" y="50" width="{bw:.2f}" height="10" '
                    f'fill="{LANG_COLORS.get(name, t["muted"])}"/>')
        x += bw
    body.append("</g>")
    for i, (name, v) in enumerate(items):
        col, row = i % 2, i // 2
        lx, ly = 24 + col * 220, 88 + row * 24
        body.append(f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{LANG_COLORS.get(name, t["muted"])}"/>'
                    f'<text x="{lx+16}" y="{ly}" {FONT} font-size="13" fill="{t["text"]}">{escape(name)}'
                    f'<tspan fill="{t["muted"]}"> {100*v/total:.1f}%</tspan></text>')
    return svg(w, h, "".join(body), t, "most used languages")


def project_card(p, repo, t):
    w, h = 420, 160
    title = p.get("title") or repo["name"]
    desc = p.get("description") or repo.get("description") or ""
    lang = repo.get("language") or ""
    body = [f'<text x="20" y="34" {FONT} font-size="15" font-weight="700" fill="{t["accent"]}">'
            f'{escape(title)}</text>',
            f'<text x="20" y="52" {MONO} font-size="11" fill="{t["muted"]}">'
            f'{escape(USER)}/{escape(repo["name"])}</text>']
    for i, line in enumerate(wrap(desc, 58)[:4]):
        body.append(f'<text x="20" y="{76 + i*17}" {FONT} font-size="12" fill="{t["text"]}">'
                    f'{escape(line)}</text>')
    y = h - 16
    x = 20
    if lang:
        body.append(f'<circle cx="{x+5}" cy="{y-4}" r="5" fill="{LANG_COLORS.get(lang, t["muted"])}"/>'
                    f'<text x="{x+15}" y="{y}" {FONT} font-size="12" fill="{t["muted"]}">{escape(lang)}</text>')
        x += 30 + 7 * len(lang)
    body.append(f'<text x="{x}" y="{y}" {FONT} font-size="12" fill="{t["muted"]}">'
                f'★ {repo["stargazers_count"]}   ⑂ {repo["forks_count"]}</text>')
    if p.get("live"):
        body.append(f'<text x="{w-20}" y="{y}" {FONT} font-size="12" font-weight="600" '
                    f'fill="{t["accent"]}" text-anchor="end">live demo ↗</text>')
    return svg(w, h, "".join(body), t, title)


# ---------------------------------------------------------------- radar

def radar(values, t, title, max_value=None):
    """values: list of (label, value). Plain polygon radar, no library."""
    w, h, cx, cy, R = 400, 360, 200, 186, 118
    n = len(values)
    mx = max_value or max(v for _, v in values) or 1
    pt = lambda i, r: (cx + r * math.sin(2 * math.pi * i / n),
                       cy - r * math.cos(2 * math.pi * i / n))
    body = [f'<text x="{cx}" y="30" {MONO} font-size="14" font-weight="700" '
            f'fill="{t["accent"]}" text-anchor="middle">{escape(title)}</text>']
    for k in range(1, 5):
        ring = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, R * k / 4) for i in range(n)))
        body.append(f'<polygon points="{ring}" fill="none" stroke="{t["grid"]}"/>')
    for i, (label, _) in enumerate(values):
        x, y = pt(i, R)
        body.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{t["grid"]}"/>')
        lx, ly = pt(i, R + 18)
        anchor = "middle" if abs(lx - cx) < 8 else ("start" if lx > cx else "end")
        body.append(f'<text x="{lx:.1f}" y="{ly+4:.1f}" {FONT} font-size="11.5" '
                    f'fill="{t["text"]}" text-anchor="{anchor}">{escape(label)}</text>')
    shape = " ".join(f"{x:.1f},{y:.1f}" for x, y in
                     (pt(i, R * max(v, 0) / mx) for i, (_, v) in enumerate(values)))
    body.append(f'<polygon points="{shape}" fill="{t["fill"]}" stroke="{t["accent"]}" stroke-width="2"/>')
    for i, (_, v) in enumerate(values):
        x, y = pt(i, R * max(v, 0) / mx)
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{t["accent"]}"/>')
    return svg(w, h, "".join(body), t, title)


# ---------------------------------------------------------------- isocalendar

def isocalendar(days):
    """3D isometric contribution calendar. Transparent, so one file fits both themes."""
    shades = ["#2d333b", "#0e4429", "#006d32", "#26a641", "#39d353"]
    nonzero = sorted(c["contributionCount"] for c in days if c["contributionCount"])
    q = [nonzero[int(len(nonzero) * f)] for f in (0.25, 0.5, 0.75)] if nonzero else [1, 2, 3]
    peak = max([c["contributionCount"] for c in days] + [1])

    def level(c):
        if c == 0:
            return 0
        return 1 + sum(c > v for v in q)

    def shade(hexc, f):
        r, g, b = (int(hexc[i:i+2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % tuple(min(255, int(v * f)) for v in (r, g, b))

    # Axis vectors: one week steps right and slightly down, one weekday steps
    # down-left. Shallow on purpose so 53 weeks stay wide rather than tall.
    ax, ay = 10.0, 2.8
    bx, by = -6.5, 4.2
    first = dt.date.fromisoformat(days[0]["date"])
    offset = (first.weekday() + 1) % 7  # GitHub weeks start on Sunday
    cubes = []
    for i, d in enumerate(days):
        wk, wd = divmod(i + offset, 7)
        c = d["contributionCount"]
        hgt = 4 + (c / peak) ** 0.6 * 44 if c else 2
        cubes.append((wk, wd, hgt, level(c)))

    weeks = max(c[0] for c in cubes) + 1
    ox, oy = 7 * -bx + 16, 112
    w = int(ox + weeks * ax + 16)
    h = int(oy + weeks * ay + 7 * by + 20)
    body = []
    for wk, wd, hgt, lv in sorted(cubes, key=lambda c: (c[0] + c[1], c[0])):
        px, py = ox + wk * ax + wd * bx, oy + wk * ay + wd * by
        P = lambda u, v, z=0: (px + u * ax + v * bx, py + u * ay + v * by - z)
        top = [P(0, 0, hgt), P(1, 0, hgt), P(1, 1, hgt), P(0, 1, hgt)]
        front = [P(0, 1, hgt), P(1, 1, hgt), P(1, 1), P(0, 1)]   # faces the viewer
        side = [P(1, 0, hgt), P(1, 1, hgt), P(1, 1), P(1, 0)]    # right-hand side
        base = shades[lv]
        for face, f in ((side, 0.7), (front, 0.85), (top, 1.15)):
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in face)
            body.append(f'<polygon points="{pts}" fill="{shade(base, f)}"/>')
    total = sum(d["contributionCount"] for d in days)
    cur, longest = streaks(days)
    body.insert(0, f'<text x="{w-20}" y="30" {MONO} font-size="15" font-weight="700" fill="#39d353" '
                   f'text-anchor="end">{total} contributions in the last year</text>'
                   f'<text x="{w-20}" y="50" {FONT} font-size="12" fill="#8b949e" text-anchor="end">'
                   f'current streak {cur}d · longest {longest}d · best day {peak}</text>')
    return svg(w, h, "".join(body), None, "isometric contribution calendar")


# ---------------------------------------------------------------- main

def main():
    ASSETS.mkdir(exist_ok=True)
    d = fetch()
    projects = json.loads((ASSETS / "projects.json").read_text(encoding="utf-8"))["projects"]
    skills = json.loads((ASSETS / "skills.json").read_text(encoding="utf-8"))["skills"]
    by_name = {r["name"]: r for r in d["repos"]}

    total = sum(d["langs"].values()) or 1
    top_langs = [kv for kv in sorted(d["langs"].items(), key=lambda kv: -kv[1])
                 if kv[1] / total >= 0.005][:6]
    # sqrt keeps a dominant language from flattening the rest into the centre
    lang_vals = [(n, math.sqrt(v / total)) for n, v in top_langs]

    for mode, t in THEMES.items():
        write(f"card-stats-{mode}.svg", stats_card(d, t))
        write(f"card-langs-{mode}.svg", langs_card(d, t))
        write(f"radar-{mode}.svg", radar(list(skills.items()), t, "skill radar (self-rated)", 10))
        if len(lang_vals) >= 3:
            write(f"radar-langs-{mode}.svg", radar(lang_vals, t, "language radar (bytes, live)"))
        for p in projects:
            repo = by_name.get(p["repo"])
            if repo:
                write(f"card-{p['repo']}-{mode}.svg", project_card(p, repo, t))
            else:
                print("skipping unknown repo", p["repo"])
    write("isocalendar.svg", isocalendar(d["days"]))


if __name__ == "__main__":
    main()
