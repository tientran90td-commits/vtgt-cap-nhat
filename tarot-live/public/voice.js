/*
 * GIỌNG ĐỌC (trình duyệt đọc to bằng giọng tiếng Việt có sẵn trên máy).
 *  - Điều phối viên (mc): giọng nữ, tươi vui.   - Trọng tài (ref): giọng nam, nghiêm túc.
 *  - Microsoft Edge có sẵn giọng "HoaiMy" (nữ) và "NamMinh" (nam) rất tự nhiên -> nên dùng Edge.
 *  - Trình duyệt chỉ cho phát tiếng sau khi người dùng bấm chuột 1 lần vào trang (hoặc mở bằng file .bat đã kèm sẵn cờ cho phép).
 */
export class Voice {
  constructor({ onCaption } = {}) {
    this.onCaption = onCaption || (() => {});
    this.supported = typeof window !== 'undefined' && 'speechSynthesis' in window;
    this.settings = { on: true, volume: 1, mcVoice: '', refVoice: '' };
    this.forceMute = false;
    this.needsGesture = false;
    this.queue = [];
    this.current = null;
    this.token = 0;
    this.watchdog = null;
    this.clearTimer = null;
    this.voices = [];
    this.pick = { mc: null, ref: null, distinct: false };
    if (this.supported) {
      this.refreshVoices();
      try {
        window.speechSynthesis.addEventListener('voiceschanged', () => this.refreshVoices());
      } catch (e) {
        /* trình duyệt cũ */
      }
      this.probe();
    }
  }

  // ---------------------------------------------------------------- giọng
  refreshVoices() {
    this.voices = window.speechSynthesis.getVoices() || [];
    this.choose();
  }

  isVi(v) {
    return /^vi/i.test(v.lang || '') || /vietnam|tiếng việt/i.test(v.name || '');
  }

  viVoices() {
    return this.voices.filter((v) => this.isVi(v));
  }

  choose() {
    const vi = this.viVoices();
    const byName = (n) => (n ? this.voices.find((v) => v.name === n) : null);
    let mc = byName(this.settings.mcVoice);
    let ref = byName(this.settings.refVoice);
    if (vi.length) {
      const pool = vi.filter((v) => /natural|online/i.test(v.name)).length ? vi.filter((v) => /natural|online/i.test(v.name)) : vi;
      const female = pool.find((v) => /hoaimy|hoài my|linh|female|nữ/i.test(v.name));
      const male = pool.find((v) => /namminh|nam minh|male|nam\b/i.test(v.name));
      // Điều phối = giọng nam (NamMinh), Người đọc Tarot = giọng nữ (HoaiMy)
      mc = mc || male || pool.find((v) => v !== female) || pool[0];
      ref = ref || female || pool.find((v) => v !== mc) || pool[0];
    }
    this.pick = { mc, ref, distinct: !!(mc && ref && mc !== ref) };
  }

  describe() {
    if (!this.supported) return 'Trình duyệt này không có giọng đọc.';
    if (!this.viVoices().length) return 'Chưa tìm thấy giọng tiếng Việt. Hãy dùng Microsoft Edge, hoặc cài gói ngôn ngữ tiếng Việt cho Windows.';
    const m = this.pick.mc ? this.pick.mc.name : '?';
    const r = this.pick.ref ? this.pick.ref.name : '?';
    return this.pick.distinct ? `Điều phối: ${m} • Người đọc Tarot: ${r}` : `Chỉ có 1 giọng (${m}): 2 vai khác nhau nhờ tốc độ và cao độ`;
  }

  setSettings(s) {
    if (!s) return;
    const before = this.settings.mcVoice + '|' + this.settings.refVoice;
    this.settings = { ...this.settings, ...s };
    if (before !== this.settings.mcVoice + '|' + this.settings.refVoice) this.choose();
    if (!this.settings.on) this.stop();
  }

  // ---------------------------------------------------------------- mở khóa tiếng
  probe() {
    try {
      const u = new SpeechSynthesisUtterance(' ');
      u.volume = 0;
      u.onerror = (e) => {
        if (e && e.error === 'not-allowed') this.needsGesture = true;
      };
      u.onend = () => {
        this.needsGesture = false;
      };
      window.speechSynthesis.speak(u);
    } catch (e) {
      /* bỏ qua */
    }
  }

  unlock() {
    if (!this.supported) return;
    this.needsGesture = false;
    try {
      window.speechSynthesis.resume();
    } catch (e) {
      /* bỏ qua */
    }
    this.probe();
  }

  // ---------------------------------------------------------------- hàng đợi
  active() {
    return this.supported && this.settings.on && !this.forceMute;
  }

  stop() {
    this.queue = [];
    this.cool = false;
    clearTimeout(this.coolTimer);
    this.current = null;
    this.token++;
    try {
      window.speechSynthesis.cancel();
    } catch (e) {
      /* bỏ qua */
    }
    this.showCaption(null);
  }

  /** cue: { role, text, prio } */
  push(cue) {
    if (!this.active()) return;
    const prio = cue.prio || 2;
    const item = { role: cue.role, text: cue.text, prio, at: Date.now() };
    if (prio <= 1) {
      // câu ít quan trọng: bỏ nếu đang bận
      const busy = this.queue.length > 0 || (this.current && this.current.prio >= 2);
      if (busy) return;
      this.queue.push(item);
    } else if (prio >= 3) {
      this.cool = false; // việc quan trọng: nói ngay, không chờ nhịp nghỉ
      if (this.current && this.current.prio <= 1) this.interrupt();
      let i = 0;
      while (i < this.queue.length && this.queue[i].prio >= 3) i++;
      this.queue.splice(i, 0, item);
    } else {
      // hàng đợi quá dài: bỏ câu thường cũ nhất để không nói dồn dập
      const soft = this.queue.filter((q) => q.prio <= 2);
      if (soft.length >= 2) this.queue.splice(this.queue.indexOf(soft[0]), 1);
      this.queue.push(item);
    }
    this.pump();
  }

  interrupt() {
    this.token++;
    this.current = null;
    try {
      window.speechSynthesis.cancel();
    } catch (e) {
      /* bỏ qua */
    }
  }

  pump() {
    if (this.current || this.cool || !this.queue.length) return;
    let item = this.queue.shift();
    // câu thường chờ quá lâu thì bỏ (đã hết hợp thời điểm)
    while (item && item.prio <= 2 && Date.now() - item.at > (item.prio <= 1 ? 8000 : 15000)) item = this.queue.shift();
    if (!item) return;
    this.speak(item);
  }

  /** Đọc ngay 1 câu (dùng khi bấm "Thử đọc" ở bảng điều khiển). */
  test(role, text) {
    this.stop();
    this.speak({ role, text, prio: 3, at: Date.now() }, true);
  }

  speak(item, force = false) {
    if (!this.supported || (!force && !this.active())) return;
    const my = ++this.token;
    this.current = item;
    const u = new SpeechSynthesisUtterance(String(item.text).replace(/@+/g, ' a còng '));
    u.lang = 'vi-VN';
    const v = item.role === 'ref' ? this.pick.ref : this.pick.mc;
    if (v) u.voice = v;
    if (this.pick.distinct) {
      u.rate = item.role === 'ref' ? 1.0 : 1.05;
      u.pitch = item.role === 'ref' ? 0.95 : 1.05;
    } else {
      u.rate = item.role === 'ref' ? 0.95 : 1.08;
      u.pitch = item.role === 'ref' ? 0.7 : 1.3;
    }
    const st = this.settings;
    const rate = item.role === 'ref' ? st.refRate : st.mcRate;
    const pitch = item.role === 'ref' ? st.refPitch : st.mcPitch;
    if (typeof rate === 'number') u.rate = rate;
    if (typeof pitch === 'number') u.pitch = pitch;
    u.volume = Math.min(1, Math.max(0, this.settings.volume));
    let finished = false;
    const done = () => {
      if (finished || my !== this.token) return;
      finished = true;
      clearTimeout(this.watchdog);
      this.current = null;
      if (this.clearTimer) clearTimeout(this.clearTimer);
      this.clearTimer = setTimeout(() => {
        if (!this.current) this.showCaption(null);
      }, 700);
      // nghỉ một nhịp giữa hai câu cho đỡ ồn
      this.cool = true;
      clearTimeout(this.coolTimer);
      this.coolTimer = setTimeout(() => {
        this.cool = false;
        this.pump();
      }, force ? 0 : 1400);
    };
    u.onstart = () => this.showCaption(item);
    u.onend = done;
    u.onerror = (e) => {
      if (e && e.error === 'not-allowed') this.needsGesture = true;
      done();
    };
    clearTimeout(this.watchdog);
    this.watchdog = setTimeout(done, 3500 + item.text.length * 130); // phòng khi trình duyệt "treo"
    this.showCaption(item);
    try {
      window.speechSynthesis.resume();
      window.speechSynthesis.speak(u);
    } catch (e) {
      done();
    }
  }

  showCaption(item) {
    this.onCaption(item);
  }
}
