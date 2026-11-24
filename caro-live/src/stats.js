'use strict';
/*
 * THÀNH TÍCH: số ván thắng của từng người, lưu vào data/thanh-tich.json
 * (tắt game bật lại vẫn còn). Xóa file đó nếu muốn làm lại từ đầu.
 */
const fs = require('fs');
const path = require('path');

class Stats {
  constructor(file) {
    this.file = file;
    this.data = {};
    this.rev = 0; // tăng mỗi khi dữ liệu đổi (để nơi khác biết cần tính lại bảng rank)
    this.timer = null;
    this.load();
    process.on('exit', () => this.saveNow());
  }

  load() {
    try {
      this.data = JSON.parse(fs.readFileSync(this.file, 'utf8')) || {};
    } catch (e) {
      this.data = {};
    }
  }

  entry(user) {
    if (!this.data[user.id]) this.data[user.id] = { name: user.name, wins: 0, games: 0 };
    this.data[user.id].name = user.name || this.data[user.id].name;
    if (user.avatar) this.data[user.id].avatar = user.avatar; // nhớ ảnh đại diện để bảng rank còn hiện khi người đó đã thoát
    return this.data[user.id];
  }

  recordGame(user) {
    this.entry(user).games += 1;
    this.rev++;
    this.save();
  }

  recordWin(user) {
    this.entry(user).wins += 1;
    this.rev++;
    this.save();
  }

  winsOf(id) {
    return (this.data[id] && this.data[id].wins) || 0;
  }

  /** Danh sách người đã thắng ít nhất 1 ván, xếp từ nhiều ván thắng nhất (rank cao nhất) trở xuống. */
  ranked(n = 5) {
    return Object.entries(this.data)
      .filter(([, e]) => e.wins > 0)
      .sort((a, b) => b[1].wins - a[1].wins || a[1].games - b[1].games)
      .slice(0, n)
      .map(([id, e]) => ({ id, name: e.name, avatar: e.avatar || '', wins: e.wins }));
  }

  top(n = 5) {
    return Object.values(this.data)
      .filter((e) => e.wins > 0)
      .sort((a, b) => b.wins - a.wins || a.games - b.games)
      .slice(0, n)
      .map((e) => ({ name: e.name, wins: e.wins }));
  }

  save() {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.saveNow();
    }, 2000);
  }

  saveNow() {
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      fs.writeFileSync(this.file, JSON.stringify(this.data, null, 2));
    } catch (e) {
      /* không sao */
    }
  }
}

module.exports = { Stats };
