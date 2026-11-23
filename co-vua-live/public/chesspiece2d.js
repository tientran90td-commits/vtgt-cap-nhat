/*
 * VẼ QUÂN CỜ VUA 2D bằng đường vẽ (không phụ thuộc font chữ nên máy nào cũng giống nhau).
 * drawPiece(ctx, loại, màu, tâm x, tâm y, cỡ): cỡ = chiều cao quân (px).
 */
const P = (ctx, pts) => {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
};

const BODY = {
  base(ctx) {
    ctx.beginPath();
    ctx.moveTo(-0.3, 0.42);
    ctx.lineTo(0.3, 0.42);
    ctx.quadraticCurveTo(0.33, 0.42, 0.33, 0.38);
    ctx.lineTo(0.33, 0.33);
    ctx.lineTo(-0.33, 0.33);
    ctx.lineTo(-0.33, 0.38);
    ctx.quadraticCurveTo(-0.33, 0.42, -0.3, 0.42);
    ctx.closePath();
  },
};

const SHAPES = {
  p: [
    (c) => { c.beginPath(); c.moveTo(-0.2, 0.34); c.quadraticCurveTo(-0.19, 0.12, -0.08, -0.02); c.lineTo(0.08, -0.02); c.quadraticCurveTo(0.19, 0.12, 0.2, 0.34); c.closePath(); },
    (c) => P(c, [[-0.14, -0.02], [0.14, -0.02], [0.14, -0.09], [-0.14, -0.09]]),
    (c) => { c.beginPath(); c.arc(0, -0.2, 0.115, 0, Math.PI * 2); },
  ],
  r: [
    (c) => P(c, [[-0.2, 0.34], [-0.15, -0.14], [0.15, -0.14], [0.2, 0.34]]),
    (c) => P(c, [[-0.23, -0.14], [-0.23, -0.38], [-0.13, -0.38], [-0.13, -0.3], [-0.05, -0.3], [-0.05, -0.38], [0.05, -0.38], [0.05, -0.3], [0.13, -0.3], [0.13, -0.38], [0.23, -0.38], [0.23, -0.14]]),
  ],
  b: [
    (c) => { c.beginPath(); c.moveTo(-0.21, 0.34); c.quadraticCurveTo(-0.17, 0.14, -0.07, 0.04); c.lineTo(0.07, 0.04); c.quadraticCurveTo(0.17, 0.14, 0.21, 0.34); c.closePath(); },
    (c) => P(c, [[-0.15, 0.06], [0.15, 0.06], [0.15, -0.01], [-0.15, -0.01]]),
    (c) => { c.beginPath(); c.ellipse(0, -0.17, 0.13, 0.2, 0, 0, Math.PI * 2); },
    (c) => { c.beginPath(); c.arc(0, -0.4, 0.05, 0, Math.PI * 2); },
  ],
  n: [
    (c) => {
      c.beginPath();
      c.moveTo(-0.23, 0.34);
      c.lineTo(-0.2, 0.16);
      c.quadraticCurveTo(-0.14, 0.06, -0.1, 0.04);
      c.lineTo(-0.26, 0.07);
      c.quadraticCurveTo(-0.33, 0.05, -0.3, -0.03);
      c.quadraticCurveTo(-0.22, -0.16, -0.1, -0.28);
      c.lineTo(-0.06, -0.41);
      c.lineTo(0.02, -0.31);
      c.quadraticCurveTo(0.13, -0.26, 0.18, -0.1);
      c.quadraticCurveTo(0.25, 0.1, 0.23, 0.34);
      c.closePath();
    },
  ],
  q: [
    (c) => { c.beginPath(); c.moveTo(-0.22, 0.34); c.quadraticCurveTo(-0.19, 0.1, -0.1, -0.06); c.lineTo(0.1, -0.06); c.quadraticCurveTo(0.19, 0.1, 0.22, 0.34); c.closePath(); },
    (c) => P(c, [[-0.2, -0.04], [-0.28, -0.34], [-0.13, -0.2], [-0.07, -0.4], [0, -0.2], [0.07, -0.4], [0.13, -0.2], [0.28, -0.34], [0.2, -0.04]]),
    (c) => { c.beginPath(); c.arc(-0.28, -0.36, 0.045, 0, Math.PI * 2); },
    (c) => { c.beginPath(); c.arc(0, -0.44, 0.05, 0, Math.PI * 2); },
    (c) => { c.beginPath(); c.arc(0.28, -0.36, 0.045, 0, Math.PI * 2); },
  ],
  k: [
    (c) => { c.beginPath(); c.moveTo(-0.22, 0.34); c.quadraticCurveTo(-0.19, 0.1, -0.1, -0.06); c.lineTo(0.1, -0.06); c.quadraticCurveTo(0.19, 0.1, 0.22, 0.34); c.closePath(); },
    (c) => { c.beginPath(); c.moveTo(-0.2, -0.04); c.lineTo(-0.22, -0.26); c.quadraticCurveTo(0, -0.18, 0.22, -0.26); c.lineTo(0.2, -0.04); c.closePath(); },
    (c) => P(c, [[-0.035, -0.26], [-0.035, -0.32], [-0.1, -0.32], [-0.1, -0.38], [-0.035, -0.38], [-0.035, -0.46], [0.035, -0.46], [0.035, -0.38], [0.1, -0.38], [0.1, -0.32], [0.035, -0.32], [0.035, -0.26]]),
  ],
};

export function drawPiece(ctx, t, color, cx, cy, s, opts = {}) {
  const white = color === 'w';
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(s, s);
  if (!white && t === 'n') ctx.scale(-1, 1); // mã đen quay mặt ngược lại
  ctx.lineJoin = 'round';
  ctx.lineCap = 'round';
  if (opts.shadow !== false) {
    ctx.shadowColor = 'rgba(0,0,0,0.38)';
    ctx.shadowBlur = 0.06 * s;
    ctx.shadowOffsetY = 0.03 * s;
  }
  const g = ctx.createLinearGradient(-0.3, -0.4, 0.3, 0.4);
  if (white) {
    g.addColorStop(0, '#ffffff');
    g.addColorStop(1, '#d6cfbb');
  } else {
    g.addColorStop(0, '#5a5a6c');
    g.addColorStop(1, '#16161e');
  }
  ctx.fillStyle = g;
  ctx.strokeStyle = white ? '#2d2618' : '#05050a';
  ctx.lineWidth = 0.04;
  const draw = (fn) => {
    fn(ctx);
    ctx.fill();
    ctx.stroke();
  };
  draw(BODY.base);
  for (const fn of SHAPES[t] || SHAPES.p) draw(fn);
  ctx.shadowColor = 'transparent';
  // chi tiết nhỏ
  ctx.strokeStyle = white ? 'rgba(60,45,20,0.75)' : 'rgba(220,225,255,0.55)';
  ctx.fillStyle = ctx.strokeStyle;
  ctx.lineWidth = 0.025;
  if (t === 'b') {
    ctx.beginPath();
    ctx.moveTo(-0.04, -0.28);
    ctx.lineTo(0.08, -0.13);
    ctx.stroke();
  } else if (t === 'n') {
    ctx.beginPath();
    ctx.arc(-0.1, -0.17, 0.028, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(0.02, -0.28);
    ctx.quadraticCurveTo(0.12, -0.12, 0.1, 0.1);
    ctx.stroke();
  } else if (t === 'r') {
    ctx.beginPath();
    ctx.moveTo(-0.16, -0.1);
    ctx.lineTo(0.16, -0.1);
    ctx.stroke();
  }
  ctx.restore();
}
