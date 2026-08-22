/* Cloudflare Worker：即時轉發高公局 1968 事件（每分鐘更新、只含現行有效事件）
   上游：tisvcloud.freeway.gov.tw（警廣 PBS 會擋雲端機房連線，已棄用）
   邏輯與 scripts/fetch_events.py 相同；60 秒邊緣快取。 */

const URL_1968 = 'https://tisvcloud.freeway.gov.tw/history/1min_incident_data_1968.xml';

const ROADS = {1: 'n1', 2: 'n2', 3: 'n3', 4: 'n4', 5: 'n5',
               6: 'n6', 10: 'n10', 8: 'n8', N1H: 'n1e', N3A: 'n3a', 31: 'n3a'};
const DIRS = {1: 1, 2: -1, 3: 1, 4: -1};   // 1東 2西 3南 4北；南/東=里程遞增

function eventType(tname, name){
  if(name.includes('散落')) return '散落物';
  if(name.includes('故障車')) return '故障車';
  if(tname.includes('事故') || name.includes('事故')) return '事故';
  if(name.includes('開放路肩')) return '路肩開放';
  if(tname.includes('施工') || name.includes('施工')) return '施工';
  if(tname.includes('壅塞') || name.includes('壅塞')) return '壅塞';
  if(tname.includes('管制') || name.includes('封閉')) return '管制';
  return '路況';
}

const tsOf = s => Date.parse(s.replace(' ', 'T') + '+08:00');

function transform(xml){
  const fm = xml.match(/<file_attribute[^>]*time="([^"]+)"/);
  const updated = fm ? tsOf(fm[1]) : Date.now();
  const out = [];
  for(const m of xml.matchAll(/<incident ([^>]+)>/g)){
    const a = {};
    for(const kv of m[1].matchAll(/(\w+)="([^"]*)"/g)) a[kv[1]] = kv[2];
    const rk = ROADS[a.freewayId] || {61: 't61', 66: 't66'}[a.expresswayId];
    if(!rk || a.inc_end_time) continue;
    const etype = eventType(a.inc_type_name || '', a.inc_name || '');
    if(etype === '路況' && a.inc_type_name === '天候事件') continue;  // 天候常整條路一筆，略過
    const ts = tsOf(a.inc_time || '');
    if(!ts) continue;

    let k1 = (parseInt(a.from_milepost) || 0) / 1000;
    let k2 = (parseInt(a.to_milepost) || 0) / 1000;
    if(k1 > k2) [k1, k2] = [k2, k1];
    const c = [a.inc_name, a.interchange, a.inc_location].filter(Boolean).join(' ');
    const ev = {r: rk, d: DIRS[a.directionId] || 0, t: etype,
                c: c.replace(/[<>&"']/g, '').slice(0, 60), ts: Math.floor(ts / 1000)};
    if(k2 > 0){                             // 0/0 視為無樁號，交給 app 用設施名稱比對
      ev.k1 = k1;
      if(k2 !== k1) ev.k2 = k2;
    }
    const lat = parseFloat(a.latitude), lon = parseFloat(a.longitude);
    if(!isNaN(lat) && !isNaN(lon)){ ev.lat = lat; ev.lon = lon; }
    out.push(ev);
  }
  out.sort((a, b) => a.r < b.r ? -1 : a.r > b.r ? 1 : (a.k1 || 0) - (b.k1 || 0));
  return {updated: Math.floor(updated / 1000), src: '高公局1968', ev: out};
}

/* tisvcloud 對 Cloudflare 邊緣是間歇性放行（時而 522），所以：
   重試 3 次 → 都失敗就回上次成功的備份（app 端超過 30 分鐘會自動隱藏舊資料） */
async function getUpstream(){
  for(let i = 0; i < 3; i++){
    try{
      const up = await fetch(URL_1968, {headers: {'User-Agent': 'Mozilla/5.0'}});
      if(up.ok) return await up.text();
    }catch(e){}
  }
  return null;
}

const HDRS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Access-Control-Allow-Origin': '*',
};

export default {
  async fetch(request, env, ctx){
    const cache = caches.default;
    const key = new Request('https://fwkm-events.cache/v3');
    const bak = new Request('https://fwkm-events.cache/v3-backup');
    const hit = await cache.match(key);
    if(hit) return hit;

    const xml = await getUpstream();
    if(xml){
      const body = JSON.stringify(transform(xml));
      const res = new Response(body, {headers: {...HDRS, 'Cache-Control': 'public, max-age=60'}});
      ctx.waitUntil(cache.put(key, res.clone()));
      ctx.waitUntil(cache.put(bak, new Response(body, {headers: {...HDRS, 'Cache-Control': 'public, max-age=86400'}})));
      return res;
    }
    const old = await cache.match(bak);
    if(old) return new Response(old.body, {headers: {...HDRS, 'Cache-Control': 'public, max-age=30'}});
    return new Response(JSON.stringify({error: 'upstream unreachable'}), {status: 502, headers: HDRS});
  }
};
