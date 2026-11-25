'use strict';
/*
 * BỘ BÀI 78 LÁ + RÚT BÀI. Dữ liệu từng lá nằm trong src/cards/*.js (lời đọc tiếng Việt).
 */
const ADVICE = require('./cards/advice');
const FILES = ['major', 'wands', 'cups', 'swords', 'pents'];

function load() {
  const out = [];
  for (const f of FILES) {
    for (const r of require('./cards/' + f)) {
      out.push({
        id: r[0], vi: r[1], en: r[2],
        kUp: r[3], kRev: r[4],
        up: r[5], rev: r[6],
        love: [r[7], r[8]],
        work: [r[9], r[10]],
        advice: ADVICE[r[0]] || [r[5], r[6]],
      });
    }
  }
  return out;
}

const CARDS = load();
const BY_ID = new Map(CARDS.map((c) => [c.id, c]));

/** Rút n lá khác nhau. reverseChance: 0-100 (% lá ngược). rng để kiểm tra tự động. */
function draw(n, reverseChance = 30, rng = Math.random) {
  const pool = CARDS.slice();
  const out = [];
  for (let i = 0; i < n && pool.length; i++) {
    const k = Math.floor(rng() * pool.length);
    const card = pool.splice(k, 1)[0];
    out.push({ card, rev: rng() * 100 < reverseChance });
  }
  return out;
}

module.exports = { CARDS, BY_ID, draw };
