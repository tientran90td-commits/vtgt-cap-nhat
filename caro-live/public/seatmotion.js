/*
 * ĐỘNG TÁC NGỒI VÀO BÀN / ĐỨNG DẬY RỜI BÀN cho 2 nhân vật chơi.
 *  - Chỉ làm 1 việc: thêm đôi chân và điều khiển vị trí, hướng quay, ghế của 1 nhân vật.
 *  - Không đụng vào luật chơi: ai đang "có mặt" do director.js báo qua scene.seat(mark, present).
 *
 * Rời bàn : đẩy ghế ra sau -> đứng dậy -> quay người -> đi ra mép phòng -> biến mất (ghế trống, bảng tên vẫn hiện).
 * Vào bàn : đi từ mép phòng tới -> quay mặt vào bàn -> kéo ghế -> ngồi xuống.
 */
import * as THREE from './vendor/three.module.js';

const ease = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const lerp = (a, b, k) => a + (b - a) * k;

// thời lượng từng giai đoạn (giây)
export const SEAT_TIMES = { stand: 0.6, turn: 0.45, walk: 2.4, sit: 0.65 };
const CHAIR_PULL = 0.9; // ghế được kéo ra sau bấy nhiêu
const THIGH = 0.58;
const SHIN = 0.6;

function buildLegs(ch) {
  const looks = ch.looks || {};
  const pant = new THREE.MeshToonMaterial({ color: looks.clothDark ? looks.clothDark.color.clone() : 0x6f788f });
  const shoe = new THREE.MeshToonMaterial({ color: 0x1d2030 });
  const group = new THREE.Group();
  group.position.y = -0.5; // ngang hông của nhân vật (toạ độ gốc nhân vật)
  const legs = [];
  for (const sd of [1, -1]) {
    const hip = new THREE.Group();
    hip.position.set(sd * 0.17, 0, 0);
    const thigh = new THREE.Mesh(new THREE.CapsuleGeometry(0.11, THIGH - 0.22, 6, 12), pant);
    thigh.position.y = -THIGH / 2;
    const knee = new THREE.Group();
    knee.position.y = -THIGH;
    const shin = new THREE.Mesh(new THREE.CapsuleGeometry(0.095, SHIN - 0.2, 6, 12), pant);
    shin.position.y = -SHIN / 2;
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.1, 0.32), shoe);
    foot.position.set(0, -SHIN + 0.02, 0.08);
    for (const m of [thigh, shin, foot]) m.castShadow = true;
    knee.add(shin, foot);
    hip.add(thigh, knee);
    group.add(hip);
    legs.push({ hip, knee });
  }
  ch.root.add(group);
  return { group, legs };
}

export class SeatMotion {
  /**
   * ch: Character | sign: +1 nếu ghế ở phía z dương, -1 nếu ở phía z âm
   * chair: các mô hình ghế [{ mesh }] đi cùng nhân vật | exitX: toạ độ x của chỗ đi ra
   */
  constructor(ch, chair, sign, exitX) {
    this.ch = ch;
    this.sign = sign;
    this.chair = chair.map((m) => ({ m, z0: m.position.z }));
    this.exitX = exitX;
    this.baseX = ch.root.position.x;
    this.baseZ = ch.root.position.z;
    this.baseRy = ch.root.rotation.y;
    this.walkRy = this.pickWalkRy();
    this.state = 'seated'; // seated | leaving | away | arriving
    this.t = 0;
    this.desired = true;
    this.cycle = false; // có người MỚI ngồi thay chỗ này: người cũ đứng dậy đi ra, người mới đi vào ngồi
    this.holding = false; // đang đợi đổi người: giữ bảng tên cũ cho đến khi người mới bước vào
    this.phase = 0; // pha bước chân
    this.legs = buildLegs(ch);
  }

  /** Góc quay để mặt hướng về phía lối ra (xoay 1/4 vòng gần nhất). */
  pickWalkRy() {
    const want = Math.sign(this.exitX - this.baseX) || 1;
    for (const d of [Math.PI / 2, -Math.PI / 2]) {
      if (Math.sign(Math.sin(this.baseRy + d)) === want) return this.baseRy + d;
    }
    return this.baseRy + Math.PI / 2;
  }

  get busy() {
    return this.state === 'leaving' || this.state === 'arriving';
  }
  get away() {
    return this.state === 'away';
  }

  /** Báo nhân vật nên có mặt hay không. instant = đặt ngay, không diễn động tác (lần đầu mở trang). */
  want(present, instant = false) {
    this.desired = !!present;
    if (!instant) return;
    if (!present && this.state === 'seated') this.setState('away');
    if (present && this.state === 'away') this.setState('seated');
  }

  /** Có người khác thay vào chỗ này (đổi người giữa các trận): diễn cảnh người cũ rời bàn rồi người mới đi vào. */
  replace() {
    if (this.state === 'away') return; // ghế đang trống: người mới tự đi vào
    this.cycle = true;
    this.holding = true;
  }

  setState(s) {
    this.state = s;
    this.t = 0;
  }

  duration() {
    const T = SEAT_TIMES;
    return T.stand + T.turn + T.walk;
  }

  update(dt, time) {
    const ch = this.ch;
    // đã chọn đúng trạng thái ổn định thì mới bắt đầu động tác mới
    if (this.state === 'seated' && (!this.desired || this.cycle)) {
      this.cycle = false;
      this.setState('leaving');
      ch.placing = null;
      ch.setHeld(false);
    } else if (this.state === 'away' && this.desired) {
      this.holding = false;
      this.setState('arriving');
    } else if (this.state === 'away') {
      this.holding = false;
    }
    this.t += dt;
    const T = SEAT_TIMES;

    // k: mức đứng của chân (0 ngồi .. 1 đứng) | chairK: ghế kéo ra | x, ry | walk: đang đi
    let legsK = 0;
    let chairK = 0;
    let x = this.baseX;
    let ry = this.baseRy;
    let walkAmp = 0;
    let lean = 0;
    let visible = true;

    if (this.state === 'leaving') {
      const t = this.t;
      const a = ease(t / T.stand);
      legsK = a;
      chairK = a;
      lean = Math.sin(Math.PI * clamp01(t / T.stand)) * 0.42;
      const b = ease((t - T.stand) / T.turn);
      ry = lerp(this.baseRy, this.walkRy, b);
      chairK = 1;
      if (t < T.stand) chairK = a;
      const w = clamp01((t - T.stand - T.turn) / T.walk);
      if (w > 0) {
        x = lerp(this.baseX, this.exitX, w);
        walkAmp = Math.min(1, w * 8) * (w > 0.92 ? (1 - w) / 0.08 : 1);
        legsK = 1;
      }
      if (t >= this.duration()) {
        this.setState('away');
        visible = false;
      }
    } else if (this.state === 'arriving') {
      const t = this.t;
      const w = clamp01(t / T.walk);
      ry = this.walkRy;
      x = lerp(this.exitX, this.baseX, w);
      legsK = 1;
      chairK = 1;
      walkAmp = Math.min(1, w * 8) * (w > 0.92 ? (1 - w) / 0.08 : 1);
      const b = ease((t - T.walk) / T.turn);
      if (t > T.walk) ry = lerp(this.walkRy, this.baseRy, b);
      const s0 = T.walk + T.turn;
      if (t > s0) {
        const a = ease((t - s0) / T.sit);
        legsK = 1 - a;
        chairK = 1 - a;
        lean = Math.sin(Math.PI * clamp01((t - s0) / T.sit)) * 0.3;
      }
      if (t >= s0 + T.sit) this.setState('seated');
    } else if (this.state === 'away') {
      visible = false;
      chairK = 1;
      legsK = 1;
    }

    // ---- áp dụng
    const root = ch.root;
    root.position.x = x;
    root.rotation.y = ry;
    root.visible = visible;
    this.phase += dt * 7.5 * (walkAmp > 0 ? 1 : 0);
    this.applyChair(chairK, visible || this.state === 'away');
    this.applyLegs(legsK, walkAmp, time);
    const rigged = !!ch.rig;
    this.legs.group.visible = !rigged;
    for (const a of ch.arms) for (const m of Object.values(a)) if (!rigged) m.visible = visible;

    // ghi đè cử động của Character khi đang đi / vắng mặt
    const driving = this.state !== 'seated';
    ch.walkDriving = driving;
    ch.walkPhase = this.phase;
    ch.walkAmp = walkAmp;
    ch.walkLegsK = legsK; // mức đứng của chân (0 ngồi .. 1 đứng): model 3D thật dùng để duỗi chân
    ch.walkLean = lean;
    if (driving) {
      ch.mode = 'walk';
      ch.placing = null;
    }
  }

  applyChair(k, show) {
    const dz = this.sign * CHAIR_PULL * k;
    for (const c of this.chair) c.m.position.z = c.z0 + dz;
  }

  applyLegs(legsK, walkAmp, time) {
    const { legs } = this.legs;
    for (let i = 0; i < 2; i++) {
      const p = this.phase + (i === 0 ? 0 : Math.PI);
      // đi bộ: đùi vung, gối gập khi đưa chân lên
      const wThigh = -Math.sin(p) * 0.55 * walkAmp;
      const wKnee = (0.08 + 0.7 * Math.max(0, Math.cos(p))) * walkAmp;
      // ngồi: đùi nằm ngang, cẳng chân thả xuống, đung đưa nhẹ
      const sit = Math.sin(time * 1.3 + i * 1.7) * 0.05;
      legs[i].hip.rotation.x = lerp(-Math.PI / 2 + sit * 0.5, wThigh, legsK);
      legs[i].knee.rotation.x = lerp(Math.PI / 2 + sit, wKnee, legsK);
    }
  }
}
