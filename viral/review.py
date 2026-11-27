r"""Gera output/review.html: folha de revisao dos shorts de output/queue.json.

Uso: python review.py [--open]      (pagina estatica; sem edicao de texto)
     python serve.py [--open]       (servidor local: mesma pagina + editor de texto que refaz o video)
As decisoes ficam no navegador (localStorage) e o botao "Exportar decisoes" baixa
review_decisions_<id aleatorio>.json (um novo a cada clique) com {id: approved|needs_fix|rejected|pending, nota}.
"""
import argparse, html, json, os
from pathlib import Path

HERE = Path(__file__).parent
PROFILE = HERE.parent / "profile"
OUT = HERE / "output"

CSS = """
:root{--bg:#0f1115;--card:#181b22;--fg:#e8eaf0;--mut:#9aa3b2;--ok:#2ea043;--no:#da3633;--fix:#d29922;--line:#2a2f3a}
@media (prefers-color-scheme: light){:root{--bg:#f4f5f7;--card:#fff;--fg:#14171f;--mut:#5b6472;--line:#dfe3ea}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;
display:flex;flex-wrap:wrap;gap:12px;align-items:center}
h1{font-size:18px;margin:0;margin-right:auto}.count{color:var(--mut)}
button{font:inherit;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:8px 14px;cursor:pointer}
button:hover{border-color:var(--mut)}button:disabled{opacity:.5;cursor:wait}
main{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.card.approved{border-color:var(--ok)}.card.fix{border-color:var(--fix)}.card.rejected{border-color:var(--no);opacity:.6}
video{width:100%;aspect-ratio:9/16;background:#000;display:block}
.body{padding:12px;display:flex;flex-direction:column;gap:8px}
.tags{display:flex;gap:6px;flex-wrap:wrap;font-size:12px;color:var(--mut)}
.tag{border:1px solid var(--line);border-radius:99px;padding:1px 8px}
.hook{font-weight:700;letter-spacing:.02em}
.cap{white-space:pre-wrap;color:var(--mut);font-size:13px;max-height:7.5em;overflow:auto}
textarea,.edit input{width:100%;background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px;font:inherit;min-height:2.6em;resize:vertical}
.row{display:flex;gap:8px}.row button{flex:1}
.fixb.on{background:var(--fix);border-color:var(--fix);color:#000}.ok.on{background:var(--ok);border-color:var(--ok);color:#fff}.no.on{background:var(--no);border-color:var(--no);color:#fff}
a{color:var(--mut)}.filters{display:flex;gap:6px;flex-wrap:wrap}.filters button{padding:6px 12px;border-radius:99px;font-size:14px}.filters button.active{background:var(--fg);color:var(--bg);border-color:var(--fg)}.card.hidden{display:none}.up{display:inline-flex;align-items:center;gap:6px;cursor:pointer;font-size:13px;color:var(--mut);border:1px dashed var(--line);border-radius:8px;padding:5px 10px;width:max-content}.up:hover{border-color:var(--mut)}.thumb{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--mut)}.thumb img{height:64px;max-width:120px;object-fit:contain;border-radius:8px;border:1px solid var(--line);background:#fff2}.thumb button{padding:2px 8px;font-size:12px}.idbar{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:var(--bg);border-bottom:1px solid var(--line);font:600 13px ui-monospace,Consolas,monospace;cursor:pointer;user-select:all}.idbar small{font:12px system-ui;color:var(--mut);user-select:none}#q{flex:1 1 220px;min-width:160px;max-width:380px;font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 12px}#q:focus{outline:2px solid var(--mut);outline-offset:0}.empty{grid-column:1/-1;text-align:center;color:var(--mut);padding:40px 0}
.edit{border:1px solid var(--line);border-radius:8px;padding:6px 10px}.edit summary{cursor:pointer;font-weight:600;font-size:14px}
.edit label{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--mut);margin-top:8px}.edit .two{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.edit .go{margin-top:10px;width:100%}.estatus{font-size:12px;color:var(--mut);margin-top:6px;min-height:1.2em}.estatus.err{color:var(--no)}
.navlink{color:var(--mut);text-decoration:none;border:1px solid var(--line);border-radius:99px;padding:4px 12px;font-size:14px}.navlink:hover{border-color:var(--mut)}
.banner{background:var(--card);border-bottom:1px solid var(--line);color:var(--mut);font-size:13px;padding:6px 16px}
@media (max-width:640px){
header{position:static;padding:10px 12px;gap:8px}h1{font-size:16px;margin-right:0;flex:1 1 auto}
.filters{flex-wrap:nowrap;overflow-x:auto;width:100%;padding-bottom:4px;-webkit-overflow-scrolling:touch}.filters button{flex:none;white-space:nowrap}
.count{width:100%;font-size:13px}#q{flex:1 1 100%;max-width:none;min-width:0}#export{width:100%}
.banner{display:none}
main{grid-template-columns:1fr;padding:10px;gap:12px}
video{max-height:78vh;object-fit:contain}.cap{max-height:none}
.edit .two{grid-template-columns:1fr}
}
@media (pointer:coarse){
button,.filters button,.navlink{min-height:44px}.row button{min-height:48px;font-size:16px}
textarea,.edit input,#q{font-size:16px;min-height:44px}.edit summary{padding:10px 0}.idbar{padding:12px}.up{padding:10px 14px}
}
"""

JS = r"""
const KEY='gta6-review-v4';let S={};try{S=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
let Q='';let F='all';try{F=localStorage.getItem(KEY+'-f')||'all'}catch(e){}
const TOKEN=(document.querySelector('meta[name=editor-token]')||{}).content||'';
let EDIT={};try{EDIT=JSON.parse(document.getElementById('edit-data').textContent||'{}')}catch(e){}
function stamp(){document.querySelectorAll('.card').forEach(c=>{if(S[c.id])S[c.id].v=c.dataset.v})}
function save(){stamp();try{localStorage.setItem(KEY,JSON.stringify(S))}catch(e){}}
function paint(){let a=0,r=0,f=0;const cnt={approved:0,fix:0,rejected:0,pending:0};let vis=0;document.querySelectorAll('.card').forEach(c=>{const s=S[c.id]||{};const st=s.d||'pending';cnt[st]++;const hay=((c.dataset.q||'')+' '+(s.n||'')).toLowerCase();const mq=!Q||Q.split(' ').filter(Boolean).every(w=>hay.includes(w));const hide=(F!=='all'&&st!==F)||!mq;if(!hide)vis++;c.classList.toggle('hidden',hide);
c.classList.toggle('approved',s.d==='approved');c.classList.toggle('rejected',s.d==='rejected');c.classList.toggle('fix',s.d==='fix');c.querySelector('.fixb').classList.toggle('on',s.d==='fix');
c.querySelector('.ok').classList.toggle('on',s.d==='approved');c.querySelector('.no').classList.toggle('on',s.d==='rejected');
c.querySelector('textarea.note').value=s.n||'';const th=c.querySelector('.thumb');th.innerHTML='';if(s.img){const im=document.createElement('img');im.src=s.img.data;im.alt=s.img.name;th.appendChild(im);const nm=document.createElement('span');nm.textContent=s.img.name;th.appendChild(nm);const rb=document.createElement('button');rb.textContent='Remover';rb.dataset.rm='1';th.appendChild(rb)}if(s.d==='approved')a++;if(s.d==='rejected')r++;if(s.d==='fix')f++});
const n=document.querySelectorAll('.card').length;
document.getElementById('count').textContent=a+' aprovados · '+f+' p/ corrigir · '+r+' descartados · '+(n-a-r-f)+' pendentes'+(vis<n?' · mostrando '+vis:'');
const names={all:'Todos',pending:'Pendentes',approved:'Aprovados',fix:'Corrigir',rejected:'Descartados'};
document.querySelectorAll('[data-f]').forEach(b=>{const k=b.dataset.f;b.textContent=names[k]+' ('+(k==='all'?n:cnt[k])+')';b.classList.toggle('active',k===F)});
document.getElementById('empty').hidden=vis>0;}
document.addEventListener('click',e=>{const b=e.target.closest('[data-d]');if(!b)return;const id=b.closest('.card').id;
S[id]=S[id]||{};S[id].d=S[id].d===b.dataset.d?undefined:b.dataset.d;save();paint()});
document.addEventListener('input',e=>{if(!e.target.classList.contains('note'))return;const id=e.target.closest('.card').id;
S[id]=S[id]||{};S[id].n=e.target.value;save()});
document.addEventListener('click',e=>{const b=e.target.closest('[data-f]');if(!b)return;F=b.dataset.f;try{localStorage.setItem(KEY+'-f',F)}catch(err){}paint();window.scrollTo(0,0)});
function shrink(file,cb){const r=new FileReader();r.onload=()=>{const im=new Image();im.onload=()=>{const k=Math.min(1,800/Math.max(im.width,im.height));const c=document.createElement('canvas');c.width=Math.round(im.width*k);c.height=Math.round(im.height*k);c.getContext('2d').drawImage(im,0,0,c.width,c.height);cb(c.toDataURL(file.type==='image/jpeg'?'image/jpeg':'image/png',0.88))};im.onerror=()=>alert('Nao consegui ler essa imagem.');im.src=r.result};r.readAsDataURL(file)}
document.addEventListener('change',e=>{if(e.target.type!=='file')return;const f=e.target.files[0];if(!f)return;const id=e.target.closest('.card').id;shrink(f,data=>{const prev=S[id]&&S[id].img;S[id]=S[id]||{};S[id].img={name:f.name,data};stamp();try{localStorage.setItem(KEY,JSON.stringify(S))}catch(err){if(prev)S[id].img=prev;else delete S[id].img;alert('Imagem grande demais para guardar no navegador. Use uma menor.')}paint()});e.target.value=''});
document.addEventListener('click',e=>{const b=e.target.closest('[data-rm]');if(!b)return;const id=b.closest('.card').id;if(S[id]){delete S[id].img;save();paint()}});
document.addEventListener('click',e=>{const b=e.target.closest('.idbar');if(!b)return;const id=b.closest('.card').id;try{navigator.clipboard.writeText(id)}catch(err){}const s=b.querySelector('small');s.textContent='copiado!';setTimeout(()=>s.textContent='copiar',1200)});
document.getElementById('q').addEventListener('input',e=>{Q=e.target.value.trim().toLowerCase();paint()});
document.getElementById('export').onclick=()=>{const o={};for(const[k,v]of Object.entries(S))if(v.d||v.n||v.img){o[k]={status:v.d==='fix'?'needs_fix':(v.d||'pending'),note:v.n||''};if(v.img)o[k].attachment=v.img}
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(o,null,2)],{type:'application/json'}));
a.download='review_decisions_'+Math.random().toString(36).slice(2,7)+'.json';a.click()};
document.addEventListener('play',e=>{document.querySelectorAll('video').forEach(v=>{if(v!==e.target)v.pause()})},true);

/* ---- editor de texto (so com o servidor: python serve.py) ---- */
function fill(c,v){c.querySelectorAll('[data-e]').forEach(el=>{const x=v[el.dataset.e];el.value=Array.isArray(x)?x.join('\n'):(x||'')})}
document.querySelectorAll('.card').forEach(c=>{if(EDIT[c.id])fill(c,EDIT[c.id])});
document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-apply]');if(!b)return;
  const c=b.closest('.card'),id=c.id,st=c.querySelector('.estatus');
  const get=k=>{const el=c.querySelector('[data-e="'+k+'"]');return el?el.value:''};
  const lines=k=>get(k).split('\n').map(x=>x.trim()).filter(Boolean);
  const body={text_pt:get('text_pt'),emoji_pt:get('emoji_pt'),bottom_text_pt:get('bottom_text_pt'),cover_text:lines('cover_text'),
    hook_pt:lines('hook_pt'),caption_pt:get('caption_pt'),name:get('name'),handle:get('handle')};
  b.disabled=true;st.className='estatus';st.textContent='Refazendo o video... (pode levar alguns segundos)';
  try{
    const r=await fetch('/api/apply/'+encodeURIComponent(id),{method:'POST',headers:{'Content-Type':'application/json','X-Token':TOKEN},body:JSON.stringify(body)});
    const j=await r.json().catch(()=>({}));
    if(!r.ok||!j.ok)throw new Error(j.error||('erro HTTP '+r.status));
    const v=c.querySelector('video');v.src=v.getAttribute('src').split('?')[0]+'?v='+j.version;v.load();
    c.dataset.v=String(j.version);c.dataset.status='pending_review';c.dataset.q=j.search;
    if(S[id])delete S[id].d;                       // video novo: decisao anterior nao vale mais
    fill(c,j.edit);c.querySelector('.hook').textContent=j.hook;c.querySelector('.cap').textContent=j.caption;
    save();paint();const w=(j.warnings||[]);st.className='estatus'+(w.length?' err':'');st.textContent='Pronto: video refeito '+new Date().toLocaleTimeString()+' (voltou para pendente)'+(w.length?' | Aviso: '+w.join(' | '):'');
  }catch(err){st.className='estatus err';st.textContent='Erro: '+err.message}
  finally{b.disabled=false}
});
document.querySelectorAll('.card').forEach(c=>{const s=S[c.id];if(s&&s.v!==c.dataset.v)delete S[c.id]});
document.querySelectorAll('.card').forEach(c=>{if(!S[c.id]){const st=c.dataset.status;if(st==='approved'||st==='rejected')S[c.id]={d:st}}});
save();paint();
"""


def profile_defaults():
    try:
        return json.loads((PROFILE / "profile.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"name": "", "handle": ""}


def edit_view(item, prof=None):
    """Campos editaveis de um item (o que o servidor aceita em /api/apply)."""
    prof = prof or profile_defaults()
    cover = (item.get("cover") or [{}])[0]
    over = item.get("profile") or {}
    return {
        "text_pt": item.get("text_pt", ""), "emoji_pt": item.get("emoji_pt", ""),
        "bottom_text_pt": item.get("bottom_text_pt", ""),
        "has_cover": bool(item.get("cover")), "cover_text": cover.get("text", []),
        "hook_pt": item.get("hook_pt") or [],
        "caption_pt": item.get("caption_pt") or item.get("caption", ""),
        "name": over.get("name") or prof.get("name", ""), "handle": over.get("handle") or prof.get("handle", ""),
    }


def display_hook(v):
    return " / ".join(v.get("hook_pt") or []) or v.get("text_pt") or " / ".join(v.get("hook") or []) or "(sem gancho)"


def search_text(vid, v):
    return " ".join(str(x) for x in [vid, v.get("type"), " ".join(v.get("hook_pt") or v.get("hook") or []), v.get("text_pt"),
                                     v.get("bottom_text_pt"), v.get("caption_pt") or v.get("caption"), v.get("original_caption"),
                                     v.get("review_note"), v.get("status"), v.get("source")] if x).lower()


def edit_section(ev):
    cover = ('<label>Texto da tarja (uma linha por linha)<textarea data-e="cover_text" rows="2"></textarea></label>'
             if ev["has_cover"] else "")
    return f"""<details class="edit"><summary>Editar texto</summary>
<label>Texto do cabecalho (aceita emoji; vazio = sem cabecalho, usa o gancho)<textarea data-e="text_pt" rows="3"></textarea></label>
<label>Emoji no fim do texto (opcional)<input data-e="emoji_pt" maxlength="12"></label>
<label>Frase embaixo do video<input data-e="bottom_text_pt" maxlength="60"></label>{cover}
<label>Gancho sobre o video (uma linha por linha; so sem cabecalho)<textarea data-e="hook_pt" rows="2"></textarea></label>
<label>Legenda do post<textarea data-e="caption_pt" rows="4"></textarea></label>
<div class="two"><label>Nome<input data-e="name" maxlength="30"></label><label>@ do perfil<input data-e="handle" maxlength="30"></label></div>
<button class="go" data-apply>Aplicar e refazer video</button><div class="estatus"></div></details>"""


def poster_for(file):
    """Quadro de capa (output/poster/<id>.jpg), refeito se o video for mais novo.
    Com preload="none" a pagina nao baixa os ~30 videos de uma vez (pelo tunel/celular isso falhava)."""
    import subprocess
    mp4 = OUT / file
    jpg = OUT / "poster" / (Path(file).stem + ".jpg")
    if not jpg.exists() or jpg.stat().st_mtime < mp4.stat().st_mtime:
        jpg.parent.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", str(mp4), "-frames:v", "1",
                        "-vf", "scale=360:-2", "-q:v", "4", str(jpg)], check=False)
    return f"poster/{jpg.name}" if jpg.exists() else ""


def card(vid, v, served=False):
    e = html.escape
    refeito = '<span class="tag" style="color:var(--fix);border-color:var(--fix)">refeito</span>' if v.get("fixes_applied") else ""
    prev = f'<div class="cap">Nota anterior: {e(v["review_note"])}</div>' if v.get("fixes_applied") and v.get("review_note") else ""
    edit = edit_section(edit_view(v)) if served else ""
    return f"""<article class="card" id="{e(vid)}" data-status="{e(v.get('status', ''))}" data-v="{int((OUT / v['file']).stat().st_mtime)}" data-q="{e(search_text(vid, v))}">
<div class="idbar" title="Clique para copiar o ID"><span>ID: {e(vid)}</span><small>copiar</small></div>
<video src="{e(v['file'])}" poster="{e(poster_for(v['file']))}" controls preload="none" playsinline></video>
<div class="body">
<div class="tags"><span class="tag">{e(v['type'])}</span><span class="tag">{v['duration']}s</span><span class="tag">{e(v.get('lang',''))}</span>{refeito}</div>{prev}
<div class="hook">{e(display_hook(v))}</div>
<div class="cap">{e(v.get('caption_pt') or v['caption'])}</div>
<a href="{e(v['source'])}" target="_blank" rel="noopener">abrir original</a>{edit}
<textarea class="note" placeholder="Nota (ex.: texto duplicado, b-roll ruim...)"></textarea><label class="up">&#128206; Anexar imagem<input type="file" accept="image/*" hidden></label><div class="thumb"></div>
<div class="row"><button class="ok" data-d="approved">Aprovar</button><button class="fixb" data-d="fix">Corrigir</button><button class="no" data-d="rejected">Descartar</button></div>
</div></article>"""


def build_page(q, token=None):
    """HTML da folha. Com token (modo servidor) inclui o editor de texto."""
    served = token is not None
    q = {k: v for k, v in q.items() if (OUT / v["file"]).exists()}
    meta = f'<meta name="editor-token" content="{html.escape(token)}">' if served else ""
    banner = ('<div class="banner">Modo editor ativo: abra "Editar texto" em um cartao, altere e clique em Aplicar.</div>'
              if served else '<div class="banner">Modo somente leitura. Para editar textos, rode <code>python serve.py --open</code>.</div>')
    nav = '<a class="navlink" href="/agenda">Agenda &rarr;</a> <a class="navlink" href="/backlog">Backlog &rarr;</a>' if served else ""
    prof = profile_defaults()
    edit_data = json.dumps({k: edit_view(v, prof) for k, v in q.items()} if served else {}, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">{meta}
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisao GTA VI</title><style>{CSS}</style></head><body>
<header><h1>Revisao dos shorts GTA VI</h1>{nav}<nav class="filters" id="filters"><button data-f="all">Todos</button><button data-f="pending">Pendentes</button><button data-f="approved">Aprovados</button><button data-f="fix">Corrigir</button><button data-f="rejected">Descartados</button></nav><span class="count" id="count"></span><input id="q" type="search" placeholder="Buscar por ID, texto, legenda ou nota..." autocomplete="off"><button id="export">Exportar decisoes</button></header>{banner}
<main id="grid">{''.join(card(k, v, served) for k, v in q.items())}<div class="empty" id="empty" hidden>Nenhum video encontrado.</div></main>
<script id="edit-data" type="application/json">{edit_data}</script><script>{JS}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    q = json.loads((OUT / "queue.json").read_text(encoding="utf-8"))
    path = OUT / "review.html"
    path.write_text(build_page(q), encoding="utf-8")
    print(f"{len([1 for v in q.values() if (OUT / v['file']).exists()])} shorts -> {path}")
    if a.open:
        os.startfile(path)


if __name__ == "__main__":
    main()
