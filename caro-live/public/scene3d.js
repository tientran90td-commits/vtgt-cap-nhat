/*
 * CẢNH 3D: phòng, bàn gỗ, bàn cờ, 2 nhân vật, quân cờ rơi xuống, khói hương và CAMERA.
 * Camera có nhiều góc quay (wide, focusX, focusO, placeX...) và lướt mượt giữa các góc.
 */
import * as THREE from './vendor/three.module.js';
import { Character } from './character.js';
import { SeatMotion } from './seatmotion.js';
import { Crowd } from './crowd.js';
import { makePieceMesh, PIECE_COLOR } from './pieces.js';
import { layout, paintBoardBase, paintWood, currentSkin, drawLed } from './board.js';

const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const BOARD_P = 1.8; // cạnh tấm bàn cờ (đơn vị 3D)
const BOARD_Y = 0.032; // mặt bàn cờ
const SEAT_Z = 1.75;

// Các góc quay. p = vị trí camera, l = điểm nhìn.
const POSES = {
  wide: { p: [5.2, 3.4, 2.4], l: [0, 0.8, 0] },
  gift: { p: [0, 0, 0], l: [0, 0, 0] }, // camera zoom vào khán giả vừa tặng quà (toạ độ do spotlight() đặt)
  room: { p: [8.4, 2.1, 5.2], l: [-0.5, -0.5, -1.2] }, // lùi xa: thấy cả phòng, ghế trống và khán giả
  table: { p: [3.6, 3.3, 2.1], l: [0, 0.55, 0] },
  focusX: { p: [4.4, 3.5, -1.2], l: [0, 1.15, 1.2] }, // sau lưng O, nhìn mặt X
  focusO: { p: [-4.4, 3.5, 1.2], l: [0, 1.15, -1.2] }, // sau lưng X, nhìn mặt O
  placeX: { p: [3.3, 4.4, -0.6], l: [0, 0.3, 0.8] },
  placeO: { p: [-3.3, 4.4, 0.6], l: [0, 0.3, -0.8] },
  winX: { p: [1.9, 2.7, -3.5], l: [0, 1.6, 1.4] },
  winO: { p: [-1.9, 2.7, 3.5], l: [0, 1.6, -1.4] },
};

function makeRadialTexture() {
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, 'rgba(255,255,255,0.9)');
  grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd;
  g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c);
  return t;
}

export class Scene3D {
  constructor(canvas, size = 15) {
    this.size = size;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.setClearColor(0x101626, 1);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x101626, 9, 22);
    this.camera = new THREE.PerspectiveCamera(42, 1.8, 0.1, 60);

    this.pose = 'wide';
    this.camPos = V(...POSES.wide.p);
    this.camLook = V(...POSES.wide.l);
    this.sway = 1;

    this.pieces = new Map();
    this.falling = [];
    this.rings = [];
    this.winGroup = null;
    this.lastRing = null;
    this.smoke = [];

    this.buildRoom();
    this.buildTable();
    this.buildBoard();
    this.buildProps();

    this.chars = {
      X: new Character({ style: 'boy', mark: 'X', seatZ: SEAT_Z, hair: 0x232c4a, hairLight: 0x7f93d8, cloth: 0x9aa3b8, accent: 0xff3b3f }),
      O: new Character({ style: 'girl', mark: 'O', seatZ: -SEAT_Z, hair: 0x1b1b2c, hairLight: 0x8a8fc8, cloth: 0xf1f3fa, accent: 0x2f9bff }),
    };
    this.chars.X.attachTo(this.scene);
    this.chars.O.attachTo(this.scene);
    this.boardCenter = V(0, BOARD_Y, 0);
    // động tác ngồi vào bàn / đứng dậy đi ra (seatmotion.js) và khán giả đứng quanh phòng (crowd.js)
    this.seats = {
      X: new SeatMotion(this.chars.X, this.chairParts.X, 1, -4.7),
      O: new SeatMotion(this.chars.O, this.chairParts.O, -1, 4.7),
    };
    this.crowd = new Crowd(this.scene);
    this.time = 0;
    this.loadModels();
  }

  /** Báo nhân vật `mark` nên ngồi ở bàn (present) hay đứng dậy đi ra. instant: đặt luôn, không diễn. */
  seat(mark, present, instant = false) {
    this.seats[mark].want(present, instant);
  }

  /** Người ngồi ở ghế `mark` đã đổi sang người khác: diễn động tác rời bàn / vào bàn. */
  replaceSeat(mark) {
    this.seats[mark].replace();
  }

  /** Ghế `mark` đang chờ đổi người (giữ bảng tên cũ)? */
  seatHolding(mark) {
    return !!this.seats[mark].holding;
  }

  /** Khán giả `id` vừa tặng quà: ăn mừng và đặt camera 'gift' trước mặt họ. Trả về true nếu có nhân vật để zoom. */
  spotlight(id, label) {
    const at = this.crowd.spotlight(id, label);
    if (!at) return false;
    const dx = -at.x;
    const dz = -at.z;
    const d = Math.hypot(dx, dz) || 1;
    const nx = dx / d;
    const nz = dz / d; // hướng từ họ về bàn
    // đứng lệch sang bên (không đứng giữa khán giả và bàn để khỏi vướng 2 người chơi), nhìn chéo vào mặt họ
    const side = at.x * 0 + (at.z >= 0 ? 1 : -1);
    POSES.gift.p = [at.x + nx * 2.5 - nz * 2.2 * side, -0.15, at.z + nz * 2.5 + nx * 2.2 * side];
    POSES.gift.l = [at.x, 0.1, at.z];
    return true;
  }

  /** Danh sách khán giả (tên + ảnh đại diện) để vẽ nhân vật đứng quanh phòng. */
  setCrowd(list, instant = false) {
    this.crowd.setViewers(list, instant);
  }

  /** Nếu có file models/nam.glb, models/nu.glb thì thay nhân vật dựng sẵn bằng model 3D thật. */
  async loadModels() {
    const q = new URLSearchParams(location.search);
    if (q.get('model') === '0') return;
    const files = { X: q.get('nam') || 'models/nam.glb', O: q.get('nu') || 'models/nu.glb' };
    let GLTFLoader = null;
    for (const mark of ['X', 'O']) {
      try {
        const head = await fetch(files[mark], { method: 'HEAD' });
        if (!head.ok) continue;
        if (!GLTFLoader) GLTFLoader = (await import('./vendor/GLTFLoader.js')).GLTFLoader;
        const gltf = await new GLTFLoader().loadAsync(files[mark]);
        this.chars[mark].useModel(gltf.scene);
      } catch (e) {
        console.warn('Không nạp được model ' + files[mark], e);
      }
    }
  }

  // ------------------------------------------------------------ dựng cảnh
  buildRoom() {
    const s = this.scene;
    s.add(new THREE.HemisphereLight(0xdfe6ff, 0x4a3a2a, 0.85));
    const sun = new THREE.DirectionalLight(0xfff1de, 1.7);
    sun.position.set(2.5, 6, 3.5);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const sc = sun.shadow.camera;
    sc.left = -4;
    sc.right = 4;
    sc.top = 4;
    sc.bottom = -4;
    sc.near = 1;
    sc.far = 16;
    sun.shadow.bias = -0.0005;
    sun.shadow.normalBias = 0.02;
    s.add(sun);
    const warm = new THREE.PointLight(0xffc27a, 14, 9, 2);
    warm.position.set(0, 2.9, 0);
    s.add(warm);
    const rim = new THREE.DirectionalLight(0x7ea6ff, 0.55);
    rim.position.set(-4, 3, -3);
    s.add(rim);

    // sàn
    const floorTex = document.createElement('canvas');
    floorTex.width = floorTex.height = 512;
    const fg = floorTex.getContext('2d');
    paintWood(fg, 512, 512, 33, '#3b2a2f', '#27181d');
    const ft = new THREE.CanvasTexture(floorTex);
    ft.wrapS = ft.wrapT = THREE.RepeatWrapping;
    ft.repeat.set(4, 4);
    ft.colorSpace = THREE.SRGBColorSpace;
    const floor = new THREE.Mesh(new THREE.CircleGeometry(12, 48), new THREE.MeshStandardMaterial({ map: ft, roughness: 0.9 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -1.95;
    floor.receiveShadow = true;
    s.add(floor);
    // thảm
    const rug = new THREE.Mesh(
      new THREE.CircleGeometry(3.6, 48),
      (this.rugMat = new THREE.MeshStandardMaterial({ color: 0x6b2230, roughness: 1 }))
    );
    rug.rotation.x = -Math.PI / 2;
    rug.position.y = -1.94;
    rug.receiveShadow = true;
    s.add(rug);
    const rugRing = new THREE.Mesh(
      new THREE.RingGeometry(3.15, 3.35, 48),
      (this.ringMat = new THREE.MeshStandardMaterial({ color: 0xd9a441, roughness: 0.8 }))
    );
    rugRing.rotation.x = -Math.PI / 2;
    rugRing.position.y = -1.93;
    s.add(rugRing);

    // tường + đèn lồng phía sau
    const wall = new THREE.Mesh(
      new THREE.CylinderGeometry(11, 11, 9, 40, 1, true, 0, Math.PI * 2),
      (this.wallMat = new THREE.MeshStandardMaterial({ color: 0x1b2238, roughness: 1, side: THREE.BackSide }))
    );
    wall.position.y = 2.5;
    s.add(wall);
    const lanternMat = new THREE.MeshStandardMaterial({ color: 0xffb35c, emissive: 0xff9a3c, emissiveIntensity: 1.6 });
    [[-4.5, 3.3, -3.2], [-5.5, 3.1, 1.2], [4.9, 3.2, -2.6], [5.4, 3.0, 2.4], [0.5, 3.5, -6], [0.8, 3.4, 6]].forEach(([x, y, z]) => {
      const l = new THREE.Mesh(new THREE.SphereGeometry(0.3, 14, 12), lanternMat);
      l.scale.y = 1.25;
      l.position.set(x, y, z);
      s.add(l);
    });
  }

  buildTable() {
    const s = this.scene;
    const c = document.createElement('canvas');
    c.width = c.height = 512;
    paintWood(c.getContext('2d'), 512, 512, 5, '#8a5a34', '#6b4122');
    this.tableCanvas = c;
    const tex = (this.tableTex = new THREE.CanvasTexture(c));
    tex.colorSpace = THREE.SRGBColorSpace;
    const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.55 });
    const top = new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.14, 2.75), mat);
    top.position.y = -0.07;
    top.receiveShadow = true;
    top.castShadow = true;
    s.add(top);
    const legMat = new THREE.MeshStandardMaterial({ color: 0x4a2c16, roughness: 0.7 });
    for (const x of [-1.9, 1.9]) {
      for (const z of [-1.1, 1.1]) {
        const leg = new THREE.Mesh(new THREE.BoxGeometry(0.2, 1.8, 0.2), legMat);
        leg.position.set(x, -1.0, z);
        leg.castShadow = true;
        s.add(leg);
      }
    }
    // ghế (đệm + lưng ghế)
    const seatMat = (this.seatMat = new THREE.MeshStandardMaterial({ color: 0x7a1f2e, roughness: 0.8 }));
    this.chairParts = { X: [], O: [] };
    for (const sign of [1, -1]) {
      const seat = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, 0.14, 28), seatMat);
      seat.position.set(0, -0.85, sign * (SEAT_Z + 0.05));
      seat.castShadow = true;
      s.add(seat);
      const stool = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 0.9, 14), legMat);
      stool.position.set(0, -1.4, sign * (SEAT_Z + 0.05));
      s.add(stool);
      this.chairParts[sign > 0 ? 'X' : 'O'].push(seat, stool);
      const back = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.5, 0.12), seatMat);
      back.position.set(0, 0.1, sign * (SEAT_Z + 0.78));
      back.castShadow = true;
      s.add(back);
      this.chairParts[sign > 0 ? 'X' : 'O'].push(back);
    }
  }

  buildBoard() {
    const s = this.scene;
    const px = 1024;
    const c = document.createElement('canvas');
    c.width = c.height = px;
    this.layout = paintBoardBase(c.getContext('2d'), px, this.size);
    this.boardCanvas = c;
    const tex = (this.boardTex = new THREE.CanvasTexture(c));
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    const frame = new THREE.Mesh(
      new THREE.BoxGeometry(BOARD_P + 0.1, BOARD_Y, BOARD_P + 0.1),
      (this.frameMat = new THREE.MeshStandardMaterial({ color: 0x4a2a12, roughness: 0.6 }))
    );
    frame.position.y = BOARD_Y / 2;
    frame.castShadow = true;
    frame.receiveShadow = true;
    s.add(frame);
    const plane = new THREE.Mesh(
      new THREE.PlaneGeometry(BOARD_P, BOARD_P),
      new THREE.MeshStandardMaterial({ map: tex, roughness: 0.6 })
    );
    plane.rotation.x = -Math.PI / 2;
    plane.position.y = BOARD_Y + 0.001;
    plane.receiveShadow = true;
    s.add(plane);
    this.cellSize = (this.layout.cell / px) * BOARD_P;
  }

  buildProps() {
    const s = this.scene;
    const bowlMat = new THREE.MeshStandardMaterial({ color: 0xb98a52, roughness: 0.5, side: THREE.DoubleSide });
    const mkBowl = (x, z, mark) => {
      const g = new THREE.Group();
      g.position.set(x, 0, z);
      const bowl = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.2, 0.13, 26, 1, true), bowlMat);
      bowl.position.y = 0.065;
      bowl.castShadow = true;
      g.add(bowl);
      const bottom = new THREE.Mesh(new THREE.CircleGeometry(0.2, 22), bowlMat);
      bottom.rotation.x = -Math.PI / 2;
      bottom.position.y = 0.012;
      g.add(bottom);
      for (let i = 0; i < 16; i++) {
        const p = makePieceMesh(mark, 0.11);
        const a = Math.random() * Math.PI * 2;
        const r = Math.random() * 0.17;
        p.position.set(Math.cos(a) * r, 0.04 + Math.random() * 0.08, Math.sin(a) * r);
        p.rotation.set(Math.random() * 0.8, Math.random() * 6, Math.random() * 0.8);
        g.add(p);
      }
      s.add(g);
    };
    mkBowl(-1.6, 1.0, 'X');
    mkBowl(1.6, -1.0, 'O');

    // lư hương + khói
    const burnerMat = new THREE.MeshStandardMaterial({ color: 0xa8742b, roughness: 0.35, metalness: 0.7 });
    const burner = new THREE.Group();
    burner.position.set(1.65, 0, 1.0);
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.12, 0.17, 20), burnerMat);
    body.position.y = 0.085;
    body.castShadow = true;
    burner.add(body);
    for (const a of [0, 2.1, 4.2]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.02, 0.08, 8), burnerMat);
      leg.position.set(Math.cos(a) * 0.12, 0.0, Math.sin(a) * 0.12);
      burner.add(leg);
    }
    s.add(burner);
    this.burnerPos = V(1.65, 0.2, 1.0);
    const smokeTex = makeRadialTexture();
    for (let i = 0; i < 12; i++) {
      const m = new THREE.Sprite(new THREE.SpriteMaterial({ map: smokeTex, transparent: true, depthWrite: false, color: 0xdfe6f5 }));
      m.userData = { life: i / 12 };
      s.add(m);
      this.smoke.push(m);
    }
  }

  // ------------------------------------------------------------ tọa độ ô cờ
  /** Đổi màu phòng, bàn, bàn cờ và 2 nhân vật theo kiểu theme (xem theme.js). Gọi sau setBoardPalette. */
  setTheme(t) {
    const r = t.room;
    this.renderer.setClearColor(r.bg, 1);
    this.scene.fog.color.set(r.bg);
    this.wallMat.color.set(r.wall);
    this.rugMat.color.set(r.rug);
    this.ringMat.color.set(r.ring);
    this.seatMat.color.set(r.seat);
    this.frameMat.color.set(r.frame3d);
    paintWood(this.tableCanvas.getContext('2d'), 512, 512, 5, r.table[0], r.table[1]);
    this.tableTex.needsUpdate = true;
    this.layout = paintBoardBase(this.boardCanvas.getContext('2d'), this.boardCanvas.width, this.size);
    this.boardTex.needsUpdate = true;
    // chụp nền tĩnh để mỗi nhịp chỉ cần chép lại rồi vẽ đèn LED lên (xem tickLed)
    if (!this.boardBase) this.boardBase = document.createElement('canvas');
    this.boardBase.width = this.boardCanvas.width;
    this.boardBase.height = this.boardCanvas.height;
    this.boardBase.getContext('2d').drawImage(this.boardCanvas, 0, 0);
    this.ledBusy = false;
    this.chars.X.recolor(t.X);
    this.chars.O.recolor(t.O);
  }

  /** Đèn LED chạy trên mặt bàn 3D (chỉ khi dùng kiểu bàn hoa văn). Cập nhật ~15 lần/giây cho nhẹ máy. */
  tickLed(time, on) {
    const skin = currentSkin();
    if (!this.boardBase) return;
    if (!skin || !on) {
      if (this.ledBusy) {
        const c = this.boardCanvas.getContext('2d');
        c.drawImage(this.boardBase, 0, 0);
        this.boardTex.needsUpdate = true;
        this.ledBusy = false;
      }
      return;
    }
    if (time - (this.ledLast || 0) < 1 / 15) return;
    this.ledLast = time;
    const c = this.boardCanvas.getContext('2d');
    c.drawImage(this.boardBase, 0, 0);
    drawLed(c, this.layout, skin, time);
    this.boardTex.needsUpdate = true;
    this.ledBusy = true;
  }

  cellToWorld(x, y) {
    const L = this.layout;
    const u = (L.gx0 + (x + 0.5) * L.cell) / L.px;
    const v = (L.gy0 + (L.size - 1 - y + 0.5) * L.cell) / L.px;
    return V((u - 0.5) * BOARD_P, BOARD_Y, (v - 0.5) * BOARD_P);
  }

  // ------------------------------------------------------------ quân cờ
  makePiece(mark) {
    return makePieceMesh(mark, this.cellSize * 0.78);
  }

  clearPieces() {
    for (const p of this.pieces.values()) this.scene.remove(p);
    this.pieces.clear();
    this.falling = [];
    this.hideWinLine();
    if (this.lastRing) this.lastRing.visible = false;
  }

  addPieceInstant(m) {
    const mesh = this.makePiece(m.m);
    const w = this.cellToWorld(m.x, m.y);
    mesh.position.set(w.x, BOARD_Y + mesh.userData.height * 0.5, w.z);
    this.scene.add(mesh);
    this.pieces.set(`${m.x},${m.y}`, mesh);
    this.markLast(m);
  }

  dropPiece(m) {
    const mesh = this.makePiece(m.m);
    const w = this.cellToWorld(m.x, m.y);
    const rest = BOARD_Y + mesh.userData.height * 0.5;
    mesh.position.set(w.x, rest + 0.28, w.z);
    this.scene.add(mesh);
    this.pieces.set(`${m.x},${m.y}`, mesh);
    this.falling.push({ mesh, t: 0, rest, from: rest + 0.28 });
    this.markLast(m);
    // vòng sóng lan ra
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.02, 0.05, 28),
      new THREE.MeshBasicMaterial({ color: PIECE_COLOR[m.m], transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(w.x, BOARD_Y + 0.004, w.z);
    this.scene.add(ring);
    this.rings.push({ ring, t: 0 });
  }

  markLast(m) {
    if (!this.lastRing) {
      this.lastRing = new THREE.Mesh(
        new THREE.RingGeometry(this.cellSize * 0.5, this.cellSize * 0.62, 4, 1, Math.PI / 4),
        new THREE.MeshBasicMaterial({ color: 0xffd54a, transparent: true, opacity: 0.9, side: THREE.DoubleSide })
      );
      this.lastRing.rotation.x = -Math.PI / 2;
      this.scene.add(this.lastRing);
    }
    const w = this.cellToWorld(m.x, m.y);
    this.lastRing.position.set(w.x, BOARD_Y + 0.003, w.z);
    this.lastRing.visible = true;
  }

  showWinLine(line) {
    this.hideWinLine();
    if (!line || line.length < 2) return;
    const a = this.cellToWorld(line[0].x, line[0].y);
    const b = this.cellToWorld(line[line.length - 1].x, line[line.length - 1].y);
    const len = a.distanceTo(b) + this.cellSize;
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(len, 0.02, this.cellSize * 0.22),
      new THREE.MeshStandardMaterial({ color: 0xffd54a, emissive: 0xffb300, emissiveIntensity: 1.4, transparent: true, opacity: 0.9 })
    );
    bar.position.copy(a).lerp(b, 0.5);
    bar.position.y = BOARD_Y + 0.07;
    bar.rotation.y = -Math.atan2(b.z - a.z, b.x - a.x);
    this.winGroup = bar;
    this.scene.add(bar);
  }

  hideWinLine() {
    if (this.winGroup) {
      this.scene.remove(this.winGroup);
      this.winGroup = null;
    }
  }

  // ------------------------------------------------------------ camera
  setPose(name) {
    if (POSES[name]) this.pose = name;
  }

  resize(w, h) {
    w = Math.max(2, Math.floor(w));
    h = Math.max(2, Math.floor(h));
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    // màn hẹp (khung gần vuông) -> mở rộng góc nhìn để đủ chỗ cho 2 nhân vật
    this.camera.fov = this.camera.aspect < 1.25 ? 62 : this.camera.aspect < 1.6 ? 50 : 42;
    this.camera.updateProjectionMatrix();
  }

  update(dt, time, ctx) {
    this.time = time;
    // camera lướt tới góc quay mới
    const P = POSES[this.pose];
    const k = 1 - Math.exp(-2.6 * dt);
    const goalPos = V(...P.p);
    const goalLook = V(...P.l);
    // chuyển động nhẹ để cảnh "sống"
    goalPos.x += Math.sin(time * 0.31) * 0.12;
    goalPos.y += Math.sin(time * 0.23) * 0.06;
    this.camPos.lerp(goalPos, k);
    this.camLook.lerp(goalLook, k);
    this.camera.position.copy(this.camPos);
    this.camera.lookAt(this.camLook);

    // bảng tên của nhân vật đứng gần camera (che hình) thì ẩn đi
    const m = /^(focus|place|win)([XO])$/.exec(this.pose);
    for (const k of ['X', 'O']) this.chars[k].tag.sprite.visible = !m || m[2] === k;

    // nhân vật
    this.seats.X.update(dt, time);
    this.seats.O.update(dt, time);
    this.crowd.update(dt, time, this.crowdCheer);
    const c = { boardCenter: this.boardCenter, urgency: 0 };
    this.chars.X.update(dt, time, { ...c, urgency: ctx.urgency.X || 0 });
    this.chars.O.update(dt, time, { ...c, urgency: ctx.urgency.O || 0 });

    // quân rơi
    for (let i = this.falling.length - 1; i >= 0; i--) {
      const f = this.falling[i];
      f.t += dt;
      const T = 0.3;
      if (f.t < T) {
        const q = f.t / T;
        f.mesh.position.y = f.from - (f.from - f.rest) * q * q;
      } else if (f.t < T + 0.22) {
        const q = (f.t - T) / 0.22;
        f.mesh.position.y = f.rest + Math.sin(q * Math.PI) * 0.035;
      } else {
        f.mesh.position.y = f.rest;
        this.falling.splice(i, 1);
      }
    }
    for (let i = this.rings.length - 1; i >= 0; i--) {
      const r = this.rings[i];
      r.t += dt;
      const q = r.t / 0.6;
      r.ring.scale.setScalar(1 + q * 7);
      r.ring.material.opacity = Math.max(0, 0.8 * (1 - q));
      if (q >= 1) {
        this.scene.remove(r.ring);
        r.ring.geometry.dispose();
        r.ring.material.dispose();
        this.rings.splice(i, 1);
      }
    }
    if (this.lastRing && this.lastRing.visible) this.lastRing.material.opacity = 0.55 + 0.35 * Math.sin(time * 5);
    if (this.winGroup) this.winGroup.material.emissiveIntensity = 1.1 + 0.7 * Math.sin(time * 8);

    // khói hương
    for (const m of this.smoke) {
      m.userData.life = (m.userData.life + dt * 0.22) % 1;
      const l = m.userData.life;
      m.position.set(this.burnerPos.x + Math.sin(l * 9 + m.id) * 0.06 * l, this.burnerPos.y + l * 1.25, this.burnerPos.z + Math.cos(l * 7) * 0.05 * l);
      m.scale.setScalar(0.1 + l * 0.35);
      m.material.opacity = Math.sin(l * Math.PI) * 0.35;
    }
  }

  render() {
    this.renderer.render(this.scene, this.camera);
  }
}

/*
 * Dùng khi máy không bật được WebGL: giữ nguyên nhịp trình diễn (không có hình 3D) để bàn cờ 2D và giọng đọc vẫn đúng.
 */
export class NullScene {
  constructor() {
    const mk = () => ({
      mode: 'idle',
      modeT: 0,
      placing: null,
      setMode(m) {
        if (this.mode !== m) {
          this.mode = m;
          this.modeT = 0;
        }
      },
      setTag() {},
      setHeld() {},
      place(cell, cb) {
        this.placing = true;
        setTimeout(() => {
          cb.onTouch();
          setTimeout(() => {
            this.placing = null;
            cb.onDone();
          }, 400);
        }, 900);
      },
    });
    this.chars = { X: mk(), O: mk() };
  }
  setTheme() {}
  seat() {}
  replaceSeat() {}
  seatHolding() {
    return false;
  }
  setCrowd() {}
  spotlight() {
    return false;
  }
  cellToWorld() {
    return {};
  }
  clearPieces() {}
  addPieceInstant() {}
  dropPiece() {}
  showWinLine() {}
  hideWinLine() {}
  setPose() {}
  resize() {}
  update(dt) {
    this.chars.X.modeT += dt;
    this.chars.O.modeT += dt;
  }
  render() {}
}
