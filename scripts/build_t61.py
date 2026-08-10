# 建置台61線(西濱快速公路)離線資料:OSM 南向幾何 + 維基官方樁號校準
# 輸出 t61.json:{label, short, fwd, rev, bbox, markers:[[km,lat,lon]...], fac:[{n,k,s}...]}
import json
import math
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
LAT_M, LON_M = 110574, 101000


def dist_m(a, b):
    return math.hypot((a[0] - b[0]) * LAT_M, (a[1] - b[1]) * LON_M)


# ---------- 1. 維基交流道樁號 ----------
wiki = json.load(open('wiki61list.json', encoding='utf-8'))['parse']['wikitext']['*']
wiki_km = {}   # 短名 -> km
for kind, km, name in re.findall(r'\{\{台灣公路(交流道|系統交流道|兩端|服務區)\|([0-9.]+)\|([^|}]+)', wiki):
    wiki_km[name.strip()] = float(km)

# ---------- 2. OSM 資料 ----------
d = json.load(open('ov61.json', encoding='utf-8'))
ways = {e['id']: e for e in d['elements'] if e['type'] == 'way'}
jnodes = {e['id']: e for e in d['elements'] if e['type'] == 'node'}

# ---------- 3. 串接 chain ----------
by_first = defaultdict(list)
last_ids = set()
for w in ways.values():
    by_first[w['nodes'][0]].append(w['id'])
    last_ids.add(w['nodes'][-1])

heads = [w['id'] for w in ways.values() if w['nodes'][0] not in last_ids]
used = set()
fragments = []
for h in heads:
    frag = []
    wid = h
    while wid is not None and wid not in used:
        used.add(wid)
        frag.append(wid)
        nxt = ways[wid]['nodes'][-1]
        cands = [c for c in by_first.get(nxt, []) if c not in used]
        wid = cands[0] if cands else None
    fragments.append(frag)
# 撿漏(環狀或亂序)
for w in ways.values():
    if w['id'] not in used:
        fragments.append([w['id']])
        used.add(w['id'])

# 每個 fragment 展開成點列 (lat, lon, node_id or None)
def frag_points(frag):
    pts = []
    for wid in frag:
        w = ways[wid]
        geo = [(g['lat'], g['lon']) for g in w['geometry']]
        ids = w['nodes']
        start = 1 if pts else 0     # 避免接點重覆
        for i in range(start, len(geo)):
            pts.append((geo[i][0], geo[i][1], ids[i] if i < len(ids) else None))
    return pts

frags = [frag_points(f) for f in fragments]

# fragment 內每點的累積距離
def cum(pts):
    c = [0.0]
    for i in range(1, len(pts)):
        c.append(c[-1] + dist_m(pts[i-1][:2], pts[i][:2]))
    return c

cums = [cum(p) for p in frags]

# ---------- 4. 錨點:junction node -> (fragment, offset, km) ----------
node_pos = {}
for fi, pts in enumerate(frags):
    for pi, p in enumerate(pts):
        if p[2] in jnodes:
            node_pos[p[2]] = (fi, pi)

anchors = defaultdict(list)   # fi -> [(offset_m, km, name)]
unmatched = []
for nid, n in jnodes.items():
    if nid not in node_pos:
        unmatched.append(n.get('tags', {}).get('name'))
        continue
    t = n.get('tags', {})
    short = (t.get('name') or '').replace('交流道', '').replace('平交匝道', '')
    km = wiki_km.get(short)
    if km is None:
        ref = t.get('ref') or ''
        m = re.match(r'^(\d+)$', ref)
        if m:
            km = float(m.group(1))
        else:
            continue
    fi, pi = node_pos[nid]
    anchors[fi].append((cums[fi][pi], km, t.get('name') or ''))

# ---------- 5. fragment 排序與校準檢查 ----------
report = []
frag_order = sorted(anchors.keys(), key=lambda fi: min(a[1] for a in anchors[fi]))
markers = []
for fi in frag_order:
    ans = sorted(set(anchors[fi]))
    # 同 km 多錨點(南北出口兩個 node)→ 取平均 offset
    merged = {}
    for off, km, name in ans:
        merged.setdefault(km, []).append(off)
    ans = sorted((sum(v) / len(v), k) for k, v in merged.items())
    # 檢查單調性,剔除不合群的錨點
    ans2 = [ans[0]]
    for off, km in ans[1:]:
        po, pk = ans2[-1]
        if km <= pk or off <= po:
            report.append(f'  !剔除亂序錨點 frag{fi} km={km}')
            continue
        ratio = (off - po) / 1000 / (km - pk)
        if not 0.7 <= ratio <= 1.3:
            report.append(f'  !比例異常 frag{fi} {pk}K->{km}K chain={((off-po)/1000):.2f}km ratio={ratio:.2f}')
        ans2.append((off, km))
    pts, c = frags[fi], cums[fi]
    report.append(f'frag{fi}: 點數{len(pts)} 長{c[-1]/1000:.1f}km 錨點{len(ans2)} km範圍 {ans2[0][1]}~{ans2[-1][1]}')
    # 頭尾外插用鄰段比例
    def scale(i):
        o0, k0 = ans2[i]
        o1, k1 = ans2[i + 1]
        return (o1 - o0) / (k1 - k0)
    ext = []
    if len(ans2) >= 2:
        s0 = scale(0)
        ext.append((ans2[0][0] - min(ans2[0][0], 3000), ans2[0][1] - min(ans2[0][0], 3000) / s0))
        ext += ans2
        sl = scale(len(ans2) - 2)
        tail = min(c[-1] - ans2[-1][0], 8000)
        ext.append((ans2[-1][0] + tail, ans2[-1][1] + tail / sl))
    else:
        ext = ans2
    # 產 markers:每 0.1 官方公里一支
    for i in range(len(ext) - 1):
        o0, k0 = ext[i]
        o1, k1 = ext[i + 1]
        if k1 <= k0:
            continue
        km = math.ceil(k0 * 10) / 10
        pj = 0
        while km < k1 - 1e-9:
            target = o0 + (km - k0) / (k1 - k0) * (o1 - o0)
            while pj < len(c) - 1 and c[pj + 1] < target:
                pj += 1
            if pj < len(c) - 1:
                seg = c[pj + 1] - c[pj]
                t = (target - c[pj]) / seg if seg else 0
                la = pts[pj][0] + t * (pts[pj + 1][0] - pts[pj][0])
                lo = pts[pj][1] + t * (pts[pj + 1][1] - pts[pj][1])
                markers.append([round(km, 1), round(la, 5), round(lo, 5)])
            km += 0.1

markers.sort()
dedup = {}
for m in markers:
    dedup[m[0]] = m
markers = [dedup[k] for k in sorted(dedup)]

# ---------- 6. fac ----------
fac = []
for name, km in wiki_km.items():
    n = name + ('' if name.endswith('端') else '交流道')
    if name == '淡水':
        n = '淡水端'
    if name == '十份':
        n = '十份端'
    fac.append({'n': n, 'k': km})
for nid, n in jnodes.items():
    t = n.get('tags', {})
    nm = t.get('name') or ''
    if nm.endswith('平交匝道') and nid in node_pos:
        ref = t.get('ref') or ''
        if re.match(r'^\d+$', ref):
            fac.append({'n': nm, 'k': float(ref), 's': '平面路段'})
for n, k, s in [('新豐休息站', 58.0, '全家'), ('新埔休息站', 115.0, '安嫻小舖'), ('大安休息站', 138.0, '7-ELEVEN')]:
    fac.append({'n': n, 'k': k, 's': s})
seen = set()
fac2 = []
for f in sorted(fac, key=lambda f: f['k']):
    if f['n'] in seen:
        continue
    seen.add(f['n'])
    fac2.append(f)

lats = [m[1] for m in markers]
lons = [m[2] for m in markers]
t61 = {'label': '台61線 西濱快速公路', 'short': '台61', 'fwd': '南下', 'rev': '北上',
       'bbox': [round(min(lats), 4), round(max(lats), 4), round(min(lons), 4), round(max(lons), 4)],
       'markers': markers, 'fac': fac2}
json.dump(t61, open('t61.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))

print('\n'.join(report))
print(f'\nmarkers {len(markers)} 支({markers[0][0]}K~{markers[-1][0]}K), fac {len(fac2)} 筆, 未定位junction {len(unmatched)}')
print('檔案大小', len(json.dumps(t61, ensure_ascii=False, separators=(",", ":"))), 'bytes')
