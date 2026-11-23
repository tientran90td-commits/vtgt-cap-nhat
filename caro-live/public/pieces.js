/*
 * QUÂN CỜ 3D: X đỏ (hai thanh chéo) và O xanh (vòng tròn).
 * Dùng cho cả quân đặt trên bàn lẫn quân đang cầm trên tay nhân vật.
 */
import * as THREE from './vendor/three.module.js';

export const PIECE_COLOR = { X: 0xff3b3f, O: 0x2f9bff };

const mats = {};
function material(mark) {
  if (!mats[mark]) {
    mats[mark] = new THREE.MeshStandardMaterial({
      color: PIECE_COLOR[mark],
      roughness: 0.3,
      metalness: 0.15,
      emissive: PIECE_COLOR[mark],
      emissiveIntensity: 0.18,
    });
  }
  return mats[mark];
}

export function makePieceMesh(mark, size = 0.07) {
  const g = new THREE.Group();
  if (mark === 'X') {
    const geo = new THREE.BoxGeometry(size * 1.25, size * 0.26, size * 0.26);
    const a = new THREE.Mesh(geo, material('X'));
    const b = new THREE.Mesh(geo, material('X'));
    a.rotation.y = Math.PI / 4;
    b.rotation.y = -Math.PI / 4;
    g.add(a, b);
  } else {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(size * 0.46, size * 0.13, 10, 28), material('O'));
    ring.rotation.x = Math.PI / 2;
    g.add(ring);
  }
  g.traverse((o) => {
    if (o.isMesh) o.castShadow = true;
  });
  g.userData.height = size * 0.26;
  return g;
}
