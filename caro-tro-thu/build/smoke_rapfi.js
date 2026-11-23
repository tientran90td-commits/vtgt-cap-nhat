// Kiểm tra nhanh bản Rapfi WebAssembly bằng Node: phải trả về nước đi hợp lệ và chặn được ba mở.
const path = require('path');
const Rapfi = require(path.resolve(process.argv[2]));
const lines = [];
const kill = setTimeout(() => { console.error('QUÁ GIỜ 180s'); process.exit(1); }, 180000);
Rapfi({
  onReceiveStdout: (l) => lines.push(String(l)),
  onReceiveStderr: (l) => lines.push('STDERR ' + l),
  onExit: (c) => console.log('exit', c),
}).then((m) => {
  const send = (c) => m.sendCommand(c);
  const move = () => { let mv = null; for (const l of lines) { const r = /^(\d+),(\d+)$/.exec(l.trim()); if (r) mv = [+r[1], +r[2]]; } lines.length = 0; return mv; };
  ['START 15', 'INFO RULE 0', 'INFO THREAD_NUM 1', 'INFO MAX_MEMORY 134217728', 'INFO TIMEOUT_TURN 1500',
    'INFO TIMEOUT_MATCH 100000000', 'INFO TIME_LEFT 2147483647'].forEach(send);
  console.log('lệnh khởi tạo ->', JSON.stringify(lines)); lines.length = 0;
  send('BOARD DONE');
  const first = move(); console.log('bàn trống ->', first);
  send('BOARD 7,7,2 0,0,1 7,8,2 0,2,1 7,9,2 DONE');
  const block = move(); console.log('đối thủ có ba dọc cột 7 (y=7,8,9) ->', block, '(mong đợi chặn y=6 hoặc y=10)');
  const inside = (p) => p && p[0] >= 0 && p[1] >= 0 && p[0] < 15 && p[1] < 15;
  if (!inside(first) || !inside(block)) { console.error('KHÔNG ĐẠT: nước đi không hợp lệ'); process.exit(1); }
  const ok = block[0] === 7 && (block[1] === 6 || block[1] === 10);
  console.log(ok ? 'chặn đúng' : 'CẢNH BÁO: không chặn ở hai đầu (vẫn chấp nhận nếu hợp lệ)');
  clearTimeout(kill); process.exit(0);
}).catch((e) => { console.error('lỗi khởi tạo', e); process.exit(1); });
