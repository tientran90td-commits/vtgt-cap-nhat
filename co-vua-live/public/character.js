/*
 * NHÂN VẬT 3D NGỒI Ở BÀN CỜ (tự dựng bằng hình khối, không cần file mô hình ngoài).
 * - Ghế X (đỏ): bạn nam áo hoodie, khăn đỏ.   - Ghế O (xanh): bạn nữ áo dài, tai mèo, ruy băng xanh.
 * - Cánh tay dùng IK 2 đoạn: tay thật sự với tới ô cờ cần đặt.
 * - Có các chế độ: idle (chờ), think (suy nghĩ: tay chống cằm, gõ bàn, bóng suy nghĩ),
 *   place (nghĩ ra ý -> nhấc quân -> đặt xuống -> rút tay), win (nhảy mừng), lose (gục xuống), shrug (hòa).
 */
import * as THREE from './vendor/three.module.js';
import { attachModel } from './rig.js';
import { getAvatar } from './avatar.js';
import { makePieceMesh, makeChessPiece } from './pieces.js';

const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const UP = V(0, 1, 0);
const damp = (cur, goal, k, dt) => cur + (goal - cur) * (1 - Math.exp(-k * dt));
const std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: 0.62, metalness: 0, ...o });

const THOUGHTS = ['Hmm…', 'Đi đâu nhỉ?', '🤔', 'Phòng thủ đã!', 'Nước này hay…', 'Tính kỹ nào…', '…', 'Được quân rồi nhé!'];

/** IK 2 đoạn: trả về vị trí khuỷu + cổ tay. */
function solveArm(S, T, L1, L2, pole, outElbow, outWrist) {
  const d = T.clone().sub(S);
  let dist = d.length();
  const maxD = (L1 + L2) * 0.995;
  if (dist > maxD) {
    d.multiplyScalar(maxD / dist);
    dist = maxD;
  }
  if (dist < 0.08) {
    d.set(0, -0.08, 0);
    dist = 0.08;
  }
  const dir = d.clone().divideScalar(dist);
  const a = (L1 * L1 - L2 * L2 + dist * dist) / (2 * dist);
  const h = Math.sqrt(Math.max(L1 * L1 - a * a, 0));
  const p = pole.clone().addScaledVector(dir, -pole.dot(dir));
  if (p.lengthSq() < 1e-6) p.set(0, -1, 0);
  p.normalize();
  outWrist.copy(S).add(d);
  outElbow.copy(S).addScaledVector(dir, a).addScaledVector(p, h);
}

function limb(mesh, A, B) {
  const dir = B.clone().sub(A);
  const len = Math.max(dir.length(), 0.001);
  mesh.position.copy(A).addScaledVector(dir, 0.5);
  mesh.quaternion.setFromUnitVectors(UP, dir.divideScalar(len));
  mesh.scale.set(1, len, 1);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function makeSprite(w, h) {
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(w * 256);
  canvas.height = Math.round(h * 256);
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(w, h, 1);
  sprite.renderOrder = 20;
  return { sprite, canvas, tex, ctx: canvas.getContext('2d') };
}


// ------------------------------------------------------------------ phong cách ANIME
// Tô bóng kiểu cel (3 mức sáng) + viền đen quanh hình khối + mắt to có tròng/đốm sáng.
let _grad = null;
function gradient() {
  if (!_grad) {
    const d = new Uint8Array([120, 112, 132, 255, 196, 190, 204, 255, 255, 255, 255, 255]);
    _grad = new THREE.DataTexture(d, 3, 1, THREE.RGBAFormat);
    _grad.minFilter = _grad.magFilter = THREE.NearestFilter;
    _grad.generateMipmaps = false;
    _grad.needsUpdate = true;
  }
  return _grad;
}
const toon = (color, o = {}) => new THREE.MeshToonMaterial({ color, gradientMap: gradient(), ...o });

const _outlines = new Map();
function outlineMat(w) {
  if (!_outlines.has(w)) {
    const m = new THREE.MeshBasicMaterial({ color: 0x1a1222, side: THREE.BackSide });
    m.onBeforeCompile = (sh) => {
      sh.vertexShader = sh.vertexShader.replace('#include <begin_vertex>', `vec3 transformed = position + normal * ${w.toFixed(4)};`);
    };
    m.customProgramCacheKey = () => 'outline' + w;
    _outlines.set(w, m);
  }
  return _outlines.get(w);
}
function outlined(mesh, w = 0.012) {
  const o = new THREE.Mesh(mesh.geometry, outlineMat(w));
  o.raycast = () => {};
  mesh.add(o);
  return mesh;
}

/** Mặt anime: cầu có cằm thon nhọn. */
function animeFaceGeometry(r = 0.52) {
  const g = new THREE.SphereGeometry(r, 56, 40);
  const pos = g.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    let x = pos.getX(i);
    let y = pos.getY(i);
    let z = pos.getZ(i);
    const t = Math.max(0, -y / r);
    const k = 1 - 0.34 * Math.pow(t, 1.35);
    x *= k * 0.95;
    z *= k;
    if (y < 0) y *= 1 + 0.16 * t;
    pos.setXYZ(i, x, y, z);
  }
  g.computeVertexNormals();
  return g;
}
/** Độ nhô ra phía trước (z) của mặt tại điểm (x, y) so với tâm mặt. */
function surfaceZ(g, x, y) {
  const p = g.attributes.position;
  let best = 0.3;
  let bd = 1e9;
  for (let i = 0; i < p.count; i++) {
    const pz = p.getZ(i);
    if (pz <= 0) continue;
    const d = (p.getX(i) - x) ** 2 + (p.getY(i) - y) ** 2;
    if (d < bd) {
      bd = d;
      best = pz;
    }
  }
  return best;
}

function makeEyeTexture(iris, flip) {
  const W = 256;
  const H = 320;
  const c = document.createElement('canvas');
  c.width = W;
  c.height = H;
  const g = c.getContext('2d');
  if (flip) {
    g.translate(W, 0);
    g.scale(-1, 1);
  }
  // tròng trắng
  g.fillStyle = '#ffffff';
  g.beginPath();
  g.ellipse(128, 188, 106, 120, 0, 0, Math.PI * 2);
  g.fill();
  // mống mắt (gradient)
  g.save();
  g.beginPath();
  g.ellipse(128, 196, 82, 106, 0, 0, Math.PI * 2);
  g.clip();
  const grd = g.createLinearGradient(0, 90, 0, 302);
  grd.addColorStop(0, iris[0]);
  grd.addColorStop(0.55, iris[1]);
  grd.addColorStop(1, iris[2]);
  g.fillStyle = grd;
  g.fillRect(0, 80, W, 240);
  // bóng mi trên
  const sh = g.createLinearGradient(0, 80, 0, 170);
  sh.addColorStop(0, 'rgba(18,8,30,0.9)');
  sh.addColorStop(1, 'rgba(18,8,30,0)');
  g.fillStyle = sh;
  g.fillRect(0, 80, W, 100);
  g.restore();
  // đồng tử
  g.fillStyle = '#140a20';
  g.beginPath();
  g.ellipse(128, 192, 34, 52, 0, 0, Math.PI * 2);
  g.fill();
  // đốm sáng
  g.fillStyle = '#ffffff';
  g.beginPath();
  g.ellipse(96, 140, 26, 30, -0.3, 0, Math.PI * 2);
  g.fill();
  g.beginPath();
  g.arc(162, 240, 12, 0, Math.PI * 2);
  g.fill();
  g.globalAlpha = 0.7;
  g.beginPath();
  g.arc(150, 120, 7, 0, Math.PI * 2);
  g.fill();
  g.globalAlpha = 1;
  // mi trên dày + đuôi mắt hất lên
  g.strokeStyle = '#17101f';
  g.lineCap = 'round';
  g.lineJoin = 'round';
  g.lineWidth = 30;
  g.beginPath();
  g.moveTo(14, 128);
  g.quadraticCurveTo(110, 18, 238, 96);
  g.stroke();
  g.lineWidth = 16;
  g.beginPath();
  g.moveTo(228, 96);
  g.lineTo(252, 66);
  g.stroke();
  // mi dưới mảnh
  g.lineWidth = 7;
  g.beginPath();
  g.ellipse(128, 188, 104, 118, 0, Math.PI * 0.2, Math.PI * 0.8);
  g.stroke();
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

function makeBlushTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(32, 32, 2, 32, 32, 30);
  grd.addColorStop(0, 'rgba(255,110,140,0.75)');
  grd.addColorStop(1, 'rgba(255,110,140,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

export class Character {
  /** opt: { style:'boy'|'girl', mark:'X'|'O', seatZ, hair, cloth, accent, scale } */
  constructor(opt) {
    this.opt = opt;
    this.mark = opt.mark;
    const S = (this.S = opt.scale || 1.15);
    this.L1 = 0.92 * S;
    this.L2 = 0.92 * S;

    this.root = new THREE.Group();
    this.root.scale.setScalar(S);
    this.root.position.set(0, 0, opt.seatZ);
    this.root.rotation.y = opt.seatZ > 0 ? Math.PI : 0; // mặt hướng vào bàn
    this.world = new THREE.Group(); // tay, quân đang cầm, bóng suy nghĩ, bảng tên (toạ độ thế giới)

    this.mode = 'idle';
    this.modeT = 0;
    this.placing = null;
    this.lean = 0.1;
    this.leanGoal = 0.1;
    this.headRot = { x: 0, y: 0, z: 0 };
    this.blinkTimer = 2 + Math.random() * 3;
    this.blink = 0;
    this.thoughtTimer = 0;
    this.thoughtIndex = Math.floor(Math.random() * THOUGHTS.length);
    this.bubbleText = '';
    this.fidgetT = Math.random() * 10;
    this.urgency = 0;
    this.tagName = '';
    this.tagPop = 0;
    this.phase = Math.random() * 6;
    this.heldVisible = false;
    this.lookYaw = 0;
    // do seatmotion.js điều khiển khi nhân vật đứng dậy / đi lại
    this.walkPhase = 0;
    this.walkAmp = 0;
    this.walkLean = 0;

    this.rig = null;
    this.build(opt);
    this.hands = [
      { pos: V(), goal: V(), k: 8, init: false },
      { pos: V(), goal: V(), k: 8, init: false },
    ];
    this.elbow = [V(), V()];
    this.wrist = [V(), V()];
  }

  /** Đổi màu tóc / áo / điểm nhấn ngay (look = { hair, hairLight, cloth, accent }), không dựng lại nhân vật. */
  recolor(look) {
    const m = this.looks;
    if (!m || !look) return;
    if (look.hair !== undefined) m.hair.color.set(look.hair);
    if (look.hairLight !== undefined) m.hairShine.color.set(look.hairLight);
    if (look.cloth !== undefined) {
      m.cloth.color.set(look.cloth);
      m.clothDark.color.set(look.cloth).multiplyScalar(0.78);
    }
    if (look.accent !== undefined) m.accent.color.set(look.accent);
  }

  /** Thay nhân vật dựng sẵn bằng model .glb có xương (xem rig.js). */
  useModel(gltfScene) {
    return attachModel(this, gltfScene);
  }

  attachTo(scene) {
    scene.add(this.root);
    scene.add(this.world);
  }

  // ------------------------------------------------------------------ dựng hình (ANIME)
  build(opt) {
    const boy = opt.style === 'boy';
    const skin = toon(0xffe1cd);
    const clothMat = toon(opt.cloth);
    const clothDark = toon(boy ? 0x6f788f : 0xc9d0e2);
    const accentMat = toon(opt.accent);
    const hairMat = toon(opt.hair);
    const hairShine = new THREE.MeshBasicMaterial({ color: opt.hairLight || 0x5566a0, transparent: true, opacity: 0.85 });
    this.sleeveMat = clothMat;
    this.looks = { hair: hairMat, hairShine, cloth: clothMat, clothDark, accent: accentMat };

    const hips = (this.hips = new THREE.Group());
    hips.position.set(0, -0.45, 0);
    this.root.add(hips);

    // ---- thân (mảnh hơn kiểu anime)
    const torso = (this.torso = outlined(new THREE.Mesh(new THREE.CapsuleGeometry(0.34, 0.64, 8, 24), clothMat), 0.012));
    torso.position.y = 0.72;
    torso.scale.set(1.16, 1, 0.82);
    hips.add(torso);

    if (boy) {
      // mũ hoodie sau gáy, dây rút, túi, khăn đỏ
      const hood = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.3, 20, 14), clothDark), 0.01);
      hood.scale.set(1.25, 0.7, 0.8);
      hood.position.set(0, 1.3, -0.2);
      hips.add(hood);
      for (const s of [-1, 1]) {
        const cord = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 0.4, 8), toon(0xf2f2f2));
        cord.position.set(s * 0.09, 1.08, 0.3);
        hips.add(cord);
        const tip = new THREE.Mesh(new THREE.SphereGeometry(0.03, 8, 8), accentMat);
        tip.position.set(s * 0.09, 0.87, 0.3);
        hips.add(tip);
      }
      const pocket = outlined(new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.2, 0.05), clothDark), 0.008);
      pocket.position.set(0, 0.36, 0.3);
      hips.add(pocket);
      const scarf = outlined(new THREE.Mesh(new THREE.TorusGeometry(0.25, 0.08, 12, 28), accentMat), 0.01);
      scarf.rotation.x = Math.PI / 2;
      scarf.position.set(0, 1.3, 0.0);
      hips.add(scarf);
      const tail = outlined(new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.55, 0.05), accentMat), 0.008);
      tail.position.set(0.14, 1.0, 0.33);
      tail.rotation.z = 0.1;
      hips.add(tail);
    } else {
      // áo dài: cổ đứng, viền chéo, nơ ruy băng
      const collar = outlined(new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.18, 0.14, 24, 1, true), toon(0xffffff, { side: THREE.DoubleSide })), 0.008);
      collar.position.set(0, 1.35, 0);
      hips.add(collar);
      const trim = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.95, 0.012), accentMat);
      trim.position.set(0.06, 0.85, 0.335);
      trim.rotation.z = 0.32;
      hips.add(trim);
      const trim2 = new THREE.Mesh(new THREE.BoxGeometry(0.03, 0.85, 0.012), clothDark);
      trim2.position.set(-0.02, 0.8, 0.337);
      trim2.rotation.z = -0.2;
      hips.add(trim2);
      for (const s of [-1, 1]) {
        const wing = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.09, 14, 10), accentMat), 0.008);
        wing.scale.set(1.5, 0.8, 0.5);
        wing.position.set(s * 0.12, 1.2, 0.3);
        wing.rotation.z = s * -0.4;
        hips.add(wing);
      }
      // đường cong ngực nhẹ nhàng dưới lớp áo
      for (const s of [-1, 1]) {
        const bust = new THREE.Mesh(new THREE.SphereGeometry(0.15, 22, 16), clothMat);
        bust.scale.set(1, 0.9, 0.7);
        bust.position.set(s * 0.15, 1.0, 0.26);
        hips.add(bust);
      }
      const knot = new THREE.Mesh(new THREE.SphereGeometry(0.05, 12, 10), accentMat);
      knot.position.set(0, 1.2, 0.32);
      hips.add(knot);
    }

    // ---- vai
    this.shoulder = [new THREE.Object3D(), new THREE.Object3D()];
    this.shoulder[0].position.set(0.46, 1.1, 0);
    this.shoulder[1].position.set(-0.46, 1.1, 0);
    hips.add(this.shoulder[0], this.shoulder[1]);

    // ---- cổ + đầu
    const neck = outlined(new THREE.Mesh(new THREE.CylinderGeometry(0.085, 0.1, 0.3, 16), skin), 0.008);
    neck.position.y = 1.42;
    hips.add(neck);

    const head = (this.head = new THREE.Group());
    head.position.set(0, 1.5, 0);
    head.scale.setScalar(0.92);
    hips.add(head);

    const faceGeo = animeFaceGeometry(0.52);
    const face = outlined(new THREE.Mesh(faceGeo, skin), 0.012);
    face.position.y = 0.46;
    head.add(face);
    const FY = 0.46; // tâm mặt

    for (const s of [-1, 1]) {
      const ear = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.075, 12, 10), skin), 0.008);
      ear.position.set(s * 0.5, FY - 0.04, -0.02);
      ear.scale.set(0.55, 1, 0.8);
      head.add(ear);
    }

    // ---- tóc
    const hairGroup = new THREE.Group();
    hairGroup.position.set(0, 0.5, -0.04);
    hairGroup.rotation.x = -0.26;
    head.add(hairGroup);
    const cap = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.575, 44, 28, 0, Math.PI * 2, 0, Math.PI * 0.6), hairMat), 0.012);
    hairGroup.add(cap);
    // vòng sáng "thiên thần" trên tóc
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.47, 0.034, 8, 40, Math.PI * 0.95), hairShine);
    ring.rotation.x = Math.PI / 2;
    ring.rotation.z = Math.PI * 0.025 + Math.PI / 2 - Math.PI * 0.475 - Math.PI / 2;
    ring.position.y = 0.33;
    hairGroup.add(ring);
    // phần tóc sau gáy
    const back = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.5, 24, 18), hairMat), 0.01);
    back.scale.set(1.04, 1.0, 0.86);
    back.position.set(0, 0.34, -0.26);
    head.add(back);

    // mái: các lọn nhọn xõa xuống trán
    for (let i = 0; i < 7; i++) {
      const x = (i - 3) * 0.125;
      const y = 0.83 - Math.abs(x) * 0.22;
      const zf = Math.sqrt(Math.max(0.02, 0.2704 - (y - FY) * (y - FY) - x * x)) + 0.035;
      const lock = outlined(new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.34 + (i % 2) * 0.06, 6), hairMat), 0.008);
      lock.position.set(x, y, zf);
      lock.rotation.set(-0.3, 0, Math.PI + (i - 3) * 0.11);
      head.add(lock);
    }
    this.tails = [];
    if (boy) {
      // tóc dựng gai
      for (let i = 0; i < 7; i++) {
        const a = (i / 6 - 0.5) * 2.4;
        const sp = outlined(new THREE.Mesh(new THREE.ConeGeometry(0.12, 0.38 + (i % 2) * 0.1, 7), hairMat), 0.009);
        sp.position.set(Math.sin(a) * 0.36, 1.0 + Math.cos(a) * 0.04, -0.06 - Math.abs(a) * 0.06);
        sp.rotation.z = -a * 0.75;
        sp.rotation.x = -0.28;
        head.add(sp);
      }
      for (const s of [-1, 1]) {
        const side = outlined(new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.42, 6), hairMat), 0.008);
        side.position.set(s * 0.48, 0.5, 0.12);
        side.rotation.set(0, 0, Math.PI + s * -0.1);
        head.add(side);
      }
    } else {
      // tai mèo (có phần lót hồng)
      for (const s of [-1, 1]) {
        const ear = outlined(new THREE.Mesh(new THREE.ConeGeometry(0.19, 0.38, 4), hairMat), 0.01);
        ear.position.set(s * 0.34, 1.07, 0.0);
        ear.rotation.z = s * -0.3;
        ear.rotation.y = Math.PI / 4;
        head.add(ear);
        const inner = new THREE.Mesh(new THREE.ConeGeometry(0.11, 0.26, 4), toon(0xff9db4));
        inner.position.set(s * 0.335, 1.04, 0.05);
        inner.rotation.z = s * -0.3;
        inner.rotation.y = Math.PI / 4;
        head.add(inner);
      }
      // sợi tóc ahoge
      const curve = new THREE.CatmullRomCurve3([V(0, 1.0, 0.06), V(0.03, 1.18, 0.1), V(0.15, 1.33, 0.1), V(0.3, 1.31, 0.04)]);
      const ahoge = outlined(new THREE.Mesh(new THREE.TubeGeometry(curve, 14, 0.022, 8, false), hairMat), 0.006);
      head.add(ahoge);
      // lọn tóc mai dài hai bên má
      for (const s of [-1, 1]) {
        const lock = outlined(new THREE.Mesh(new THREE.ConeGeometry(0.075, 0.62, 6), hairMat), 0.008);
        lock.position.set(s * 0.46, 0.34, 0.2);
        lock.rotation.set(-0.12, 0, Math.PI + s * -0.06);
        head.add(lock);
      }
      // hai bím tóc dài, thon dần
      for (const s of [-1, 1]) {
        const g = new THREE.Group();
        g.position.set(s * 0.5, 0.7, -0.12);
        const tie = outlined(new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.04, 8, 18), accentMat), 0.006);
        tie.rotation.y = Math.PI / 2;
        g.add(tie);
        const radii = [0.17, 0.15, 0.11, 0.06, 0.005];
        let pos = V(0, -0.06, 0);
        for (let i = 0; i < 4; i++) {
          const ang = 0.1 + i * 0.12;
          const dir = V(s * Math.sin(ang), -Math.cos(ang), -0.12).normalize();
          const len = 0.4;
          const seg = outlined(new THREE.Mesh(new THREE.CylinderGeometry(radii[i], radii[i + 1], len, 14), hairMat), 0.008);
          seg.position.copy(pos).addScaledVector(dir, len / 2);
          seg.quaternion.setFromUnitVectors(UP, dir.clone().negate());
          g.add(seg);
          pos = pos.clone().addScaledVector(dir, len * 0.95);
        }
        head.add(g);
        this.tails.push({ g, s });
      }
    }

    // ---- mắt to kiểu anime (decal vẽ bằng canvas)
    this.eyes = [];
    const irisCols = boy ? ['#4a2208', '#e0892a', '#ffe3a0'] : ['#16305e', '#2f86d6', '#aee6ff'];
    const eyeTex = [makeEyeTexture(irisCols, false), makeEyeTexture(irisCols, true)];
    const EYE_Y = FY - 0.045;
    for (const s of [-1, 1]) {
      const ex = s * 0.205;
      const ez = surfaceZ(faceGeo, ex, EYE_Y - FY) + 0.006;
      const eye = new THREE.Group();
      eye.position.set(ex, EYE_Y, ez);
      eye.rotation.y = Math.asin(Math.min(0.9, Math.abs(ex) / 0.5)) * s * 0.95;
      const plane = new THREE.Mesh(
        new THREE.PlaneGeometry(0.27, 0.34),
        new THREE.MeshBasicMaterial({ map: eyeTex[s > 0 ? 0 : 1], transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -3 })
      );
      eye.add(plane);
      head.add(eye);
      this.eyes.push(eye);
    }
    // lông mày mảnh
    this.brows = [];
    for (const s of [-1, 1]) {
      const baseY = FY + 0.2;
      const br = new THREE.Mesh(new THREE.BoxGeometry(0.15, 0.022, 0.025), hairMat);
      br.position.set(s * 0.205, baseY, surfaceZ(faceGeo, s * 0.205, 0.2) + 0.012);
      br.rotation.y = s * 0.4;
      head.add(br);
      this.brows.push({ m: br, s, baseY });
    }
    // má hồng
    const blushTex = makeBlushTexture();
    for (const s of [-1, 1]) {
      const bz = surfaceZ(faceGeo, s * 0.3, -0.12) + 0.004;
      const bl = new THREE.Mesh(
        new THREE.PlaneGeometry(0.17, 0.1),
        new THREE.MeshBasicMaterial({ map: blushTex, transparent: true, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })
      );
      bl.position.set(s * 0.3, FY - 0.12, bz);
      bl.rotation.y = s * 0.7;
      head.add(bl);
    }
    // mũi nhỏ
    const nose = new THREE.Mesh(new THREE.SphereGeometry(0.016, 8, 8), toon(0xf0b69e));
    nose.position.set(0, FY - 0.12, surfaceZ(faceGeo, 0, -0.12) + 0.006);
    head.add(nose);
    // miệng (nhiều kiểu, bật/tắt theo biểu cảm)
    const mouthMat = new THREE.MeshBasicMaterial({ color: 0x8a2f3a });
    this.mouths = {};
    const MY = FY - 0.255;
    const mz = surfaceZ(faceGeo, 0, -0.255) + 0.008;
    const smile = new THREE.Mesh(new THREE.TorusGeometry(0.06, 0.011, 8, 24, Math.PI), mouthMat);
    smile.rotation.z = Math.PI;
    smile.position.set(0, MY + 0.05, mz);
    const sad = new THREE.Mesh(new THREE.TorusGeometry(0.05, 0.011, 8, 24, Math.PI), mouthMat);
    sad.position.set(0, MY - 0.03, mz);
    const flat = new THREE.Mesh(new THREE.BoxGeometry(0.075, 0.016, 0.012), mouthMat);
    flat.position.set(0, MY, mz);
    const oh = new THREE.Mesh(new THREE.SphereGeometry(0.032, 12, 10), mouthMat);
    oh.scale.set(1, 1.25, 0.35);
    oh.position.set(0, MY, mz);
    for (const [k, m] of Object.entries({ smile, sad, flat, oh })) {
      head.add(m);
      this.mouths[k] = m;
    }

    // ---- tay (toạ độ thế giới)
    this.arms = [];
    for (let i = 0; i < 2; i++) {
      const upper = outlined(new THREE.Mesh(new THREE.CylinderGeometry(0.135, 0.12, 1, 20), clothMat), 0.01);
      const fore = outlined(new THREE.Mesh(new THREE.CylinderGeometry(0.118, 0.095, 1, 20), clothMat), 0.01);
      const joint = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.128, 16, 14), clothMat), 0.01);
      const cuff = boy
        ? outlined(new THREE.Mesh(new THREE.CylinderGeometry(0.108, 0.108, 0.07, 18), accentMat), 0.008)
        : outlined(new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.11, 0.26, 20, 1, true), toon(0xffffff, { side: THREE.DoubleSide })), 0.008);
      const hand = outlined(new THREE.Mesh(new THREE.SphereGeometry(0.115, 18, 16), skin), 0.01);
      hand.scale.set(1, 0.85, 1.2);
      for (const m of [upper, fore, joint, cuff, hand]) {
        m.castShadow = true;
        this.world.add(m);
      }
      this.arms.push({ upper, fore, joint, cuff, hand });
    }

    // quân đang cầm
    this.held = makePieceMesh(this.mark, 0.13);
    this.held.visible = false;
    this.world.add(this.held);

    // bảng tên
    this.tag = makeSprite(2.0, 0.5);
    this.world.add(this.tag.sprite);
    // bóng suy nghĩ
    this.bubble = makeSprite(1.9, 0.95);
    this.bubble.sprite.visible = false;
    this.world.add(this.bubble.sprite);
    this.dots = [];
    for (let i = 0; i < 2; i++) {
      const d = makeSprite(0.3, 0.3);
      d.ctx.fillStyle = 'rgba(255,255,255,0.95)';
      d.ctx.beginPath();
      d.ctx.arc(d.canvas.width / 2, d.canvas.height / 2, d.canvas.width * 0.42, 0, Math.PI * 2);
      d.ctx.fill();
      d.tex.needsUpdate = true;
      d.sprite.scale.set(0.16 + i * 0.1, 0.16 + i * 0.1, 1);
      d.sprite.visible = false;
      this.world.add(d.sprite);
      this.dots.push(d);
    }

    this.root.traverse((o) => {
      if (o.isMesh && o.material !== hairShine) o.castShadow = true;
    });
    this.setTag('Chờ người chơi…');
    this.drawBubble('Hmm…');
  }

  // ------------------------------------------------------------------ chữ nổi
  setTag(name, neutral = false, avatarUrl = '') {
    const img = avatarUrl && !neutral ? getAvatar(avatarUrl, () => this.redrawTag()) : null;
    const key = name + (neutral ? '|n' : '') + (img ? '|a' + avatarUrl : '');
    if (key === this.tagName) return;
    this.tagName = key;
    this.tagArgs = [name, neutral, avatarUrl];
    this.tagPop = 1;
    const { ctx, canvas, tex } = this.tag;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(10,14,26,0.82)';
    roundRect(ctx, 4, 4, W - 8, H - 8, H / 2 - 4);
    ctx.fill();
    ctx.lineWidth = 6;
    const col = neutral ? '#8a93aa' : this.mark === 'X' ? '#ffd166' : '#6aa8ff';
    ctx.strokeStyle = col;
    ctx.stroke();
    const cx = H / 2 + 4;
    const R = H / 2 - 12;
    if (img) {
      // ảnh đại diện TikTok làm biểu tượng, có viền màu đội + chấm nhỏ X / O
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, H / 2, R, 0, Math.PI * 2);
      ctx.clip();
      const sz = Math.min(img.naturalWidth || R * 2, img.naturalHeight || R * 2);
      const sx = ((img.naturalWidth || sz) - sz) / 2;
      const sy = ((img.naturalHeight || sz) - sz) / 2;
      ctx.drawImage(img, sx, sy, sz, sz, cx - R, H / 2 - R, R * 2, R * 2);
      ctx.restore();
      ctx.lineWidth = 7;
      ctx.strokeStyle = col;
      ctx.beginPath();
      ctx.arc(cx, H / 2, R, 0, Math.PI * 2);
      ctx.stroke();
      const bx = cx + R * 0.72;
      const by = H / 2 + R * 0.72;
      ctx.fillStyle = col;
      ctx.beginPath();
      ctx.arc(bx, by, H * 0.17, 0, Math.PI * 2);
      ctx.fill();
      ctx.lineWidth = 3;
      ctx.strokeStyle = '#0a0e1a';
      ctx.stroke();
      ctx.fillStyle = '#14141c';
      ctx.font = `800 ${Math.round(H * 0.22)}px system-ui, Arial, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(this.mark === 'X' ? 'T' : 'Đ', bx, by + 1);
    } else {
      // huy hiệu X / O (chưa chọn thì hiện dấu ?)
      ctx.fillStyle = col;
      ctx.beginPath();
      ctx.arc(cx, H / 2, H / 2 - 20, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#14141c';
      ctx.font = `800 ${Math.round(H * 0.46)}px system-ui, Arial, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(neutral ? '?' : this.mark === 'X' ? 'T' : 'Đ', cx, H / 2 + 3);
    }
    // tên
    let text = name;
    let size = Math.round(H * 0.46);
    ctx.font = `800 ${size}px system-ui, Arial, sans-serif`;
    const maxW = W - H - 40;
    while (ctx.measureText(text).width > maxW && size > 20) {
      size -= 2;
      ctx.font = `800 ${size}px system-ui, Arial, sans-serif`;
    }
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#fff';
    ctx.fillText(text, H + 6, H / 2 + 3);
    tex.needsUpdate = true;
  }

  /** Vẽ lại bảng tên khi ảnh đại diện vừa tải xong. */
  redrawTag() {
    if (!this.tagArgs) return;
    this.tagName = '';
    this.setTag(...this.tagArgs);
  }

  drawBubble(text) {
    if (text === this.bubbleText) return;
    this.bubbleText = text;
    const { ctx, canvas, tex } = this.bubble;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(255,255,255,0.97)';
    ctx.strokeStyle = 'rgba(60,70,100,0.9)';
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.ellipse(W / 2, H / 2, W / 2 - 8, H / 2 - 8, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    let size = Math.round(H * 0.34);
    ctx.font = `800 ${size}px system-ui, Arial, sans-serif`;
    while (ctx.measureText(text).width > W * 0.72 && size > 18) {
      size -= 2;
      ctx.font = `800 ${size}px system-ui, Arial, sans-serif`;
    }
    ctx.fillStyle = '#232a44';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, W / 2, H / 2 + 3);
    tex.needsUpdate = true;
  }

  // ------------------------------------------------------------------ điều khiển
  setMode(mode) {
    if (this.mode === mode) return;
    this.mode = mode;
    this.modeT = 0;
    if (mode === 'think') this.thoughtTimer = 0;
  }

  /** Nhân vật đặt 1 quân vào ô `cell` (toạ độ thế giới). cb: { onTouch, onDone } */
  place(cell, cb) {
    this.placing = { t: 0, phase: 'idea', cell: cell.clone(), cb };
    this.setHeld(false);
  }

  setHeld(v) {
    this.heldVisible = v;
    this.held.visible = v;
  }

  /** Quân cờ đang cầm trên tay: 'p' tốt, 'n' mã, 'b' tượng, 'r' xe, 'q' hậu, 'k' vua */
  setHeldPiece(t) {
    if (this.heldType === t) return;
    this.heldType = t;
    this.world.remove(this.held);
    this.held = makeChessPiece(t, this.mark === 'X' ? 'w' : 'b', 0.17);
    this.held.visible = this.heldVisible;
    this.world.add(this.held);
  }

  isBusy() {
    return !!this.placing;
  }

  /** Quân đỏ đứng sau lưng nhân vật nào? -> dùng cho camera */
  headWorld() {
    return this.head.localToWorld(V(0, 0.46, 0));
  }

  rel(x, y, z) {
    const p = V(x, y, z).applyQuaternion(this.root.quaternion);
    p.x += this.root.position.x;
    p.z += this.root.position.z;
    return p;
  }

  /** Chọn độ nghiêng người đủ để tay với tới điểm target. */
  chooseLean(target) {
    const S = this.S;
    const reach = (this.L1 + this.L2) * 0.93;
    const yaw = this.root.quaternion;
    for (let lean = 0.1; lean <= 0.9; lean += 0.04) {
      const c = Math.cos(lean);
      const s = Math.sin(lean);
      const loc = V(-0.5, 1.05 * c, 1.05 * s);
      loc.y -= 0.45;
      loc.multiplyScalar(S).applyQuaternion(yaw);
      loc.x += this.root.position.x;
      loc.z += this.root.position.z;
      if (loc.distanceTo(target) <= reach) return lean;
    }
    return 0.9;
  }

  // ------------------------------------------------------------------ mỗi khung hình
  update(dt, time, ctx) {
    const S = this.S;
    this.modeT += dt;
    this.urgency = ctx.urgency || 0;
    const root = this.root;
    const board = ctx.boardCenter;

    // ---- mục tiêu bàn tay (tính theo toạ độ thế giới)
    const rest = (side) => this.rel(side * 0.62, 0.075, 0.6);
    const goals = [rest(1), rest(-1)];
    let speeds = [7, 7];
    let leanGoal = 0.1;
    const head = { x: 0.05, y: 0, z: 0 };
    let mouth = 'smile';
    let browRaise = 0;
    let browTilt = 0;
    let squint = 0;
    let jump = 0;
    let bubble = false;

    const t = time + this.phase;
    // người ngồi nhìn nhẹ về phía bàn, thỉnh thoảng nhìn quanh
    head.y = Math.sin(t * 0.5) * 0.12;

    switch (this.mode) {
      case 'think': {
        // tay phải chống cằm, tay trái gõ bàn
        const chin = this.head.localToWorld(V(-0.12, 0.02, 0.55));
        goals[1] = chin;
        speeds[1] = 6;
        const tap = Math.max(0, Math.sin(time * 6 + this.phase)) * (Math.sin(time * 0.8 + this.phase) > 0 ? 0.05 : 0);
        goals[0] = this.rel(0.5, 0.075 + tap, 0.78);
        head.x = 0.3 + Math.sin(t * 0.9) * 0.05;
        head.y = Math.sin(t * 0.55) * 0.22;
        head.z = -0.14;
        leanGoal = 0.2;
        mouth = this.urgency > 0.65 ? 'oh' : 'flat';
        browRaise = 0.02 + this.urgency * 0.04;
        browTilt = 0.12 + this.urgency * 0.12;
        bubble = true;
        break;
      }
      case 'walk': {
        // đứng dậy / đi bộ: 2 tay buông, vung nhẹ ngược chân
        const sw = Math.sin(this.walkPhase) * 0.34 * this.walkAmp;
        goals[0] = this.rel(0.5, -0.5, 0.05 - sw);
        goals[1] = this.rel(-0.5, -0.5, 0.05 + sw);
        speeds = [10, 10];
        leanGoal = this.walkLean;
        head.x = 0;
        mouth = 'smile';
        break;
      }
      case 'win':
        goals[0] = this.rel(0.95, 2.15 + Math.sin(time * 9) * 0.1, 0.25);
        goals[1] = this.rel(-0.95, 2.15 + Math.cos(time * 9) * 0.1, 0.25);
        speeds = [9, 9];
        leanGoal = -0.04;
        head.x = -0.12;
        head.z = Math.sin(time * 6) * 0.1;
        mouth = 'smile';
        squint = 0.75;
        browRaise = 0.04;
        jump = Math.abs(Math.sin(time * 6.5)) * 0.2;
        break;
      case 'lose':
        goals[0] = this.rel(0.5, 0.075, 0.85);
        goals[1] = this.rel(-0.5, 0.075, 0.85);
        speeds = [3.5, 3.5];
        leanGoal = 0.32;
        head.x = 0.62;
        head.z = 0.06;
        mouth = 'sad';
        browRaise = 0.0;
        browTilt = -0.32;
        break;
      case 'shrug':
        goals[0] = this.rel(1.05, 1.0, 0.35);
        goals[1] = this.rel(-1.05, 1.0, 0.35);
        head.z = 0.18;
        mouth = 'flat';
        browTilt = -0.15;
        browRaise = 0.03;
        break;
      case 'cheer':
        goals[0] = this.rel(0.8, 1.0 + Math.sin(time * 5) * 0.12, 0.3);
        mouth = 'smile';
        browRaise = 0.04;
        head.y = Math.sin(time * 1.6) * 0.2;
        break;
      default: {
        // idle: ngồi chờ, thỉnh thoảng nghịch tay
        this.fidgetT += dt;
        const f = Math.sin(this.fidgetT * 0.7) > 0.6 ? Math.sin(this.fidgetT * 5) * 0.03 : 0;
        goals[0] = this.rel(0.62, 0.075 + Math.max(0, f), 0.6);
        mouth = 'smile';
      }
    }

    // ---- chuỗi đặt cờ (ghi đè tay phải)
    const p = this.placing;
    if (p) {
      p.t += dt;
      const up = V(0, 0.55, 0);
      const cell = p.cell;
      switch (p.phase) {
        case 'idea': // "à! có ý rồi" - giơ ngón tay
          goals[1] = this.rel(-0.55, 1.55, 0.95);
          speeds[1] = 9;
          browRaise = 0.07;
          mouth = 'smile';
          this.drawBubble('💡');
          bubble = true;
          head.x = 0.1;
          if (p.t > 0.38) {
            p.phase = 'lift';
            p.t = 0;
            this.setHeld(true);
            if (p.cb && p.cb.onLift) p.cb.onLift();
          }
          break;
        case 'lift':
          goals[1] = cell.clone().add(up);
          speeds[1] = 10;
          leanGoal = this.chooseLean(cell);
          head.x = 0.35;
          mouth = 'flat';
          if (p.t > 0.5) {
            p.phase = 'down';
            p.t = 0;
          }
          break;
        case 'down':
          goals[1] = cell.clone().add(V(0, 0.07, 0));
          speeds[1] = 16;
          leanGoal = this.chooseLean(cell);
          head.x = 0.38;
          mouth = 'flat';
          if (p.t > 0.26) {
            p.phase = 'hold';
            p.t = 0;
            this.setHeld(false);
            if (p.cb && p.cb.onTouch) p.cb.onTouch();
          }
          break;
        case 'hold':
          goals[1] = cell.clone().add(V(0, 0.07, 0));
          leanGoal = this.chooseLean(cell);
          head.x = 0.3;
          mouth = 'smile';
          if (p.t > 0.22) {
            p.phase = 'return';
            p.t = 0;
          }
          break;
        default: // return
          speeds[1] = 7;
          if (p.t > 0.65) {
            const cb = p.cb;
            this.placing = null;
            if (cb && cb.onDone) cb.onDone();
          }
      }
    }

    // ---- chuyển động mượt
    this.leanGoal = leanGoal;
    this.lean = damp(this.lean, this.leanGoal, 5, dt);
    this.hips.rotation.x = this.rig ? 0 : this.lean;
    this.torso.scale.y = 1 + Math.sin(time * 1.9 + this.phase) * 0.014;
    root.position.y = damp(root.position.y, jump, 18, dt);

    for (const k of ['x', 'y', 'z']) this.headRot[k] = damp(this.headRot[k], head[k], 6, dt);
    this.head.rotation.set(this.headRot.x, this.headRot.y, this.headRot.z);

    if (this.rig) this.rig.body(this.lean, this.headRot);
    root.updateMatrixWorld(true);
    for (let i = 0; i < 2; i++) {
      const h = this.hands[i];
      if (!h.init) {
        h.pos.copy(goals[i]);
        h.init = true;
      }
      h.pos.lerp(goals[i], 1 - Math.exp(-speeds[i] * dt));
    }

    // ---- IK cho 2 tay
    for (let i = 0; i < 2; i++) {
      const sh = this.shoulder[i].getWorldPosition(V());
      const side = i === 0 ? 1 : -1;
      const pole = V(side * 0.85, -1, -0.45).applyQuaternion(root.quaternion);
      solveArm(sh, this.hands[i].pos, this.L1, this.L2, pole, this.elbow[i], this.wrist[i]);
      if (this.rig) this.rig.arm(i, sh, this.elbow[i], this.wrist[i]);
      const a = this.arms[i];
      limb(a.upper, sh, this.elbow[i]);
      limb(a.fore, this.elbow[i], this.wrist[i]);
      a.joint.position.copy(this.elbow[i]);
      a.hand.position.copy(this.wrist[i]);
      a.cuff.position.copy(this.wrist[i]).lerp(this.elbow[i], 0.14);
      a.cuff.quaternion.copy(a.fore.quaternion);
    }
    // quân trên tay
    if (this.heldVisible) {
      this.held.position.copy(this.wrist[1]).add(V(0, -0.1, 0));
      this.held.rotation.y = time * 2;
    }

    // ---- khuôn mặt
    this.blinkTimer -= dt;
    if (this.blinkTimer <= 0) {
      this.blink = 1;
      this.blinkTimer = 2 + Math.random() * 3.5;
    }
    this.blink = Math.max(0, this.blink - dt * 7);
    const closed = Math.max(this.blink, squint);
    for (const e of this.eyes) e.scale.y = 1 - closed * 0.88;
    for (const b of this.brows) {
      b.m.position.y = b.baseY + browRaise * 1.2;
      b.m.rotation.z = b.s * -browTilt * 0.9;
    }
    for (const [k, m] of Object.entries(this.mouths)) m.visible = k === mouth;
    if (this.rig) this.rig.face(mouth, this.blink);
    for (const tl of this.tails) tl.g.rotation.z = tl.s * (Math.sin(time * 1.7 + this.phase) * 0.05 + this.lean * 0.1);

    // ---- chữ nổi
    const headW = this.head.localToWorld(V(0, 0.46, 0));
    const tagY = headW.y + 0.98 * S * 0.72 + 0.62;
    this.tagPop = Math.max(0, this.tagPop - dt * 2.2);
    const pop = 1 + Math.sin(this.tagPop * Math.PI) * 0.35;
    this.tag.sprite.position.set(headW.x, tagY, headW.z);
    this.tag.sprite.scale.set(2.0 * pop, 0.5 * pop, 1);

    // bóng suy nghĩ
    const showBubble = bubble && !(this.mode !== 'think' && !p);
    if (showBubble) {
      if (this.mode === 'think' && !p) {
        this.thoughtTimer -= dt;
        if (this.thoughtTimer <= 0) {
          this.thoughtTimer = 2.4 + Math.random() * 1.4;
          this.thoughtIndex = (this.thoughtIndex + 1 + Math.floor(Math.random() * 3)) % THOUGHTS.length;
          this.drawBubble(THOUGHTS[this.thoughtIndex]);
        }
      }
      const side = V(this.mark === 'X' ? 1 : -1, 0, 0).applyQuaternion(root.quaternion);
      const base = headW.clone().add(V(0, 0.62 * S + 0.55, 0)).addScaledVector(side, 0.95 * S);
      base.y += Math.sin(time * 2.2 + this.phase) * 0.04;
      this.bubble.sprite.position.copy(base);
      this.bubble.sprite.visible = true;
      this.dots[0].sprite.position.copy(headW).add(V(0, 0.58 * S + 0.15, 0)).addScaledVector(side, 0.42 * S);
      this.dots[1].sprite.position.copy(headW).add(V(0, 0.58 * S + 0.33, 0)).addScaledVector(side, 0.62 * S);
      this.dots.forEach((d) => (d.sprite.visible = true));
    } else {
      this.bubble.sprite.visible = false;
      this.dots.forEach((d) => (d.sprite.visible = false));
    }
  }
}
