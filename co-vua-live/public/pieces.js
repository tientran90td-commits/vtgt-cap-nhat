/*
 * QUÂN CỜ VUA 3D (dựng bằng hình khối đơn giản: xoay profile + vài khối ghép).
 * Dùng cho quân trên bàn cờ 3D và quân đang cầm trên tay nhân vật.
 * Gốc tọa độ của quân nằm GIỮA chiều cao (userData.height = chiều cao thật).
 */
import * as THREE from './vendor/three.module.js';

export const PIECE_COLOR = { X: 0xf4efe0, O: 0x6aa8ff };

const mats = {};
function material(color) {
  if (!mats[color]) {
    mats[color] =
      color === 'w'
        ? new THREE.MeshStandardMaterial({ color: 0xf2ecd8, roughness: 0.32, metalness: 0.05, emissive: 0x2a2618, emissiveIntensity: 0.25 })
        : new THREE.MeshStandardMaterial({ color: 0x2a2a36, roughness: 0.28, metalness: 0.25, emissive: 0x0a0a14, emissiveIntensity: 0.3 });
  }
  return mats[color];
}

const V2 = (r, y) => new THREE.Vector2(r, y);
const lathe = (pts, mat) => new THREE.Mesh(new THREE.LatheGeometry(pts.map(([r, y]) => V2(r, y)), 28), mat);
const ball = (r, y, mat, sy = 1) => {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 20, 14), mat);
  m.position.y = y;
  m.scale.y = sy;
  return m;
};
const box = (w, h, d, x, y, z, mat) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  m.position.set(x, y, z);
  return m;
};

// hình đầu ngựa (cùng dáng với quân 2D), toạ độ theo "đơn vị ô"
function knightHead(mat) {
  const s = new THREE.Shape();
  const pts = [
    [-0.23, 0.0], [-0.2, 0.22], [-0.1, 0.34], [-0.26, 0.31], [-0.32, 0.36], [-0.28, 0.45], [-0.12, 0.62], [-0.06, 0.78], [0.04, 0.66],
    [0.16, 0.6], [0.22, 0.4], [0.25, 0.2], [0.24, 0.0],
  ];
  s.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) s.lineTo(pts[i][0], pts[i][1]);
  s.closePath();
  const geo = new THREE.ExtrudeGeometry(s, { depth: 0.2, bevelEnabled: true, bevelThickness: 0.04, bevelSize: 0.03, bevelSegments: 2, curveSegments: 6 });
  geo.translate(0, 0, -0.1);
  return new THREE.Mesh(geo, mat);
}

const BASE = [[0, 0], [0.36, 0], [0.37, 0.05], [0.33, 0.1], [0.27, 0.14]];

/** t: 'p|n|b|r|q|k', color: 'w'|'b', cell: độ rộng 1 ô (đơn vị 3D). */
export function makeChessPiece(t, color, cell = 0.2) {
  const mat = material(color);
  const g = new THREE.Group();
  switch (t) {
    case 'r':
      g.add(lathe([...BASE, [0.2, 0.2], [0.18, 0.5], [0.27, 0.56], [0.27, 0.62], [0, 0.62]], mat));
      for (const [x, z] of [[0.19, 0], [-0.19, 0], [0, 0.19], [0, -0.19]]) g.add(box(0.12, 0.12, 0.12, x, 0.68, z, mat));
      g.add(box(0.5, 0.05, 0.1, 0, 0.64, 0, mat));
      break;
    case 'n':
      g.add(lathe([...BASE, [0.22, 0.2], [0, 0.2]], mat));
      {
        const h = knightHead(mat);
        h.position.y = 0.17;
        h.scale.setScalar(1.0);
        g.add(h);
      }
      break;
    case 'b':
      g.add(lathe([...BASE, [0.17, 0.28], [0.12, 0.42], [0.2, 0.46], [0.2, 0.5], [0.12, 0.54], [0, 0.54]], mat));
      g.add(ball(0.15, 0.7, mat, 1.45));
      g.add(ball(0.05, 0.98, mat));
      break;
    case 'q':
      g.add(lathe([...BASE, [0.2, 0.3], [0.14, 0.6], [0.26, 0.68], [0.3, 0.84], [0.2, 0.84], [0.17, 0.78], [0, 0.78]], mat));
      for (let i = 0; i < 7; i++) {
        const a = (i / 7) * Math.PI * 2;
        g.add(Object.assign(ball(0.045, 0.9, mat), { position: new THREE.Vector3(Math.cos(a) * 0.23, 0.9, Math.sin(a) * 0.23) }));
      }
      g.add(ball(0.07, 0.95, mat));
      break;
    case 'k':
      g.add(lathe([...BASE, [0.2, 0.3], [0.14, 0.64], [0.26, 0.72], [0.28, 0.88], [0.18, 0.9], [0, 0.9]], mat));
      g.add(box(0.07, 0.3, 0.07, 0, 1.02, 0, mat));
      g.add(box(0.2, 0.07, 0.07, 0, 1.06, 0, mat));
      break;
    default: // tốt
      g.add(lathe([...BASE, [0.19, 0.22], [0.12, 0.36], [0.2, 0.4], [0.2, 0.44], [0.1, 0.48], [0, 0.48]], mat));
      g.add(ball(0.15, 0.56, mat));
  }
  g.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
    }
  });
  g.scale.setScalar(cell);
  const box3 = new THREE.Box3().setFromObject(g);
  const H = box3.max.y - box3.min.y;
  const outer = new THREE.Group();
  g.position.y = -H / 2;
  outer.add(g);
  outer.userData.height = H;
  outer.userData.t = t;
  outer.userData.color = color;
  return outer;
}

/** Tương thích cũ: quân cầm trên tay (tốt) theo bên 'X' (trắng) / 'O' (đen). */
export function makePieceMesh(mark, size = 0.13) {
  return makeChessPiece('p', mark === 'X' ? 'w' : 'b', size * 1.5);
}
