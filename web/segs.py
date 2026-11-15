"""Find word blocks (ink runs separated by spaces) on each scanned page.
Writes web/pages/segs.json: {"scale": 110/DPI, "pages": {"1": [[line_y0, line_y1, [[x0,x1],...]], ...]}}
Coordinates are already scaled to the 910px page JPEGs used by the viewer."""
import fitz, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, '..', 'diagnose.pdf')
DPI = 200
K = 110 / DPI

def bands_of(ink):
    h, w = ink.shape
    rows = ink.sum(1)
    on = rows > max(2, w * 0.004)
    gap = int(round(3 * DPI / 110))
    bands, y, n = [], 0, len(on)
    while y < n:
        if on[y]:
            y0 = y
            while y < n and (on[y] or (y + gap < n and on[y + 1:y + 1 + gap].any())): y += 1
            bands.append([y0, y])
        y += 1
    singles = [b for b in bands if 12 / K <= b[1] - b[0] <= 34 / K]
    typ = float(np.median([b[1] - b[0] for b in singles])) if singles else 22 / K
    steps = [b2[0] - b1[0] for b1, b2 in zip(singles, singles[1:]) if 0 < b2[0] - b1[0] < typ * 2]
    pitch = float(np.median(steps)) if steps else typ * 1.3
    out = []
    for y0, y1 in bands:
        H = y1 - y0
        k = int(round(H / pitch)) if H > typ * 1.5 else 1
        if k <= 1: out.append([y0, y1]); continue
        cuts, prev = [], y0
        for j in range(1, k):
            c = y0 + H * j / k
            lo, hi = int(max(prev + 4, c - pitch * .35)), int(min(y1 - 4, c + pitch * .35))
            if hi <= lo: continue
            cut = lo + int(np.argmin(rows[lo:hi])); cuts.append(cut); prev = cut
        e = [y0] + cuts + [y1]
        out += [[a, b] for a, b in zip(e, e[1:])]
    return [b for b in out if b[1] - b[0] >= 4], typ

def segs_of(ink, y0, y1, typ):
    cols = ink[y0:y1].any(0)
    xs = np.where(cols)[0]
    if len(xs) == 0: return []
    # gaps between ink runs; a space is clearly wider than the gaps between Thai glyphs
    runs, start, prev = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - prev > 1:
            runs.append([start, prev]); start = x
        prev = x
    runs.append([start, prev])
    thr = max(5.0, typ * float(os.environ.get("SEG_GAP", "0.21")))
    segs = [runs[0][:]]
    for a, b in runs[1:]:
        if a - segs[-1][1] - 1 >= thr: segs.append([a, b])
        else: segs[-1][1] = b
    return segs

doc = fitz.open(PDF)
res = {'pages': {}}
for i, p in enumerate(doc):
    pix = p.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    ink = g < 150
    w = ink.shape[1]
    ink[:, :int(w * .04)] = False; ink[:, int(w * .96):] = False
    bands, typ = bands_of(ink)
    lines = []
    for y0, y1 in bands:
        ss = segs_of(ink, y0, y1, typ)
        # drop specks: tiny isolated blobs
        ss = [s for s in ss if s[1] - s[0] >= 2]
        if not ss: continue
        lines.append([round(y0 * K, 1), round(y1 * K, 1), [[round(a * K, 1), round(b * K, 1)] for a, b in ss]])
    res['pages'][str(i + 1)] = lines
json.dump(res, open(os.path.join(HERE, 'pages', 'segs.json'), 'w'))
print('pages', len(res['pages']), 'p50 lines', len(res['pages']['50']), 'p50 segs', sum(len(l[2]) for l in res['pages']['50']))
