# Cloudflare Worker 部署步驟（免費、約 5 分鐘）

把警廣路況改成即時轉發（延遲從 15~60 分鐘降到 1 分鐘內）。

1. 到 https://dash.cloudflare.com 註冊帳號（免費方案即可，第一次會請你取一個
   `xxx.workers.dev` 子網域名稱）。
2. 左側選 **Workers & Pages** → **Create** → **Create Worker**，
   名稱填 `fwkm-events` → **Deploy**。
3. 點 **Edit code**，把本資料夾 `worker.js` 的內容全部貼上覆蓋 → **Deploy**。
4. 複製網址（形如 `https://fwkm-events.你的子網域.workers.dev`），
   開瀏覽器貼上測試：應該回傳 `{"updated":...,"ev":[...]}`。
5. 把網址填進 `index.html` 裡的 `const EV_WORKER = ''`（引號內），
   commit 推上 GitHub 即完成。

免費額度每天 10 萬次請求；worker 有 60 秒邊緣快取，警廣端每分鐘最多被打一次。
原本的 GitHub Actions 管線可以留著當備援（app 會依序嘗試 Worker → Actions 資料）。
