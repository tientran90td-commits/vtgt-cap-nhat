import zipfile, os, sys
import sys
SRC=sys.argv[1]; EL=sys.argv[2]; OUT=sys.argv[3]
SKIP_TOP={'data','ten-tiktok.txt','euler-api-key.txt','ai-api-key.txt','.git'}
zin=zipfile.ZipFile(EL)
zout=zipfile.ZipFile(OUT,'w',zipfile.ZIP_DEFLATED,compresslevel=6)
for i in zin.infolist():
    if i.filename.endswith('/'): continue
    n=i.filename
    if n=='resources/default_app.asar': continue
    if n=='electron.exe': n='Caro LIVE.exe'
    zout.writestr(n, zin.read(i.filename))
count=0
for root,dirs,files in os.walk(SRC):
    rel=os.path.relpath(root,SRC)
    if rel=='.': dirs[:]=[d for d in dirs if d not in SKIP_TOP]
    for f in files:
        if rel=='.' and f in SKIP_TOP: continue
        full=os.path.join(root,f); arc='resources/app/'+os.path.normpath(os.path.join(rel,f)).replace(os.sep,'/')
        zout.write(full,arc); count+=1
zout.writestr('DOC-TRUOC-KHI-CHAY.txt','''CARO LIVE - APP WINDOWS
1) Giai nen toan bo thu muc nay ra o dia (vi du D:\\\\CaroLIVE). Dung chay thang trong file zip.
2) Bam dup "Caro LIVE.exe".
   Neu Windows hien canh bao xanh: bam "Thong tin them" -> "Van chay" (app chua mua chu ky so).
3) Huong dan day du: resources\\\\app\\\\HUONG-DAN.txt (muc dau tien).
''')
zout.close()
print('game files',count,'size MB',os.path.getsize(OUT)//1048576)
