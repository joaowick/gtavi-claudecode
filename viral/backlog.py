r"""Pagina de backlog (/backlog no serve.py). Estado em viral/backlog.json (versionado, vale entre sessoes).

Cada item: id, title, detail, status (todo|doing|done), prio (alta|media|baixa), created, updated.
API: POST /api/backlog {action: add|update|delete, ...}, mesmo token/Host das outras rotas.
"""
import json, os, secrets
from datetime import datetime
from pathlib import Path

import agenda as A

FILE = Path(__file__).parent / "backlog.json"
STATUS = ("todo", "doing", "done")
PRIO = ("alta", "media", "baixa")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load():
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        d = {}
    items = d.get("items") if isinstance(d, dict) else None
    return {"items": [i for i in (items or []) if isinstance(i, dict) and i.get("id")]}


def save(d):
    tmp = FILE.with_name("backlog.tmp.json")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, FILE)


def _text(v, n):
    return str(v or "").strip()[:n]


def apply_action(d, body):
    act = body.get("action")
    items = d["items"]
    if act == "add":
        title = _text(body.get("title"), 140)
        if not title:
            raise ValueError("titulo vazio")
        prio = body.get("prio") if body.get("prio") in PRIO else "media"
        items.append({"id": secrets.token_hex(4), "title": title, "detail": _text(body.get("detail"), 4000),
                      "status": "todo", "prio": prio, "created": _now(), "updated": _now()})
        return "Item adicionado"
    it = next((i for i in items if i["id"] == body.get("id")), None)
    if it is None:
        raise KeyError(body.get("id"))
    if act == "delete":
        items.remove(it)
        return "Item removido"
    if act == "update":
        if "title" in body:
            t = _text(body["title"], 140)
            if not t:
                raise ValueError("titulo vazio")
            it["title"] = t
        if "detail" in body:
            it["detail"] = _text(body["detail"], 4000)
        if "status" in body:
            if body["status"] not in STATUS:
                raise ValueError("status invalido")
            it["status"] = body["status"]
        if "prio" in body:
            if body["prio"] not in PRIO:
                raise ValueError("prioridade invalida")
            it["prio"] = body["prio"]
        it["updated"] = _now()
        return "Item atualizado"
    raise ValueError("acao invalida")


CSS = A.CSS + """
main{max-width:1100px;margin:0 auto;padding:16px}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;align-items:start}
@media(max-width:800px){.cols{grid-template-columns:1fr}}
.col{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px;min-height:120px}
.col h2{display:flex;justify-content:space-between}
.it{border:1px solid var(--line);border-radius:10px;padding:8px 10px;margin-bottom:8px;background:var(--bg)}
.it b{display:block;margin-bottom:2px}.it .d{white-space:pre-wrap;color:var(--mut);font-size:13px;margin:4px 0}
.it .r{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}.it .r button,.it .r select{padding:3px 8px;font-size:12px}
select{background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px}
.tag{font-size:11px;border-radius:99px;padding:1px 8px;border:1px solid var(--line);color:var(--mut)}
.tag.alta{border-color:var(--no);color:var(--no)}.tag.media{border-color:var(--fix);color:var(--fix)}
.add{display:grid;gap:6px;margin-bottom:14px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:10px}
.add .row{display:flex;gap:8px}.col.done .it{opacity:.65}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 14px;border-radius:99px;font-size:14px;opacity:0;pointer-events:none;transition:opacity .2s}
"""

JS = """
const TOKEN=(document.querySelector('meta[name=editor-token]')||{}).content||'';
let D=JSON.parse(document.getElementById('data').textContent);
const LBL={todo:'A fazer',doing:'Em andamento',done:'Feito'},PL={alta:'alta',media:'média',baixa:'baixa'};
const esc=s=>String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(m){const t=document.getElementById('toast');t.textContent=m;t.style.opacity=1;setTimeout(()=>t.style.opacity=0,2200)}
async function api(body){
  const r=await fetch('/api/backlog',{method:'POST',headers:{'Content-Type':'application/json','X-Token':TOKEN},body:JSON.stringify(body)});
  const j=await r.json();if(!j.ok){toast(j.error||'Erro');return false}
  D=j.backlog;toast(j.message);render();return true}
function render(){
  const order={alta:0,media:1,baixa:2};
  document.getElementById('cols').innerHTML=['todo','doing','done'].map(s=>{
    const its=D.items.filter(i=>i.status===s).sort((a,b)=>order[a.prio]-order[b.prio]);
    return `<div class="col ${s}"><h2>${LBL[s]} <span class="count">${its.length}</span></h2>`+its.map(i=>`<div class="it">
      <b>${esc(i.title)}</b><span class="tag ${i.prio}">${PL[i.prio]}</span> <small>${esc(i.created)}</small>
      ${i.detail?`<div class="d">${esc(i.detail)}</div>`:''}
      <div class="r">${['todo','doing','done'].filter(x=>x!==s).map(x=>`<button data-id="${i.id}" data-st="${x}">→ ${LBL[x]}</button>`).join('')}
      <select data-id="${i.id}" data-prio>${['alta','media','baixa'].map(p=>`<option value="${p}" ${p===i.prio?'selected':''}>${PL[p]}</option>`).join('')}</select>
      <button data-id="${i.id}" data-edit>Editar</button><button data-id="${i.id}" data-del>Remover</button></div></div>`).join('')+'</div>'}).join('')}
document.addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b||!b.dataset.id)return;const id=b.dataset.id,it=D.items.find(i=>i.id===id);
  if(b.dataset.st)api({action:'update',id,status:b.dataset.st});
  else if(b.hasAttribute('data-del')){if(confirm('Remover "'+it.title+'"?'))api({action:'delete',id})}
  else if(b.hasAttribute('data-edit')){const t=prompt('Título',it.title);if(t===null)return;const d=prompt('Detalhes',it.detail);if(d===null)return;api({action:'update',id,title:t,detail:d})}});
document.addEventListener('change',e=>{const s=e.target;if(s.hasAttribute&&s.hasAttribute('data-prio'))api({action:'update',id:s.dataset.id,prio:s.value})});
document.getElementById('addGo').onclick=async()=>{
  const title=document.getElementById('nt').value,detail=document.getElementById('nd').value,prio=document.getElementById('np').value;
  if(await api({action:'add',title,detail,prio})){document.getElementById('nt').value='';document.getElementById('nd').value=''}};
render();
"""

TEMPLATE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="editor-token" content="__TOKEN__">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Backlog GTA VI</title><style>__CSS__</style></head><body>
<header><h1>Backlog</h1><nav class="tabs"><a href="/">Revisão</a><a href="/agenda">Agenda</a><a class="on" href="/backlog">Backlog</a></nav></header>
<main><div class="add"><input id="nt" placeholder="Novo item (título)" maxlength="140"><textarea id="nd" rows="2" placeholder="Detalhes (opcional)"></textarea>
<div class="row"><select id="np"><option value="alta">prioridade alta</option><option value="media" selected>prioridade média</option><option value="baixa">prioridade baixa</option></select>
<button class="primary" id="addGo">Adicionar</button></div></div>
<div class="cols" id="cols"></div></main><div id="toast" role="status"></div>
<script id="data" type="application/json">__DATA__</script><script>__JS__</script></body></html>"""


def build_page(token):
    blob = json.dumps(load(), ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__TOKEN__", token).replace("__CSS__", CSS).replace("__JS__", JS).replace("__DATA__", blob)
