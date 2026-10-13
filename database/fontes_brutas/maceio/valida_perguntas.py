import csv,glob,json,sys
sys.path.insert(0,'backend')
from app.core.evaluation.gold_metrics import evidence_found_in
blocks=[]
for f in sorted(glob.glob('database/maceio/*.md')):
    meta=json.load(open(f.replace('.md','.fontes.json')))['blocos']
    conf={b['cabecalho'] if 'cabecalho' in b else b.get('heading'):b['confianca'] for b in meta}
    for raw in open(f).read().split('\n\n'):
        if raw.startswith('### '):
            h=raw.splitlines()[0][4:]
            blocks.append((f.split('/')[-1][12:14],h,raw,conf.get(h,'?')))
print(len(blocks),'blocos')
bad=0
for row in csv.DictReader(open('database/perguntas_guia_maceio.csv')):
    ev=row['evidencia_referencia'].split('|'); hops=list(map(int,row['evidencia_salto'].split('|')))
    hopblocks={}
    for e,h in zip(ev,hops):
        m=[(b[0],b[1],b[3]) for b in blocks if evidence_found_in(e,b[2])]
        if not m: print('SEM CASAMENTO:',row['pergunta'][:60],'|',e[:60]); bad+=1
        if any(c=='secundario' for _,_,c in m): print('SECUNDARIO:',row['pergunta'][:60])
        hopblocks.setdefault(h,set()).update((a,b) for a,b,_ in m)
    if row['tipo'] in('ponte','comparacao') and len(hopblocks)>1:
        s1,s2=hopblocks.get(1,set()),hopblocks.get(2,set())
        if s1 and s2 and s1==s2: print('MESMO BLOCO nos saltos:',row['pergunta'][:60]); bad+=1
    n=max(len(v) for v in hopblocks.values()) if hopblocks else 0
    if n>2: print(f'aviso: evidência casa em {n} blocos:',row['pergunta'][:60])
print('problemas',bad)
