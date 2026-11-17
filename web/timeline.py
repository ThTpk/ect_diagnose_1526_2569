"""Timeline events for the "ลำดับเวลา" view.

Every date written in the ruling (e.g. "วันที่ ๒๑ พฤษภาคม พ.ศ. ๒๕๖๗", "ระหว่างวันที่ ... ถึงวันที่ ...")
becomes one event. Its quote is taken verbatim from the document: the shortest extracted
edge / money transfer whose text contains the date, otherwise the surrounding clause.
Who took part (and so which swimlanes it appears in) comes from those edges plus the
"ผู้ถูกร้องที่ N" / "พยานรหัส" mentions inside the quote.
"""
import re, bisect, datetime, collections

TD = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
MONTHS = {'มกราคม': 1, 'กุมภาพันธ์': 2, 'มีนาคม': 3, 'เมษายน': 4, 'พฤษภาคม': 5, 'มิถุนายน': 6,
          'กรกฎาคม': 7, 'สิงหาคม': 8, 'กันยายน': 9, 'ตุลาคม': 10, 'พฤศจิกายน': 11, 'ธันวาคม': 12,
          'ม.ค.': 1, 'ก.พ.': 2, 'มี.ค.': 3, 'เม.ย.': 4, 'พ.ค.': 5, 'มิ.ย.': 6,
          'ก.ค.': 7, 'ส.ค.': 8, 'ก.ย.': 9, 'ต.ค.': 10, 'พ.ย.': 11, 'ธ.ค.': 12}
MON = '|'.join(sorted((re.escape(m) for m in MONTHS), key=len, reverse=True))
DAY = r'[๐-๙]{1,2}'
DATE = re.compile(rf'(?<![๐-๙])(?P<pre>(?:{DAY}\s*(?:,|และ|ถึง|-|–)\s*)*)(?P<d>{DAY})\s*(?P<m>{MON})\s*'
                  rf'(?:พ\.ศ\s*\.\s*)?(?P<y>[๐-๙]{{4}}(?![๐-๙]))?')
JOIN = re.compile(r'\s*(?:ถึง|–|-)\s*(?:วันที่\s*)?$')
PROC = re.compile(r'ลงวันที่|มีหนังสือ|ยื่นคำร้อง|คำร้อง|ร้องเรียน|ให้ถ้อยคำต่อ|แจ้งข้อกล่าวหา|รับเรื่อง|ประกาศคณะกรรมการ|คณะกรรมการสืบสวน')
AGENCY = re.compile(r'กกต|คณะกรรมการ|สำนักงาน|กรมสอบสวน|ผู้ร้อง|ตำรวจ|ศาล|อัยการ|ปปง|ป\.ป\.ช')

LANES = [
    {'id': 'proc', 'label': 'ผู้ร้อง · กกต. · DSI', 'sub': 'คำร้อง หนังสือ การไต่สวน'},
    {'id': 'politic', 'label': 'พรรค / นักการเมือง', 'sub': 'ผู้ดำรงตำแหน่งทางการเมือง'},
    {'id': 'national', 'label': 'ผู้ถูกร้อง', 'sub': 'ระดับประเทศ'},
    {'id': 'province', 'label': 'ผู้ถูกร้อง', 'sub': 'ระดับจังหวัด'},
    {'id': 'district', 'label': 'ผู้ถูกร้อง', 'sub': 'ระดับอำเภอ / ไม่ระบุ'},
    {'id': 'other', 'label': 'พยาน · บุคคลอื่น', 'sub': 'บริษัท และอื่น ๆ'},
]
# the turning points of the case, drawn as dashed lines across every lane (quotes located verbatim)
MILESTONES = [
    ('ประกาศกำหนดวันเลือก', '2024-05-13', 'ประกาศคณะกรรมการการเลือกตั้ง ลงวันที่ ๑๓ พฤษภาคม พ.ศ. ๒๕๖๗ เรื่อง กำหนดวันเลือกและวันรับสมัครรับเลือกสมาชิกวุฒิสภา'),
    ('เลือกระดับอำเภอ', '2024-06-09', 'กำหนดวันเลือกระดับอำเภอ วันที่ ๙ มิถุนายน พ.ศ. ๒๕๖๗'),
    ('เลือกระดับจังหวัด', '2024-06-16', 'วันเลือกระดับจังหวัด วันที่ ๑๖ มิถุนายน พ.ศ. ๒๕๖๗'),
    ('เลือกระดับประเทศ', '2024-06-26', 'วันเลือกระดับประเทศ วันที่ ๒๖ มิถุนายน พ.ศ. ๒๕๖๗'),
    ('DSI รับเรื่องไว้สืบสวน', '2024-09-25', 'กรมสอบสวนคดีพิเศษมีหนังสือ ที่ ยธ ๐๘๒๔/๔๗๕๔ ลงวันที่ ๒๕ กันยายน พ.ศ. ๒๕๖๗ ได้แจ้งการรับเรื่องไว้สืบสวน'),
    ('ออกคำวินิจฉัย', '2026-09-14', 'วันจันทร์ที่ ๑๔ กันยายน พ.ศ. ๒๕๖๙'),
]
PRI = ['action', 'testimony', 'defense', 'accusation', 'finding', 'ruling']
SUBJECT_ONLY = {'accusation', 'finding', 'ruling'}   # the accuser / กกต. did not do the dated thing


def num(s): return int(s.translate(TD))


def year_of(s):
    y = num(s)
    if 2400 < y < 2700: return y - 543
    if 1900 < y < 2100: return y
    return None


def mk(y, m, d):
    try: return datetime.date(y, m, d)
    except (ValueError, TypeError): return None


def build(DOCN, page_at, NL, hl_for, locate, edges, money, sections, resp, entities):
    NL = sorted(NL)
    R = {'R%d' % r['n']: r for r in resp}

    def lane_of(pid):
        if pid in R:
            c = R[pid]['cls']
            return c if c in ('politic', 'national', 'province') else 'district'
        if pid.startswith('O:'):
            if 'พรรค' in pid: return 'politic'
            if AGENCY.search(pid): return 'proc'
        e = entities.get(pid) or {}
        if e.get('type') == 'org' and AGENCY.search(e.get('label', '')): return 'proc'
        return 'other'

    def infer_year(p):
        for m in reversed(list(re.finditer(r'(?<![๐-๙/])[๐-๙]{4}(?![๐-๙])', DOCN[max(0, p - 900):p]))):
            y = num(m.group(0))
            if 2550 < y < 2600: return y - 543
        return 2024

    # ---- 1. every date mention, with ranges ("... ถึงวันที่ ...") merged ----
    ments = []
    for m in DATE.finditer(DOCN):
        mo = MONTHS[m.group('m')]
        y = year_of(m.group('y')) if m.group('y') else None
        explicit = y is not None
        pre = m.group('pre')
        days = [num(x) for x in re.findall(DAY, pre)] + [num(m.group('d'))]
        rng = bool(re.search(r'ถึง|-|–', pre))
        s = m.start('pre') if pre else m.start('d')
        if DOCN[max(0, s - 7):s] == 'วันที่ ': s -= 7
        elif DOCN[max(0, s - 6):s] == 'วันที่': s -= 6
        cur = {'s': s, 'e': m.end(), 'y': y, 'explicit': explicit, 'mo': mo, 'days': days, 'rng': rng}
        prev = ments[-1] if ments else None
        if prev and prev['e'] <= m.start() and JOIN.match(DOCN[prev['e']:m.start()]) and m.start() - prev['e'] < 16:
            if not prev['explicit'] and explicit:
                prev['y'] = y - (1 if prev['mo'] > mo else 0); prev['explicit'] = True
            prev['end'] = (y or prev['y'], mo, days[-1]); prev['e'] = m.end(); prev['rng'] = True
            continue
        ments.append(cur)
    for c in ments:
        if c['y'] is None: c['y'] = infer_year(c['s'])
        c['dates'] = [d for d in (mk(c['y'], c['mo'], x) for x in c['days']) if d]
        if 'end' in c:
            ey, em, ed = c['end']
            c['dates'] = c['dates'][:1] + [d for d in [mk(ey or c['y'], em, ed)] if d]
    ments = [c for c in ments if c['dates']]

    # ---- 2. what each mention is part of ----
    spans = sorted(((e['_at'][0], e['_at'][1], i) for i, e in enumerate(edges)), key=lambda t: t[0])
    starts = [t[0] for t in spans]
    mspans = [(m['_at'][0], m['_at'][1], i) for i, m in enumerate(money) if m.get('_at')]
    longest = max((b - a for a, b, _ in spans), default=0)

    def overlapping(s, e):
        lo = bisect.bisect_left(starts, s - longest)
        return [i for a, b, i in spans[lo:bisect.bisect_right(starts, e)] if a <= s and b >= e]

    def para(p):
        i = bisect.bisect_right(NL, p)
        return (NL[i - 1] + 1 if i > 0 else 0), (NL[i] if i < len(NL) else len(DOCN))

    events = []
    for c in ments:
        s, e = c['s'], c['e']
        ei = overlapping(s, e)
        mi = [i for a, b, i in mspans if a <= s and b >= e]
        # quote: the shortest extracted passage containing the date, else the clause around it
        cands = [(edges[i]['_at'], edges[i]) for i in ei] + [(money[i]['_at'], money[i]) for i in mi]
        if cands:
            (L, Rr), src = min(cands, key=lambda t: t[0][1] - t[0][0])
            text, hl = src['text'], src['hl']
        else:
            a, b = para(s)
            L = max(a, s - 170)
            if L > a:
                sp = DOCN.find(' ', L, s); L = sp + 1 if sp >= 0 else L
            Rr = min(b, e + 200)
            if Rr < b:
                sp = DOCN.rfind(' ', e, Rr); Rr = sp if sp > e else Rr
            text = DOCN[L:Rr].strip(); hl = hl_for(L, Rr - L)
        if len(text) < 12: continue
        # kind
        kinds = {edges[i]['kind'] for i in ei}
        if 'ลงวันที่' in DOCN[max(0, s - 4):s + 8]: k = 'proc'
        elif mi: k = 'money'
        else: k = next((x for x in PRI if x in kinds), None) or ('proc' if PROC.search(DOCN[max(0, s - 90):e + 40]) else 'mention')
        if k == 'ruling': k = 'finding'
        # who
        who = []
        def add(p):
            if p and p not in who and p != 'O:กกต.': who.append(p)
        for i in ei:
            x = edges[i]
            if x['kind'] not in SUBJECT_ONLY: add(x['from'])
            add(x['to'])
        for i in mi: add(money[i]['from']); add(money[i]['to'])
        # section: from the passage, else the nearest extracted statement before it
        cnt = collections.Counter([edges[i]['section'] for i in ei] + [money[i]['section'] for i in mi])
        if cnt: sec = cnt.most_common(1)[0][0]
        else:
            j = bisect.bisect_right(starts, s) - 1
            sec = edges[spans[j][2]]['section'] if j >= 0 else None
        top = sec
        while top and sections.get(top, {}).get('parent'): top = sections[top]['parent']
        for n in re.findall(r'ผู้ถูกร้องที่ ([๐-๙]+)', text):
            if 'R%d' % num(n) in R: add('R%d' % num(n))
        for a_, b_ in re.findall(r'พยานรหัส ([๐-๙]+)/([๐-๙]+)', text):
            wid = 'W:%d-%d@%s' % (num(a_), num(b_), top)
            if wid in entities: add(wid)
        lanes = []
        for p in who:
            ln = lane_of(p)
            if ln not in lanes: lanes.append(ln)
        if k == 'proc' and 'proc' not in lanes: lanes.insert(0, 'proc')
        if not lanes: lanes = ['other']
        # money: which side of the transfer each lane is on (sender / receiver / both),
        # and only the lanes of the people in the transfer itself
        ml = None
        if k == 'money':
            roles = {}
            for i in mi:
                roles.setdefault(lane_of(money[i]['from']), set()).add('out')
                roles.setdefault(lane_of(money[i]['to']), set()).add('in')
            ml = {l: ('both' if len(r) > 1 else next(iter(r))) for l, r in roles.items()}
            lanes = list(ml)
        ev = {'d': c['dates'][0].isoformat(), 'dt': DOCN[s:e], 'k': k,
              'lanes': sorted(lanes, key=[l['id'] for l in LANES].index), 'who': who[:60],
              'sec': sec, 'page': page_at[L], 'text': text, 'hl': hl}
        if len(c['dates']) > 1:
            if c['rng']: ev['d2'] = max(c['dates']).isoformat()
            else: ev['ds'] = sorted({d.isoformat() for d in c['dates']})
        if ml: ev['ml'] = ml
        if ei: ev['ei'] = ei[:40]
        if mi: ev['mi'] = mi
        events.append(ev)

    # same quote + same date twice (a date repeated inside one passage) -> one event
    seen, out = set(), []
    for ev in events:
        key = (ev['d'], ev['text'])
        if key in seen: continue
        seen.add(key); out.append(ev)
    out.sort(key=lambda ev: (ev['d'], ev['page']))

    miles = []
    for label, d, phrase in MILESTONES:
        t, p, hl = locate(phrase, None, True)
        if t is None:
            print('  timeline milestone NOT located:', label); continue
        miles.append({'label': label, 'd': d, 'text': t, 'page': p, 'hl': hl})

    by_k = collections.Counter(ev['k'] for ev in out)
    print('timeline events:', len(out), dict(by_k), '| milestones', len(miles), '/', len(MILESTONES))
    return {'lanes': LANES, 'events': out, 'milestones': miles}
