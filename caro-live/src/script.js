'use strict';
/*
 * KỊCH BẢN LỜI THOẠI (sửa được ở bảng điều khiển -> mục "Lời thoại").
 * - Mỗi câu có thể có nhiều DÒNG: mỗi dòng là một cách nói, game luân phiên chọn cho đỡ lặp.
 * - Trong câu dùng {ten}, {qua}... là chỗ game tự điền (xem danh sách bên dưới).
 * - Lưu vào data/thoai.json. Xóa file đó hoặc bấm "Mặc định" để quay lại câu gốc.
 */
const fs = require('fs');
const path = require('path');

const SAMPLE = {
  ten: 'Minh Anh',
  ten1: 'Minh Anh',
  ten2: 'Tuấn Kiệt',
  tiep: 'Tuấn Kiệt',
  thua: 'Bích Trâm',
  oco: 'ca 6',
  diem: '30',
  giay: '25',
  qua: 'Hoa hồng',
  so: '3',
  lydo: 'hết giờ quá nhiều lần và bị xử thua',
};

const VAR_HELP = {
  ten: 'tên người chính trong câu',
  ten1: 'tên người thứ nhất',
  ten2: 'tên người thứ hai',
  tiep: 'tên người đến lượt tiếp theo',
  thua: 'tên người thua',
  oco: 'ô cờ, ví dụ "ca 6"',
  diem: 'số điểm thưởng',
  giay: 'số giây',
  qua: 'tên món quà',
  so: 'số lượng / số ván',
  lydo: 'lý do xử thua',
};

// role: 'mc' = điều phối viên, 'ref' = trọng tài
const DEFAULTS = [
  { key: 'welcome', group: 'Mở đầu', role: 'mc', label: 'Chào mừng (vòng đầu tiên)', vars: ['giay'],
    text: 'Chào mừng các bạn đến với Caro trực tiếp! Hãy bình luận, thả tim hoặc tặng quà để giành suất lên bàn đấu. Chỉ còn {giay} giây!' },
  { key: 'lobbyStart', group: 'Mở đầu', role: 'mc', label: 'Bắt đầu vòng mới', vars: ['giay'],
    text: 'Vòng mới bắt đầu! Hãy bình luận, thả tim hoặc tặng quà để giành suất lên bàn đấu. Chỉ còn {giay} giây!' },
  { key: 'howTo', group: 'Mở đầu', role: 'mc', label: 'Giải thích cách chơi (lúc chờ)', vars: [],
    text: 'Cách chơi rất dễ: khi đến lượt, người chơi bình luận tọa độ, ví dụ j chín, để đặt quân. Ai có năm quân liền nhau là thắng. Muốn lên bàn đấu, hãy bình luận, thả tim và tặng quà!\nLuật rất đơn giản: gõ cột và hàng, như k sáu, để đánh. Năm quân liền nhau là thắng, kể cả bị chặn hai đầu. Bình luận nhiều, thả tim, tặng quà để được chọn lên bàn nhé!' },
  { key: 'greet', group: 'Mở đầu', role: 'mc', label: 'Chào người mới vào', vars: ['ten'],
    text: 'Chào {ten} đã ghé xem! Bình luận hoặc thả tim để giành suất chơi nhé.\nXin chào {ten}! Chúc bạn xem live vui vẻ, nhớ bình luận để được chọn lên bàn đấu nha.' },
  { key: 'lobbyWarn', group: 'Mở đầu', role: 'mc', label: 'Sắp hết giờ đua tương tác', vars: ['ten', 'ten1', 'ten2'],
    text: 'Còn mười giây! Đang dẫn đầu tương tác là {ten}.' },
  { key: 'lobbyEmpty', group: 'Mở đầu', role: 'mc', label: 'Chưa có ai lên bàn', vars: [],
    text: 'Chưa có ai lên bàn. Hãy bình luận hoặc thả tim để vào chơi nào!' },
  { key: 'pickedPair', group: 'Chọn người chơi', role: 'mc', label: 'Công bố 2 người chơi', vars: ['ten1', 'ten2'],
    text: 'Hai người chơi được chọn là {ten1} và {ten2}. Xin chúc mừng!' },
  { key: 'pickedChamp', group: 'Chọn người chơi', role: 'mc', label: 'Người thắng ở lại, có người thách đấu', vars: ['ten1', 'ten2'],
    text: '{ten1} tiếp tục giữ bàn, và sẽ thách đấu với {ten2}.' },
  { key: 'coinToss', group: 'Tung đồng xu', role: 'ref', label: 'Trọng tài tung đồng xu', vars: [],
    text: 'Trọng tài tung đồng xu!' },
  { key: 'coinResult', group: 'Tung đồng xu', role: 'ref', label: 'Kết quả đồng xu', vars: ['ten1', 'ten2'],
    text: 'Kết quả: {ten1} đi trước, cầm quân X đỏ. {ten2} cầm quân O xanh.' },
  { key: 'startGame', group: 'Trong ván', role: 'ref', label: 'Mời đi nước đầu tiên', vars: ['ten'],
    text: 'Mời {ten} đánh nước đầu tiên!' },
  { key: 'move', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi + người kế tiếp', vars: ['ten', 'oco', 'tiep'],
    text: '{ten} đánh {oco}. Đến lượt {tiep}.\n{ten} chọn ô {oco}. Đến lượt {tiep}.\n{ten} đặt quân tại {oco}. Đến lượt {tiep}.' },
  { key: 'moveEnd', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi quyết định (cuối ván)', vars: ['ten', 'oco'],
    text: '{ten} đánh {oco}.' },
  { key: 'occupied', group: 'Trong ván', role: 'ref', label: 'Ô đã có quân', vars: ['ten', 'oco'],
    text: 'Ô {oco} đã có quân. Mời {ten} chọn ô khác.' },
  { key: 'warn10', group: 'Trong ván', role: 'ref', label: 'Cảnh báo còn 10 giây', vars: ['ten'],
    text: '{ten} còn mười giây.' },
  { key: 'timeoutAuto', group: 'Trong ván', role: 'ref', label: 'Hết giờ, đánh thay', vars: ['ten', 'oco'],
    text: '{ten} hết giờ. Hệ thống đánh thay vào ô {oco}.' },
  { key: 'winGame', group: 'Kết quả', role: 'ref', label: 'Có người thắng', vars: ['ten', 'thua', 'so'],
    text: 'Ván đấu kết thúc! {ten} chiến thắng với năm quân liên tiếp.' },
  { key: 'winForfeit', group: 'Kết quả', role: 'ref', label: 'Thắng do đối thủ bỏ cuộc / hết giờ', vars: ['ten', 'thua', 'lydo'],
    text: '{thua} {lydo}. {ten} giành chiến thắng!' },
  { key: 'congrats', group: 'Kết quả', role: 'mc', label: 'Chúc mừng người thắng', vars: ['ten'],
    text: 'Xin chúc mừng {ten}!' },
  { key: 'streak', group: 'Kết quả', role: 'mc', label: 'Thắng liên tiếp', vars: ['ten', 'so'],
    text: '{ten} đã thắng {so} ván liên tiếp.' },
  { key: 'stepDown', group: 'Kết quả', role: 'mc', label: 'Đủ chuỗi thắng, nhường chỗ', vars: ['ten'],
    text: 'Đã đủ số ván liên tiếp, xin nhường chỗ cho người khác.' },
  { key: 'draw', group: 'Kết quả', role: 'ref', label: 'Hòa', vars: [],
    text: 'Bàn cờ đã đầy. Ván đấu hòa!' },
  { key: 'hostReset', group: 'Khác', role: 'mc', label: 'Chủ phòng làm mới trận', vars: [],
    text: 'Chủ phòng đã làm mới trận đấu.' },
  { key: 'remindFollow', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc bấm follow', vars: ['diem'],
    text: 'Nếu bạn thấy vui, hãy bấm follow để không bỏ lỡ các buổi live sau nhé! Follow ngay được cộng {diem} điểm tương tác.\nBạn nào chưa follow thì bấm giúp mình một cái nha, được cộng {diem} điểm để giành suất lên bàn đấu!' },
  { key: 'remindShare', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc chia sẻ', vars: ['diem'],
    text: 'Chia sẻ buổi live này cho bạn bè để cùng vào đấu cờ nào! Chia sẻ được cộng {diem} điểm tương tác.\nMời thêm bạn bè vào xem và chơi cùng, chia sẻ live là được cộng {diem} điểm đó!' },
  { key: 'extraTime', group: 'Trong ván', role: 'ref', label: 'Người chơi xin thêm giờ', vars: ['ten', 'giay'],
    text: '{ten} xin thêm {giay} giây. Mời tiếp tục suy nghĩ!' },
  { key: 'confirmAsk', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 2 người thả tim xác nhận', vars: ['ten1', 'ten2', 'giay'],
    text: 'Xin mời {ten1} và {ten2} thả tim để xác nhận tham gia. Chỉ còn {giay} giây!' },
  { key: 'confirmAskOne', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 1 người thả tim xác nhận', vars: ['ten', 'giay'],
    text: 'Xin mời {ten} thả tim để xác nhận tham gia. Chỉ còn {giay} giây!' },
  { key: 'confirmOk', group: 'Xác nhận thả tim', role: 'mc', label: 'Một người đã xác nhận', vars: ['ten'],
    text: '{ten} đã sẵn sàng!' },
  { key: 'confirmWarn', group: 'Xác nhận thả tim', role: 'mc', label: 'Sắp hết giờ xác nhận', vars: ['ten', 'giay'],
    text: '{ten} ơi, thả tim ngay để giữ suất chơi, còn {giay} giây!' },
  { key: 'confirmFail', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, mời người khác thay', vars: ['ten', 'ten2'],
    text: '{ten} chưa thả tim nên mất suất. Xin mời {ten2} thay thế, hãy thả tim để xác nhận nhé!' },
  { key: 'confirmFailNone', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, không còn ai thay', vars: ['ten'],
    text: '{ten} chưa thả tim nên mất suất. Chúng ta sẽ chọn lại người chơi nhé!' },
  { key: 'giftThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn tặng quà', vars: ['ten', 'qua', 'so'],
    text: 'Cảm ơn {ten} đã tặng {qua}!\nCảm ơn bạn {ten} đã gửi tặng {qua}, thật tuyệt vời!\nWow, {ten} vừa tặng {qua}! Cảm ơn bạn nhiều nhé!' },
  { key: 'giftBig', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn quà LỚN', vars: ['ten', 'qua', 'so'],
    text: 'Wow! Cảm ơn {ten} đã tặng {qua}. Bạn thật hào phóng!\nÔi trời ơi, {qua} từ {ten}! Cảm ơn bạn rất nhiều!' },
  { key: 'followThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn follow', vars: ['ten'],
    text: 'Cảm ơn {ten} đã follow!' },
  { key: 'shareThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn chia sẻ LIVE', vars: ['ten'],
    text: 'Cảm ơn {ten} đã chia sẻ buổi LIVE!' },
];

class Script {
  constructor(file) {
    this.file = file;
    this.timer = null;
    this.items = new Map(DEFAULTS.map((d) => [d.key, { ...d, custom: null, enabled: true }]));
    this.counter = 0;
    if (!process.env.CARO_FAST) this.load();
  }

  load() {
    try {
      const saved = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      for (const [k, v] of Object.entries(saved)) {
        const it = this.items.get(k);
        if (!it || !v) continue;
        if (typeof v.text === 'string') it.custom = v.text;
        if (typeof v.enabled === 'boolean') it.enabled = v.enabled;
      }
    } catch (e) {
      /* chưa có file */
    }
  }

  item(key) {
    return this.items.get(key);
  }

  textOf(key) {
    const it = this.items.get(key);
    if (!it) return '';
    return it.custom != null ? it.custom : it.text;
  }

  /** Điền chỗ trống và chọn 1 dòng. n = số thứ tự để luân phiên; trả về null nếu tắt / rỗng. */
  render(key, vars = {}, n = null) {
    const it = this.items.get(key);
    if (!it || !it.enabled) return null;
    const lines = this.textOf(key).split('\n').map((s) => s.trim()).filter(Boolean);
    if (!lines.length) return null;
    const idx = n == null ? this.counter++ % lines.length : Math.abs(n) % lines.length;
    const out = lines[idx]
      .replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? '' : String(vars[k])))
      .replace(/\s+([.,!?])/g, '$1')
      .replace(/\s{2,}/g, ' ')
      .trim();
    return out || null;
  }

  set(key, { text, enabled }) {
    const it = this.items.get(key);
    if (!it) return false;
    if (typeof text === 'string') {
      const t = text.slice(0, 1200);
      it.custom = t.trim() === it.text.trim() ? null : t;
    }
    if (typeof enabled === 'boolean') it.enabled = enabled;
    this.save();
    return true;
  }

  reset(key) {
    const it = this.items.get(key);
    if (!it) return false;
    it.custom = null;
    it.enabled = true;
    this.save();
    return true;
  }

  resetAll() {
    for (const it of this.items.values()) {
      it.custom = null;
      it.enabled = true;
    }
    this.save();
  }

  list() {
    return [...this.items.values()].map((it) => ({
      key: it.key,
      group: it.group,
      role: it.role,
      label: it.label,
      vars: it.vars,
      text: it.custom != null ? it.custom : it.text,
      def: it.text,
      enabled: it.enabled,
      edited: it.custom != null,
    }));
  }

  save() {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      const out = {};
      for (const it of this.items.values()) {
        if (it.custom != null || !it.enabled) out[it.key] = { text: it.custom != null ? it.custom : it.text, enabled: it.enabled };
      }
      try {
        fs.mkdirSync(path.dirname(this.file), { recursive: true });
        fs.writeFileSync(this.file, JSON.stringify(out, null, 2));
      } catch (e) {
        /* không sao */
      }
    }, 600);
  }
}

module.exports = { Script, SAMPLE, VAR_HELP };
