/*
 * KIỂU BÀN CỜ + ĐÈN LED CHẠY Ở ĐƯỜNG KẺ.
 * File này chỉ lo phần "trang trí": hoa văn nền (rồng, tứ linh, công nghệ...) và đèn LED chạy.
 * Muốn thêm kiểu mới: thêm 1 mục vào SKINS (copy mục gần giống rồi đổi màu / đổi hàm vẽ hoa văn).
 *
 * QUY TẮC ĐỂ QUÂN X (đỏ) VÀ O (xanh) LUÔN DỄ NHÌN:
 *  - Vùng ô cờ luôn được phủ 1 lớp "tấm nền" tối (plate) nên hoa văn chỉ hiện mờ phía sau.
 *  - Quân có viền sáng mỏng (halo) nên nổi trên mọi nền.
 *  - Đèn LED và vạch kẻ không dùng màu đỏ thuần / xanh dương thuần giống quân cờ.
 */

function rngOf(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const hash = (n) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const TAU = Math.PI * 2;

// ------------------------------------------------------------------ vẽ hoa văn dùng chung
function catmull(P, per) {
  const out = [];
  const g = (i) => P[Math.max(0, Math.min(P.length - 1, i))];
  for (let i = 0; i < P.length - 1; i++) {
    const p0 = g(i - 1), p1 = g(i), p2 = g(i + 1), p3 = g(i + 2);
    for (let s = 0; s < per; s++) {
      const t = s / per, t2 = t * t, t3 = t2 * t;
      out.push([
        0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
        0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3),
      ]);
    }
  }
  out.push(P[P.length - 1].slice());
  return out;
}

/** Rồng uốn lượn: thân thon dần về đuôi, có vảy, vây lưng, đầu có sừng - râu - mắt - ngọc. */
function dragon(ctx, w, h, o) {
  const fx = (x) => (o.flip ? 1 - x : x) * w;
  const P = o.pts.map(([x, y]) => [fx(x), y * h]);
  const S = catmull(P, 28);
  const n = S.length;
  const rMax = w * (o.thick || 0.034);
  ctx.save();
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  const rad = (i) => {
    const t = i / (n - 1);
    return rMax * (0.12 + 0.88 * Math.pow(Math.sin(Math.min(1, t * 1.15) * Math.PI * 0.5), 0.8));
  };
  // vây lưng
  ctx.fillStyle = o.fin;
  for (let i = 6; i < n - 12; i += 5) {
    const [x, y] = S[i], [x2, y2] = S[i + 1];
    const a = Math.atan2(y2 - y, x2 - x) - Math.PI / 2;
    const r = rad(i);
    ctx.beginPath();
    ctx.moveTo(x + Math.cos(a) * r * 0.8 - Math.cos(a + Math.PI / 2) * r * 0.5, y + Math.sin(a) * r * 0.8 - Math.sin(a + Math.PI / 2) * r * 0.5);
    ctx.lineTo(x + Math.cos(a) * r * 1.9, y + Math.sin(a) * r * 1.9);
    ctx.lineTo(x + Math.cos(a) * r * 0.8 + Math.cos(a + Math.PI / 2) * r * 0.5, y + Math.sin(a) * r * 0.8 + Math.sin(a + Math.PI / 2) * r * 0.5);
    ctx.closePath();
    ctx.fill();
  }
  // thân
  for (let i = 0; i < n; i++) {
    ctx.fillStyle = o.body;
    ctx.beginPath();
    ctx.arc(S[i][0], S[i][1], rad(i), 0, TAU);
    ctx.fill();
  }
  // bụng sáng
  ctx.strokeStyle = o.belly;
  for (let i = 2; i < n - 8; i += 2) {
    const [x, y] = S[i], [x2, y2] = S[i + 1];
    const a = Math.atan2(y2 - y, x2 - x) + Math.PI / 2;
    const r = rad(i);
    ctx.lineWidth = Math.max(1, r * 0.22);
    ctx.beginPath();
    ctx.moveTo(x + Math.cos(a) * r * 0.55, y + Math.sin(a) * r * 0.55);
    ctx.lineTo(x + Math.cos(a) * r * 0.95, y + Math.sin(a) * r * 0.95);
    ctx.stroke();
  }
  // vảy
  ctx.strokeStyle = o.scale;
  for (let i = 4; i < n - 6; i += 3) {
    const [x, y] = S[i], [x2, y2] = S[i + 1];
    const a = Math.atan2(y2 - y, x2 - x);
    const r = rad(i);
    ctx.lineWidth = Math.max(1, r * 0.12);
    ctx.beginPath();
    ctx.arc(x, y, r * 0.55, a - 1.2, a + 1.2);
    ctx.stroke();
  }
  // đầu
  const [hx, hy] = S[n - 1], [px, py] = S[n - 6];
  const ang = Math.atan2(hy - py, hx - px);
  const s = rMax;
  ctx.translate(hx, hy);
  ctx.rotate(ang);
  ctx.fillStyle = o.body;
  ctx.beginPath(); // hàm trên
  ctx.moveTo(-s * 0.9, -s * 0.9);
  ctx.quadraticCurveTo(s * 1.2, -s * 1.15, s * 2.7, -s * 0.2);
  ctx.quadraticCurveTo(s * 2.9, s * 0.05, s * 2.5, s * 0.2);
  ctx.lineTo(-s * 0.9, s * 0.35);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath(); // hàm dưới
  ctx.moveTo(-s * 0.6, s * 0.3);
  ctx.quadraticCurveTo(s * 1.4, s * 0.45, s * 2.3, s * 0.55);
  ctx.quadraticCurveTo(s * 1.0, s * 1.3, -s * 0.8, s * 1.0);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = o.horn; // sừng
  ctx.lineWidth = Math.max(1.5, s * 0.22);
  for (const sg of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(-s * 0.2, sg * s * 0.8);
    ctx.quadraticCurveTo(-s * 1.2, sg * s * 1.7, -s * 2.4, sg * s * 1.2);
    ctx.stroke();
  }
  ctx.strokeStyle = o.fin; // râu
  ctx.lineWidth = Math.max(1, s * 0.12);
  for (const sg of [-1, 1]) {
    ctx.beginPath();
    ctx.moveTo(s * 2.3, sg * s * 0.1);
    ctx.bezierCurveTo(s * 3.2, sg * s * 1.2, s * 4.2, sg * s * 0.1, s * 5.2, sg * s * 1.1);
    ctx.stroke();
  }
  ctx.fillStyle = o.eye; // mắt
  ctx.beginPath();
  ctx.arc(s * 0.9, -s * 0.45, s * 0.2, 0, TAU);
  ctx.fill();
  const pr = ctx.createRadialGradient(s * 5.0, 0, 1, s * 5.0, 0, s * 1.2); // ngọc
  pr.addColorStop(0, o.eye);
  pr.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = pr;
  ctx.beginPath();
  ctx.arc(s * 5.0, 0, s * 1.2, 0, TAU);
  ctx.fill();
  ctx.restore();
}

/** Vảy cá xếp lớp (dùng cho rồng, rùa). */
function fishScales(ctx, w, h, r, color, lw) {
  ctx.strokeStyle = color;
  ctx.lineWidth = lw;
  for (let row = 0, y = 0; y < h + r; row++, y += r * 0.5) {
    for (let x = (row % 2) * r; x < w + r; x += r * 2) {
      for (let k = 1; k <= 3; k++) {
        ctx.beginPath();
        ctx.arc(x, y, r * (k / 3), 0, Math.PI);
        ctx.stroke();
      }
    }
  }
}

/** Mây cuộn kiểu cổ (tường vân). */
function cloud(ctx, x, y, s, color, lw) {
  ctx.save();
  ctx.translate(x, y);
  ctx.strokeStyle = color;
  ctx.lineWidth = lw;
  ctx.lineCap = 'round';
  ctx.beginPath();
  ctx.arc(0, 0, s * 0.5, Math.PI, TAU * 0.95);
  ctx.arc(s * 0.85, -s * 0.05, s * 0.38, Math.PI, TAU);
  ctx.arc(s * 1.5, s * 0.1, s * 0.28, Math.PI * 1.05, TAU * 1.02);
  ctx.moveTo(-s * 0.5, 0);
  ctx.quadraticCurveTo(-s * 0.9, s * 0.35, -s * 0.5, s * 0.55);
  ctx.quadraticCurveTo(-s * 0.2, s * 0.65, 0, s * 0.35);
  ctx.moveTo(-s * 0.5, 0);
  ctx.lineTo(s * 1.75, s * 0.1);
  ctx.stroke();
  ctx.restore();
}

/** Sóng nước kiểu Nhật/Á Đông (nhiều vòng cung xếp so le). */
function waves(ctx, w, h, r, color, lw) {
  ctx.strokeStyle = color;
  ctx.lineWidth = lw;
  for (let row = 0, y = r; y < h + r; row++, y += r * 0.5) {
    for (let x = (row % 2) * r; x < w + r; x += r * 2) {
      for (let k = 1; k <= 4; k++) {
        ctx.beginPath();
        ctx.arc(x, y, r * (k / 4), Math.PI, TAU);
        ctx.stroke();
      }
    }
  }
}

/** Sọc hổ: các nét thon nhọn, hơi cong. */
function tigerStripes(ctx, w, h, rnd, color, count) {
  ctx.fillStyle = color;
  for (let i = 0; i < count; i++) {
    const fromLeft = rnd() > 0.5;
    const x0 = fromLeft ? -w * 0.02 : w * 1.02;
    const y0 = rnd() * h;
    const dir = fromLeft ? 1 : -1;
    const len = w * (0.08 + rnd() * 0.22);
    const th = w * (0.012 + rnd() * 0.02);
    const bend = (rnd() - 0.5) * w * 0.12;
    ctx.beginPath();
    ctx.moveTo(x0, y0 - th);
    ctx.quadraticCurveTo(x0 + dir * len * 0.5, y0 - th * 0.8 + bend, x0 + dir * len, y0 + bend * 1.4);
    ctx.quadraticCurveTo(x0 + dir * len * 0.5, y0 + th * 0.8 + bend, x0, y0 + th);
    ctx.closePath();
    ctx.fill();
  }
}

/** Dấu chân hổ. */
function paw(ctx, x, y, s, color) {
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.ellipse(x, y + s * 0.25, s * 0.55, s * 0.45, 0, 0, TAU);
  ctx.fill();
  for (const [dx, dy] of [[-0.7, -0.35], [-0.25, -0.75], [0.25, -0.75], [0.7, -0.35]]) {
    ctx.beginPath();
    ctx.ellipse(x + dx * s, y + dy * s, s * 0.2, s * 0.27, 0, 0, TAU);
    ctx.fill();
  }
}

/** Quạt lông phượng: nhiều chiếc lông xòe ra từ 1 góc. */
function featherFan(ctx, ox, oy, len, rays, colA, colB, rotate) {
  ctx.save();
  ctx.translate(ox, oy);
  ctx.rotate(rotate);
  for (let layer = 0; layer < 3; layer++) {
    const L = len * (1 - layer * 0.22);
    for (let k = 0; k < rays; k++) {
      const a = -Math.PI / 2 + (k / (rays - 1) - 0.5) * Math.PI * 0.95;
      ctx.save();
      ctx.rotate(a + Math.PI / 2);
      const g = ctx.createLinearGradient(0, 0, 0, -L);
      g.addColorStop(0, colA);
      g.addColorStop(1, colB);
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.quadraticCurveTo(L * 0.16, -L * 0.45, 0, -L);
      ctx.quadraticCurveTo(-L * 0.16, -L * 0.45, 0, 0);
      ctx.fill();
      ctx.strokeStyle = colB;
      ctx.lineWidth = Math.max(1, L * 0.012);
      ctx.beginPath();
      ctx.moveTo(0, -L * 0.1);
      ctx.lineTo(0, -L * 0.95);
      ctx.stroke();
      ctx.restore();
    }
  }
  ctx.restore();
}

function flames(ctx, w, h, rnd, colA, colB) {
  for (let i = 0; i < 26; i++) {
    const x = (i / 25) * w + (rnd() - 0.5) * w * 0.03;
    const fh = h * (0.08 + rnd() * 0.16);
    const fw = w * (0.02 + rnd() * 0.02);
    const g = ctx.createLinearGradient(0, h, 0, h - fh);
    g.addColorStop(0, colA);
    g.addColorStop(1, colB);
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.moveTo(x - fw, h);
    ctx.quadraticCurveTo(x - fw * 0.2, h - fh * 0.5, x + (rnd() - 0.5) * fw, h - fh);
    ctx.quadraticCurveTo(x + fw * 0.9, h - fh * 0.4, x + fw, h);
    ctx.closePath();
    ctx.fill();
  }
}

function hexagon(ctx, x, y, r) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i + Math.PI / 6;
    const px = x + Math.cos(a) * r, py = y + Math.sin(a) * r;
    if (i) ctx.lineTo(px, py);
    else ctx.moveTo(px, py);
  }
  ctx.closePath();
}

function hexGrid(ctx, w, h, r, color, lw, inner) {
  ctx.strokeStyle = color;
  ctx.lineWidth = lw;
  const dx = Math.sqrt(3) * r, dy = r * 1.5;
  for (let row = 0, y = 0; y < h + r; row++, y += dy) {
    for (let x = (row % 2) * dx * 0.5; x < w + r; x += dx) {
      hexagon(ctx, x, y, r);
      ctx.stroke();
      if (inner) {
        hexagon(ctx, x, y, r * inner);
        ctx.stroke();
      }
    }
  }
}

function circuit(ctx, w, h, rnd, color, lw) {
  const step = w / 36;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = lw;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  for (let i = 0; i < 46; i++) {
    let x = Math.round((rnd() * w) / step) * step;
    let y = Math.round((rnd() * h) / step) * step;
    ctx.beginPath();
    ctx.moveTo(x, y);
    let dir = Math.floor(rnd() * 4);
    for (let seg = 0; seg < 5; seg++) {
      const len = step * (2 + Math.floor(rnd() * 5));
      const ang = (dir * Math.PI) / 2 + (rnd() > 0.7 ? Math.PI / 4 : 0);
      x += Math.cos(ang) * len;
      y += Math.sin(ang) * len;
      ctx.lineTo(x, y);
      dir = (dir + (rnd() > 0.5 ? 1 : 3)) % 4;
    }
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, lw * 2.4, 0, TAU);
    ctx.stroke();
  }
}

function glow(ctx, x, y, r, rgb, a) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(${rgb},${a})`);
  g.addColorStop(1, `rgba(${rgb},0)`);
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, TAU);
  ctx.fill();
}

// ------------------------------------------------------------------ danh sách kiểu
// bg = nền khung (2 màu), plate = tấm nền tối phủ vùng ô cờ, line = vạch kẻ, led = màu đèn chạy,
// art(ctx, w, h) = hàm vẽ hoa văn nền.
export const SKINS = [
  {
    id: 'rong-vang',
    name: 'Rồng vàng',
    bg: ['#2a0c10', '#0e0507'],
    plate: 'rgba(12,6,6,0.60)',
    line: 'rgba(240,205,120,0.62)',
    border: '#e8b84a',
    label: '#f0cd78',
    led: ['#ffd24a', '#ffb02e', '#fff2b0'],
    art(ctx, w, h) {
      ctx.globalAlpha = 0.34;
      fishScales(ctx, w, h, w / 26, '#b8862a', Math.max(1, w / 900));
      ctx.globalAlpha = 0.62;
      dragon(ctx, w, h, {
        pts: [[-0.05, 0.95], [0.16, 0.72], [0.3, 0.92], [0.5, 0.62], [0.35, 0.38], [0.6, 0.22], [0.8, 0.34], [0.84, 0.17]],
        body: '#c9922d', belly: '#f4d98a', scale: '#7a4f12', fin: '#e8b84a', horn: '#ffe9a8', eye: '#fff3b0', thick: 0.036,
      });
      ctx.globalAlpha = 0.3;
      cloud(ctx, w * 0.08, h * 0.12, w * 0.07, '#d9a441', Math.max(1.5, w / 500));
      cloud(ctx, w * 0.72, h * 0.86, w * 0.06, '#d9a441', Math.max(1.5, w / 500));
    },
  },
  {
    id: 'thanh-long',
    name: 'Thanh Long',
    bg: ['#06241f', '#031210'],
    plate: 'rgba(3,16,14,0.60)',
    line: 'rgba(150,230,200,0.55)',
    border: '#4fd1a0',
    label: '#9fe8cc',
    led: ['#7dffb5', '#3ff0d0', '#d6ffe8'],
    art(ctx, w, h) {
      ctx.globalAlpha = 0.34;
      waves(ctx, w, h, w / 20, '#2e8f78', Math.max(1, w / 900));
      ctx.globalAlpha = 0.62;
      dragon(ctx, w, h, {
        flip: true,
        pts: [[-0.05, 0.1], [0.2, 0.3], [0.1, 0.55], [0.4, 0.7], [0.65, 0.5], [0.55, 0.3], [0.8, 0.18], [0.9, 0.42]],
        body: '#2fae83', belly: '#bdf5dc', scale: '#126148', fin: '#5be3b5', horn: '#e6fff5', eye: '#fff7a8', thick: 0.036,
      });
      ctx.globalAlpha = 0.34;
      cloud(ctx, w * 0.7, h * 0.08, w * 0.07, '#6fe3bd', Math.max(1.5, w / 500));
      cloud(ctx, w * 0.05, h * 0.82, w * 0.06, '#6fe3bd', Math.max(1.5, w / 500));
    },
  },
  {
    id: 'bach-ho',
    name: 'Bạch Hổ',
    bg: ['#9aa4b2', '#59616d'],
    plate: 'rgba(12,14,18,0.56)',
    line: 'rgba(225,232,242,0.55)',
    border: '#dfe6f0',
    label: '#e4eaf3',
    led: ['#ffffff', '#c9f0ff', '#ffe9a8'],
    art(ctx, w, h) {
      const r = rngOf(21);
      ctx.globalAlpha = 0.8;
      tigerStripes(ctx, w, h, r, '#05070a', 90);
      ctx.globalAlpha = 0.16;
      tigerStripes(ctx, w, h, rngOf(5), '#ffffff', 26);
      ctx.globalAlpha = 0.3;
      for (let i = 0; i < 7; i++) paw(ctx, w * (0.12 + (i % 4) * 0.25 + (i > 3 ? 0.1 : 0)), h * (0.18 + Math.floor(i / 4) * 0.55 + (i % 2) * 0.12), w * 0.035, '#cfd8e6');
    },
  },
  {
    id: 'chu-tuoc',
    name: 'Chu Tước',
    bg: ['#2c0d08', '#120406'],
    plate: 'rgba(14,5,4,0.62)',
    line: 'rgba(255,200,130,0.58)',
    border: '#ffb347',
    label: '#ffcf8a',
    led: ['#ffd35a', '#ff9a3c', '#fff0a0'],
    art(ctx, w, h) {
      ctx.globalAlpha = 0.5;
      featherFan(ctx, w * 0.5, h * 1.02, h * 0.78, 13, 'rgba(255,120,30,0.55)', 'rgba(255,214,90,0.9)', 0);
      ctx.globalAlpha = 0.45;
      featherFan(ctx, w * 0.02, h * 0.05, h * 0.38, 7, 'rgba(255,110,30,0.5)', 'rgba(255,214,90,0.85)', Math.PI * 0.75);
      featherFan(ctx, w * 0.98, h * 0.05, h * 0.38, 7, 'rgba(255,110,30,0.5)', 'rgba(255,214,90,0.85)', -Math.PI * 0.75);
      ctx.globalAlpha = 0.55;
      flames(ctx, w, h, rngOf(9), 'rgba(255,90,20,0.75)', 'rgba(255,210,80,0.0)');
    },
  },
  {
    id: 'huyen-vu',
    name: 'Huyền Vũ',
    bg: ['#0c1f2a', '#050d13'],
    plate: 'rgba(4,12,18,0.60)',
    line: 'rgba(160,225,235,0.52)',
    border: '#6fd0dc',
    label: '#a8e4ec',
    led: ['#7ef2ff', '#c8fff0', '#ffe9a8'],
    art(ctx, w, h) {
      ctx.globalAlpha = 0.4;
      hexGrid(ctx, w, h, w / 17, '#3f9aa8', Math.max(1.5, w / 600), 0.55);
      ctx.globalAlpha = 0.3;
      ctx.strokeStyle = '#7ad7e3';
      ctx.lineWidth = Math.max(1.5, w / 600);
      for (const [cx, cy] of [[0.15, 0.85], [0.88, 0.14]]) {
        for (let k = 1; k <= 6; k++) {
          ctx.beginPath();
          ctx.arc(cx * w, cy * h, w * 0.035 * k, 0, TAU);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = 0.5; // rắn quấn quanh rùa
      dragon(ctx, w, h, {
        pts: [[0.02, 0.5], [0.2, 0.62], [0.4, 0.4], [0.6, 0.6], [0.8, 0.38], [0.97, 0.52]],
        body: '#3f8f8a', belly: '#bff3ee', scale: '#144a4a', fin: '#5fc0b8', horn: '#d9fffb', eye: '#fff7a8', thick: 0.022,
      });
    },
  },
  {
    id: 'cong-nghe',
    name: 'Công nghệ',
    bg: ['#08111e', '#03060c'],
    plate: 'rgba(3,7,14,0.58)',
    line: 'rgba(120,230,255,0.50)',
    border: '#37e0ff',
    label: '#8fe9ff',
    led: ['#35f0ff', '#55ffb0', '#d8fbff'],
    art(ctx, w, h) {
      ctx.globalAlpha = 0.26;
      hexGrid(ctx, w, h, w / 24, '#1d8fb0', Math.max(1, w / 900), 0);
      ctx.globalAlpha = 0.6;
      circuit(ctx, w, h, rngOf(77), '#22b9d6', Math.max(1.5, w / 520));
      ctx.globalAlpha = 0.18;
      ctx.fillStyle = '#6fe8ff';
      for (let y = 0; y < h; y += 5) ctx.fillRect(0, y, w, 1);
    },
  },
  {
    id: 'neon-tim',
    name: 'Neon tím',
    bg: ['#1b0a30', '#07030f'],
    plate: 'rgba(8,3,16,0.42)',
    line: 'rgba(235,160,255,0.55)',
    border: '#ff6ad5',
    label: '#f0b8ff',
    led: ['#ff6ad5', '#37f0ff', '#fff29a'],
    art(ctx, w, h) {
      ctx.globalAlpha = 0.55;
      glow(ctx, w * 0.5, h * 0.5, w * 0.6, '170,60,220', 0.45);
      ctx.globalAlpha = 0.38;
      ctx.lineWidth = Math.max(1.5, w / 600);
      const s = w / 12;
      for (let i = -12; i < 26; i++) {
        ctx.strokeStyle = i % 2 ? '#ff6ad5' : '#37e8ff';
        ctx.beginPath();
        ctx.moveTo(i * s, 0);
        ctx.lineTo(i * s + h, h);
        ctx.moveTo(i * s + h, 0);
        ctx.lineTo(i * s, h);
        ctx.stroke();
      }
      ctx.globalAlpha = 0.6;
      ctx.fillStyle = '#fff1ff';
      const r = rngOf(3);
      for (let i = 0; i < 50; i++) ctx.fillRect(r() * w, r() * h, 2, 2);
    },
  },
  {
    id: 'thien-ha',
    name: 'Thiên hà',
    bg: ['#120c26', '#04030a'],
    plate: 'rgba(5,4,12,0.40)',
    line: 'rgba(215,205,255,0.50)',
    border: '#cdbbff',
    label: '#d9ccff',
    led: ['#ffe9a8', '#ffffff', '#e0b8ff'],
    art(ctx, w, h) {
      const r = rngOf(12);
      ctx.globalAlpha = 0.6;
      glow(ctx, w * 0.25, h * 0.3, w * 0.5, '150,70,200', 0.5);
      glow(ctx, w * 0.78, h * 0.7, w * 0.5, '200,70,140', 0.4);
      glow(ctx, w * 0.6, h * 0.2, w * 0.3, '60,170,170', 0.32);
      ctx.globalAlpha = 0.9;
      const stars = [];
      for (let i = 0; i < 170; i++) {
        const x = r() * w, y = r() * h, s = r() * 2.2 + 0.6;
        stars.push([x, y]);
        ctx.fillStyle = r() > 0.8 ? '#ffe9a8' : '#ffffff';
        ctx.globalAlpha = 0.4 + r() * 0.5;
        ctx.fillRect(x, y, s, s);
      }
      ctx.globalAlpha = 0.28;
      ctx.strokeStyle = '#d9ccff';
      ctx.lineWidth = Math.max(1, w / 900);
      ctx.beginPath();
      for (let i = 0; i < 14; i++) {
        const a = stars[i * 7 % stars.length], b = stars[(i * 7 + 3) % stars.length];
        ctx.moveTo(a[0], a[1]);
        ctx.lineTo(b[0], b[1]);
      }
      ctx.stroke();
    },
  },
  {
    id: 'vu-tru',
    name: 'Vũ trụ',
    bg: ['#0a0f2c', '#02030b'],
    plate: 'rgba(3,5,16,0.42)',
    line: 'rgba(190,215,255,0.46)',
    border: '#9fc4ff',
    label: '#c9dcff',
    led: ['#bfe3ff', '#ffffff', '#c9b6ff'],
    art(ctx, w, h) {
      const r = rngOf(2024);
      // tinh vân xanh tím + một chút hồng ngọc, loãng
      ctx.globalAlpha = 0.65;
      glow(ctx, w * 0.2, h * 0.25, w * 0.55, '70,90,220', 0.5);
      glow(ctx, w * 0.82, h * 0.68, w * 0.5, '140,70,210', 0.42);
      glow(ctx, w * 0.55, h * 0.95, w * 0.35, '50,160,200', 0.3);
      // sao nền
      for (let i = 0; i < 230; i++) {
        const x = r() * w, y = r() * h, s = r() * 1.9 + 0.5;
        ctx.fillStyle = r() > 0.85 ? '#ffe6b0' : r() > 0.6 ? '#bfd8ff' : '#ffffff';
        ctx.globalAlpha = 0.3 + r() * 0.6;
        ctx.fillRect(x, y, s, s);
      }
      // vài ngôi sao lớn có tia sáng chữ thập
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = Math.max(1, w / 1100);
      for (let i = 0; i < 9; i++) {
        const x = r() * w, y = r() * h, l = w * (0.006 + r() * 0.008);
        ctx.globalAlpha = 0.55;
        ctx.beginPath();
        ctx.moveTo(x - l, y);
        ctx.lineTo(x + l, y);
        ctx.moveTo(x, y - l);
        ctx.lineTo(x, y + l);
        ctx.stroke();
      }
      // hành tinh có vành đai (góc trên phải)
      const pxp = w * 0.86, pyp = h * 0.14, pr = w * 0.075;
      ctx.globalAlpha = 0.7;
      const pg = ctx.createRadialGradient(pxp - pr * 0.4, pyp - pr * 0.4, pr * 0.1, pxp, pyp, pr);
      pg.addColorStop(0, '#ffd9a0');
      pg.addColorStop(0.6, '#d98c5f');
      pg.addColorStop(1, '#6b3a4f');
      ctx.fillStyle = pg;
      ctx.beginPath();
      ctx.arc(pxp, pyp, pr, 0, TAU);
      ctx.fill();
      ctx.save();
      ctx.translate(pxp, pyp);
      ctx.rotate(-0.35);
      ctx.strokeStyle = 'rgba(255,230,190,0.75)';
      ctx.lineWidth = Math.max(2, pr * 0.14);
      ctx.beginPath();
      ctx.ellipse(0, 0, pr * 1.75, pr * 0.46, 0, Math.PI, TAU); // nửa vành đai phía sau hành tinh bị che
      ctx.stroke();
      ctx.restore();
      ctx.fillStyle = pg;
      ctx.beginPath();
      ctx.arc(pxp, pyp, pr, 0, TAU);
      ctx.fill();
      ctx.save();
      ctx.translate(pxp, pyp);
      ctx.rotate(-0.35);
      ctx.strokeStyle = 'rgba(255,236,200,0.85)';
      ctx.lineWidth = Math.max(2, pr * 0.14);
      ctx.beginPath();
      ctx.ellipse(0, 0, pr * 1.75, pr * 0.46, 0, 0, Math.PI); // nửa vành đai phía trước
      ctx.stroke();
      ctx.restore();
      // mặt trăng nhỏ (góc dưới trái)
      const mx = w * 0.1, my = h * 0.86, mr = w * 0.04;
      const mg = ctx.createRadialGradient(mx - mr * 0.4, my - mr * 0.4, mr * 0.1, mx, my, mr);
      mg.addColorStop(0, '#ffffff');
      mg.addColorStop(1, '#8e99b8');
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = mg;
      ctx.beginPath();
      ctx.arc(mx, my, mr, 0, TAU);
      ctx.fill();
      ctx.fillStyle = 'rgba(80,90,120,0.35)';
      for (const [dx, dy, rr] of [[-0.3, 0.2, 0.22], [0.25, -0.25, 0.16], [0.2, 0.35, 0.12]]) {
        ctx.beginPath();
        ctx.arc(mx + dx * mr, my + dy * mr, rr * mr, 0, TAU);
        ctx.fill();
      }
    },
    /** Hiệu ứng động (gọi mỗi khung hình): sao lấp lánh + THỈNH THOẢNG có sao băng vút qua. t = giây. */
    fx(ctx, L, t) {
      const px = L.px;
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      // sao lấp lánh nhẹ
      const r = rngOf(909);
      for (let i = 0; i < 18; i++) {
        const x = r() * px, y = r() * px, ph = r() * 6.28, sp = 0.8 + r() * 1.6;
        const a = 0.15 + 0.35 * (0.5 + 0.5 * Math.sin(t * sp + ph));
        ctx.globalAlpha = a;
        ctx.fillStyle = '#ffffff';
        ctx.beginPath();
        ctx.arc(x, y, Math.max(1, px / 520) * (1 + 0.5 * a), 0, TAU);
        ctx.fill();
      }
      // sao băng: mỗi chu kỳ 8 giây có ~65% khả năng xuất hiện 1 sao, vút qua trong ~1 giây
      const PERIOD = 8;
      const DUR = 1.05;
      const k = Math.floor(t / PERIOD);
      const rr = rngOf(k * 7919 + 31);
      const show = rr() < 0.65;
      const off = rr() * (PERIOD - DUR - 0.5);
      const x0 = px * (0.12 + rr() * 0.76);
      const y0 = px * (0.02 + rr() * 0.38);
      const dir = rr() < 0.5 ? 1 : -1;
      const ang = 0.35 + rr() * 0.45; // độ nghiêng so với phương ngang (rad), đi chéo xuống
      const dx = Math.cos(ang) * dir;
      const dy = Math.sin(ang);
      const p = (t - k * PERIOD - off) / DUR;
      if (show && p >= 0 && p <= 1) {
        const dist = px * 0.42;
        const hxx = x0 + dx * dist * p;
        const hy = y0 + dy * dist * p;
        const tail = px * 0.17;
        const ux = dx;
        const uy = dy;
        const a = Math.pow(Math.sin(Math.PI * p), 0.7);
        const g = ctx.createLinearGradient(hxx, hy, hxx - ux * tail, hy - uy * tail);
        g.addColorStop(0, 'rgba(255,255,255,0.95)');
        g.addColorStop(0.35, 'rgba(190,220,255,0.55)');
        g.addColorStop(1, 'rgba(120,160,255,0)');
        ctx.globalAlpha = a;
        ctx.strokeStyle = g;
        ctx.lineCap = 'round';
        ctx.lineWidth = Math.max(2, px / 260);
        ctx.beginPath();
        ctx.moveTo(hxx, hy);
        ctx.lineTo(hxx - ux * tail, hy - uy * tail);
        ctx.stroke();
        glow(ctx, hxx, hy, px * 0.02, '220,235,255', 0.9);
      }
      ctx.restore();
    },
  },
];

const ID_INDEX = Object.fromEntries(SKINS.map((s, i) => [s.id, i]));
const SHIFT = Math.floor(Math.random() * SKINS.length);

/**
 * Chọn kiểu theo cài đặt trên bảng điều khiển:
 *  'wood' = bàn gỗ cũ (không hoa văn, không LED) | 'auto' = mỗi ván 1 kiểu khác nhau | 0..7 hoặc tên kiểu = cố định.
 */
export function pickSkin(setting, gameNo = 0) {
  const s = setting === undefined || setting === null ? 'auto' : String(setting);
  if (s === 'wood') return null;
  if (s === 'auto') return SKINS[(((Number(gameNo) || 0) + SHIFT) % SKINS.length + SKINS.length) % SKINS.length];
  if (s in ID_INDEX) return SKINS[ID_INDEX[s]];
  const n = Number(s);
  if (Number.isInteger(n) && n >= 0 && n < SKINS.length) return SKINS[n];
  return SKINS[0];
}

// ------------------------------------------------------------------ vẽ nền + đèn LED
/** Vẽ nền bàn cờ kiểu skin (thay cho nền gỗ). L = layout(px, size) của board.js. */
export function paintSkinBase(ctx, px, size, L, skin) {
  const g = ctx.createLinearGradient(0, 0, px, px);
  g.addColorStop(0, skin.bg[0]);
  g.addColorStop(1, skin.bg[1]);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, px, px);
  ctx.save();
  skin.art(ctx, px, px);
  ctx.restore();
  ctx.globalAlpha = 1;
  const gw = L.cell * size;
  ctx.fillStyle = skin.plate; // tấm nền tối: giữ quân X/O dễ nhìn
  ctx.fillRect(L.gx0, L.gy0, gw, gw);
  ctx.strokeStyle = skin.line;
  ctx.lineWidth = Math.max(1, px / 700);
  ctx.beginPath();
  for (let i = 0; i <= size; i++) {
    const a = L.gx0 + i * L.cell;
    ctx.moveTo(a, L.gy0);
    ctx.lineTo(a, L.gy0 + gw);
    const b = L.gy0 + i * L.cell;
    ctx.moveTo(L.gx0, b);
    ctx.lineTo(L.gx0 + gw, b);
  }
  ctx.stroke();
  ctx.strokeStyle = skin.border;
  ctx.lineWidth = Math.max(2, px / 300);
  ctx.strokeRect(L.gx0, L.gy0, gw, gw);
  ctx.fillStyle = skin.label;
  ctx.font = `800 ${Math.round(L.cell * 0.55)}px system-ui, Arial, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (let x = 0; x < size; x++) ctx.fillText(String.fromCharCode(65 + x), L.gx0 + (x + 0.5) * L.cell, L.gy0 + gw + L.label * 0.55);
  ctx.textAlign = 'right';
  for (let y = 0; y < size; y++) ctx.fillText(String(y + 1), L.gx0 - L.pad - 2, L.gy0 + (size - 1 - y + 0.5) * L.cell + 1);
}

/**
 * LED ĐƯỜNG KẺ: các đường kẻ + viền SÁNG LÊN đều (đổi màu LED rất chậm, thở nhẹ),
 * cứ vài giây lại có 1 vệt sáng như ánh phản chiếu của gương quét chéo qua bàn cờ, vệt đi tới đâu đường kẻ sáng rực tới đó.
 * Gọi MỖI KHUNG HÌNH sau khi đã vẽ nền (và trước khi vẽ quân cờ). t = giây.
 */
const GLINT_PERIOD = 6; // cứ 6 giây có 1 lần vệt sáng quét qua
const GLINT_SECONDS = 1.8; // 1 lần quét kéo dài bấy nhiêu giây

/** Hiệu ứng động riêng của kiểu bàn (ví dụ sao băng của bàn Vũ trụ). Gọi mỗi khung hình, trước khi vẽ quân cờ. */
export function drawSkinFx(ctx, L, skin, t) {
  if (skin && typeof skin.fx === 'function') skin.fx(ctx, L, t);
}

export function drawLed(ctx, L, skin, t) {
  const n = L.size;
  const gw = L.cell * n;
  const cols = skin.led && skin.led.length ? skin.led : ['#7df'];
  const dot = Math.max(1.4, L.cell * 0.07);
  const cx = L.gx0 + gw / 2;
  const cy = L.gy0 + gw / 2;

  // dải màu LED chạy rất chậm theo đường chéo (gradient lặp 3 lần để không bị đứt khi trượt)
  const span = gw * 0.9;
  const shift = ((t * 0.035) % 1) * span;
  const gx = L.gx0 - shift;
  const gy = L.gy0 - shift * 0.6;
  const grad = ctx.createLinearGradient(gx, gy, gx + span * 3, gy + span * 1.8);
  const stops = cols.length * 3 + 1;
  for (let k = 0; k < stops; k++) grad.addColorStop(k / (stops - 1), cols[k % cols.length]);

  const strokeGrid = (wide, core, alphaMul) => {
    ctx.strokeStyle = grad;
    for (const [w, al] of [[wide, 0.12], [core, 0.5]]) {
      ctx.lineWidth = w;
      ctx.globalAlpha = Math.min(1, al * alphaMul);
      ctx.beginPath();
      for (let i = 1; i < n; i++) {
        const o = i * L.cell;
        ctx.moveTo(L.gx0 + o, L.gy0); ctx.lineTo(L.gx0 + o, L.gy0 + gw);
        ctx.moveTo(L.gx0, L.gy0 + o); ctx.lineTo(L.gx0 + gw, L.gy0 + o);
      }
      ctx.rect(L.gx0, L.gy0, gw, gw); // viền
      ctx.stroke();
    }
  };

  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.lineCap = 'butt';
  ctx.lineJoin = 'miter';

  // 1) đường kẻ sáng đều, thở nhẹ
  const breathe = 0.85 + 0.15 * Math.sin(t * 1.4);
  strokeGrid(dot * 3.4, dot * 0.95, breathe);

  // 2) vệt sáng "ánh gương" quét chéo, mỗi lần đổi hướng
  const cyc = Math.floor(t / GLINT_PERIOD);
  const u = (t - cyc * GLINT_PERIOD) / GLINT_SECONDS;
  if (u >= 0 && u <= 1) {
    const ease = u * u * (3 - 2 * u); // đi chậm ở 2 đầu, nhanh ở giữa
    const flip = cyc % 2 === 1;
    const ang = flip ? (Math.PI * 3) / 4 : Math.PI / 4; // 45° hoặc 135°
    const half = Math.SQRT2 * gw / 2; // nửa đường chéo bàn cờ
    const w = L.cell * 2.4; // nửa bề rộng vệt sáng
    const pos = -half - w + ease * (2 * half + 2 * w);
    const fade = Math.sin(Math.min(1, u) * Math.PI); // mờ dần ở 2 đầu
    // vệt phản chiếu: 3 lớp từ rộng-nhạt tới hẹp-chói, và đường kẻ trong vệt sáng rực lên
    for (const [k, ak] of [[1, 0.5], [0.55, 0.8], [0.22, 1]]) {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(ang);
      ctx.beginPath();
      ctx.rect(pos - w * k, -gw, w * 2 * k, gw * 2);
      ctx.clip();
      ctx.rotate(-ang);
      ctx.translate(-cx, -cy);
      ctx.strokeStyle = '#ffffff';
      ctx.fillStyle = '#ffffff';
      ctx.globalAlpha = 0.5 * fade * ak;
      ctx.lineWidth = dot * 1.5;
      ctx.beginPath();
      for (let i = 1; i < n; i++) {
        const o = i * L.cell;
        ctx.moveTo(L.gx0 + o, L.gy0); ctx.lineTo(L.gx0 + o, L.gy0 + gw);
        ctx.moveTo(L.gx0, L.gy0 + o); ctx.lineTo(L.gx0 + gw, L.gy0 + o);
      }
      ctx.rect(L.gx0, L.gy0, gw, gw);
      ctx.stroke();
      ctx.restore();
    }
    // lớp ánh sáng mờ phủ nhẹ lên mặt bàn (giống mặt gương lóe sáng)
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(ang);
    const sg = ctx.createLinearGradient(pos - w, 0, pos + w, 0);
    sg.addColorStop(0, 'rgba(255,255,255,0)');
    sg.addColorStop(0.5, 'rgba(255,255,255,1)');
    sg.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = sg;
    ctx.globalAlpha = 0.09 * fade;
    ctx.beginPath();
    ctx.rect(pos - w, -gw, w * 2, gw * 2);
    ctx.clip();
    ctx.fillRect(-gw * 2, -gw * 2, gw * 4, gw * 4);
    ctx.restore();
  }
  ctx.restore();
}
