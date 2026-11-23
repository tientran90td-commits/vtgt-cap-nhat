/*
 * CẦU NỐI TỚI RAPFI (engine caro mã nguồn mở, vô địch Gomocup 2024, giấy phép GPL-3).
 * https://github.com/dhbloo/rapfi  -  bản chạy trong app là WebAssembly, build trên GitHub Actions.
 * Module này chỉ lo việc nói chuyện với Rapfi. Nếu Rapfi không có / lỗi / quá giờ thì trả lỗi để app dùng bộ não nội bộ.
 * Dùng: RapfiBridge.init(onState); RapfiBridge.think({size, moves:[{x,y,p}], me, ms}, (err, {x,y,why}) => ...)
 */
(function (root) {
  // ----- đoạn chạy trong Web Worker (được chuyển thành chữ để tạo worker từ Blob) -----
  function workerMain() {
    var inst = null;
    var lines = [];
    self.onmessage = function (e) {
      var d = e.data;
      if (d.t === 'init') {
        try { importScripts(d.urls['rapfi-single.js']); } catch (err) { self.postMessage({ t: 'fail', m: 'importScripts: ' + err }); return; }
        self.Rapfi({
          locateFile: function (u) { if (/\.data$/.test(u)) return d.urls['rapfi-single.data']; if (/\.wasm$/.test(u)) return d.urls['rapfi-single.wasm']; return d.urls[u] || u; },
          onReceiveStdout: function (o) { lines.push(String(o)); },
          onReceiveStderr: function (o) { lines.push('STDERR ' + o); },
          onExit: function (c) { self.postMessage({ t: 'exit', c: c }); },
          setStatus: function (s) { self.postMessage({ t: 'status', s: s }); },
        }).then(function (m) { inst = m; self.postMessage({ t: 'ready' }); })
          .catch(function (err) { self.postMessage({ t: 'fail', m: 'init: ' + err }); });
      } else if (d.t === 'run') {
        if (!inst) { self.postMessage({ t: 'result', id: d.id, out: ['ERROR engine chưa sẵn sàng'] }); return; }
        lines = [];
        try { for (var i = 0; i < d.cmds.length; i++) inst.sendCommand(d.cmds[i]); }
        catch (err) { lines.push('ERROR ' + err); }
        var out = lines; lines = [];
        self.postMessage({ t: 'result', id: d.id, out: out });
      }
    };
  }

  const B = { state: 'idle', note: '' }; // idle | loading | ready | off
  let worker = null;
  let seq = 0;
  const waiting = {}; // id -> {cb, timer}
  let startedSize = 0;
  let onState = () => {};

  function setState(s, note) { B.state = s; B.note = note || ''; try { onState(s, B.note); } catch (e) {} }

  B.supported = function () {
    return typeof Worker === 'function' && typeof WebAssembly === 'object' && /^https?:$/.test(root.location.protocol);
  };

  /** Báo cho app biết khi trạng thái đổi: 'loading' | 'ready' | 'off' */
  B.init = function (cb) {
    if (cb) onState = cb;
    if (B.state !== 'idle') return;
    if (!B.supported()) { setState('off', 'không hỗ trợ ở chế độ này'); return; }
    setState('loading');
    const guard = setTimeout(() => { if (B.state === 'loading') B.kill('tải quá lâu'); }, 90000);
    // Tải các file engine ở luồng chính (chắc chắn đi qua app), rồi đưa cho worker dưới dạng blob:
    const base = root.location.origin + '/rapfi/';
    const files = ['rapfi-single.js', 'rapfi-single.wasm', 'rapfi-single.data'];
    Promise.all(files.map((f) => root.fetch(base + f).then((r) => { if (!r.ok) throw new Error(f + ' ' + r.status); return r.blob(); })))
      .then((blobs) => {
        if (B.state !== 'loading') return;
        const urls = {};
        files.forEach((f, i) => { urls[f] = URL.createObjectURL(blobs[i]); });
        const src = '(' + workerMain.toString() + ')();';
        worker = new Worker(URL.createObjectURL(new Blob([src], { type: 'text/javascript' })));
        worker.onmessage = (e) => {
          const d = e.data;
          if (d.t === 'ready') { clearTimeout(guard); setState('ready'); run(['INFO RULE 0', 'START 15'], 0, (err) => { if (!err) startedSize = 15; }); }
          else if (d.t === 'fail') { clearTimeout(guard); B.kill(d.m); }
          else if (d.t === 'exit') B.kill('engine thoát');
          else if (d.t === 'result') {
            const w = waiting[d.id];
            if (!w) return;
            delete waiting[d.id];
            clearTimeout(w.timer);
            w.cb(null, d.out);
          }
        };
        worker.onerror = (ev) => B.kill('lỗi worker: ' + (ev && ev.message));
        worker.postMessage({ t: 'init', urls });
      })
      .catch((err) => { clearTimeout(guard); B.kill('không tải được engine: ' + err); });
  };

  B.kill = function (why) {
    try { if (worker) worker.terminate(); } catch (e) {}
    worker = null;
    for (const id of Object.keys(waiting)) { clearTimeout(waiting[id].timer); waiting[id].cb(new Error(why || 'engine dừng'), null); delete waiting[id]; }
    setState('off', why || '');
  };

  B.usable = function (strict) { return B.state === 'ready' && !strict; };

  function run(cmds, ms, cb) {
    const id = ++seq;
    const timer = setTimeout(() => { delete waiting[id]; B.kill('quá giờ'); cb(new Error('quá giờ'), null); }, ms + 10000);
    waiting[id] = { cb, timer };
    worker.postMessage({ t: 'run', id, cmds });
  }

  /**
   * opts: { size, moves:[{x,y,p}], me (số quân của người dùng), ms }
   * Rapfi tính nước cho phe `me`. Luật: 5 quân liền là thắng (freestyle).
   */
  B.think = function (opts, cb) {
    if (B.state !== 'ready' || !worker) { cb(new Error('Rapfi chưa sẵn sàng'), null); return; }
    const cmds = [];
    if (startedSize !== opts.size) { cmds.push('START ' + opts.size); startedSize = opts.size; }
    cmds.push('INFO RULE 0', 'INFO THREAD_NUM 1', 'INFO MAX_MEMORY 134217728',
      'INFO TIMEOUT_TURN ' + opts.ms, 'INFO TIMEOUT_MATCH 100000000', 'INFO TIME_LEFT 2147483647');
    let board = 'BOARD';
    for (const m of opts.moves) board += ' ' + m.x + ',' + m.y + ',' + (m.p === opts.me ? 1 : 2);
    cmds.push(board + ' DONE');
    run(cmds, opts.ms, (err, out) => {
      if (err) { cb(err, null); return; }
      let mv = null;
      const msgs = [];
      for (const l of out) {
        const mm = /^(\d+),(\d+)$/.exec(l.trim());
        if (mm) mv = { x: +mm[1], y: +mm[2] };
        else if (/^ERROR|^STDERR/.test(l)) msgs.push(l);
      }
      if (!mv) { cb(new Error('Rapfi không trả nước đi: ' + msgs.join(' | ').slice(0, 200)), null); return; }
      const bad = mv.x < 0 || mv.y < 0 || mv.x >= opts.size || mv.y >= opts.size || opts.moves.some((m) => m.x === mv.x && m.y === mv.y);
      if (bad) { cb(new Error('Rapfi trả nước không hợp lệ ' + mv.x + ',' + mv.y), null); return; }
      cb(null, { x: mv.x, y: mv.y, why: 'Rapfi', depth: 0 });
    });
  };

  root.RapfiBridge = B;
})(typeof self !== 'undefined' ? self : this);
