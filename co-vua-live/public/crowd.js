/*
 * KHÁN GIẢ ĐỨNG QUANH PHÒNG: mỗi người xem đang tương tác (không phải người chơi) là 1 nhân vật nhỏ
 * đứng xa bàn cờ, có bảng tên + ảnh đại diện TikTok. Người mới đi từ mép phòng vào chỗ đứng, người
 * không còn tương tác thì quay đi ra. Khi ván kết thúc, khán giả nhảy mừng.
 *  - Module chỉ nhận danh sách { id, name, avatar } từ scene.setCrowd(); không đụng vào luật chơi.
 *  - Tắt bằng ?crowd=0 trên đường dẫn live, hoặc đặt crowdMax: 0 trong config.js.
 */
import * as THREE from './vendor/three.module.js';
import { getAvatar } from './avatar.js';

const FLOOR_Y = -1.95;
const MAX_FIGURES = 14;
const WALK_SPEED = 1.7;
const SKINS = [0xffe1cd, 0xf6cfb2, 0xe8b894, 0xd9a27c];
const HAIRS = [0x1b1b2c, 0x2b1d18, 0x4a2c16, 0x232c4a, 0x5a3b52, 0x6b5a2a];
const CLOTHS = [0x3d6bd6, 0xd6543d, 0x3fa56a, 0xb9559e, 0xe0a63a, 0x4aa8c9, 0x8f6bd6, 0xe0e4ee];

const hash = (s) => {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
};
const mat = (c) => new THREE.MeshToonMaterial({ color: c });

/** Các chỗ đứng: 3 hàng vòng cung phía sau bàn, tránh phía camera và lối đi của 2 người chơi. */
function makeSlots() {
  const out = [];
  [5.3, 6.3, 7.3].forEach((r, row) => {
    const step = row === 0 ? 14 : 11.5;
    for (let a = 80; a <= 330; a += step) {
      const rad = (a * Math.PI) / 180;
      const x = r * Math.cos(rad);
      const z = r * Math.sin(rad);
      if (Math.abs(Math.abs(z) - 1.75) < 1.05 && Math.abs(x) > 0.4) continue; // lối đi của người chơi
      const az = (Math.atan2(z, x) * 180) / Math.PI;
      if (az > -25 && az < 78) continue; // phía camera
      out.push({ x, z, row, taken: null, order: out.length });
    }
  });
  return out;
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

function makeTag(v) {
  const canvas = document.createElement('canvas');
  canvas.width = 384;
  canvas.height = 96;
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  sprite.scale.set(1.5, 0.375, 1);
  const draw = () => {
    const ctx = canvas.getContext('2d');
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgba(10,14,26,0.8)';
    roundRect(ctx, 3, 3, W - 6, H - 6, H / 2 - 3);
    ctx.fill();
    ctx.lineWidth = 4;
    ctx.strokeStyle = '#ffd54a';
    ctx.stroke();
    const cx = H / 2 + 3;
    const R = H / 2 - 10;
    const img = v.avatar ? getAvatar(v.avatar, draw) : null;
    if (img) {
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, H / 2, R, 0, Math.PI * 2);
      ctx.clip();
      const sz = Math.min(img.naturalWidth || 64, img.naturalHeight || 64);
      const sx = ((img.naturalWidth || sz) - sz) / 2;
      const sy = ((img.naturalHeight || sz) - sz) / 2;
      ctx.drawImage(img, sx, sy, sz, sz, cx - R, H / 2 - R, R * 2, R * 2);
      ctx.restore();
    } else {
      ctx.fillStyle = '#' + new THREE.Color(CLOTHS[hash(v.id) % CLOTHS.length]).getHexString();
      ctx.beginPath();
      ctx.arc(cx, H / 2, R, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.font = `800 ${Math.round(H * 0.42)}px system-ui, Arial, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText((Array.from(v.name || '?')[0] || '?').toUpperCase(), cx, H / 2 + 2);
    }
    let size = Math.round(H * 0.4);
    ctx.font = `800 ${size}px system-ui, Arial, sans-serif`;
    const maxW = W - H - 28;
    while (ctx.measureText(v.name).width > maxW && size > 16) {
      size -= 2;
      ctx.font = `800 ${size}px system-ui, Arial, sans-serif`;
    }
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = '#fff';
    ctx.fillText(v.name, H + 2, H / 2 + 2);
    tex.needsUpdate = true;
  };
  draw();
  return { sprite, dispose: () => { tex.dispose(); sprite.material.dispose(); } };
}

function buildFigure(id) {
  const h = hash(id);
  const skin = mat(SKINS[h % SKINS.length]);
  const hair = mat(HAIRS[(h >> 3) % HAIRS.length]);
  const cloth = mat(CLOTHS[(h >> 6) % CLOTHS.length]);
  const pant = mat(0x2a3048);
  const g = new THREE.Group();
  const legs = [];
  for (const sd of [1, -1]) {
    const hip = new THREE.Group();
    hip.position.set(sd * 0.11, 0.84, 0);
    const leg = new THREE.Mesh(new THREE.CapsuleGeometry(0.085, 0.66, 5, 10), pant);
    leg.position.y = -0.42;
    hip.add(leg);
    g.add(hip);
    legs.push(hip);
  }
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.23, 0.46, 6, 14), cloth);
  torso.position.y = 1.2;
  torso.scale.z = 0.8;
  g.add(torso);
  const arms = [];
  for (const sd of [1, -1]) {
    const sh = new THREE.Group();
    sh.position.set(sd * 0.3, 1.45, 0);
    const arm = new THREE.Mesh(new THREE.CapsuleGeometry(0.07, 0.5, 5, 10), cloth);
    arm.position.y = -0.3;
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.075, 10, 8), skin);
    hand.position.y = -0.62;
    sh.add(arm, hand);
    g.add(sh);
    arms.push(sh);
  }
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.2, 18, 14), skin);
  head.position.y = 1.78;
  g.add(head);
  const cap = new THREE.Mesh(new THREE.SphereGeometry(0.215, 18, 12, 0, Math.PI * 2, 0, Math.PI * 0.58), hair);
  cap.position.y = 1.8;
  cap.rotation.x = -0.25;
  g.add(cap);
  if (h % 3 === 0) {
    const bun = new THREE.Mesh(new THREE.SphereGeometry(0.09, 10, 8), hair);
    bun.position.set(0, 1.99, -0.08);
    g.add(bun);
  }
  const eyeMat = mat(0x1b1b2c);
  for (const sd of [1, -1]) {
    const e = new THREE.Mesh(new THREE.SphereGeometry(0.026, 8, 6), eyeMat);
    e.position.set(sd * 0.07, 1.78, 0.185);
    g.add(e);
  }
  g.traverse((o) => {
    if (o.isMesh) o.castShadow = false;
  });
  return { group: g, legs, arms, torso, head };
}

export class Crowd {
  constructor(scene) {
    this.scene = scene;
    this.enabled = new URLSearchParams(location.search).get('crowd') !== '0';
    this.slots = makeSlots();
    this.members = new Map(); // id -> thành viên
    this.leaving = [];
  }

  /** Cập nhật danh sách người xem. instant: có mặt ngay (lần đầu mở trang) không cần đi vào. */
  setViewers(list, instant = false) {
    if (!this.enabled) return;
    const want = new Map();
    for (const v of (list || []).slice(0, MAX_FIGURES)) if (v && v.id) want.set(String(v.id), v);
    // người không còn trong danh sách -> đi ra
    for (const [id, m] of [...this.members]) {
      if (!want.has(id)) {
        this.members.delete(id);
        if (m.slot) m.slot.taken = null;
        m.mode = 'leave';
        m.ry = Math.atan2(m.pos.x, m.pos.z); // quay lưng lại bàn, đi ra tường
        this.leaving.push(m);
      }
    }
    for (const [id, v] of want) {
      const old = this.members.get(id);
      if (old) {
        if (old.name !== v.name || old.avatar !== (v.avatar || '')) this.retag(old, v);
        continue;
      }
      const slot = this.pickSlot(id);
      if (!slot) continue;
      this.members.set(id, this.makeMember(id, v, slot, instant));
    }
  }

  pickSlot(id) {
    const h = hash(id);
    let best = null;
    let bestScore = Infinity;
    for (const s of this.slots) {
      if (s.taken) continue;
      const score = s.row * 1000 + ((h + s.order * 37) % 997);
      if (score < bestScore) {
        bestScore = score;
        best = s;
      }
    }
    return best;
  }

  makeMember(id, v, slot, instant) {
    const f = buildFigure(id);
    const m = { id, name: v.name, avatar: v.avatar || '', slot, ...f, phase: Math.random() * 6, mode: 'stand', t: 0, wave: 0 };
    slot.taken = id;
    m.pos = new THREE.Vector3(slot.x, FLOOR_Y, slot.z);
    if (!instant) {
      const k = 10.2 / Math.hypot(slot.x, slot.z);
      m.pos.set(slot.x * k, FLOOR_Y, slot.z * k);
      m.mode = 'enter';
    }
    m.ry = Math.atan2(-slot.x, -slot.z);
    m.group.position.copy(m.pos);
    m.group.rotation.y = m.ry;
    m.tag = makeTag(m);
    this.scene.add(m.group);
    this.scene.add(m.tag.sprite);
    return m;
  }

  retag(m, v) {
    m.name = v.name;
    m.avatar = v.avatar || '';
    m.tag.dispose();
    this.scene.remove(m.tag.sprite);
    m.tag = makeTag(m);
    this.scene.add(m.tag.sprite);
  }

  remove(m) {
    this.scene.remove(m.group);
    this.scene.remove(m.tag.sprite);
    m.tag.dispose();
  }

  update(dt, time, cheer = false) {
    if (!this.enabled) return;
    for (const m of this.members.values()) this.step(m, dt, time, cheer);
    for (let i = this.leaving.length - 1; i >= 0; i--) {
      const m = this.leaving[i];
      this.step(m, dt, time, false);
      if (Math.hypot(m.pos.x, m.pos.z) > 10.4) {
        this.remove(m);
        this.leaving.splice(i, 1);
      }
    }
  }

  step(m, dt, time, cheer) {
    const slot = m.slot;
    let walking = false;
    if (m.mode === 'enter') {
      const dx = slot.x - m.pos.x;
      const dz = slot.z - m.pos.z;
      const d = Math.hypot(dx, dz);
      if (d < 0.05) {
        m.mode = 'stand';
        m.wave = 1.6; // vừa tới thì vẫy tay chào
      } else {
        const s = Math.min(d, WALK_SPEED * dt);
        m.pos.x += (dx / d) * s;
        m.pos.z += (dz / d) * s;
        walking = true;
      }
    } else if (m.mode === 'leave') {
      const d = Math.hypot(m.pos.x, m.pos.z) || 1;
      m.pos.x += (m.pos.x / d) * WALK_SPEED * dt;
      m.pos.z += (m.pos.z / d) * WALK_SPEED * dt;
      walking = true;
    }
    const t = time + m.phase;
    let hop = 0;
    let armUp = 0;
    if (walking) {
      m.walkT = (m.walkT || 0) + dt * 7;
      const s = Math.sin(m.walkT);
      m.legs[0].rotation.x = s * 0.55;
      m.legs[1].rotation.x = -s * 0.55;
      m.arms[0].rotation.x = -s * 0.4;
      m.arms[1].rotation.x = s * 0.4;
    } else {
      m.legs[0].rotation.x = m.legs[1].rotation.x = 0;
      m.wave = Math.max(0, m.wave - dt);
      if (cheer) {
        hop = Math.abs(Math.sin(t * 6)) * 0.22;
        armUp = 1;
      }
      m.arms[0].rotation.x = 0;
      m.arms[1].rotation.x = 0;
      m.arms[0].rotation.z = -0.08 - (armUp ? 2.6 : 0);
      m.arms[1].rotation.z = 0.08 + (armUp ? 2.6 : 0);
      if (!armUp && m.wave > 0) {
        m.arms[0].rotation.z = -2.5 + Math.sin(time * 12) * 0.35;
      }
      m.group.rotation.z = Math.sin(t * 1.2) * 0.025;
    }
    if (walking) {
      m.arms[0].rotation.z = -0.08;
      m.arms[1].rotation.z = 0.08;
      m.group.rotation.z = 0;
    }
    m.group.position.set(m.pos.x, FLOOR_Y + hop, m.pos.z);
    m.group.rotation.y = m.mode === 'leave' ? m.ry : m.mode === 'enter' ? Math.atan2(slot.x - m.pos.x, slot.z - m.pos.z) : m.ry;
    m.tag.sprite.position.set(m.pos.x, FLOOR_Y + hop + 2.55, m.pos.z);
    m.tag.sprite.visible = m.mode !== 'leave';
  }
}
