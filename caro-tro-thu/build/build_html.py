import pathlib
root = pathlib.Path(__file__).resolve().parent.parent
t = (root / 'www/index.template.html').read_text(encoding='utf8')
out = t.replace('/*CSS*/', (root / 'www/style.css').read_text(encoding='utf8')) \
       .replace('/*ENGINE*/', (root / 'www/engine.js').read_text(encoding='utf8')) \
       .replace('/*RAPFI*/', (root / 'www/rapfi.js').read_text(encoding='utf8')) \
       .replace('/*ACCOUNT*/', (root / 'www/account-core.js').read_text(encoding='utf8')) \
       .replace('/*APP*/', (root / 'www/app.js').read_text(encoding='utf8')) \
       .replace('/*LINK*/', (root / 'www/link.js').read_text(encoding='utf8')) \
       .replace('/*TABS*/', (root / 'www/tabs.js').read_text(encoding='utf8'))
(root / 'dist').mkdir(exist_ok=True)
(root / 'dist/index.html').write_text(out, encoding='utf8')
print('dist/index.html', len(out), 'bytes')
