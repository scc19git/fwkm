# 把 t61.json 與台61測速桿整合進 fwkm/index.html
import csv
import io
import json
import math
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
LAT_M, LON_M = 110574, 101000

t61 = json.load(open('t61.json', encoding='utf-8'))
mk = t61['markers']

def nearest_km(lat, lon):
    best, bd = None, 1e18
    for m in mk:
        d = ((lat - m[1]) * LAT_M) ** 2 + ((lon - m[2]) * LON_M) ** 2
        if d < bd:
            bd, best = d, m[0]
    return best, math.sqrt(bd)

def parse_dir(s):
    if '雙' in s:
        return 0
    if re.search('[向往]南', s):
        return 1
    if re.search('[向往]北', s):
        return -1
    if s.startswith('南'):
        return 1
    if s.startswith('北'):
        return -1
    return 0

cams = []
rows = list(csv.DictReader(io.open('speedcams_all.csv', encoding='utf-8-sig')))[1:]  # 第2列是中文欄名
for r in rows:
    addr = (r['Address'] or '').strip()
    if '台61' not in addr and '西濱' not in addr:
        continue
    if '台61乙' in addr:
        continue
    lim = int(float(r['limit'] or 0))
    if not lim:
        continue
    ranges = re.findall(r'(\d+(?:\.\d+)?)\s*(?:[Kk]|公里)?\s*至\s*(\d+(?:\.\d+)?)\s*(?:[Kk]|公里)', addr)
    if ranges:
        for a, b in ranges:
            a, b = float(a), float(b)
            if not (0 <= a <= 306 and 0 <= b <= 306):
                continue
            cams.append([min(a, b), 1 if b > a else -1, lim, max(a, b)])
        continue
    m = re.search(r'(\d+(?:\.\d+)?)\s*[Kk]\s*\+\s*(\d+)\s*[mM]?', addr)
    if m:
        km = float(m.group(1)) + int(m.group(2)) / 1000
    else:
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:[Kk](?![mM])|公里)', addr)
        km = float(m.group(1)) if m else None
    d = parse_dir((r['direct'] or '').strip())
    if km is None or not 0 <= km <= 306:
        try:
            lat, lon = float(r['Latitude']), float(r['Longitude'])
        except ValueError:
            continue
        km, off = nearest_km(lat, lon)
        if off > 600:
            print(f'  跳過(離台61 {off:.0f}m): {addr[:40]}')
            continue
    else:
        # 用座標驗證樁號解析
        try:
            k2, off = nearest_km(float(r['Latitude']), float(r['Longitude']))
            if abs(k2 - km) > 3:
                print(f'  ⚠樁號{km}K 但座標對到{k2}K: {addr[:40]}')
        except ValueError:
            pass
    cams.append([round(km, 2), d, lim])

cams.sort(key=lambda c: c[0])
print(f'台61 測速 {len(cams)} 筆(含區間 {sum(1 for c in cams if len(c) > 3)} 段)')
for c in cams:
    print(' ', c)

# ---------- 寫進 index.html ----------
p = 'fwkm/index.html'
lines = io.open(p, encoding='utf-8').read().split('\n')

ci = next(i for i, l in enumerate(lines) if l.startswith('const CAMS='))
cams_obj = json.loads(lines[ci][len('const CAMS='):].rstrip(';'))
cams_obj['t61'] = cams
lines[ci] = 'const CAMS=' + json.dumps(cams_obj, separators=(',', ':')) + ';'

t61_line = 'const T61=' + json.dumps(t61, ensure_ascii=False, separators=(',', ':')) + ';'
if not any(l.startswith('const T61=') for l in lines):
    lines[ci+1:ci+1] = ['/* 台61線西濱快速公路：OSM 幾何＋官方交流道樁號校準（新編號跳號段為比例內插）；測速含區間 [k1,dir,速限,k2] */', t61_line]
else:
    ti = next(i for i, l in enumerate(lines) if l.startswith('const T61='))
    lines[ti] = t61_line

for i, l in enumerate(lines):
    if l.strip() == 'const R = FW.roads;':
        lines[i] = 'const R = FW.roads; R.t61 = T61;'
    if l.startswith("const AUTO = ['n1'") and "'t61'" not in l:
        lines[i] = l.replace("'n10']", "'n10','t61']")

io.open(p, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
print('index.html 已更新')
