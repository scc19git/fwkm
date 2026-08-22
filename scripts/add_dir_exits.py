# 用 OSM 出口匝道節點(motorway_junction)為每個交流道補「方向別」出口里程:
# ks=里程遞增方向(南下/東行)出口、kn=遞減方向。判定方法:出口節點位於
# 主線行進方向的右側=該方向的出口(靠右行駛)。輸入 junctions.json(Overpass)。
import io
import json
import math
import sys

sys.stdout.reconfigure(encoding='utf-8')
LAT_M, LON_M = 110574, 101000

lines = io.open('fwkm/index.html', encoding='utf-8').read().split('\n')
fw_i = next(i for i, l in enumerate(lines) if l.startswith('const FW='))
t61_i = next(i for i, l in enumerate(lines) if l.startswith('const T61='))
t66_i = next(i for i, l in enumerate(lines) if l.startswith('const T66='))
FW = json.loads(lines[fw_i][len('const FW='):].rstrip(';'))
T61 = json.loads(lines[t61_i][len('const T61='):].rstrip(';'))
T66 = json.loads(lines[t66_i][len('const T66='):].rstrip(';'))
roads = dict(FW['roads'])
roads['t61'] = T61
roads['t66'] = T66

nodes = [e for e in json.load(open('junctions.json', encoding='utf-8'))['elements']
         if e.get('tags', {}).get('name')]
by_name = {}
for n in nodes:
    by_name.setdefault(n['tags']['name'], []).append(n)

stats = {'patched': 0, 'skipped': 0}
detail = []
for rk, r in roads.items():
    mk = r['markers']
    for f in r['fac']:
        cands = by_name.get(f['n'], [])
        sides = {1: [], -1: []}
        for n in cands:
            la, lo = n['lat'], n['lon']
            # 最近樁
            bi, bd = -1, 1e18
            for i, m in enumerate(mk):
                d = ((la - m[1]) * LAT_M) ** 2 + ((lo - m[2]) * LON_M) ** 2
                if d < bd:
                    bd, bi = d, i
            if math.sqrt(bd) > 300 or abs(mk[bi][0] - f['k']) > 3:
                continue
            m0 = mk[bi]
            # 找同一路段上里程差 0.1~0.4、距離合理的另一支樁,取得行進方向向量
            m1 = None
            for m in mk:
                dk = m[0] - m0[0]
                if 0.05 < abs(dk) < 0.45:
                    dist = math.hypot((m[1] - m0[1]) * LAT_M, (m[2] - m0[2]) * LON_M)
                    if dist < 600:
                        m1 = m if dk > 0 else None
                        if m1:
                            break
            if not m1:
                continue
            vx = (m1[2] - m0[2]) * LON_M
            vy = (m1[1] - m0[1]) * LAT_M
            wx = (lo - m0[2]) * LON_M
            wy = (la - m0[1]) * LAT_M
            cross = vx * wy - vy * wx
            side = 1 if cross < 0 else -1        # 右側=里程遞增方向的出口
            sides[side].append(mk[bi][0])
        ks = min(sides[1]) if sides[1] else None    # 順向取最先到的出口
        kn = max(sides[-1]) if sides[-1] else None
        changed = False
        if ks is not None and abs(ks - f['k']) > 0.05:
            f['ks'] = round(ks, 1)
            changed = True
        if kn is not None and abs(kn - f['k']) > 0.05:
            f['kn'] = round(kn, 1)
            changed = True
        if changed:
            stats['patched'] += 1
            detail.append(f"{rk} {f['n']} k={f['k']} ks={f.get('ks')} kn={f.get('kn')}")
        else:
            stats['skipped'] += 1

lines[fw_i] = 'const FW=' + json.dumps(FW, ensure_ascii=False, separators=(',', ':')) + ';'
lines[t61_i] = 'const T61=' + json.dumps(T61, ensure_ascii=False, separators=(',', ':')) + ';'
lines[t66_i] = 'const T66=' + json.dumps(T66, ensure_ascii=False, separators=(',', ':')) + ';'
io.open('fwkm/index.html', 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
print(f"補方向別里程 {stats['patched']} 筆,不變 {stats['skipped']} 筆")
for d in detail[:25]:
    print(' ', d)
