'use strict';
/*
 * DỰNG BUỔI BÓI BÀI: từ các lá đã rút -> danh sách "bước" (xáo bài, lật từng lá + đọc, tổng kết, kết thúc),
 * mỗi bước có lời MC đọc và thời lượng ước tính theo độ dài lời đọc. Màn hình live chạy theo danh sách này.
 */
const POS = {
  1: { general: ['Thông điệp dành cho bạn'], love: ['Thông điệp tình cảm'], work: ['Thông điệp công việc'] },
  3: {
    general: ['Quá khứ', 'Hiện tại', 'Tương lai gần'],
    love: ['Bạn', 'Mối quan hệ', 'Lời khuyên'],
    work: ['Hiện tại', 'Thử thách', 'Lời khuyên'],
  },
  5: {
    general: ['Tình huống', 'Nguyên nhân', 'Trở ngại', 'Lời khuyên', 'Kết quả có thể'],
    love: ['Bạn', 'Mối quan hệ', 'Trở ngại', 'Lời khuyên', 'Hướng đi'],
    work: ['Hiện tại', 'Nguyên nhân', 'Trở ngại', 'Lời khuyên', 'Hướng đi'],
  },
};
const TOPIC_LABEL = { general: 'Tổng quát', love: 'Tình duyên', work: 'Công việc - học tập' };
const ORD = ['Lá thứ nhất', 'Lá thứ hai', 'Lá thứ ba', 'Lá thứ tư', 'Lá thứ năm'];
const MS_PER_CHAR = { slow: 95, normal: 75, fast: 60 };
const pick = (a, rnd) => a[Math.floor(rnd() * a.length)];

const INTRO = [
  (n) => `Chào ${n}! Mình xáo bài cho bạn nhé. Hãy hít một hơi thật sâu và nghĩ về điều bạn đang quan tâm.`,
  (n) => `${n} ơi, đến lượt bạn rồi. Mình trải bài ra nhé, bạn cứ nghĩ đến điều mình muốn lắng nghe.`,
  (n) => `Xin chào ${n}. Cùng xem lá bài hôm nay muốn nhắn nhủ điều gì nhé.`,
];
const OUTRO = [
  'Hy vọng thông điệp này mang lại cho bạn một góc nhìn nhẹ nhàng. Chúc bạn bình an.',
  'Lá bài chỉ là gợi ý để suy ngẫm, quyết định luôn nằm trong tay bạn. Chúc bạn một ngày vui.',
  'Cảm ơn bạn đã tham gia. Chúc bạn nhiều niềm vui và may mắn.',
];
const DISCLAIMER = 'Nhắc nhẹ: Tarot chỉ mang tính giải trí và gợi mở, không thay thế lời khuyên của chuyên gia.';
const SENSITIVE_NOTE = 'Mình không xem các chuyện sức khỏe, tiền bạc hay pháp lý nhé. Bạn nhận một thông điệp chung cho tinh thần nhẹ nhàng.';

function cardText(c, rev, topic) {
  if (topic === 'love') return c.love[rev ? 1 : 0];
  if (topic === 'work') return c.work[rev ? 1 : 0];
  return rev ? c.rev : c.up;
}

/**
 * Nội dung đọc theo VAI TRÒ của vị trí trong trải bài (nên cùng 1 lá ở vị trí khác nhau sẽ cho lời đọc khác nhau):
 *  - Lời khuyên: lời khuyên riêng của lá.   - Trở ngại: mặt cần lưu ý (nghĩa ngược) của lá.
 *  - Các vị trí còn lại: nghĩa của lá theo chủ đề (tổng quát / tình duyên / công việc).
 */
function roleText(c, rev, topic, pos) {
  const adv = c.advice[rev ? 1 : 0];
  if (pos === 'Lời khuyên') return topic === 'general' ? adv : `${adv} ${cardText(c, rev, topic)}`;
  if (pos === 'Trở ngại') return `Điều cần lưu ý: ${c.kRev}. ${topic === 'general' ? c.rev : cardText(c, true, topic)}`;
  if (pos === 'Nguyên nhân') return `Gốc rễ của chuyện này là ${(rev ? c.kRev : c.kUp).split(',')[0].trim()}. ${cardText(c, rev, topic)}`;
  return cardText(c, rev, topic);
}

/** Lời chào đầu buổi: có thể kèm cung hoàng đạo, số chủ đạo, chuyện muốn xem (nếu người xem đã cung cấp). */
function introText(name, profile, sensitive, rnd = Math.random) {
  let t = pick(INTRO, rnd)(name);
  if (profile && profile.zodiac) t += ` Bạn thuộc cung ${profile.zodiac}, thường được mô tả là ${profile.zodiacTrait}.`;
  if (profile && profile.lifeNo) t += ` Số chủ đạo của bạn là ${profile.lifeNo}, gắn với tính cách ${profile.lifeTrait}.`;
  if (profile && profile.question && !sensitive) t += ` Chuyện bạn muốn xem: ${profile.question}.`;
  if (sensitive) t += ' ' + SENSITIVE_NOTE;
  return t;
}

/**
 * drawn: [{card, rev}]  user: {name, avatar}  opts: { profile, ai: {cards, summary}, skipIntro, { topic, sensitive, speed, number (đếm lượt để thỉnh thoảng nhắc lưu ý), rng }
 */
function build(drawn, user, opts = {}) {
  const rnd = opts.rng || Math.random;
  const topic = opts.sensitive ? 'general' : opts.topic || 'general';
  const spread = drawn.length === 5 ? 5 : drawn.length === 3 ? 3 : 1;
  const mpc = MS_PER_CHAR[opts.speed] || MS_PER_CHAR.normal;
  const fast = !!opts.fast;
  const dur = (text, min) => (fast ? 1200 : Math.max(min, Math.round(text.length * mpc)));
  const positions = POS[spread][topic];

  const cards = drawn.map((d, i) => ({
    id: d.card.id,
    vi: d.card.vi,
    en: d.card.en,
    rev: d.rev,
    pos: positions[i],
    kw: d.rev ? d.card.kRev : d.card.kUp,
    text: opts.ai && opts.ai.cards[i] ? opts.ai.cards[i] : roleText(d.card, d.rev, topic, positions[i]),
  }));

  const steps = [];
  if (opts.skipIntro) steps.push({ kind: 'shuffle', say: '', dur: fast ? 1200 : 1800 }); // lời chào đã nói ở bước chuẩn bị
  else {
    const intro = introText(user.name, opts.profile, opts.sensitive, rnd);
    steps.push({ kind: 'shuffle', say: intro, dur: dur(intro, 5000) });
  }

  const flipAll = spread > 1; // 3 / 5 lá: luôn úp cả bài, lật hết 1 lượt rồi mới đọc từng lá
  if (flipAll) {
    const rv = `Mình lật cả ${spread === 3 ? 'ba' : 'năm'} lá cùng lúc nhé. Giờ cùng xem từng lá một.`;
    steps.push({ kind: 'reveal', say: rv, dur: dur(rv, 4500) });
  }

  cards.forEach((c, i) => {
    const lead = `${spread > 1 ? ORD[i] + ', ' + c.pos : c.pos}: ${c.vi}${c.rev ? ', lá ngược' : ''}.`;
    const say = `${lead} Từ khóa: ${c.kw}. ${c.text}`;
    steps.push({ kind: 'card', idx: i, say, dur: dur(say, 7000) });
  });

  if (spread > 1) {
    const kws = cards.map((c) => c.kw.split(',')[0].trim());
    const list = kws.slice(0, -1).join(', ') + ' và ' + kws[kws.length - 1];
    const sum = opts.ai && opts.ai.summary ? `Tổng kết: ${opts.ai.summary}` : `Tổng kết: ${spread === 3 ? 'ba' : 'năm'} từ khóa dành cho bạn là ${list}. Hãy xem ${spread === 3 ? 'ba' : 'năm'} lá bài như một câu chuyện gợi mở để suy ngẫm, quyết định luôn nằm ở bạn.`;
    steps.push({ kind: 'sum', say: sum, dur: dur(sum, 4500) });
  }
  let out = pick(OUTRO, rnd);
  if (opts.number == null || opts.number % 4 === 0) out += ' ' + DISCLAIMER;
  steps.push({ kind: 'outro', say: out, dur: dur(out, 3500) });

  let at = 0;
  for (const s of steps) {
    s.at = at;
    at += s.dur;
  }
  return { cards, steps, total: at, flipAll, ai: !!opts.ai, profile: opts.profile || null, topic, topicLabel: TOPIC_LABEL[topic], spread };
}


// ---------------------------------------------------------------- luồng 5 lá kiểu "chờ AI"
// 1) showSteps: xáo bài (MC chào) -> chia bài -> lật cả 5 lá -> đọc tên từng lá. Chạy NGAY, trong lúc AI đang viết.
// 2) readSteps: đọc từng lá + tổng kết + lời chúc. Được nối vào sau khi AI trả lời (hoặc dùng lời viết sẵn).
function makeDur(opts) {
  const mpc = MS_PER_CHAR[opts.speed] || MS_PER_CHAR.normal;
  return (text, min) => (opts.fast ? 1200 : Math.max(min, Math.round(text.length * mpc)));
}

function layout(steps, base = 0) {
  let at = base;
  for (const st of steps) {
    st.at = at;
    at += st.dur;
  }
  return at;
}

/** 5 lá chưa có lời AI: lời đọc viết sẵn theo vị trí (dùng khi AI tắt / lỗi). */
function makeCards(drawn, opts = {}) {
  const topic = opts.sensitive ? 'general' : opts.topic || 'general';
  const positions = POS[drawn.length === 5 ? 5 : drawn.length === 3 ? 3 : 1][topic];
  return {
    topic,
    topicLabel: TOPIC_LABEL[topic],
    cards: drawn.map((d, i) => ({
      id: d.card.id,
      vi: d.card.vi,
      en: d.card.en,
      rev: d.rev,
      pos: positions[i],
      kw: d.rev ? d.card.kRev : d.card.kUp,
      text: roleText(d.card, d.rev, topic, positions[i]),
    })),
  };
}

function showSteps(cards, user, opts = {}) {
  const dur = makeDur(opts);
  const rnd = opts.rng || Math.random;
  const n = cards.length;
  const steps = [];
  const intro = introText(user.name, opts.profile, opts.sensitive, rnd);
  steps.push({ kind: 'shuffle', say: intro, dur: dur(intro, 6000) });
  const deal = `Mình chia ${n === 5 ? 'năm' : n} lá bài ra bàn.`;
  steps.push({ kind: 'deal', say: deal, dur: dur(deal, 3500) });
  const rv = `Giờ mình lật cả ${n === 5 ? 'năm' : n} lá cùng lúc nhé.`;
  steps.push({ kind: 'reveal', say: rv, dur: dur(rv, 3500) });
  cards.forEach((c, i) => {
    const say = `${ORD[i]}, ${c.pos}: ${c.vi}${c.rev ? ', lá ngược' : ''}.`;
    steps.push({ kind: 'name', idx: i, say, dur: dur(say, 3200) });
  });
  return { steps, total: layout(steps, 0) };
}

/** Đọc từng lá + tổng kết + lời chúc. ai = { cards:[chuỗi], summary } hoặc null. Trả về { steps (at tính từ 0), total }. */
function readSteps(cards, opts = {}) {
  const dur = makeDur(opts);
  const rnd = opts.rng || Math.random;
  const n = cards.length;
  const steps = [];
  cards.forEach((c, i) => {
    const say = `${ORD[i]}, ${c.pos}: ${c.vi}${c.rev ? ', lá ngược' : ''}. Từ khóa: ${c.kw}. ${c.text}`;
    steps.push({ kind: 'card', idx: i, say, dur: dur(say, 7000) });
  });
  if (n > 1) {
    const w = n === 3 ? 'ba' : 'năm';
    let sum;
    if (opts.ai && opts.ai.summary) sum = `Tổng kết: ${opts.ai.summary}`;
    else {
      const kws = cards.map((c) => c.kw.split(',')[0].trim());
      const list = kws.slice(0, -1).join(', ') + ' và ' + kws[kws.length - 1];
      sum = `Tổng kết: ${w} từ khóa dành cho bạn là ${list}. Hãy xem ${w} lá bài như một câu chuyện gợi mở để suy ngẫm, quyết định luôn nằm ở bạn.`;
    }
    steps.push({ kind: 'sum', say: sum, dur: dur(sum, 4500) });
  }
  let out = pick(OUTRO, rnd);
  if (opts.number == null || opts.number % 4 === 0) out += ' ' + DISCLAIMER;
  steps.push({ kind: 'outro', say: out, dur: dur(out, 3500) });
  return { steps, total: layout(steps, 0) };
}

module.exports = { makeCards, showSteps, readSteps, layout, build, introText, TOPIC_LABEL, DISCLAIMER, POS };
