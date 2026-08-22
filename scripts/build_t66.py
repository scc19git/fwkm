# 建置台66線(觀音大溪)離線資料,方法同 build_t61.py(OSM 東向幾何+官方樁號校準)
# 輸入 wiki66.json / ov66.json,輸出 t66.json
import json
import math
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
LAT_M, LON_M = 110574, 101000


def dist_m(a, b):
    return math.hypot((a[0] - b[0]) * LAT_M, (a[1] - b[1]) * LON_M)


wiki = json.load(open('wiki66.json', encoding='utf-8'))['parse']['wikitext']['*']
wiki_km = {}
for kind, km, name in re.findall(r'\{\{台灣公路(交流道|系統交流道|兩端|服務區)\|([0-9.]+)\|([^|}]+)', wiki):
    wiki_km[name.strip()] = float(km)
wiki_km['平鎮系統'] = 18.0     # 主表漏列,出口牌編號 18

d = json.load(open('ov66.json', encoding='utf-8'))
ways = {e['id']: e for e in d['elements'] if e['type'] == 'way'}
jnodes = {e['id']: e for e in d['elements'] if e['type'] == 'node'}

by_first = defaultdict(list)
last_ids = set()
for w in ways.values():
    by_first[w['nodes'][0]].append(w['id'])
    last_ids.add(w['nodes'][-1])
heads = [w['id'] for w in ways.values() if w['nodes'][0] not in last_ids]
used = set()
fragments = []
for h in heads:
    frag, wid = [], h
    while wid is not None and wid not in used:
        used.add(wid)
        frag.append(wid)
        cands = [c for c in by_first.get(ways[wid]['nodes'][-1], []) if c not in used]
        wid = cands[0] if cands else None
    fragments.append(frag)
for w in ways.values():
    if w['id'] not in used:
        fragments.append([w['id']])
        used.add(w['id'])

def frag_points(frag):
    pts = []
    for wid in frag:
        w = ways[wid]
        geo = [(g['lat'], g['lon']) for g in w['geometry']]
        ids = w['nodes']
        for i in range(1 if pts else 0, len(geo)):
            pts.append((geo[i][0], geo[i][1], ids[i] if i < len(ids) else None))
    return pts

frags = [frag_points(f) for f in fragments]
def cum(pts):
    c = [0.0]
    for i in range(1, len(pts)):
        c.append(c[-1] + dist_m(pts[i-1][:2], pts[i][:2]))
    return c
cums = [cum(p) for p in frags]

node_pos = {}
for fi, pts in enumerate(frags):
    for pi, p in enumerate(pts):
        if p[2] in jnodes:
            node_pos[p[2]] = (fi, pi)

anchors = defaultdict(dict)
for nid, n in jnodes.items():
    if nid not in node_pos:
        continue
    t = n.get('tags', {})
    short = (t.get('name') or '').replace('交流道', '').replace('端', '')
    km = wiki_km.get(short)
    if km is None:
        ref = t.get('ref') or ''
        if re.match(r'^\d+$', ref):
            km = float(ref)
        else:
            continue
    fi, pi = node_pos[nid]
    anchors[fi].setdefault(km, []).append(cums[fi][pi])

markers = []
for fi in sorted(anchors, key=lambda fi: min(anchors[fi])):
    ans = sorted((sum(v) / len(v), k) for k, v in anchors[fi].items())
    ans2 = [ans[0]]
    for off, km in ans[1:]:
        if km > ans2[-1][1] and off > ans2[-1][0]:
            ans2.append((off, km))
    pts, c = frags[fi], cums[fi]
    if len(ans2) >= 2:
        s0 = (ans2[1][0] - ans2[0][0]) / (ans2[1][1] - ans2[0][1])
        head = min(ans2[0][0], 6500)
        sl = (ans2[-1][0] - ans2[-2][0]) / (ans2[-1][1] - ans2[-2][1])
        tail = min(c[-1] - ans2[-1][0], 6500)
        ext = [(ans2[0][0] - head, ans2[0][1] - head / s0)] + ans2 + \
              [(ans2[-1][0] + tail, ans2[-1][1] + tail / sl)]
    else:
        ext = ans2
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
                tt = (target - c[pj]) / seg if seg else 0
                markers.append([round(km, 1),
                                round(pts[pj][0] + tt * (pts[pj+1][0] - pts[pj][0]), 5),
                                round(pts[pj][1] + tt * (pts[pj+1][1] - pts[pj][1]), 5)])
            km += 0.1

dedup = {}
for m in sorted(markers):
    dedup[m[0]] = m
markers = [dedup[k] for k in sorted(dedup)]

fac = []
for name, km in wiki_km.items():
    if name == '觀音':
        fac.append({'n': '觀音交流道', 'k': km, 's': '連接台61線'})
    elif name == '大溪':
        fac.append({'n': '大溪交流道', 'k': km, 's': '連接國道3號'})
    elif name == '平鎮系統':
        fac.append({'n': '平鎮系統交流道', 'k': km, 's': '連接國道1號'})
    else:
        fac.append({'n': name + '交流道', 'k': km})
fac.sort(key=lambda f: f['k'])

lats = [m[1] for m in markers]
lons = [m[2] for m in markers]
t66 = {'label': '台66線 觀音大溪', 'short': '台66', 'fwd': '東行', 'rev': '西行',
       'bbox': [round(min(lats), 4), round(max(lats), 4), round(min(lons), 4), round(max(lons), 4)],
       'markers': markers, 'fac': fac}
json.dump(t66, open('t66.json', 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
print(f'markers {len(markers)} ({markers[0][0]}K~{markers[-1][0]}K), fac {len(fac)}')
