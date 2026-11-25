/*
 * NỐI GAME: app nối thẳng vào Caro LIVE đang chạy (WebSocket), tự hiện bàn cờ + tên/avatar 2 người chơi.
 * Bạn chọn "Tôi là ai" -> tới lượt bạn thì app tự tính và tô sáng ô nên đánh (không phải nhập tay).
 * Module này độc lập với chế độ "Tự nhập" (app.js). Dùng bộ não CaroEngine / RapfiBridge sẵn có.
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const KEY = 'caroLink.v1';
  const LEVELS = { fast: { ms: 700, depth: 6 }, mid: { ms: 2000, depth: 8 }, deep: { ms: 6000, depth: 10 } };
  const PHASE = {
    lobby: 'Đang chờ người chơi',
    confirm: 'Đang xác nhận người chơi',
    coin: 'Tung đồng xu chọn bên đi trước',
    playing: 'Đang đánh',
    finished: 'Ván vừa kết thúc',
  };
  const cellName = (x, y) => String.fromCharCode(65 + x) + (y + 1);

  let cfg = { addr: '', code: '', level: 'mid', me: null, bubble: false };
  try { Object.assign(cfg, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(cfg)); } catch (e) {} };

  let ws = null;
  let st = null; // trạng thái game mới nhất
  let lastMsg = 0; // lần cuối nhận tin từ game (để phát hiện kết nối "treo" khi sang app khác rồi quay lại)
  let base = ''; // http://địa-chỉ:cổng
  let everOpen = false;
  let retry = null;
  let zoom = false;
  let hint = null; // { key, x, y, alts, nhay:{list, idx}, busy }
  let reqId = 0;
  let worker = null;
  let nhayWorker = null;
  let pulse = 0;
  let L = null; // bố cục bàn cờ

  // ---------- kết nối ----------
  function normAddr(a) {
    a = String(a || '').trim().replace(/^https?:\/\//i, '').replace(/^wss?:\/\//i, '').replace(/\/.*$/, '');
    if (a && !/:\d+$/.test(a)) a += ':3000';
    return a;
  }
  function connect() {
    clearTimeout(retry);
    if (ws) { try { ws.onclose = null; ws.close(); } catch (e) {} ws = null; }
    const addr = normAddr(cfg.addr);
    if (!addr) { showConnect(true, 'Nhập địa chỉ máy đang chạy game.'); return; }
    base = 'http://' + addr;
    setChip('off', 'Đang nối…');
    try {
      ws = new WebSocket('ws://' + addr + '/' + (cfg.code ? '?code=' + encodeURIComponent(cfg.code) : ''));
    } catch (e) { setChip('off', 'Địa chỉ không đúng'); return; }
    const mine = ws;
    lastMsg = Date.now();
    ws.onopen = () => { everOpen = true; lastMsg = Date.now(); setChip('on', 'Đã nối game'); showConnect(false); };
    ws.onmessage = (e) => {
      if (mine !== ws) return;
      lastMsg = Date.now();
      try { st = JSON.parse(e.data); } catch (err) { return; }
      onState();
    };
    ws.onclose = () => {
      if (mine !== ws) return;
      setChip('off', 'Mất kết nối, đang thử lại…');
      if (!everOpen) showConnect(true, 'Chưa nối được. Kiểm tra: game đang chạy? điện thoại cùng WiFi (hoặc cùng Tailscale)? đã bấm "Bật kết nối qua WiFi" trong bảng điều khiển và mở lại game? đúng mã 6 số?');
      retry = setTimeout(connect, 2500);
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }
  function setChip(kind, text) {
    const c = $('lkChip');
    c.className = 'chip ' + kind;
    c.textContent = text;
  }
  function showConnect(on, msg) {
    $('lkConn').classList.toggle('hidden', !on);
    if (msg !== undefined) $('lkConnMsg').textContent = msg;
  }

  // ---------- ai là tôi ----------
  function players() {
    const p = (st && st.players) || {};
    return { X: p.X || null, O: p.O || null };
  }
  function myMark() {
    if (!cfg.me || !st) return null;
    const p = players();
    for (const m of ['X', 'O']) if (p[m] && (p[m].id === cfg.me.id)) return m;
    return null;
  }
  function fillMe() {
    const sel = $('lkMe');
    const p = players();
    const seen = new Set();
    const opts = [['', '— Chưa chọn —']];
    const add = (id, name, tag) => {
      if (!id || seen.has(id)) return;
      seen.add(id);
      opts.push([id, (tag ? tag + ' ' : '') + name]);
    };
    if (p.X) add(p.X.id, p.X.name, '✕ (đỏ)');
    if (p.O) add(p.O.id, p.O.name, '◯ (xanh)');
    if (st && st.lobby && st.lobby.preview) for (const v of st.lobby.preview) add(v.id, v.name, '');
    if (st && st.top) for (const v of st.top) add(v.id, v.name, '');
    if (cfg.me && !seen.has(cfg.me.id)) add(cfg.me.id, cfg.me.name, '(đã chọn)');
    const sig = JSON.stringify(opts) + '|' + (cfg.me ? cfg.me.id : '');
    if (sel.dataset.sig === sig) return;
    sel.dataset.sig = sig;
    sel.innerHTML = '';
    for (const [v, t] of opts) {
      const o = document.createElement('option');
      o.value = v;
      o.textContent = t;
      sel.appendChild(o);
    }
    sel.value = cfg.me ? cfg.me.id : '';
  }

  // ---------- bộ não ----------
  const strictRule = () => !!(st && st.settings && st.settings.blockBothEnds);
  function makeWorker(kind) {
    try {
      const eng = document.getElementById('engine').textContent;
      const tail = kind === 'nhay'
        ? '\nself.onmessage=function(e){var d=e.data;var g=CaroEngine.fromMoves(d.size,d.strict,d.moves);var l=g.nhay(d.p,{ms:d.ms,lastOpp:d.lastOpp,max:4});self.postMessage({id:d.id,list:l});};'
        : '\nself.onmessage=function(e){var d=e.data;var g=CaroEngine.fromMoves(d.size,d.strict,d.moves);var m=g.bestMove(d.p,{ms:d.ms,maxDepth:d.depth});m.id=d.id;self.postMessage(m);};';
      return new Worker(URL.createObjectURL(new Blob([eng + tail], { type: 'text/javascript' })));
    } catch (e) { return null; }
  }
  function think(size, strict, moves, p, cb) {
    const lv = LEVELS[cfg.level] || LEVELS.mid;
    const id = ++reqId;
    const done = (r) => { if (id === reqId) cb(r); };
    if (window.RapfiBridge && RapfiBridge.usable(strict)) {
      RapfiBridge.think({ size, moves: moves.map((m) => ({ x: m[0], y: m[1], p: m[2] })), me: p, ms: lv.ms }, (err, r) => {
        if (id !== reqId) return;
        if (err || !r) { thinkJs(id, size, strict, moves, p, lv, done); return; }
        const alts = [{ x: r.x, y: r.y }];
        try {
          const g = CaroEngine.fromMoves(size, strict, moves);
          for (const [c] of g.candidates(p, 6)) { const ax = c % size, ay = (c / size) | 0; if (!(ax === r.x && ay === r.y) && alts.length < 4) alts.push({ x: ax, y: ay }); }
        } catch (e) {}
        r.alts = alts;
        done(r);
      });
      return;
    }
    thinkJs(id, size, strict, moves, p, lv, done);
  }
  function thinkJs(id, size, strict, moves, p, lv, done) {
    const payload = { id, size, strict, moves, p, ms: lv.ms, depth: lv.depth };
    if (worker === null) worker = makeWorker('best') || false;
    if (worker) {
      worker.onmessage = (e) => { if (e.data.id === id) done(e.data); };
      worker.onerror = () => { worker = false; setTimeout(() => thinkJs(id, size, strict, moves, p, lv, done), 0); };
      worker.postMessage(payload);
    } else {
      setTimeout(() => done(CaroEngine.fromMoves(size, strict, moves).bestMove(p, { ms: lv.ms, maxDepth: lv.depth })), 30);
    }
  }
  function runNhay(payload, cb) {
    if (nhayWorker === null) nhayWorker = makeWorker('nhay') || false;
    if (nhayWorker) {
      nhayWorker.onmessage = (e) => { if (e.data.id === payload.id) cb(e.data.list || []); };
      nhayWorker.onerror = () => { nhayWorker = false; cb([]); };
      nhayWorker.postMessage(payload);
    } else {
      try { cb(CaroEngine.fromMoves(payload.size, payload.strict, payload.moves).nhay(payload.p, { ms: payload.ms, lastOpp: payload.lastOpp, max: 4 })); } catch (e) { cb([]); }
    }
  }

  // ---------- mỗi khi game gửi trạng thái ----------
  function movesOf() {
    return ((st && st.moves) || []).map((m) => [m.x, m.y, m.m === 'X' ? 1 : 2]);
  }
  function onState() {
    fillMe();
    // tự nhận ra tôi khi đã chọn tên: nhớ tên mới nhất
    const mm = myMark();
    if (mm) { const pl = players()[mm]; if (pl && cfg.me.name !== pl.name) { cfg.me.name = pl.name; save(); } }
    const want = mm && st.phase === 'playing' && !st.result && st.turn === mm;
    const key = want ? st.gameNo + ':' + st.moves.length + ':' + mm : null;
    if (!want) { if (hint) { reqId++; hint = null; } }
    else if (!hint || hint.key !== key) {
      const mine = { key, x: -1, y: -1, alts: [], nhay: { list: [], idx: -1 }, busy: true };
      hint = mine;
      const p = mm === 'X' ? 1 : 2;
      const size = st.size;
      const strict = strictRule();
      const moves = movesOf();
      think(size, strict, moves, p, (r) => {
        if (hint !== mine || !r) return;
        mine.busy = false;
        mine.x = r.x; mine.y = r.y; mine.alts = r.alts || [{ x: r.x, y: r.y }]; mine.altIdx = 0;
        mine.shown = { x: r.x, y: r.y };
        if (navigator.vibrate) { try { navigator.vibrate(80); } catch (e) {} }
        render();
        let lastOpp = -1;
        for (let i = moves.length - 1; i >= 0; i--) if (moves[i][2] !== p) { lastOpp = moves[i][1] * size + moves[i][0]; break; }
        runNhay({ id: reqId, size, strict, moves, p, ms: 1400, lastOpp }, (list) => {
          if (hint !== mine) return;
          mine.nhay.list = list.filter((k) => !(k.x === mine.x && k.y === mine.y));
          render();
        });
      });
    }
    render();
  }

  // ---------- giao diện ----------
  function avatarUrl(a) {
    if (!a) return '';
    return /^https?:/i.test(a) ? a : base + a;
  }
  function renderPlayers() {
    const p = players();
    const mm = myMark();
    for (const m of ['X', 'O']) {
      const box = $('lkP' + m);
      const v = p[m];
      box.classList.toggle('turn', !!(v && st.phase === 'playing' && !st.result && st.turn === m));
      box.classList.toggle('me', mm === m);
      const img = box.querySelector('img');
      const nm = box.querySelector('.nm');
      const rk = box.querySelector('.rk');
      if (v) {
        const u = avatarUrl(v.avatar);
        if (u && img.getAttribute('src') !== u) img.src = u;
        img.style.visibility = u ? 'visible' : 'hidden';
        nm.textContent = v.name + (mm === m ? ' (Tôi)' : '');
        rk.textContent = (m === 'X' ? '✕ đỏ' : '◯ xanh') + (v.rank ? ' · ' + v.rank.name : '');
      } else {
        img.style.visibility = 'hidden';
        nm.textContent = 'Chưa có người';
        rk.textContent = m === 'X' ? '✕ đỏ' : '◯ xanh';
      }
    }
  }
  function renderStatus() {
    const big = $('lkBig');
    const sub = $('lkSub');
    big.className = 'big';
    if (!st) { big.textContent = 'Chưa nối game'; sub.textContent = 'Nhập địa chỉ và bấm Kết nối.'; return; }
    const mm = myMark();
    const p = players();
    const phaseTxt = PHASE[st.phase] || st.phase;
    if (st.phase === 'playing' && !st.result) {
      if (!cfg.me) { big.textContent = 'Chọn tên của bạn ↑'; sub.textContent = 'Chọn "Tôi là" để app gợi ý nước đi cho bạn.'; return; }
      if (!mm) { big.textContent = 'Bạn không ở trong ván này'; sub.textContent = 'Ván hiện tại: ' + (p.X ? p.X.name : '?') + ' gặp ' + (p.O ? p.O.name : '?') + '. Vẫn xem được bàn cờ.'; return; }
      if (st.turn === mm) {
        if (!hint || hint.busy) { big.textContent = '⏳ Đang tính nước đi…'; sub.textContent = 'Chờ một chút.'; return; }
        const nh = hint.nhay.idx >= 0 ? hint.nhay.list[hint.nhay.idx] : null;
        const c = nh || hint.shown || hint;
        big.className = 'big ' + (nh ? 'nhay' : 'me');
        big.textContent = (nh ? '😜 Nhây: bạn đánh ô ' : '👉 Bạn đánh ô ') + cellName(c.x, c.y);
        sub.textContent = nh ? 'Máy đã kiểm tra: dù họ đáp thế nào bạn vẫn thắng.' : 'Gõ ô này vào bình luận để đánh. Còn ' + Math.max(0, Math.ceil((st.turnEndsAt - Date.now()) / 1000)) + ' giây (ước tính).';
        return;
      }
      const opp = p[mm === 'X' ? 'O' : 'X'];
      big.className = 'big opp';
      big.textContent = '⏳ ' + (opp ? opp.name : 'Đối thủ') + ' đang nghĩ…';
      sub.textContent = 'Tới lượt bạn app sẽ tự gợi ý.';
      return;
    }
    if (st.phase === 'finished' && st.result) {
      const w = st.result.winner;
      big.textContent = w ? '🏆 ' + (p[w] ? p[w].name : w) + ' thắng' : 'Ván hòa';
      sub.textContent = phaseTxt + '.';
      return;
    }
    big.textContent = phaseTxt;
    sub.textContent = st.phase === 'lobby' ? 'Chưa đủ người chơi. App sẽ tự hiện khi ván bắt đầu.' : '';
  }
  function layout() {
    const wrap = $('lkWrap');
    const n = (st && st.size) || 15;
    const m = 22; // lề cho chữ cột/hàng
    const avail = Math.max(240, wrap.clientWidth - 2);
    const cell = zoom ? Math.max(34, Math.floor((avail - m * 2) / n)) : Math.floor((avail - m * 2) / n);
    const px = cell * n + m * 2;
    L = { n, cell, m, px };
    const c = $('lkBoard');
    const dpr = window.devicePixelRatio || 1;
    c.style.width = px + 'px';
    c.style.height = px + 'px';
    c.width = Math.round(px * dpr);
    c.height = Math.round(px * dpr);
    L.dpr = dpr;
  }
  function drawBoard() {
    if (!st) return;
    if (!L || L.n !== st.size) layout();
    const c = $('lkBoard');
    const ctx = c.getContext('2d');
    const { n, cell, m, px, dpr } = L;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#d9b873';
    ctx.fillRect(0, 0, px, px);
    ctx.strokeStyle = 'rgba(60,40,10,.75)';
    ctx.lineWidth = 1;
    const C = (v) => m + cell * v + cell / 2; // tâm ô theo chỉ số
    // Lưới theo Ô VUÔNG (giống bàn trên màn hình LIVE): vạch kẻ là viền ô, quân cờ nằm GIỮA ô.
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const e = m + cell * i;
      ctx.moveTo(e, m); ctx.lineTo(e, m + cell * n);
      ctx.moveTo(m, e); ctx.lineTo(m + cell * n, e);
    }
    ctx.stroke();
    ctx.fillStyle = 'rgba(40,25,5,.85)';
    ctx.font = '600 ' + Math.max(9, Math.min(13, cell * 0.45)) + 'px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < n; i++) {
      ctx.fillText(String.fromCharCode(65 + i), C(i), m * 0.45);
      ctx.fillText(String.fromCharCode(65 + i), C(i), px - m * 0.45);
      const ry = C(n - 1 - i); // hàng 1 ở dưới cùng, giống bàn cờ trên màn hình LIVE
      ctx.fillText(String(i + 1), m * 0.45, ry);
      ctx.fillText(String(i + 1), px - m * 0.45, ry);
    }
    const P = (x, y) => [C(x), C(n - 1 - y)];
    const r = cell * 0.36;
    const list = st.moves || [];
    for (const mv of list) {
      const [cx, cy] = P(mv.x, mv.y);
      if (mv.m === 'X') {
        ctx.strokeStyle = '#e23b3b'; ctx.lineWidth = Math.max(2.5, cell * 0.14); ctx.lineCap = 'round';
        ctx.beginPath(); ctx.moveTo(cx - r, cy - r); ctx.lineTo(cx + r, cy + r); ctx.moveTo(cx + r, cy - r); ctx.lineTo(cx - r, cy + r); ctx.stroke();
      } else {
        ctx.strokeStyle = '#1f78e0'; ctx.lineWidth = Math.max(2.5, cell * 0.14);
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      }
    }
    const last = list[list.length - 1];
    if (last) {
      const [cx, cy] = P(last.x, last.y);
      ctx.fillStyle = '#ffd54a'; ctx.beginPath(); ctx.arc(cx, cy, Math.max(3, cell * 0.12), 0, Math.PI * 2); ctx.fill();
    }
    // ô gợi ý (nhấp nháy)
    if (hint && !hint.busy) {
      const nh = hint.nhay.idx >= 0 ? hint.nhay.list[hint.nhay.idx] : null;
      const c2 = nh || hint.shown;
      if (c2) {
        const [cx, cy] = P(c2.x, c2.y);
        const a = 0.55 + 0.45 * Math.sin(pulse * 5);
        ctx.strokeStyle = nh ? 'rgba(197,139,255,' + a + ')' : 'rgba(61,220,132,' + a + ')';
        ctx.fillStyle = nh ? 'rgba(197,139,255,.25)' : 'rgba(61,220,132,.28)';
        ctx.lineWidth = Math.max(3, cell * 0.14);
        ctx.beginPath(); ctx.arc(cx, cy, cell * 0.46, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        ctx.fillStyle = nh ? '#7b3fc4' : '#0f7a3f';
        ctx.font = '900 ' + Math.max(10, cell * 0.5) + 'px system-ui, sans-serif';
        ctx.fillText('★', cx, cy + 1);
      }
    }
  }
  function render() {
    renderPlayers();
    renderStatus();
    const mm = myMark();
    const ready = !!(hint && !hint.busy);
    $('lkAlt').disabled = !(ready && hint.alts.length > 1);
    $('lkNhay').disabled = !(ready && hint.nhay.list.length);
    $('lkPhase').textContent = st ? '#' + st.gameNo + ' · ' + (PHASE[st.phase] || st.phase) : '';
    $('lkMeHint').textContent = cfg.me ? (mm ? 'Bạn đang ở bên ' + (mm === 'X' ? '✕ đỏ' : '◯ xanh') : 'Bạn chưa vào bàn — khi được chọn app tự nhận ra.') : '';
    drawBoard();
    syncBubble();
  }
  function altMove() {
    if (!hint || hint.busy || hint.alts.length < 2) return;
    hint.nhay.idx = -1;
    hint.altIdx = (hint.altIdx + 1) % hint.alts.length;
    hint.shown = { x: hint.alts[hint.altIdx].x, y: hint.alts[hint.altIdx].y };
    render();
  }
  function nhayPress() {
    if (!hint || hint.busy || !hint.nhay.list.length) return;
    hint.nhay.idx++;
    if (hint.nhay.idx >= hint.nhay.list.length) hint.nhay.idx = -1;
    render();
  }

  // ---------- BONG BÓNG NỔI (chỉ có trong app Android: cầu nối AndroidBubble) ----------
  // Tới lượt bạn: bong bóng bật ra "tin nhắn" hiện toạ độ, nổi trên TikTok/app khác. Tới lượt đối thủ thì thu lại.
  let lastBubble = '';
  function bubbleSend(kind, small, big) {
    const nb = window.AndroidBubble;
    if (!nb || !cfg.bubble) return;
    const key = kind + '|' + small + '|' + big;
    if (key === lastBubble) return;
    lastBubble = key;
    try { if (kind === 'idle') nb.idle(); else nb.show(small, big, kind); } catch (e) {}
  }
  function syncBubble() {
    if (!window.AndroidBubble || !cfg.bubble) return;
    const mm = st ? myMark() : null;
    if (mm && st.phase === 'playing' && !st.result && st.turn === mm) {
      if (!hint || hint.busy) { bubbleSend('info', 'Đang tính nước đi…', '⏳'); return; }
      const nh = hint.nhay.idx >= 0 ? hint.nhay.list[hint.nhay.idx] : null;
      const c = nh || hint.shown || hint;
      bubbleSend(nh ? 'nhay' : 'me', nh ? '😜 Nhây: bạn đánh ô' : '👉 Bạn đánh ô', cellName(c.x, c.y));
      return;
    }
    bubbleSend('idle', '', '');
  }
  function toggleBubble() {
    const nb = window.AndroidBubble;
    if (!nb) return;
    if (cfg.bubble) {
      cfg.bubble = false; save();
      try { nb.disable(); } catch (e) {}
    } else {
      let r = 'fail';
      try { r = nb.enable(); } catch (e) {}
      if (r === 'ok') { cfg.bubble = true; lastBubble = ''; save(); }
      else {
        $('lkBig').className = 'big';
        $('lkBig').textContent = 'Cần cấp quyền cho bong bóng';
        $('lkSub').textContent = 'Màn hình cài đặt vừa mở: bật "Hiển thị trên các ứng dụng khác" cho Caro Trợ Thủ, rồi quay lại và bấm 🫧 lần nữa.';
      }
    }
    bubbleLabel();
    syncBubble();
  }
  function bubbleLabel() { $('lkBubble').textContent = '🫧 Bong bóng: ' + (cfg.bubble ? 'Bật' : 'Tắt'); }

  // ---------- khởi tạo ----------
  function bind() {
    $('lkAddr').value = cfg.addr;
    $('lkCode').value = cfg.code;
    $('lkLevel').value = cfg.level;
    $('lkGo').onclick = () => {
      cfg.addr = normAddr($('lkAddr').value);
      cfg.code = $('lkCode').value.trim();
      cfg.level = $('lkLevel').value;
      $('lkAddr').value = cfg.addr;
      save();
      everOpen = false;
      connect();
    };
    $('lkSettings').onclick = () => showConnect(true, '');
    $('lkMe').onchange = () => {
      const id = $('lkMe').value;
      if (!id) cfg.me = null;
      else {
        const o = $('lkMe').selectedOptions[0];
        cfg.me = { id, name: o ? o.textContent.replace(/^(✕ \(đỏ\)|◯ \(xanh\)|\(đã chọn\))\s*/, '') : id };
      }
      save();
      hint = null; reqId++;
      onState();
    };
    if (window.AndroidBubble) {
      $('lkBubble').classList.remove('hidden');
      if (cfg.bubble) { let r = 'fail'; try { r = window.AndroidBubble.enable(); } catch (e) {} if (r !== 'ok') cfg.bubble = false; }
      bubbleLabel();
      $('lkBubble').onclick = toggleBubble;
    }
    $('lkAlt').onclick = altMove;
    $('lkNhay').onclick = nhayPress;
    $('lkZoom').onclick = () => { zoom = !zoom; $('lkZoom').textContent = zoom ? '🔍 Thu nhỏ' : '🔍 Phóng to'; L = null; render(); };
    window.addEventListener('resize', () => { L = null; if (st) drawBoard(); });
    // Giữ kết nối "sống": game gửi tin ít nhất 1,5 giây/lần. Quá 5 giây im lặng (điện thoại ngủ, đổi mạng...) thì nối lại ngay.
    const revive = () => { if (cfg.addr && ws && Date.now() - lastMsg > 5000) connect(); };
    setInterval(revive, 2000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) { lastMsg = 0; revive(); } });
    window.addEventListener('online', () => { lastMsg = 0; revive(); });
    window.addEventListener('focus', revive);
    const tick = (t) => { pulse = t / 1000; if (hint && !hint.busy && $('viewLink').classList.contains('on')) drawBoard(); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    setInterval(() => { if (st && hint && !hint.busy && $('viewLink').classList.contains('on')) renderStatus(); }, 1000);
    // bảng điều khiển trong app
    window.LinkApp = {
      panelUrl() {
        const a = normAddr(cfg.addr);
        return a ? 'http://' + a + '/' + (cfg.code ? '?code=' + encodeURIComponent(cfg.code) : '') : '';
      },
      relayout() { L = null; if (st) render(); },
    };
    if (cfg.addr) { showConnect(false); connect(); } else showConnect(true, 'Nhập địa chỉ máy đang chạy game (xem trong bảng điều khiển, thẻ "Kết nối app Caro Trợ Thủ").');
  }
  bind();
})();
