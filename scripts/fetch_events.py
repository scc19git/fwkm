# 抓高公局 1968 即時事件（tisvcloud），轉成 app 用的 events.json
# 資料源：https://tisvcloud.freeway.gov.tw/history/1min_incident_data_1968.xml
# 每分鐘更新、只含現行有效事件（結束的事件會從檔案消失）。
# 先前用警廣 PBS，但其防火牆擋 Cloudflare/GitHub 機房，故改此源。
import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

URL = 'https://tisvcloud.freeway.gov.tw/history/1min_incident_data_1968.xml'
TZ = ZoneInfo('Asia/Taipei')

ROADS = {'1': 'n1', '2': 'n2', '3': 'n3', '4': 'n4', '5': 'n5',
         '6': 'n6', '8': 'n8', '10': 'n10', 'N1H': 'n1e', 'N3A': 'n3a', '31': 'n3a'}
DIRS = {'1': 1, '2': -1, '3': 1, '4': -1}   # 1東 2西 3南 4北；南/東=里程遞增


def event_type(tname, name):
    if '散落' in name:
        return '散落物'
    if '故障車' in name:
        return '故障車'
    if '事故' in tname or '事故' in name:
        return '事故'
    if '開放路肩' in name:
        return '路肩開放'
    if '施工' in tname or '施工' in name:
        return '施工'
    if '壅塞' in tname or '壅塞' in name:
        return '壅塞'
    if '管制' in tname or '封閉' in name:
        return '管制'
    return '路況'


def fetch():
    import ssl
    import sys
    import time
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    })
    last = None
    for attempt in range(3):
        for ctx in (None, ssl._create_unverified_context()):
            try:
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    return resp.read().decode('utf-8')
            except Exception as e:
                last = e
                print(f'attempt {attempt} ctx={"loose" if ctx else "strict"}: {e!r}', file=sys.stderr)
        time.sleep(5)
    raise last


def main():
    xml = fetch()
    m = re.search(r'<file_attribute[^>]*time="([^"]+)"', xml)
    updated = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ) if m else datetime.now(TZ)

    out = []
    for inc in re.findall(r'<incident ([^>]+)>', xml):
        a = dict(re.findall(r'(\w+)="([^"]*)"', inc))
        rk = ROADS.get(a.get('freewayId', ''))
        if not rk or a.get('inc_end_time'):
            continue
        etype = event_type(a.get('inc_type_name', ''), a.get('inc_name', ''))
        if etype == '路況' and a.get('inc_type_name') == '天候事件':
            continue                       # 天候常整條路一筆，佔版面，略過
        try:
            ts = int(datetime.strptime(a['inc_time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ).timestamp())
        except (KeyError, ValueError):
            continue

        k1 = int(a.get('from_milepost') or 0) / 1000
        k2 = int(a.get('to_milepost') or 0) / 1000
        k1, k2 = sorted((k1, k2))
        c = ' '.join(x for x in (a.get('inc_name'), a.get('interchange'), a.get('inc_location')) if x)
        ev = {'r': rk, 'd': DIRS.get(a.get('directionId', ''), 0), 't': etype,
              'c': re.sub(r'[<>&"\']', '', c)[:60], 'ts': ts}
        if k2 > 0:                          # 0/0 視為無樁號，交給 app 用設施名稱比對
            ev['k1'] = k1
            if k2 != k1:
                ev['k2'] = k2
        try:
            ev['lat'], ev['lon'] = float(a['latitude']), float(a['longitude'])
        except (KeyError, ValueError):
            pass
        out.append(ev)

    out.sort(key=lambda e: (e['r'], e.get('k1', 0)))
    data = {'updated': int(updated.timestamp()), 'src': '高公局1968', 'ev': out}
    Path(__file__).resolve().parent.parent.joinpath('events.json').write_text(
        json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(out)} 筆國道事件')


if __name__ == '__main__':
    main()
