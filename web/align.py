"""Place every transcribed character on its scanned page.

Each page's words (space-separated runs in diagnose.md) are matched in reading order
to the word blocks found in the image (pages/segs.json) by dynamic programming on
their widths. Characters are then spread across their matched block(s) by weight,
so a highlight starts and ends on the right word instead of a guessed proportion
of the line."""
import json, math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
BRK = float(os.environ.get('ALIGN_BRK', '0.15'))   # cost of a word wrapping onto the next line
SAME = float(os.environ.get('ALIGN_SAME', '0.35'))  # cost of one word spanning two blocks on a line
SPLIT = float(os.environ.get('ALIGN_SPLIT', '0.6'))  # cost of a word boundary at a gap that barely looks like a space
G0, G1 = float(os.environ.get('ALIGN_G0', '5.1')), float(os.environ.get('ALIGN_G1', '5.4'))  # gap widths (px) from doubtful to sure

class PageMap:
    def __init__(self, DOCN, wt, page_start, page_end):
        S = json.load(open(os.path.join(HERE, 'pages', 'segs.json')))
        L = json.load(open(os.path.join(HERE, 'pages', 'lines.json')))
        self.W, self.H = L['w'], L['h']
        self.DOCN, self.wt = DOCN, wt
        self.ps, self.pe = page_start, page_end
        self.lines, self.pos, self.stats, self.found = {}, {}, {}, {}
        for p in page_start:                       # pass 1: every character 1 unit wide
            self._page(p, S['pages'].get(str(p), []))
        if os.environ.get('ALIGN_FIT', '1') == '1':
            self.wt = self._fit_widths()           # pass 2: widths learned from the scan
            for p in page_start:
                self._page(p, S['pages'].get(str(p), []))

    def _fit_widths(self):
        """Least-squares width of each character, from words that sit alone in one block."""
        import numpy as np
        D, wt = self.DOCN, self.wt
        rows, rhs = [], []
        for toks, segs, groups in self.found.values():
            ratios = sorted((segs[si][2] - segs[si][1] + 1) / toks[ti][2] for ti, tj, si, sj in groups
                            if tj - ti == 1 and sj - si == 1 and toks[ti][2] > 0)
            if not ratios: continue
            med = ratios[len(ratios) // 2]
            for ti, tj, si, sj in groups:
                if tj - ti != 1 or sj - si != 1 or toks[ti][3]: continue
                k, j, w, _ = toks[ti]; px = segs[si][2] - segs[si][1] + 1
                if not 0.8 < px / (w * med) < 1.25: continue
                rows.append([c for c in range(k, j) if wt[c] > 0]); rhs.append(px)
        chars = sorted({D[c] for r in rows for c in r})
        idx = {ch: n for n, ch in enumerate(chars)}
        A = np.zeros((len(rows), len(chars)))
        for r, cs in enumerate(rows):
            for c in cs: A[r, idx[D[c]]] += 1
        # light pull toward the mean width keeps rare characters sensible
        mean = sum(rhs) / A.sum()
        lam = 3.0
        A2 = np.vstack([A, lam * np.eye(len(chars))]); b2 = np.concatenate([rhs, lam * mean * np.ones(len(chars))])
        x = np.linalg.lstsq(A2, b2, rcond=None)[0]
        x = np.clip(x, mean * 0.25, mean * 2.5)
        width = {ch: x[idx[ch]] / mean for ch in chars}
        for ch in ':;.,': width[ch] = 0.3              # thin punctuation: too rare to learn, always narrow
        self.char_width = width
        self.fit_info = (len(rows), len(chars))
        return [0.0 if w == 0 else (0.5 if D[c] == ' ' else width.get(D[c], 1.0)) for c, w in enumerate(wt)]

    def _page(self, p, raw):
        W, H = self.W, self.H
        lines = []
        for y0, y1, ss in raw:
            if y0 < H * 0.09 and ss[-1][1] - ss[0][0] < W * 0.14: continue   # running page number
            lines.append([y0, y1, ss])
        self.lines[p] = [[l[0], l[1], l[2][0][0], l[2][-1][1]] for l in lines]
        segs = [(li, a, b) for li, l in enumerate(lines) for a, b in l[2]]
        def speck(q):                      # a narrow blot far from any neighbouring word
            li, a, b = segs[q]
            if b - a >= 4: return False
            near = [segs[r] for r in (q - 1, q + 1) if 0 <= r < len(segs) and segs[r][0] == li]
            return all(min(abs(a - n[2]), abs(n[1] - b)) > 25 for n in near)
        segs = [sg for q, sg in enumerate(segs) if not speck(q)]
        self.text_lines = getattr(self, 'text_lines', {})
        self.text_lines[p] = {sg[0] for sg in segs}
        s, e, D, wt = self.ps[p], self.pe[p], self.DOCN, self.wt
        toks, k = [], s
        imgs = {m.start(): m.end() for m in re.finditer(r'\[(?:ภาพ|ลายมือชื่อ)[^\]]*\]', D[s:e])}
        while k < e:
            if D[k] == ' ': k += 1; continue
            if k - s in imgs:                     # a picture in the scan: may soak up blocks
                j = imgs[k - s] + s; toks.append((k, j, 0.0, True)); k = j; continue
            j = k
            while j < e and D[j] != ' ': j += 1
            w = sum(wt[k:j])
            if w > 0: toks.append((k, j, w, False))
            k = j
        if toks and all(t[3] for t in toks): toks = []
        pos = {}
        if toks and segs:
            groups = self._align(toks, segs)
            self.found[p] = (toks, segs, groups)
            for ti, tj, si, sj in groups:
                self._place(toks[ti:tj], segs[si:sj], pos)
            self.stats[p] = self.diag
        self.pos[p] = pos

    def _align(self, toks, segs):
        n, m = len(toks), len(segs)
        TW = [0.0]; [TW.append(TW[-1] + t[2]) for t in toks]
        SW = [0.0]; [SW.append(SW[-1] + (b - a + 1)) for _, a, b in segs]
        scale = SW[m] / max(TW[n], 1.0)
        LN = [li for li, _, _ in segs]
        # how sure we are that the gap before block q is a real space (0 = maybe not, 1 = clearly)
        SURE = [1.0] + [1.0 if LN[q] != LN[q - 1] else
                        max(0.0, min(1.0, (segs[q][1] - segs[q - 1][2] - G0) / (G1 - G0))) for q in range(1, m)]
        JOIN = [0.0]                                   # cumulative cost of gluing blocks into one word
        def narrow(q): return max(0.0, min(1.0, (segs[q][2] - segs[q][1] - 4) / 16))   # single spaced-out glyphs
        for q in range(1, m): JOIN.append(JOIN[-1] + (BRK if LN[q] != LN[q - 1] else
                                                      SAME * SURE[q] * min(narrow(q), narrow(q - 1))))
        INF = float('inf')
        band = max(40, int(0.2 * max(n, m)))
        for it in range(2):
            dp = [[INF] * (m + 1) for _ in range(n + 1)]
            bk = [[None] * (m + 1) for _ in range(n + 1)]
            dp[0][0] = 0.0
            for i in range(n + 1):
                c = i * m / n
                lo, hi = max(0, int(c - band)), min(m, int(c + band))
                row = dp[i]
                for j in range(lo, hi + 1):
                    v = row[j]
                    if v == INF: continue
                    if j < m and v + 1.2 < row[j + 1]:          # block with no text (stamp, speck)
                        row[j + 1] = v + 1.2; bk[i][j + 1] = (i, j)
                    if i < n and v + 1.2 < dp[i + 1][j]:        # text with no block
                        dp[i + 1][j] = v + 1.2; bk[i + 1][j] = (i, j)
                    if i < n and toks[i][3]:
                        for b in range(0, min(m - j, 25) + 1):
                            cst = v + 0.05 * b
                            if cst < dp[i + 1][j + b]:
                                dp[i + 1][j + b] = cst; bk[i + 1][j + b] = (i, j, 'img')
                        continue
                    split = SPLIT * (1 - SURE[j]) if j < m else 0.0   # a word starting at a doubtful gap
                    for a in (1, 2, 3):
                        if i + a > n or toks[i + a - 1][3]: break
                        tw = (TW[i + a] - TW[i] + 0.5 * (a - 1)) * scale
                        for b in (1, 2, 3, 4, 5, 6):
                            if j + b > m: break
                            sw = SW[j + b] - SW[j] + (b - 1) * 4
                            pen = 0.35 * (a - 1) + (JOIN[j + b - 1] - JOIN[j]) + split
                            cst = v + abs(math.log(tw / sw)) + pen
                            if cst < dp[i + a][j + b]:
                                dp[i + a][j + b] = cst; bk[i + a][j + b] = (i, j)
            groups, i, j = [], n, m
            sk_t = sk_s = 0
            while (i, j) != (0, 0) and bk[i][j]:
                pi, pj = bk[i][j][:2]
                if len(bk[i][j]) == 3: pass
                elif pi < i and pj < j: groups.append((pi, i, pj, j))
                elif pi < i: sk_t += i - pi
                else: sk_s += j - pj
                i, j = pi, pj
            groups.reverse()
            r = sorted((SW[sj] - SW[si]) / (TW[tj] - TW[ti]) for ti, tj, si, sj in groups if tj - ti == 1 and sj - si == 1 and TW[tj] > TW[ti])
            if r: scale = r[len(r) // 2]
        self.diag = {'tok': n, 'seg': m, 'skip_tok': sk_t, 'skip_seg': sk_s,
                     'cost': round(dp[n][m] / max(1, len(groups)), 3), 'multi': sum(1 for g in groups if g[1]-g[0] > 1 or g[3]-g[2] > 1)}
        return groups

    def _place(self, toks, segs, pos):
        # strip = the blocks laid end to end; characters fill it by weight
        lens = [b - a + 1 for _, a, b in segs]
        L = sum(lens)
        units = []
        for q, (k, j, *_) in enumerate(toks):
            if q: units.append((None, 0.5))
            for c in range(k, j): units.append((c, self.wt[c]))
        tot = sum(u[1] for u in units) or 1.0
        def at(f):
            d = f * L
            for q, ((li, a, b), ln) in enumerate(zip(segs, lens)):
                if d <= ln: return q, a + d
                d -= ln
            return len(segs) - 1, segs[-1][2]
        acc = 0.0
        for c, w in units:
            q0, x0 = at(acc / tot); acc += w; q1, x1 = at(acc / tot)
            if c is None: continue
            if q1 != q0:                       # a glyph sits in one block: the one holding most of it
                if x1 - segs[q1][1] > segs[q0][2] - x0: q0, x0 = q1, segs[q1][1]
                else: x1 = segs[q0][2]
            pos[c] = (segs[q0][0], x0, x1)

    def rects(self, i, n):
        """[[page, [[x0,y0,x1,y1], ...]], ...] for DOCN[i:i+n]; None when unmapped."""
        out, j, end = [], i, i + n
        while j < end:
            p = self._page_of(j)
            stop = min(end, self.pe[p])
            r = self._rects_on(p, j, stop)
            if r: out.append([p, r])
            j = stop
        return out

    def _page_of(self, j):
        for p, s in self.ps.items():
            if s <= j < self.pe[p]: return p

    def _rects_on(self, p, a, b):
        pos, lines = self.pos[p], self.lines[p]
        idx = [c for c in range(a, b) if c in pos and self.wt[c] > 0]
        if not idx or not lines: return None
        la, xa, _ = pos[idx[0]]; lb, _, xb = pos[idx[-1]]
        if (lb, xb) < (la, xa): la, xa, lb, xb = lb, xb, la, xa
        out = []
        for li in range(la, lb + 1):
            if li not in self.text_lines[p]: continue      # a speck between lines, not text
            y0, y1, x0, x1 = lines[li]
            l, r = (xa if li == la else x0), (xb if li == lb else x1)
            if r - l > 1: out.append([round(l - 2, 1), round(y0 - 2, 1), round(r + 2, 1), round(y1 + 2, 1)])
        return out
