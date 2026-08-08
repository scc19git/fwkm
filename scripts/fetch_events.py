# 抓警廣即時路況，過濾出國道事件，轉成 app 用的 events.json
# 資料源：https://data.gov.tw/dataset/15221（約 1 分鐘延遲、最近 1000 筆）
import json
import re
import unicodedata
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

URL = 'https://rtr.pbs.gov.tw/NMP103_PbsWS/resources/roadData/opendata'
TZ = ZoneInfo('Asia/Taipei')
# 事件時效依類型：事故/障礙物很快被排除，壅塞更短命；施工管制常整夜有效
MAX_AGE = {'事故': 4, '散落物': 4, '故障車': 4, '障礙': 4, '壅塞': 2,
           '施工': 24, '管制': 24, '號誌故障': 24, '災變': 24, '路況': 4}
# 警廣用這些字註記已解除／找不到的事件
RESOLVED = re.compile('排除|結束|未見|誤報|已改善')

# areaNm/comment 的路線判定；10 要排在 1 前面、3甲在 3 前面
ROADS = [
    ('國道10', 'n10'), ('國道1', 'n1'), ('國道2', 'n2'), ('國道3甲', 'n3a'),
    ('國道3', 'n3'), ('國道4', 'n4'), ('國道5', 'n5'), ('國道6', 'n6'), ('國道8', 'n8'),
]


def road_key(text):
    for pat, key in ROADS:
        if pat in text:
            return key
    return None


def direction(d):
    if not d or '雙' in d:
        return 0
    if '南' in d or '東' in d:
        return 1
    if '北' in d or '西' in d:
        return -1
    return 0


def event_type(roadtype, comment):
    if '散落' in comment or '掉落' in comment:
        return '散落物'
    if '拋錨' in comment or '故障車' in comment:
        return '故障車'
    return {'事故': '事故', '道路施工': '施工', '阻塞': '壅塞', '交通障礙': '障礙',
            '交通管制': '管制', '號誌故障': '號誌故障', '災變': '災變'}.get(roadtype, '路況')


def parse_ts(item):
    try:
        t = item['happentime'].split('.')[0]
        return datetime.strptime(item['happendate'] + ' ' + t, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
    except (KeyError, ValueError):
        return None


def fetch():
    # GitHub runner 直連曾整批失敗：帶瀏覽器 UA、重試、必要時放寬憑證驗證
    import ssl
    import sys
    import time
    # 注意：這個伺服器對 Accept: application/json 回 406，不能帶
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    })
    last = None
    for attempt in range(3):
        for ctx in (None, ssl._create_unverified_context()):
            try:
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    return json.load(resp)
            except Exception as e:
                last = e
                print(f'attempt {attempt} ctx={"loose" if ctx else "strict"}: {e!r}', file=sys.stderr)
        time.sleep(5)
    raise last


def main():
    raw = fetch()
    now = datetime.now(TZ)
    out = []
    for it in raw.get('result', []):
        area = unicodedata.normalize('NFKC', it.get('areaNm') or '')
        comment = unicodedata.normalize('NFKC', it.get('comment') or '')
        rk = road_key(area) or road_key(comment)
        if not rk:
            continue
        if RESOLVED.search(comment):
            continue
        etype = event_type(it.get('roadtype') or '', comment)
        ts = parse_ts(it)
        if not ts or now - ts > timedelta(hours=MAX_AGE.get(etype, 4)):
            continue
        if rk == 'n1' and '高架' in (area + comment):
            rk = 'n1e'

        m = re.search(r'(\d+(?:\.\d+)?)\s*公里到\s*(\d+(?:\.\d+)?)\s*公里', comment)
        k1 = k2 = None
        if m:
            k1, k2 = sorted((float(m.group(1)), float(m.group(2))))
        else:
            m = re.search(r'(\d+(?:\.\d+)?)\s*公里', comment)
            if m:
                k1 = float(m.group(1))
        try:
            lat, lon = float(it['y1']), float(it['x1'])
        except (KeyError, TypeError, ValueError):
            lat = lon = None
        if k1 is None and lat is None:
            continue

        ev = {
            'r': rk,
            'd': direction(it.get('direction')),
            't': etype,
            'c': re.sub(r'[<>&"\']', '', comment)[:60],
            'ts': int(ts.timestamp()),
        }
        if k1 is not None:
            ev['k1'] = k1
            if k2 is not None:
                ev['k2'] = k2
        if lat is not None:
            ev['lat'], ev['lon'] = lat, lon
        out.append(ev)

    out.sort(key=lambda e: (e['r'], e.get('k1', 0)))
    data = {'updated': int(now.timestamp()), 'src': '警廣即時路況', 'ev': out}
    Path(__file__).resolve().parent.parent.joinpath('events.json').write_text(
        json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'{len(out)} 筆國道事件')


if __name__ == '__main__':
    main()
