"""Render each PDF page to a JPEG for the web viewer and detect its text lines.
Writes web/pages/pNNN.jpg and web/pages/lines.json:
  {"w":W,"h":H,"pages":{"1":[[y0,y1,x0,x1,ink],...], ...}}  (pixel coords of the JPEG)
"""
import fitz, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PDF = os.path.join(HERE, '..', 'diagnose.pdf')
OUT = os.path.join(HERE, 'pages'); os.makedirs(OUT, exist_ok=True)
DPI = 110

def lines_of(gray):
    h, w = gray.shape
    ink = gray < 150                                   # dark pixels
    ink[:, :int(w * 0.04)] = False; ink[:, int(w * 0.96):] = False   # scanner edges
    rows = ink.sum(1)
    on = rows > max(2, w * 0.004)
    # close tiny gaps (tone marks / vowels detached from the line body)
    bands, y, n = [], 0, len(on)
    while y < n:
        if on[y]:
            y0 = y
            while y < n and (on[y] or (y + 3 < n and on[y + 1:y + 4].any())): y += 1
            bands.append([y0, y])
        y += 1
    # Thai upper/lower marks often touch the next line, so a band can hold several
    # lines; split tall bands at the emptiest rows near the expected line pitch.
    hs = [b[1] - b[0] for b in bands]
    singles = [b for b in bands if 12 <= b[1] - b[0] <= 34]
    typ = float(np.median([b[1] - b[0] for b in singles])) if singles else 22.0
    steps = [b2[0] - b1[0] for b1, b2 in zip(singles, singles[1:]) if 0 < b2[0] - b1[0] < typ * 2]
    pitch = float(np.median(steps)) if steps else typ * 1.3
    split = []
    for y0, y1 in bands:
        H = y1 - y0
        k = int(round(H / pitch)) if H > typ * 1.5 else 1
        if k <= 1:
            split.append([y0, y1]); continue
        cuts, prev = [], y0
        for j in range(1, k):
            c = y0 + H * j / k
            lo, hi = int(max(prev + 4, c - pitch * 0.35)), int(min(y1 - 4, c + pitch * 0.35))
            if hi <= lo: continue
            cut = lo + int(np.argmin(rows[lo:hi]))
            cuts.append(cut); prev = cut
        edges = [y0] + cuts + [y1]
        split += [[a, b] for a, b in zip(edges, edges[1:])]
    bands = split
    out = []
    for y0, y1 in bands:
        if y1 - y0 < 4: continue
        cols = ink[y0:y1].any(0)
        xs = np.where(cols)[0]
        if len(xs) == 0: continue
        out.append([int(y0), int(y1), int(xs[0]), int(xs[-1]), int(cols.sum())])
    # merge bands that are too thin to be a line (split marks) into the nearest neighbour
    med = np.median([b[1] - b[0] for b in out]) if out else 0
    merged = []
    for b in out:
        if merged and (b[1] - b[0] < med * 0.35) and b[0] - merged[-1][1] < med * 0.6:
            m = merged[-1]; m[1] = b[1]; m[2] = min(m[2], b[2]); m[3] = max(m[3], b[3]); m[4] = max(m[4], b[4])
        else:
            merged.append(b)
    return merged

doc = fitz.open(PDF)
res = {'pages': {}}
for i, p in enumerate(doc):
    pix = p.get_pixmap(dpi=DPI, colorspace=fitz.csGRAY)
    open(os.path.join(OUT, 'p%03d.jpg' % (i + 1)), 'wb').write(pix.tobytes('jpg', jpg_quality=55))
    g = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    res['w'], res['h'] = pix.width, pix.height
    res['pages'][str(i + 1)] = lines_of(g)
json.dump(res, open(os.path.join(OUT, 'lines.json'), 'w'))
sizes = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT) if f.endswith('.jpg'))
print('pages', len(res['pages']), 'w,h', res['w'], res['h'], 'jpg MB', round(sizes / 1e6, 1),
      'lines p1,p2,p50,p114', [len(res['pages'][k]) for k in ('1', '2', '50', '114')])
