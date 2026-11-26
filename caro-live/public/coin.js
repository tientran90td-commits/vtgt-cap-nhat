/*
 * ĐỒNG XU 3D (màn hình LIVE): đồng xu có độ dày (viền), mặt vàng kim loại có ánh sáng chớp theo góc quay, bóng đổ dưới sàn.
 * Diễn biến (khớp với src/match.js: COIN_DRAW_MS / COIN_LAND_MS):
 *   0 -> ~2.4s : tung lên, lộn vòng liên tục (CHƯA ai biết kết quả - server chưa bốc)
 *   ~2.4s      : chạm sàn, nảy 2 lần, vẫn quay chậm dần
 *   drawMs     : server bốc kết quả (s.coin.face) -> đồng xu giảm tốc và dừng đúng mặt ngửa/sấp trong ~1.5s
 *   revealMs   : đã dừng hẳn -> server mới chia X/O, màn hình mới hiện "ai đi trước".
 * Vị trí của đồng xu là HÀM CỦA THỜI GIAN (không cần giữ trạng thái) nên mở trang giữa chừng vẫn hiện đúng.
 */
const R = 3.6; // bán kính (rem)
const T = 0.55; // độ dày (rem)
const N = 44; // số lát tạo viền tròn
const TOSS_MS = 2400; // thời gian bay lên + rơi xuống
const SPIN = 3.4; // vòng/giây khi đang bay
const SPIN_MIN = 0.7; // vòng/giây khi quay trên sàn lúc chờ kết quả
const TAU = 450; // độ tắt dần của tốc độ quay sau khi chạm sàn (ms)
const PEAK = 5.2; // độ cao tối đa (rem)

const ease = (u) => 1 - Math.pow(1 - Math.min(1, Math.max(0, u)), 3);

/** Góc quay (độ) của đồng xu tại thời điểm t (ms) khi CHƯA có kết quả. */
export function freeAngle(t) {
  if (t <= TOSS_MS) return SPIN * 360 * (t / 1000);
  const dt = t - TOSS_MS;
  return SPIN * 360 * (TOSS_MS / 1000) + (SPIN - SPIN_MIN) * 360 * (TAU / 1000) * (1 - Math.exp(-dt / TAU)) + SPIN_MIN * 360 * (dt / 1000);
}

/** Độ cao (rem, dương = lên cao) tại thời điểm t. */
export function heightAt(t) {
  if (t < 0) return 0;
  if (t <= TOSS_MS) {
    const u = t / TOSS_MS;
    return PEAK * 4 * u * (1 - u);
  }
  const dt = t - TOSS_MS;
  if (dt < 340) return 1.15 * 4 * (dt / 340) * (1 - dt / 340); // nảy lần 1
  if (dt < 340 + 210) return 0.38 * 4 * ((dt - 340) / 210) * (1 - (dt - 340) / 210); // nảy lần 2
  return 0;
}

/**
 * Góc quay (độ) khi đã biết kết quả: bắt đầu giảm tốc từ thời điểm ts, kéo dài durMs, dừng đúng mặt.
 * face: 'heads' -> góc ≡ 0 (mod 360); 'tails' -> ≡ 180.
 */
export function settleAngle(t, ts, durMs, face) {
  const a0 = freeAngle(ts);
  const w0 = (freeAngle(ts + 1) - freeAngle(ts - 1)) / 2; // độ/ms
  const want = a0 + (w0 * durMs) / 3; // ease-out cubic có vận tốc đầu = 3*(đoạn)/dur
  const base = face === 'tails' ? 180 : 0;
  const aF = Math.ceil((want - base) / 360) * 360 + base;
  if (t >= ts + durMs) return aF;
  return a0 + (aF - a0) * ease((t - ts) / durMs);
}

function face(cls, label, person) {
  const el = document.createElement('div');
  el.className = 'cface ' + cls;
  const av = person && person.avatar ? `<i class="cav" style="background-image:url('${String(person.avatar).replace(/['"\\()]/g, '')}')"></i>` : '';
  el.innerHTML = `<div class="cring"></div><b>${label}</b>${av}<span class="cnm"></span>`;
  el.querySelector('.cnm').textContent = person && person.name ? person.name : '';
  return el;
}

export class CoinFx {
  constructor(scene, sfx) {
    this.scene = scene;
    this.sfx = sfx;
    this.raf = 0;
    this.key = null;
    this.st = null; // { s, nowFn }
    this.landed = false;
    this.built = false;
  }

  build(s) {
    const sc = this.scene;
    sc.innerHTML = '';
    const stage = document.createElement('div');
    stage.className = 'cstage';
    stage.innerHTML = '<div class="cshadow"></div><div class="cfly"><div class="coin3d"></div></div>';
    sc.appendChild(stage);
    const coin = stage.querySelector('.coin3d');
    coin.appendChild(face('head', 'NGỬA', s.coin.heads));
    coin.appendChild(face('tail', 'SẤP', s.coin.tails));
    const chord = 2 * R * Math.sin(Math.PI / N) + 0.04;
    for (let i = 0; i < N; i++) {
      const r = document.createElement('div');
      r.className = 'crim';
      r.style.cssText = `width:${T}rem;height:${chord}rem;margin:${-chord / 2}rem 0 0 ${-T / 2}rem;transform:rotateZ(${(i * 360) / N}deg) translateX(${R}rem) rotateY(90deg);`;
      coin.appendChild(r);
    }
    this.el = { stage, fly: stage.querySelector('.cfly'), coin, shadow: stage.querySelector('.cshadow') };
    this.built = true;
  }

  /** Gọi mỗi lần có dữ liệu mới khi đang ở pha tung xu. nowFn() = giờ máy chủ. */
  set(s, nowFn) {
    this.st = { s, nowFn };
    if (this.key !== s.gameNo) {
      this.key = s.gameNo;
      this.landed = false;
      this.build(s);
      if (nowFn() - s.phaseStartedAt < 1500 && this.sfx) this.sfx.coinToss();
    }
    if (!this.raf) this.raf = requestAnimationFrame(() => this.frame());
  }

  stop() {
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.st = null;
  }

  frame() {
    this.raf = 0;
    const st = this.st;
    if (!st || !this.built) return;
    const { s, nowFn } = st;
    const c = s.coin;
    const t = nowFn() - s.phaseStartedAt;
    const land = (c.revealMs || 4100) - (c.drawMs || 2600);
    const ts = c.drawMs || 2600; // lúc server bốc kết quả: từ đó đồng xu giảm tốc về đúng mặt (mọi máy xem cùng một đường cong)
    const angle = c.face ? settleAngle(t, ts, land, c.face) : freeAngle(t);
    // chạm sàn: tiếng "keng"
    if (!this.landed && t >= TOSS_MS) {
      this.landed = true;
      if (this.sfx) this.sfx.coinLand();
    }
    const h = heightAt(t);
    // lắc nhẹ khi gần dừng (đồng xu "chao" rồi nằm yên)
    const tt = c.face ? t - ts : 0;
    const settling = c.face ? Math.max(0, 1 - tt / land) : 0;
    const wob = c.face ? Math.sin(tt / 70) * 7 * settling * settling : 0;
    const drift = t < TOSS_MS ? Math.sin((t / TOSS_MS) * Math.PI * 2) * 0.35 : 0; // lệch ngang nhẹ khi bay
    const { fly, coin, shadow } = this.el;
    fly.style.transform = `translate3d(${drift}rem, ${-h}rem, 0)`;
    coin.style.transform = `rotateX(${angle}deg) rotateZ(${wob + Math.sin(t / 380) * (t < TOSS_MS ? 6 : 0)}deg)`;
    // ánh kim loại chớp khi mặt đồng xu hướng thẳng về phía người xem (góc ≈ 0/180)
    const facing = Math.abs(Math.cos((angle * Math.PI) / 180));
    const glint = Math.pow(facing, 14);
    this.el.fly.style.filter = `brightness(${(0.82 + 0.2 * facing + 0.45 * glint).toFixed(3)}) saturate(${(0.95 + 0.25 * glint).toFixed(3)})`;
    // bóng: nhỏ + mờ khi đồng xu ở trên cao, to + đậm khi sát sàn
    const k = 1 - Math.min(1, h / (PEAK * 1.2));
    const edge = 0.35 + 0.65 * facing; // nghiêng cạnh -> bóng hẹp lại
    shadow.style.transform = `translateX(-50%) scale(${(0.45 + 0.55 * k) * edge}, ${0.45 + 0.55 * k})`;
    shadow.style.opacity = (0.18 + 0.5 * k).toFixed(2);
    this.raf = requestAnimationFrame(() => this.frame());
  }
}
