/* Cloudflare Worker：即時轉發警廣國道路況（取代 GitHub Actions 的 5~60 分鐘延遲）
   邏輯與 scripts/fetch_events.py 相同；輸出格式一致，app 換網址即可。
   邊緣快取 60 秒——路上再多人用，警廣那邊每分鐘也只會被打一次。 */

const URL_PBS = 'https://rtr.pbs.gov.tw/NMP103_PbsWS/resources/roadData/opendata';

// 10 要排在 1 前面、3甲在 3 前面
const ROADS = [
  ['國道10', 'n10'], ['國道1', 'n1'], ['國道2', 'n2'], ['國道3甲', 'n3a'],
  ['國道3', 'n3'], ['國道4', 'n4'], ['國道5', 'n5'], ['國道6', 'n6'], ['國道8', 'n8'],
];
// 事件時效（小時）：事故/障礙物很快被排除，壅塞更短命；施工管制常整夜有效
const MAX_AGE = {事故: 4, 散落物: 4, 故障車: 4, 障礙: 4, 壅塞: 2,
                 施工: 24, 管制: 24, 號誌故障: 24, 災變: 24, 路況: 4};
const RESOLVED = /排除|結束|未見|誤報|已改善/;

const roadKey = t => { for(const [p, k] of ROADS) if(t.includes(p)) return k; return null; };

function direction(d){
  if(!d || d.includes('雙')) return 0;
  if(d.includes('南') || d.includes('東')) return 1;
  if(d.includes('北') || d.includes('西')) return -1;
  return 0;
}

function eventType(roadtype, comment){
  if(/散落|掉落/.test(comment)) return '散落物';
  if(/拋錨|故障車/.test(comment)) return '故障車';
  return {事故: '事故', 道路施工: '施工', 阻塞: '壅塞', 交通障礙: '障礙',
          交通管制: '管制', 號誌故障: '號誌故障', 災變: '災變'}[roadtype] || '路況';
}

function transform(raw){
  const now = Date.now();
  const out = [];
  for(const it of raw.result || []){
    const area = (it.areaNm || '').normalize('NFKC');
    const comment = (it.comment || '').normalize('NFKC');
    let rk = roadKey(area) || roadKey(comment);
    if(!rk || RESOLVED.test(comment)) continue;
    const etype = eventType(it.roadtype || '', comment);
    const ts = Date.parse(`${it.happendate}T${(it.happentime || '').slice(0, 8)}+08:00`);
    if(!ts || now - ts > (MAX_AGE[etype] || 4) * 3600e3) continue;
    if(rk === 'n1' && (area + comment).includes('高架')) rk = 'n1e';

    let k1 = null, k2 = null;
    let m = comment.match(/(\d+(?:\.\d+)?)\s*公里到\s*(\d+(?:\.\d+)?)\s*公里/);
    if(m){
      [k1, k2] = [parseFloat(m[1]), parseFloat(m[2])].sort((a, b) => a - b);
    }else if((m = comment.match(/(\d+(?:\.\d+)?)\s*公里/))){
      k1 = parseFloat(m[1]);
    }
    const lat = parseFloat(it.y1), lon = parseFloat(it.x1);
    const hasCoord = !isNaN(lat) && !isNaN(lon);
    if(k1 === null && !hasCoord) continue;

    const ev = {r: rk, d: direction(it.direction), t: etype,
                c: comment.replace(/[<>&"']/g, '').slice(0, 60),
                ts: Math.floor(ts / 1000)};
    if(k1 !== null){ ev.k1 = k1; if(k2 !== null) ev.k2 = k2; }
    if(hasCoord){ ev.lat = lat; ev.lon = lon; }
    out.push(ev);
  }
  out.sort((a, b) => a.r < b.r ? -1 : a.r > b.r ? 1 : (a.k1 || 0) - (b.k1 || 0));
  return {updated: Math.floor(Date.now() / 1000), src: '警廣即時路況', ev: out};
}

export default {
  async fetch(request, env, ctx){
    const cache = caches.default;
    const key = new Request('https://fwkm-events.cache/v1');
    let res = await cache.match(key);
    if(!res){
      let up;
      try{
        // 注意：警廣伺服器對 Accept: application/json 回 406，不能帶
        up = await fetch(URL_PBS, {headers: {'User-Agent': 'Mozilla/5.0'}});
        if(!up.ok) throw new Error('upstream ' + up.status);
        const data = transform(await up.json());
        res = new Response(JSON.stringify(data), {headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'Access-Control-Allow-Origin': '*',
          'Cache-Control': 'public, max-age=60',
        }});
        ctx.waitUntil(cache.put(key, res.clone()));
      }catch(e){
        return new Response(JSON.stringify({error: String(e)}), {status: 502,
          headers: {'Access-Control-Allow-Origin': '*'}});
      }
    }
    return res;
  }
};
