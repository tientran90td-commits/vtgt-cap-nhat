#!/usr/bin/env python3
"""Doi file VRM (VRoid, 0.x) thanh .glb cho game Caro LIVE:
 - doi ten xuong theo kieu Mixamo (LeftArm, LeftForeArm...) de rig.js nhan ra
 - xoay 180 do de nhan vat nhin ve phia truoc (VRM 0.x nhin ve -Z)
 - thu nho anh (texture) xuong toi da MAXTEX de nhe va muot
 - dat ten morph (chop mat, cuoi, buon, mo mieng) theo ten ma rig.js dung
Dung:  python3 vrm2glb.py vao.vrm ra.glb [MAXTEX=1024]"""
import sys, json, struct, io
from PIL import Image

HUMAN = {  # ten VRM -> ten kieu Mixamo
 'hips':'Hips','spine':'Spine','chest':'Spine1','upperChest':'Spine2','neck':'Neck','head':'Head',
 'leftUpperArm':'LeftArm','leftLowerArm':'LeftForeArm','leftHand':'LeftHand',
 'rightUpperArm':'RightArm','rightLowerArm':'RightForeArm','rightHand':'RightHand',
 'leftUpperLeg':'LeftUpLeg','leftLowerLeg':'LeftLeg','leftFoot':'LeftFoot','leftToes':'LeftToeBase',
 'rightUpperLeg':'RightUpLeg','rightLowerLeg':'RightLeg','rightFoot':'RightFoot','rightToes':'RightToeBase',
}
BLEND = {'blink':'eyeBlinkLeft','joy':'mouthSmile','sorrow':'mouthFrownLeft','a':'jawOpen','o':'mouthFunnel'}

def read_glb(p):
    b = open(p,'rb').read()
    assert b[:4]==b'glTF'
    off=12; js=None; binc=b''
    while off < len(b):
        n,t = struct.unpack('<II', b[off:off+8]); d=b[off+8:off+8+n]; off+=8+n
        if t==0x4E4F534A: js=json.loads(d)
        elif t==0x004E4942: binc=d
    return js, binc

def write_glb(p, js, binc):
    j = json.dumps(js, separators=(',',':')).encode()
    j += b' '*((4-len(j)%4)%4)
    binc += b'\0'*((4-len(binc)%4)%4)
    out = struct.pack('<4sII', b'glTF', 2, 12+8+len(j)+8+len(binc))
    out += struct.pack('<II', len(j), 0x4E4F534A)+j + struct.pack('<II', len(binc), 0x004E4942)+binc
    open(p,'wb').write(out)

def main(src, dst, maxtex=1024):
    js, binc = read_glb(src)
    ext = js.get('extensions',{}).get('VRM')
    assert ext, 'khong phai VRM 0.x'
    nodes = js['nodes']
    # 1) doi ten xuong
    for hb in ext['humanoid']['humanBones']:
        nm = HUMAN.get(hb['bone'])
        if nm and hb['node'] < len(nodes): nodes[hb['node']]['name'] = nm
    # 2) ten morph
    meshes = js.get('meshes',[])
    for grp in ext.get('blendShapeMaster',{}).get('blendShapeGroups',[]):
        key = (grp.get('presetName') or '').lower()
        if key in BLEND:
            for bind in grp.get('binds',[]):
                m = meshes[bind['mesh']]
                for prim in m.get('primitives',[]):
                    tn = prim.get('extras',{}).get('targetNames')
                    if tn is None:
                        tn = m.setdefault('extras',{}).get('targetNames')
                    if tn is not None and bind['index'] < len(tn): tn[bind['index']] = BLEND[key]
    # 3) thu nho anh
    bvs = js['bufferViews']
    img_bv = {im['bufferView']: i for i,im in enumerate(js.get('images',[])) if 'bufferView' in im}
    newdata = []
    for i,bv in enumerate(bvs):
        raw = binc[bv.get('byteOffset',0): bv.get('byteOffset',0)+bv['byteLength']]
        if i in img_bv:
            im = Image.open(io.BytesIO(raw)); im.load()
            w,h = im.size; s = min(1.0, maxtex/max(w,h))
            if s < 1: im = im.resize((max(1,int(w*s)), max(1,int(h*s))), Image.LANCZOS)
            has_a = im.mode in ('RGBA','LA') and im.getchannel('A').getextrema()[0] < 250
            buf = io.BytesIO()
            if has_a: im.convert('RGBA').save(buf,'PNG',optimize=True); mt='image/png'
            else: im.convert('RGB').save(buf,'JPEG',quality=90); mt='image/jpeg'
            raw = buf.getvalue(); js['images'][img_bv[i]]['mimeType'] = mt
        newdata.append(raw)
    out = bytearray(); 
    for bv,raw in zip(bvs,newdata):
        while len(out)%4: out.append(0)
        bv['byteOffset'] = len(out); bv['byteLength'] = len(raw); out += raw
    js['buffers'] = [{'byteLength': len(out)}]
    # 4) quay 180 do quanh Y (VRM 0.x nhin ve -Z)
    for sc in js['scenes']:
        roots = sc['nodes']
        js['nodes'].append({'name':'VRMRoot','rotation':[0,1,0,0],'children':list(roots)})
        sc['nodes'] = [len(js['nodes'])-1]
        sc.setdefault('extras',{})['toonAnime'] = True
    title = ext.get('meta',{}).get('title','')
    js.setdefault('asset',{}).setdefault('extras',{})['title'] = title
    # bo phan mo rong VRM (khong can nua)
    js['extensions'].pop('VRM',None)
    if not js['extensions']: js.pop('extensions')
    if 'extensionsUsed' in js:
        js['extensionsUsed'] = [e for e in js['extensionsUsed'] if e!='VRM']
        if not js['extensionsUsed']: js.pop('extensionsUsed')
    write_glb(dst, js, bytes(out))
    print(dst, round(len(out)/1e6,2),'MB', title)

if __name__=='__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv)>3 else 1024)
