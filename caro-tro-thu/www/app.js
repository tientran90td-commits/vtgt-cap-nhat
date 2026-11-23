/* GIAO DIỆN: nhập nước đi của ĐỐI THỦ (chạm vào bàn cờ) -> app tính và tự đặt nước của BẠN, tô sáng ô bạn cần đánh. */
(function () {
  const $ = (id) => document.getElementById(id);
  const ME = 1; // người dùng
  const OPP = 2; // đối thủ ở ngoài
  const LEVELS = { fast: { ms: 700, depth: 6, name: 'Nhanh' }, mid: { ms: 2000, depth: 8, name: 'Vừa' }, deep: { ms: 6000, depth: 10, name: 'Sâu' } };
  const SAVE = 'caroHelper.v1';

  let S = null; // trạng thái ván
  let tent = null; // ô đối thủ đang chọn (chưa xác nhận)
  let mode = 'opp'; // 'opp' = nhập nước đối thủ; 'mine' = chọn ô tôi thực sự đánh
  let thinking = false;
  let zoom = false;
  let lastAlts = [];
  let altIdx = 0;
  let worker = null;
  let reqId = 0;
  let pulse = 0;

  const colName = (x) => String.fromCharCode(65 + x);
  const cellName = (x, y) => colName(x) + (y + 1);

  // ---------- lưu / tải ----------
  function save() {
    try { localStorage.setItem(SAVE, JSON.stringify(S)); } catch (e) {}
  }
  function load() {
    try { const t = localStorage.getItem(SAVE); if (t) return JSON.parse(t); } catch (e) {}
    return null;
  }

  function newState(opts) {
    return { size: opts.size, strict: opts.strict, level: opts.level, first: opts.first, moves: [], over: null };
  }

  function engineOf() {
    return CaroEngine.fromMoves(S.size, S.strict, S.moves.map((m) => [m.x, m.y, m.p]));
  }

  // ---------- bộ não (Web Worker, nếu không được thì chạy thẳng) ----------
  function makeWorker() {
    try {
      const src = document.getElementById('engine').textContent +
        '\nself.onmessage=function(e){var d=e.data;var g=CaroEngine.fromMoves(d.size,d.strict,d.moves);var m=g.bestMove(d.p,{ms:d.ms,maxDepth:d.depth});m.id=d.id;self.postMessage(m);};';
      const url = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
      return new Worker(url);
    } catch (e) { return null; }
  }
  function think(cb) {
    const lv = LEVELS[S.level] || LEVELS.mid;
    const payload = { id: ++reqId, size: S.size, strict: S.strict, moves: S.moves.map((m) => [m.x, m.y, m.p]), p: ME, ms: lv.ms, depth: lv.depth };
    if (worker === null) worker = makeWorker() || false;
    if (worker) {
      const my = payload.id;
      worker.onmessage = (e) => { if (e.data.id === my) cb(e.data); };
      worker.onerror = () => { worker = false; setTimeout(() => think(cb), 0); };
      worker.postMessage(payload);
    } else {
      setTimeout(() => {
        const g = CaroEngine.fromMoves(S.size, S.strict, payload.moves);
        cb(g.bestMove(ME, { ms: lv.ms, maxDepth: lv.depth }));
      }, 30);
    }
  }

  // ---------- luật thắng ----------
  function checkOver() {
    const m = S.moves[S.moves.length - 1];
    if (!m) { S.over = null; return; }
    const g = engineOf();
    const line = g.winLineAt(m.x, m.y, m.p);
    S.over = line ? { who: m.p === ME ? 'me' : 'opp', line } : null;
    if (!S.over && S.moves.length >= S.size * S.size) S.over = { who: 'draw', line: null };
  }

  // ---------- vòng chơi ----------
  function startGame() {
    tent = null; mode = 'opp'; lastAlts = []; altIdx = 0;
    if (S.first === 'me') computeMine(); else { render(); save(); }
  }

  function computeMine() {
    thinking = true; render();
    think((r) => {
      thinking = false;
      S.moves.push({ x: r.x, y: r.y, p: ME, why: r.why, depth: r.depth });
      lastAlts = r.alts || [{ x: r.x, y: r.y }];
      altIdx = 0;
      checkOver();
      if (navigator.vibrate) { try { navigator.vibrate(60); } catch (e) {} }
      save(); render();
    });
  }

  function confirmOpp() {
    if (!tent || thinking || S.over || mode !== 'opp') return;
    S.moves.push({ x: tent.x, y: tent.y, p: OPP });
    tent = null;
    checkOver();
    if (S.over) { save(); render(); return; }
    computeMine();
  }

  function tapCell(x, y) {
    if (thinking || S.over) return;
    const occupied = S.moves.some((m) => m.x === x && m.y === y);
    if (occupied) return;
    if (mode === 'mine') {
      S.moves.push({ x, y, p: ME, why: 'tự chọn' });
      mode = 'opp'; lastAlts = []; altIdx = 0;
      checkOver(); save(); render();
      return;
    }
    if (tent && tent.x === x && tent.y === y) { confirmOpp(); return; } // chạm lần 2 = xác nhận
    tent = { x, y };
    render();
  }

  function altMove() {
    if (thinking || S.over || lastAlts.length < 2) return;
    const last = S.moves[S.moves.length - 1];
    if (!last || last.p !== ME) return;
    altIdx = (altIdx + 1) % lastAlts.length;
    const a = lastAlts[altIdx];
    last.x = a.x; last.y = a.y; last.why = 'gợi ý khác';
    checkOver(); save(); render();
  }

  function mineElsewhere() {
    if (thinking) return;
    const last = S.moves[S.moves.length - 1];
    if (last && last.p === ME) S.moves.pop();
    S.over = null; mode = 'mine'; tent = null; lastAlts = [];
    save(); render();
  }

  function undo() {
    if (thinking) return;
    mode = 'opp'; tent = null; lastAlts = []; S.over = null;
    // gỡ về trước nước đối thủ gần nhất
    while (S.moves.length) {
      const m = S.moves.pop();
      if (m.p === OPP) break;
    }
    checkOver(); save(); render();
    if (!S.moves.length && S.first === 'me') computeMine();
  }

  // ---------- vẽ ----------
  const cv = $('board');
  const ctx = cv.getContext('2d');
  let L = null;
  function layout() {
    const wrap = $('boardWrap');
    const base = Math.min(wrap.clientWidth, 680);
    const px = zoom ? Math.round(base * 1.8) : base;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(px * dpr); cv.height = Math.round(px * dpr);
    cv.style.width = px + 'px'; cv.style.height = px + 'px';
    const n = S.size;
    const pad = Math.round(px * 0.055);
    const cell = (px - pad * 2) / n;
    L = { px, dpr, n, pad, cell, x0: pad, y0: pad };
  }
  const cx = (x) => L.x0 + (x + 0.5) * L.cell;
  const cy = (y) => L.y0 + (L.n - 1 - y + 0.5) * L.cell;

  function drawBoard() {
    if (!L || L.n !== S.size) layout();
    const { px, dpr, n, cell } = L;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const g = ctx.createLinearGradient(0, 0, px, px);
    g.addColorStop(0, '#d9a468'); g.addColorStop(1, '#b57a3c');
    ctx.fillStyle = g; ctx.fillRect(0, 0, px, px);
    // lưới
    ctx.strokeStyle = 'rgba(40,20,5,.75)'; ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      ctx.moveTo(cx(i), cy(0)); ctx.lineTo(cx(i), cy(n - 1));
      ctx.moveTo(cx(0), cy(i)); ctx.lineTo(cx(n - 1), cy(i));
    }
    ctx.stroke();
    // nhãn
    ctx.fillStyle = '#3a2006'; ctx.font = `700 ${Math.max(8, Math.round(cell * 0.42))}px system-ui, Arial`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (let i = 0; i < n; i++) {
      ctx.fillText(colName(i), cx(i), L.y0 + n * cell + L.pad * 0.5);
      ctx.fillText(String(i + 1), L.x0 * 0.5, cy(i));
    }
    const last = S.moves[S.moves.length - 1];
    // quân đã đi
    S.moves.forEach((m, i) => {
      const X = cx(m.x), Y = cy(m.y), r = cell * 0.36;
      ctx.lineCap = 'round'; ctx.lineWidth = Math.max(2, cell * 0.12);
      if (m.p === OPP) {
        ctx.strokeStyle = '#e53935';
        ctx.beginPath(); ctx.moveTo(X - r, Y - r); ctx.lineTo(X + r, Y + r); ctx.moveTo(X + r, Y - r); ctx.lineTo(X - r, Y + r); ctx.stroke();
      } else {
        ctx.strokeStyle = '#1e7fe0';
        ctx.beginPath(); ctx.arc(X, Y, r, 0, Math.PI * 2); ctx.stroke();
      }
    });
    // nước vừa đi của đối thủ: ô vàng nhạt
    for (let i = S.moves.length - 1; i >= 0; i--) {
      if (S.moves[i].p === OPP) { const m = S.moves[i]; ctx.fillStyle = 'rgba(255,220,60,.28)'; ctx.fillRect(cx(m.x) - cell / 2, cy(m.y) - cell / 2, cell, cell); break; }
    }
    // gợi ý của bạn: vòng xanh lá nhấp nháy
    if (last && last.p === ME && !S.over) {
      const X = cx(last.x), Y = cy(last.y);
      const k = 0.5 + 0.5 * Math.sin(pulse * 5);
      ctx.fillStyle = 'rgba(61,220,132,' + (0.18 + 0.18 * k) + ')'; ctx.fillRect(X - cell / 2, Y - cell / 2, cell, cell);
      ctx.strokeStyle = '#3ddc84'; ctx.lineWidth = Math.max(2, cell * 0.1);
      ctx.beginPath(); ctx.arc(X, Y, cell * (0.55 + 0.12 * k), 0, Math.PI * 2); ctx.stroke();
    }
    // ô đối thủ đang chọn (chưa xác nhận)
    if (tent && mode === 'opp') {
      const X = cx(tent.x), Y = cy(tent.y);
      ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(X, cy(0)); ctx.lineTo(X, cy(n - 1)); ctx.moveTo(cx(0), Y); ctx.lineTo(cx(n - 1), Y); ctx.stroke();
      ctx.strokeStyle = 'rgba(229,57,53,.9)'; ctx.lineWidth = Math.max(2, cell * 0.12);
      const r = cell * 0.36;
      ctx.beginPath(); ctx.moveTo(X - r, Y - r); ctx.lineTo(X + r, Y + r); ctx.moveTo(X + r, Y - r); ctx.lineTo(X - r, Y + r); ctx.stroke();
      ctx.beginPath(); ctx.arc(X, Y, cell * 0.62, 0, Math.PI * 2); ctx.stroke();
    }
    if (mode === 'mine' && !S.over) { ctx.fillStyle = 'rgba(61,220,132,.07)'; ctx.fillRect(0, 0, px, px); }
    // đường thắng
    if (S.over && S.over.line) {
      ctx.strokeStyle = '#ffd54a'; ctx.lineWidth = Math.max(4, cell * 0.2); ctx.lineCap = 'round';
      const a = S.over.line[0], b = S.over.line[S.over.line.length - 1];
      ctx.beginPath(); ctx.moveTo(cx(a[0]), cy(a[1])); ctx.lineTo(cx(b[0]), cy(b[1])); ctx.stroke();
    }
  }

  function render() {
    const st = $('status');
    const last = S.moves[S.moves.length - 1];
    let big = '', sub = '', cls = '';
    if (S.over) {
      if (S.over.who === 'me') { big = '🎉 BẠN THẮNG!'; cls = 'me'; sub = 'Đủ 5 quân liền. Bấm "Ván mới" để chơi tiếp.'; }
      else if (S.over.who === 'opp') { big = 'Đối thủ thắng'; cls = 'opp'; sub = 'Nếu nhập nhầm nước, bấm "Lùi" để sửa.'; }
      else { big = 'Hòa'; sub = 'Bàn cờ đã đầy.'; }
    } else if (thinking) { big = '⏳ Đang tính nước đi…'; sub = 'Chờ một chút.'; }
    else if (mode === 'mine') { big = 'Chạm ô bạn đã đánh'; sub = 'Chạm vào ô trống bạn thực sự đi (thay cho gợi ý).'; cls = 'me'; }
    else if (last && last.p === ME && !tent) {
      big = '👉 Bạn đánh ô ' + cellName(last.x, last.y); cls = 'me';
      const why = last.why ? ' (' + last.why + (last.depth ? ', sâu ' + last.depth : '') + ')' : '';
      sub = 'Đánh xong, chạm vào ô đối thủ vừa đi để nhập nước tiếp theo' + why + '.';
    } else if (tent) { big = 'Đối thủ đánh ' + cellName(tent.x, tent.y) + '?'; cls = 'opp'; sub = 'Bấm "Xác nhận" hoặc chạm lại đúng ô đó.'; }
    else if (!S.moves.length) { big = S.first === 'me' ? 'Đang chuẩn bị…' : 'Đối thủ đi trước'; sub = 'Chạm vào ô đối thủ vừa đánh.'; }
    else { big = 'Chạm ô đối thủ vừa đánh'; cls = 'opp'; sub = 'Nước đối thủ ở ngoài game, nhập vào đây.'; }
    st.innerHTML = '<div class="big ' + cls + '"></div><div class="sub"></div>';
    st.firstChild.textContent = big; st.lastChild.textContent = sub;
    $('bConfirm').disabled = !(tent && mode === 'opp' && !thinking && !S.over);
    $('bAlt').disabled = !(last && last.p === ME && lastAlts.length > 1 && !thinking && !S.over);
    $('bMine').disabled = thinking || !S.moves.length || !!S.over;
    $('bUndo').disabled = thinking || !S.moves.length;
    $('bZoom').textContent = zoom ? '🔍 Thu nhỏ' : '🔍 Phóng to';
    $('legend').textContent = '✕ đỏ = đối thủ · ○ xanh = bạn · bàn ' + S.size + 'x' + S.size + ' · ' + (S.strict ? 'chặn 2 đầu không thắng' : '5 quân liền là thắng') + ' · ' + (LEVELS[S.level] || LEVELS.mid).name;
    layout(); drawBoard();
  }

  // ---------- chạm vào bàn ----------
  cv.addEventListener('click', (e) => {
    const r = cv.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left - L.x0) / L.cell);
    const y = L.n - 1 - Math.floor((e.clientY - r.top - L.y0) / L.cell);
    if (x < 0 || y < 0 || x >= L.n || y >= L.n) return;
    tapCell(x, y);
  });

  // ---------- màn hình bắt đầu ----------
  function openSetup() { $('setup').classList.remove('hidden'); }
  function begin(first) {
    S = newState({ first, size: Number($('selSize').value), strict: $('selRule').value === 'strict', level: $('selLevel').value });
    $('setup').classList.add('hidden');
    L = null; zoom = false;
    startGame();
  }
  $('goMe').onclick = () => begin('me');
  $('goOpp').onclick = () => begin('opp');
  $('bNew').onclick = openSetup;
  $('bConfirm').onclick = confirmOpp;
  $('bAlt').onclick = altMove;
  $('bMine').onclick = mineElsewhere;
  $('bUndo').onclick = undo;
  $('bZoom').onclick = () => { zoom = !zoom; L = null; render(); };
  $('bResume').onclick = () => $('setup').classList.add('hidden');
  window.addEventListener('resize', () => { if (S) { L = null; render(); } });

  // nhấp nháy ô gợi ý
  function tick(t) { pulse = t / 1000; if (S && !thinking && S.moves.length && S.moves[S.moves.length - 1].p === ME && !S.over) drawBoard(); requestAnimationFrame(tick); }

  // ---------- khởi động: khôi phục ván dở ----------
  const saved = load();
  if (saved && saved.moves && saved.size) {
    S = saved; $('selSize').value = String(S.size); $('selRule').value = S.strict ? 'strict' : 'free'; $('selLevel').value = S.level || 'mid';
    $('setup').classList.add('hidden'); $('bResume').style.display = '';
    checkOver(); render();
    if (S.first === 'me' && !S.moves.length) computeMine();
  } else {
    $('bResume').style.display = 'none';
    S = newState({ first: 'opp', size: 15, strict: false, level: 'mid' });
    layout(); drawBoard();
  }
  requestAnimationFrame(tick);
})();
