"""Merge the extracted graph chunks, check every sentence against diagnose.md
verbatim, fix its page number, and inject the data into template.html."""
import json, re, sys, glob, os, bisect

HERE = os.path.dirname(os.path.abspath(__file__))
DOC = os.path.join(HERE, '..', 'diagnose.md')
GRAPH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'graph')   # chunk_*.json + respondents.json
OUT = os.path.join(HERE, 'index.html')

# ---------- document index: whitespace-normalised text + page offsets ----------
raw = open(DOC, encoding='utf-8').read()
norm_chars, page_at = [], []
page, prev_space = 0, True
for part in re.split(r'(<!-- page \d+ -->)', raw):
    m = re.match(r'<!-- page (\d+) -->', part)
    if m:
        page = int(m.group(1)); continue
    if page == 0:
        continue
    part = re.sub(r'(?m)^#+\s*', '', part)           # drop markdown heading marks
    part = part.replace('**', '')
    for ch in part:
        if ch.isspace():
            if prev_space: continue
            ch = ' '; prev_space = True
        else:
            prev_space = False
        norm_chars.append(ch); page_at.append(page)
DOCN = ''.join(norm_chars)

def nrm(s):
    s = re.sub(r'<!--.*?-->', ' ', s or '')
    s = s.replace('**', '')
    return re.sub(r'\s+', ' ', s).strip()

# ---------- where each character sits on its page image ----------
# Weight = how much horizontal space a character takes in the scan: Thai combining
# marks take none, placeholders like [ภาพ: ตราครุฑ] are not printed text.
COMB = set(chr(c) for c in [0x0E31] + list(range(0x0E34, 0x0E3B)) + list(range(0x0E47, 0x0E4F)))
wt = [0.0 if c in COMB or c == '—' else 0.5 if c == ' ' else 1.0 for c in DOCN]
for m in re.finditer(r'\[(?:ภาพ|ลายมือชื่อ)[^\]]*\]', DOCN):
    for i in range(m.start(), m.end()): wt[i] = 0.0
page_start, page_end = {}, {}
for i, p in enumerate(page_at):
    page_start.setdefault(p, i); page_end[p] = i + 1
cum = [0.0]
for w in wt: cum.append(cum[-1] + w)
page_W = {p: cum[page_end[p]] - cum[page_start[p]] or 1.0 for p in page_start}
def frac(i, p):
    return round((cum[i] - cum[page_start[p]]) / page_W[p], 5)

sys.path.insert(0, HERE)
from align import PageMap
PM = PageMap(DOCN, wt, page_start, page_end)
def hl_for(i, n):
    """Highlight boxes [[page, [[x0,y0,x1,y1], ...]], ...] for DOCN[i:i+n]."""
    return PM.rects(i, n)

def locate(text, hint=None, want_hl=False):
    """Return (verbatim_text, page[, highlight]) or Nones."""
    t = nrm(text)
    if len(t) < 8: return (None, None, None) if want_hl else (None, None)
    hits = [m.start() for m in re.finditer(re.escape(t), DOCN)]
    if not hits:
        return (None, None, None) if want_hl else (None, None)
    if hint:
        hits.sort(key=lambda i: abs(page_at[i] - hint))
    i = hits[0]
    return (t, page_at[i], hl_for(i, len(t))) if want_hl else (t, page_at[i])

# ---------- respondents ----------
R = json.load(open(os.path.join(GRAPH, 'respondents.json'), encoding='utf-8'))
def cls(role):
    if not role: return 'unknown'
    if 'พรรค' in role or 'ผู้ดำรงตำแหน่งทางการเมือง' in role: return 'politic'
    if 'ระดับประเทศ' in role: return 'national'
    if 'ระดับจังหวัด' in role: return 'province'
    if 'ระดับอำเภอ' in role: return 'district'
    return 'unknown'
resp = [{'n': r['n'], 'name': r['name'], 'role': r['role'], 'cls': cls(r['role'])} for r in R]
# where each respondent's own entry ("๑. พลเอก ...") sits in the list on pages 1–21
TH = str.maketrans('0123456789', '๐๑๒๓๔๕๖๗๘๙')
list_end = page_end_21 = max(i for i, p in enumerate(page_at) if p <= 21) + 1
miss = 0
for r in resp:
    key = f"{str(r['n']).translate(TH)}. {nrm(r['name'])}"
    i = DOCN.find(key, 0, list_end)
    while i > 0 and DOCN[i - 1] not in ' ':      # avoid matching "๑๑. " inside "๑๑๑. "
        i = DOCN.find(key, i + 1, list_end)
    if i < 0: miss += 1; continue
    nxt = DOCN.find(f" {str(r['n'] + 1).translate(TH)}. ", i + 1, list_end + 400)
    end = nxt if nxt > 0 else min(i + len(key) + len(r['role']) + 3, len(DOCN))
    r['page'] = page_at[i]
    r['hl'] = hl_for(i, end - i)
print('respondent list entries located:', len(resp) - miss, '/', len(resp))

# ---------- merge chunks ----------
sections, entities, edges, orders = {}, {}, [], []
for f in sorted(glob.glob(os.path.join(GRAPH, 'chunk_*.json'))):
    d = json.load(open(f, encoding='utf-8'))
    for s in d.get('sections', []):
        cur = sections.get(s['id'])
        if not cur or (not cur.get('summary') and s.get('summary')):
            sections[s['id']] = s
    for e in d.get('entities', []):
        if e['id'].startswith('R'): continue
        entities.setdefault(e['id'], e)
    edges += d.get('edges', [])
    orders += d.get('orders', [])

# ---------- verbatim check ----------
stats = {'edge_ok': 0, 'edge_bad': 0, 'page_fixed': 0, 'sum_ok': 0, 'sum_bad': 0, 'ord_ok': 0, 'ord_bad': 0}
bad_samples = []
clean_edges = []
for e in edges:
    t, p, hl = locate(e.get('text'), e.get('page'), True)
    if t is None:
        stats['edge_bad'] += 1
        bad_samples.append(('edge', e.get('section'), e.get('page'), (e.get('text') or '')[:90]))
        continue
    if p != e.get('page'): stats['page_fixed'] += 1
    stats['edge_ok'] += 1
    clean_edges.append({k: v for k, v in {
        'section': e['section'], 'from': e['from'], 'to': e['to'], 'kind': e['kind'],
        'verb': e.get('verb', ''), 'text': t, 'page': p, 'hl': hl}.items()})
for s in sections.values():
    t, p, hl = locate(s.get('summary'), (s.get('pages') or [None])[0], True)
    if s.get('summary'):
        if t: stats['sum_ok'] += 1; s['summary'], s['summaryPage'], s['summaryHl'] = t, p, hl
        else:
            stats['sum_bad'] += 1; bad_samples.append(('summary', s['id'], None, s['summary'][:90])); s['summary'] = ''
clean_orders = []
for o in orders:
    t, p, hl = locate(o.get('text'), o.get('page'), True)
    if t: stats['ord_ok'] += 1; clean_orders.append({'section': o['section'], 'text': t, 'page': p, 'hl': hl})
    else: stats['ord_bad'] += 1; bad_samples.append(('order', o.get('section'), o.get('page'), (o.get('text') or '')[:90]))

# normalise entity types to the ones the page draws
TYPE_MAP = {'witness': 'witness', 'person': 'person', 'org': 'org', 'group': 'group',
            'complainant': 'person', 'evidence': 'org', 'place': 'org', 'agency': 'org', 'company': 'org'}
for e in entities.values():
    t = e.get('type', '')
    e['type'] = TYPE_MAP.get(t, 'org' if e['id'].startswith('O:') else 'person')
    if e['id'].startswith('W:'): e['type'] = 'witness'
# the split cases hang off an umbrella "s-misc"; show each case on its own in the menu
for s in sections.values():
    if s.get('parent') == 's-misc': s['parent'] = None

# drop exact duplicates
seen, dedup = set(), []
for e in clean_edges:
    k = (e['section'], e['from'], e['to'], e['kind'], e['text'])
    if k in seen: continue
    seen.add(k); dedup.append(e)
clean_edges = dedup

# sections referenced but undefined -> create a stub titled by id
for e in clean_edges + clean_orders:
    sid = e['section']
    if sid not in sections:
        parent = sid.rsplit('/', 1)[0] if '/' in sid else None
        sections[sid] = {'id': sid, 'parent': parent, 'title': sid.split('/')[-1], 'pages': None, 'summary': ''}
for s in list(sections.values()):
    if s.get('parent') and s['parent'] not in sections:
        sections[s['parent']] = {'id': s['parent'], 'parent': None, 'title': s['parent'], 'pages': None, 'summary': ''}

# ---------- categories (table of contents) ----------
def top(sid):
    while sections[sid].get('parent'): sid = sections[sid]['parent']
    return sid
def num_key(sid):
    m = re.findall(r'\d+', sid); return [int(x) for x in m] or [0]
cats = [
    ('ข้อกล่าวหาและคำร้องที่รวมไว้', lambda s: s.startswith('intro')),
    ('ข้อกล่าวหาที่ ๑–๒ · พรรคการเมืองช่วยเหลือผู้สมัคร', lambda s: s.startswith('a12')),
    ('ข้อกล่าวหาที่ ๓–๗ · การกระทำเป็นกลุ่ม', lambda s: s.startswith('g-') or s.startswith('a37')),
    ('การกระทำรายบุคคล', lambda s: s.startswith('i-')),
    ('สำนวนที่แยกเรื่องหรือประเด็น', lambda s: s.startswith('s-')),
]
order_a12 = ['a12-plan','a12-krungsri','a12-klongsuanplu','a12-wangyao','a12-thara','a12-pinehurst','a12-srinanaporn','a12-ruling','a12-naphintorn','a12-withee','a12-pichai']
order_g = ['a37-intro','g-surat','g-uthai','g-nst','g-songkhla','g-nbl','g-singburi','g-phuket','g-ratchaburi','g-nakhonphanom','g-sukhothai']
tops = sorted({top(s) for s in sections})
categories = []
for title, pred in cats:
    ids = [s for s in tops if pred(s)]
    if title.startswith('ข้อกล่าวหาที่ ๑'): ids.sort(key=lambda s: order_a12.index(s) if s in order_a12 else 99)
    elif title.startswith('ข้อกล่าวหาที่ ๓'): ids.sort(key=lambda s: order_g.index(s) if s in order_g else 99)
    else: ids.sort(key=num_key)
    if ids: categories.append({'title': title, 'ids': ids})
# children order by first page
for s in sections.values(): s.setdefault('pages', None)

# ---------- money flow: who transferred how much to whom (graph/money.json) ----------
money, money_bad = [], []
MONEY = os.path.join(GRAPH, 'money.json')
if os.path.exists(MONEY):
    for m in json.load(open(MONEY, encoding='utf-8'))['transfers']:
        s = sections.get(m['sec'])
        if not s: money_bad.append(('section', m['sec'], m['f'], m['t'])); continue
        t, p, hl = locate(m['q'], (s.get('pages') or [None])[0], True)
        if t is None: money_bad.append(('quote', m['sec'], m['f'], m['t'], m['q'][:80])); continue
        for x in (m['f'], m['t']):
            if not x.startswith('R') and x not in entities:
                entities[x] = {'id': x, 'label': x.split(':', 1)[1].split('@')[0], 'type': 'org' if x.startswith('O:') else 'person'}
        money.append({k: v for k, v in {'from': m['f'], 'to': m['t'], 'amt': m['amt'], 'date': m.get('date'),
            'section': m['sec'], 'v': m.get('v'), 'text': t, 'page': p, 'hl': hl, 'note': m.get('note')}.items() if v is not None})
    print('money transfers located:', len(money), '/', len(money) + len(money_bad))
    for b in money_bad: print('  money NOT located:', b)

overview, ov_page, ov_hl = locate('ก่อนและหลังประกาศผลการเลือก คณะกรรมการการเลือกตั้งได้รับคำร้องและรายงานกรณีมีเหตุอันควรสงสัยหรือความปรากฏว่ามีบุคคลรวม ๔๒๗ ราย', None, True)

data = {
    'pageImg': {'w': PM.W, 'h': PM.H, 'n': len(page_start)},
    'overviewHl': ov_hl,
    'respondents': resp,
    'entities': list(entities.values()),
    'sections': sorted(sections.values(), key=lambda s: ((s.get('pages') or [999])[0], s['id'])),
    'categories': categories,
    'edges': clean_edges,
    'orders': clean_orders,
    'money': money,
    'overview': overview, 'overviewPage': ov_page,
}
js = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
html = open(os.path.join(HERE, 'template.html'), encoding='utf-8').read().replace('__DATA__', js)
open(OUT, 'w', encoding='utf-8').write(html)
json.dump(data, open(os.path.join(HERE, 'graph_data.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

kinds = {}
for e in clean_edges: kinds[e['kind']] = kinds.get(e['kind'], 0) + 1
report = {'stats': stats, 'edges': len(clean_edges), 'kinds': kinds, 'sections': len(sections),
          'entities': len(entities), 'orders': len(clean_orders), 'bytes': len(html.encode()),
          'bad_samples': bad_samples[:60], 'bad_by_section': {}}
for b in bad_samples: report['bad_by_section'][b[1]] = report['bad_by_section'].get(b[1], 0) + 1
json.dump(report, open(os.path.join(GRAPH, 'build_report.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(json.dumps({k: report[k] for k in ('stats','edges','kinds','sections','entities','orders','bytes')}))
