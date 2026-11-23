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
    text: 'Hoan nghênh chư vị đạo hữu giá lâm Caro Tiên Giới! Chư vị hãy bình luận, thả tim hoặc tặng lễ vật để giành suất lên đài luận võ. Chỉ còn {giay} giây!' },
  { key: 'lobbyStart', group: 'Mở đầu', role: 'mc', label: 'Bắt đầu vòng mới', vars: ['giay'],
    text: 'Một vòng tranh đài mới đã mở! Chư vị đạo hữu hãy bình luận, thả tim hoặc tặng lễ vật để giành suất lên đài. Chỉ còn {giay} giây!' },
  { key: 'howTo', group: 'Mở đầu', role: 'mc', label: 'Giải thích cách chơi (lúc chờ)', vars: [],
    text: 'Quy củ rất đơn giản: đến lượt mình, đạo hữu hãy bình luận tọa độ, ví dụ j chín, để bố trận. Ai kết được năm quân liền một đường là thắng. Muốn lên đài, chư vị hãy bình luận, thả tim và tặng lễ vật!\nPháp môn rất dễ: gõ cột và hàng, như ca sáu, để xuất chiêu. Năm quân nối liền là đại thắng, kể cả bị chặn hai đầu. Tích cực bình luận, thả tim, tặng lễ vật để được chọn lên đài nhé, chư vị đạo hữu!' },
  { key: 'greet', group: 'Mở đầu', role: 'mc', label: 'Chào người mới vào', vars: ['ten'],
    text: 'Hoan nghênh đạo hữu {ten} ghé thăm! Hãy bình luận hoặc thả tim để giành suất lên đài nhé.\nBái kiến đạo hữu {ten}! Chúc đạo hữu tiêu dao thưởng lãm, nhớ bình luận để được chọn lên đài nha.' },
  { key: 'lobbyWarn', group: 'Mở đầu', role: 'mc', label: 'Sắp hết giờ đua tương tác', vars: ['ten', 'ten1', 'ten2'],
    text: 'Còn mười giây nữa! Đạo hữu {ten} đang dẫn đầu bảng tương tác.' },
  { key: 'lobbyEmpty', group: 'Mở đầu', role: 'mc', label: 'Chưa có ai lên bàn', vars: [],
    text: 'Trên đài chưa có đạo hữu nào. Mời chư vị bình luận hoặc thả tim để lên đài luận võ!' },
  { key: 'pickedPair', group: 'Chọn người chơi', role: 'mc', label: 'Công bố 2 người chơi', vars: ['ten1', 'ten2'],
    text: 'Hai vị đạo hữu được chọn lên đài là {ten1} và {ten2}. Xin chúc mừng!' },
  { key: 'pickedChamp', group: 'Chọn người chơi', role: 'mc', label: 'Người thắng ở lại, có người thách đấu', vars: ['ten1', 'ten2'],
    text: 'Đạo hữu {ten1} tiếp tục trấn giữ lôi đài, và sẽ tỷ thí cùng đạo hữu {ten2}.' },
  { key: 'coinToss', group: 'Tung đồng xu', role: 'ref', label: 'Trọng tài tung đồng xu', vars: [],
    text: 'Tại hạ xin tung đồng xu để định tiên cơ!' },
  { key: 'coinResult', group: 'Tung đồng xu', role: 'ref', label: 'Kết quả đồng xu', vars: ['ten1', 'ten2'],
    text: 'Kết quả: đạo hữu {ten1} đi trước, cầm quân X đỏ. Đạo hữu {ten2} cầm quân O xanh.' },
  { key: 'startGame', group: 'Trong ván', role: 'ref', label: 'Mời đi nước đầu tiên', vars: ['ten'],
    text: 'Mời đạo hữu {ten} xuất chiêu đầu tiên!' },
  { key: 'move', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi + người kế tiếp', vars: ['ten', 'oco', 'tiep'],
    text: 'Đạo hữu {ten} xuất chiêu tại {oco}. Đến lượt đạo hữu {tiep}.\nĐạo hữu {ten} bố trận ở ô {oco}. Mời đạo hữu {tiep}.\nĐạo hữu {ten} đặt quân tại {oco}. Đạo hữu {tiep}, mời xuất chiêu.' },
  { key: 'moveEnd', group: 'Trong ván', role: 'ref', label: 'Đọc nước đi quyết định (cuối ván)', vars: ['ten', 'oco'],
    text: 'Đạo hữu {ten} xuất chiêu tại {oco}.' },
  { key: 'occupied', group: 'Trong ván', role: 'ref', label: 'Ô đã có quân', vars: ['ten', 'oco'],
    text: 'Ô {oco} đã có quân rồi. Mời đạo hữu {ten} chọn ô khác.' },
  { key: 'warn10', group: 'Trong ván', role: 'ref', label: 'Cảnh báo còn 10 giây', vars: ['ten'],
    text: 'Đạo hữu {ten}, chỉ còn mười giây, mau suy diễn!' },
  { key: 'timeoutAuto', group: 'Trong ván', role: 'ref', label: 'Hết giờ, đánh thay', vars: ['ten', 'oco'],
    text: 'Đạo hữu {ten} đã hết thời gian. Thiên đạo đánh thay vào ô {oco}.' },
  { key: 'winGame', group: 'Kết quả', role: 'ref', label: 'Có người thắng', vars: ['ten', 'thua', 'so'],
    text: 'Trận tỷ thí kết thúc! Đạo hữu {ten} kết thành năm quân liền một đường, đại thắng!' },
  { key: 'winForfeit', group: 'Kết quả', role: 'ref', label: 'Thắng do đối thủ bỏ cuộc / hết giờ', vars: ['ten', 'thua', 'lydo'],
    text: 'Đạo hữu {thua} {lydo}. Đạo hữu {ten} đắc thắng!' },
  { key: 'congrats', group: 'Kết quả', role: 'mc', label: 'Chúc mừng người thắng', vars: ['ten'],
    text: 'Cung hỉ đạo hữu {ten}! Quả là tu vi cao thâm!' },
  { key: 'streak', group: 'Kết quả', role: 'mc', label: 'Thắng liên tiếp', vars: ['ten', 'so'],
    text: 'Đạo hữu {ten} đã liên tiếp thắng {so} trận, đạo hạnh thâm hậu!' },
  { key: 'stepDown', group: 'Kết quả', role: 'mc', label: 'Đủ chuỗi thắng, nhường chỗ', vars: ['ten'],
    text: 'Đã đủ số trận liên thắng, xin đạo hữu nhường lôi đài cho người khác.' },
  { key: 'draw', group: 'Kết quả', role: 'ref', label: 'Hòa', vars: [],
    text: 'Bàn cờ đã kín quân. Hai bên bất phân thắng bại, hòa cục!' },
  { key: 'hostReset', group: 'Khác', role: 'mc', label: 'Chủ phòng làm mới trận', vars: [],
    text: 'Chủ phòng đã khai mở lại trận pháp.' },
  { key: 'remindFollow', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc bấm follow', vars: ['diem'],
    text: 'Nếu đạo hữu thấy hữu duyên, xin hãy follow để khỏi lỡ các buổi tiên hội sau! Follow ngay được cộng {diem} điểm tương tác.\nVị đạo hữu nào chưa follow, xin bấm giúp tại hạ một cái, sẽ được cộng {diem} điểm để giành suất lên đài!' },
  { key: 'remindShare', group: 'Nhắc nhở', role: 'mc', label: 'Nhắc chia sẻ', vars: ['diem'],
    text: 'Hãy chia sẻ buổi LIVE này cho bằng hữu để cùng đến luận võ! Chia sẻ được cộng {diem} điểm tương tác.\nMời thêm đồng đạo vào xem và tỷ thí, chia sẻ live là được cộng {diem} điểm đó!' },
  { key: 'extraTime', group: 'Trong ván', role: 'ref', label: 'Người chơi xin thêm giờ', vars: ['ten', 'giay'],
    text: 'Đạo hữu {ten} xin thêm {giay} giây. Mời tiếp tục suy diễn!' },
  { key: 'confirmAsk', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 2 người thả tim xác nhận', vars: ['ten1', 'ten2', 'giay'],
    text: 'Mời đạo hữu {ten1} và đạo hữu {ten2} thả tim để xác nhận lên đài. Chỉ còn {giay} giây!' },
  { key: 'confirmAskOne', group: 'Xác nhận thả tim', role: 'mc', label: 'Mời 1 người thả tim xác nhận', vars: ['ten', 'giay'],
    text: 'Mời đạo hữu {ten} thả tim để xác nhận lên đài. Chỉ còn {giay} giây!' },
  { key: 'confirmOk', group: 'Xác nhận thả tim', role: 'mc', label: 'Một người đã xác nhận', vars: ['ten'],
    text: 'Đạo hữu {ten} đã sẵn sàng!' },
  { key: 'confirmWarn', group: 'Xác nhận thả tim', role: 'mc', label: 'Sắp hết giờ xác nhận', vars: ['ten', 'giay'],
    text: 'Đạo hữu {ten} ơi, mau thả tim để giữ suất, còn {giay} giây!' },
  { key: 'confirmFail', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, mời người khác thay', vars: ['ten', 'ten2'],
    text: 'Đạo hữu {ten} chưa thả tim nên mất suất. Mời đạo hữu {ten2} thế chỗ, xin thả tim để xác nhận!' },
  { key: 'confirmFailNone', group: 'Xác nhận thả tim', role: 'mc', label: 'Không thả tim, không còn ai thay', vars: ['ten'],
    text: 'Đạo hữu {ten} chưa thả tim nên mất suất. Chúng ta sẽ chọn lại người lên đài nhé!' },
  { key: 'giftThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn tặng quà', vars: ['ten', 'qua', 'so'],
    text: 'Đa tạ đạo hữu {ten} đã tặng {qua}!\nĐa tạ đạo hữu {ten} đã ban tặng {qua}, thật là hào phóng!\nÔ, đạo hữu {ten} vừa tặng {qua}! Tại hạ vô cùng cảm kích!' },
  { key: 'giftBig', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn quà LỚN', vars: ['ten', 'qua', 'so'],
    text: 'Chấn động! Đa tạ đạo hữu {ten} đã tặng {qua}. Quả là đại thiện nhân!\nTrời ơi, {qua} từ đạo hữu {ten}! Tại hạ xin đa tạ, ân đức này xin ghi tạc!' },
  { key: 'followThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn follow', vars: ['ten'],
    text: 'Đa tạ đạo hữu {ten} đã follow, kết duyên cùng chúng ta!' },
  { key: 'shareThanks', group: 'Cảm ơn', role: 'mc', label: 'Cảm ơn chia sẻ LIVE', vars: ['ten'],
    text: 'Đa tạ đạo hữu {ten} đã chia sẻ buổi LIVE!' },
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
