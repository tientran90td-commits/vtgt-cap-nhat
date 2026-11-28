/*
 * NHÂN VẬT 3D THẬT (file .glb có khung xương kiểu Mixamo / Ready Player Me).
 * Module này chỉ làm 1 việc: lấy 1 model người đã có xương, cho NGỒI vào ghế và điều khiển xương theo
 * cử động mà character.js tính sẵn (nghiêng người, quay đầu, 2 tay với tới ô cờ).
 * Không có file model -> game vẫn dùng nhân vật dựng sẵn trong character.js.
 *
 * Đặt file vào  public/models/nam.glb  (người chơi ✕)  và  public/models/nu.glb  (người chơi ○).
 */
import * as THREE from './vendor/three.module.js';

const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);

// ---- Model anime (đổi từ VRM bằng tools/vrm2glb.py): vẽ kiểu hoạt hình (toon) + viền mực mỏng
let _grad = null;
function gradient() {
  if (!_grad) {
    const d = new Uint8Array([165, 225, 255]);
    _grad = new THREE.DataTexture(d, d.length, 1, THREE.RedFormat);
    _grad.minFilter = _grad.magFilter = THREE.NearestFilter;
    _grad.needsUpdate = true;
  }
  return _grad;
}
let _ink = null;
function inkMat() {
  if (!_ink) {
    _ink = new THREE.MeshBasicMaterial({ color: 0x2a1a22, side: THREE.BackSide });
    _ink.onBeforeCompile = (sh) => {
      sh.vertexShader = sh.vertexShader.replace('#include <begin_vertex>', 'vec3 transformed = position + normal * 0.0028;');
    };
    _ink.customProgramCacheKey = () => 'animeInk';
  }
  return _ink;
}
function toonify(root) {
  const cache = new Map();
  const conv = (m) => {
    if (!m || m.isMeshToonMaterial) return m;
    if (!cache.has(m)) {
      const n = new THREE.MeshToonMaterial({
        color: m.color ? m.color.clone() : 0xffffff,
        map: m.map || null,
        gradientMap: gradient(),
        transparent: !!m.transparent,
        alphaTest: m.alphaTest || 0,
        opacity: m.opacity === undefined ? 1 : m.opacity,
        side: m.side,
      });
      if (m.emissive) n.emissive.copy(m.emissive);
      if (m.emissiveMap) n.emissiveMap = m.emissiveMap;
      n.name = m.name;
      cache.set(m, n);
    }
    return cache.get(m);
  };
  const inks = [];
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.material = Array.isArray(o.material) ? o.material.map(conv) : conv(o.material);
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    const skip = mats.every((m) => /eye|brow|lash|mouth|highlight|iris|white/i.test(m.name || ''));
    if (!skip && o.isSkinnedMesh) inks.push(o);
  });
  for (const o of inks) {
    const ink = new THREE.SkinnedMesh(o.geometry, inkMat());
    ink.bind(o.skeleton, o.bindMatrix);
    ink.morphTargetInfluences = o.morphTargetInfluences;
    ink.morphTargetDictionary = o.morphTargetDictionary;
    ink.frustumCulled = false;
    ink.raycast = () => {};
    o.parent.add(ink);
  }
}
const norm = (n) => String(n || '').replace(/^mixamorig[:_]?/i, '').replace(/[^a-z0-9]/gi, '').toLowerCase();

const NAMES = {
  hips: ['hips', 'pelvis'],
  spine: ['spine'],
  spine1: ['spine1', 'chest'],
  spine2: ['spine2', 'upperchest'],
  neck: ['neck'],
  head: ['head'],
  armL: ['leftarm', 'leftupperarm'],
  foreL: ['leftforearm', 'leftlowerarm'],
  handL: ['lefthand'],
  armR: ['rightarm', 'rightupperarm'],
  foreR: ['rightforearm', 'rightlowerarm'],
  handR: ['righthand'],
  thighL: ['leftupleg', 'leftupperleg'],
  shinL: ['leftleg', 'leftlowerleg'],
  footL: ['leftfoot'],
  toeL: ['lefttoebase', 'lefttoes'],
  thighR: ['rightupleg', 'rightupperleg'],
  shinR: ['rightleg', 'rightlowerleg'],
  footR: ['rightfoot'],
  toeR: ['righttoebase', 'righttoes'],
};

function findBones(scene) {
  const all = [];
  scene.traverse((o) => {
    if (o.isBone) all.push(o);
  });
  const map = new Map(all.map((b) => [norm(b.name), b]));
  const out = {};
  for (const [k, names] of Object.entries(NAMES)) {
    for (const n of names) {
      if (map.has(n)) {
        out[k] = map.get(n);
        break;
      }
    }
  }
  return out;
}

/** Đặt hướng (toạ độ thế giới) cho bone. */
function setWorldQuat(bone, q) {
  const pq = bone.parent.getWorldQuaternion(new THREE.Quaternion());
  bone.quaternion.copy(pq.invert().multiply(q));
  bone.updateMatrixWorld(true);
}

/** Xoay bone sao cho đường từ nó tới `child` chỉ về hướng dir (thế giới). */
function aim(bone, child, dir) {
  bone.updateMatrixWorld(true);
  const p = bone.getWorldPosition(V());
  const c = child.getWorldPosition(V());
  const cur = c.sub(p).normalize();
  const des = dir.clone().normalize();
  const delta = new THREE.Quaternion().setFromUnitVectors(cur, des);
  const bq = bone.getWorldQuaternion(new THREE.Quaternion());
  setWorldQuat(bone, delta.multiply(bq));
}

/**
 * Gắn model vào nhân vật `ch` (Character). Trả về null nếu model không có khung xương người.
 * Với model KHÔNG có xương: model đứng yên ngồi tại ghế, chỉ nghiêng/lắc nhẹ (không có tay).
 */
export function attachModel(ch, gltfScene) {
  const bones = findBones(gltfScene);
  const rigged = !!(bones.hips && bones.head && bones.armL && bones.foreL && bones.handL && bones.armR && bones.foreR && bones.handR);

  // ẩn nhân vật dựng sẵn
  for (const c of ch.hips.children) c.visible = false;
  for (const a of ch.arms) for (const m of Object.values(a)) m.visible = false;

  if (gltfScene.userData && gltfScene.userData.toonAnime) toonify(gltfScene);
  const holder = new THREE.Group();
  holder.add(gltfScene);
  ch.root.add(holder);
  gltfScene.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
      o.frustumCulled = false;
      if (o.material && !(gltfScene.userData && gltfScene.userData.toonAnime)) o.material.side = THREE.FrontSide;
    }
  });

  // ---- chuẩn hoá kích thước: khoảng hông -> vai khoảng 1.25 đơn vị
  holder.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(gltfScene);
  const size = box.getSize(V());
  let k;
  if (rigged) {
    const d = bones.hips.getWorldPosition(V()).distanceTo(bones.armL.getWorldPosition(V()));
    k = 1.25 / Math.max(0.05, d);
  } else {
    k = 3.0 / Math.max(0.1, size.y); // model tĩnh: cao ~3 đơn vị
  }
  holder.scale.setScalar(k);
  // đặt hông ngang gốc thân (ghế)
  holder.updateMatrixWorld(true);
  const hipsHolder = rigged ? holder.worldToLocal(bones.hips.getWorldPosition(V())) : V(0, box.min.y, 0);
  holder.position.set(0, -0.45 - hipsHolder.y * k + (rigged ? 0.12 : 0.0), rigged ? 0 : 0);
  if (rigged) holder.position.x = -hipsHolder.x * k;
  if (rigged) holder.position.z = -hipsHolder.z * k - 0.12;
  ch.root.updateMatrixWorld(true);

  if (!rigged) {
    ch.rig = {
      rigged: false,
      body(lean) {
        holder.rotation.x = lean * 0.5;
      },
      arm() {},
      face() {},
    };
    // thân giả cho camera/bảng tên
    ch.head.position.set(0, 1.5, 0);
    return ch.rig;
  }

  // ---- ghi nhớ tư thế gốc (T-pose) theo hệ trục của nhân vật
  const rootQ0 = ch.root.getWorldQuaternion(new THREE.Quaternion());
  const rootQ0inv = rootQ0.clone().invert();
  const rest = new Map();
  for (const b of [bones.spine, bones.spine1, bones.spine2, bones.neck, bones.head, bones.hips]) {
    if (b) rest.set(b, rootQ0inv.clone().multiply(b.getWorldQuaternion(new THREE.Quaternion())));
  }

  // ---- đo tay, kéo dài nhẹ nếu quá ngắn để với tới bàn cờ
  const armLen = (arm, fore, hand) => arm.getWorldPosition(V()).distanceTo(fore.getWorldPosition(V())) + fore.getWorldPosition(V()).distanceTo(hand.getWorldPosition(V()));
  const worldLen = armLen(bones.armL, bones.foreL, bones.handL);
  const stretch = Math.min(1.35, Math.max(1, (ch.S * 1.0 * 1.85) / Math.max(0.01, worldLen)));
  for (const b of [bones.armL, bones.armR]) b.scale.multiplyScalar(stretch);
  holder.updateMatrixWorld(true);
  const dist = (a, b) => a.getWorldPosition(V()).distanceTo(b.getWorldPosition(V()));
  ch.L1 = dist(bones.armL, bones.foreL);
  ch.L2 = dist(bones.foreL, bones.handL) * 1.08; // tính cả lòng bàn tay

  // vai (gốc IK) gắn vào xương cánh tay
  bones.armL.add(ch.shoulder[0]);
  bones.armR.add(ch.shoulder[1]);
  ch.shoulder[0].position.set(0, 0, 0);
  ch.shoulder[1].position.set(0, 0, 0);

  // đầu (dùng cho camera, bảng tên, tay chống cằm)
  const headW = bones.head.getWorldPosition(V());
  ch.hips.updateMatrixWorld(true);
  const hl = ch.hips.worldToLocal(headW.clone());
  ch.head.position.set(hl.x, hl.y - 0.1, hl.z);
  ch.head.scale.setScalar(0.8);

  const R = () => ch.root.getWorldQuaternion(new THREE.Quaternion());
  const dirRoot = (x, y, z) => V(x, y, z).applyQuaternion(R());

  // ---- khuôn mặt (nếu có morph target kiểu Ready Player Me)
  const morphs = [];
  gltfScene.traverse((o) => {
    if (o.isMesh && o.morphTargetDictionary && o.morphTargetInfluences) morphs.push(o);
  });
  const setMorph = (name, v) => {
    for (const m of morphs) {
      const i = m.morphTargetDictionary[name];
      if (i !== undefined) m.morphTargetInfluences[i] = v;
    }
  };

  ch.rig = {
    rigged: true,
    bones,
    /** nghiêng người + quay đầu + ngồi */
    body(lean, headRot) {
      ch.root.updateMatrixWorld(true);
      const q = R();
      const frame = (e) => q.clone().multiply(new THREE.Quaternion().setFromEuler(new THREE.Euler(e.x || 0, e.y || 0, e.z || 0)));
      const put = (b, e) => {
        if (!b) return;
        setWorldQuat(b, frame(e).multiply(rest.get(b)));
      };
      put(bones.hips, { x: 0.04 });
      put(bones.spine, { x: lean * 0.3 });
      put(bones.spine1, { x: lean * 0.65 });
      put(bones.spine2, { x: lean * 0.95 });
      put(bones.neck, { x: lean + headRot.x * 0.3, y: headRot.y * 0.3, z: headRot.z * 0.3 });
      put(bones.head, { x: lean + headRot.x * 0.7, y: headRot.y * 0.7, z: headRot.z * 0.7 });
      // chân: ngồi (đùi hướng ra trước, cẳng chân thẳng xuống). Khi đứng dậy / đi bộ (seatmotion.js) thì chuyển dần sang tư thế đứng + bước chân.
      const stand = ch.walkDriving ? Math.max(0, Math.min(1, ch.walkLegsK || 0)) : 0;
      const amp = ch.walkDriving ? ch.walkAmp || 0 : 0;
      const mix = (u, v) => V(u[0] + (v[0] - u[0]) * stand, u[1] + (v[1] - u[1]) * stand, u[2] + (v[2] - u[2]) * stand);
      for (const sd of ['L', 'R']) {
        const x = sd === 'L' ? 0.07 : -0.07;
        const ph = (ch.walkPhase || 0) + (sd === 'L' ? 0 : Math.PI);
        const sw = Math.sin(ph) * 0.55 * amp; // đùi vung ra trước (+) / ra sau (-)
        const knee = (0.08 + 0.7 * Math.max(0, Math.cos(ph))) * amp; // gối gập khi đưa chân lên
        const thighStand = [x, -Math.cos(sw), Math.sin(sw)];
        const shinStand = [x * 0.5, -Math.cos(sw - knee), Math.sin(sw - knee)];
        if (bones['thigh' + sd] && bones['shin' + sd]) aim(bones['thigh' + sd], bones['shin' + sd], dirRoot(...mix([x, -0.1, 1], thighStand).toArray()));
        if (bones['shin' + sd] && bones['foot' + sd]) aim(bones['shin' + sd], bones['foot' + sd], dirRoot(...mix([x * 0.5, -1, 0.08], shinStand).toArray()));
        if (bones['foot' + sd] && bones['toe' + sd]) aim(bones['foot' + sd], bones['toe' + sd], dirRoot(...mix([0, -0.25, 1], [0, -0.12, 1]).toArray()));
      }
      ch.root.updateMatrixWorld(true);
    },
    /** tay: xương cánh tay chỉ về khuỷu, cẳng tay chỉ về cổ tay (toạ độ thế giới đã tính bằng IK) */
    arm(i, shoulder, elbow, wrist) {
      const arm = i === 0 ? bones.armL : bones.armR;
      const fore = i === 0 ? bones.foreL : bones.foreR;
      const hand = i === 0 ? bones.handL : bones.handR;
      aim(arm, fore, elbow.clone().sub(shoulder));
      aim(fore, hand, wrist.clone().sub(elbow));
    },
    face(mouth, blink) {
      if (!morphs.length) return;
      setMorph('mouthSmile', mouth === 'smile' ? 0.55 : 0);
      setMorph('mouthFrownLeft', mouth === 'sad' ? 0.6 : 0);
      setMorph('mouthFrownRight', mouth === 'sad' ? 0.6 : 0);
      setMorph('jawOpen', mouth === 'oh' ? 0.25 : 0);
      setMorph('mouthFunnel', mouth === 'oh' ? 0.4 : 0);
      setMorph('eyeBlinkLeft', blink);
      setMorph('eyeBlinkRight', blink);
    },
  };
  return ch.rig;
}
