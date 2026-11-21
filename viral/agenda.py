r"""Pagina de agenda: ver os videos aprovados e organiza-los num calendario.

IMPORTANTE: so organiza. Nada e publicado (nenhuma rede esta conectada). O estado fica em output/schedule.json.
A pagina so e servida por `python serve.py` (precisa da API /api/schedule).
"""
import copy
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import review as R

HERE = Path(__file__).parent
OUT = HERE / "output"
DEFAULT = {"settings": {"networks": ["Instagram Reels", "TikTok", "YouTube Shorts"]}, "items": {}}
HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ---------- logica de agendamento (pura: facil de testar) ----------
def norm_sched(s):
    s = copy.deepcopy(s) if s else copy.deepcopy(DEFAULT)
    s.setdefault("settings", {}).setdefault("networks", list(DEFAULT["settings"]["networks"]))
    s.setdefault("items", {})
    return s


def parse_when(w):
    if not isinstance(w, str):
        raise ValueError("data/hora invalida")
    try:
        datetime.strptime(w, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("data/hora invalida (use AAAA-MM-DDTHH:MM)") from None
    return w


def clean_networks(lst, allowed):
    if not isinstance(lst, list):
        raise ValueError("redes invalidas")
    return [n for n in dict.fromkeys(lst) if n in allowed][:8]


def apply_action(sched, queue, body):
    """Aplica uma acao em `sched` (modifica no lugar) e devolve uma mensagem. ValueError = pedido invalido."""
    if not isinstance(body, dict):
        raise ValueError("corpo invalido")
    act, items, nets_all = body.get("action"), sched["items"], sched["settings"]["networks"]

    if act == "set":
        vid = str(body.get("id", ""))
        if body.get("when") is None:
            items.pop(vid, None)
            return "removido da agenda"
        if vid not in queue or queue[vid].get("status") != "approved":
            raise ValueError("so videos aprovados podem ser agendados")
        nets = clean_networks(body.get("networks", []), nets_all)
        if not nets:
            raise ValueError("escolha ao menos uma rede")
        items[vid] = {"when": parse_when(body["when"]), "networks": nets}
        return "agendado"

    if act == "networks":
        raw = body.get("networks")
        if not isinstance(raw, list):
            raise ValueError("lista de redes invalida")
        names = [re.sub(r"\s+", " ", str(n)).strip()[:30] for n in raw]
        names = list(dict.fromkeys(n for n in names if n))[:8]
        if not names:
            raise ValueError("informe ao menos uma rede")
        sched["settings"]["networks"] = names
        for it in items.values():
            it["networks"] = [n for n in it["networks"] if n in names] or names[:1]
        return "redes atualizadas"

    if act == "auto":
        try:
            start = datetime.strptime(str(body.get("start", "")), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError("data inicial invalida") from None
        times = body.get("times")
        if not isinstance(times, list) or not all(isinstance(t, str) and HM.match(t) for t in times) or not times:
            raise ValueError("horarios invalidos (use HH:MM)")
        times = sorted(dict.fromkeys(times))[:6]
        try:
            per_day = max(1, min(int(body.get("per_day", 1)), len(times), 5))
        except (TypeError, ValueError):
            raise ValueError("videos por dia invalido") from None
        nets = clean_networks(body.get("networks", []), nets_all)
        if not nets:
            raise ValueError("escolha ao menos uma rede")
        todo = [v for v, it in queue.items() if it.get("status") == "approved" and v not in items]
        if not todo:
            return "nenhum video aprovado sem data"
        d, i = start, 0
        for vid in todo:
            items[vid] = {"when": f"{d.isoformat()}T{times[i]}", "networks": nets}
            i += 1
            if i >= per_day:
                d, i = d + timedelta(days=1), 0
        last = d - timedelta(days=1) if i == 0 else d          # d ja avancou se o ultimo dia fechou completo
        return f"{len(todo)} video(s) agendado(s), de {start.strftime('%d/%m')} a {last.strftime('%d/%m')}"

    raise ValueError("acao desconhecida")


def videos_view(queue, sched):
    """Dados que a pagina precisa: aprovados + qualquer um que ja esteja na agenda."""
    out = {}
    for vid, v in queue.items():
        f = OUT / v["file"]
        if (v.get("status") == "approved" or vid in sched["items"]) and f.exists():
            out[vid] = {"file": v["file"], "v": int(f.stat().st_mtime), "status": v.get("status", ""),
                        "hook": R.display_hook(v), "caption": v.get("caption_pt") or v["caption"],
                        "duration": v["duration"], "source": v["source"]}
    return out


# ---------- pagina ----------
CSS = """
:root{--bg:#0f1115;--card:#181b22;--fg:#e8eaf0;--mut:#9aa3b2;--ok:#2ea043;--no:#da3633;--fix:#d29922;--line:#2a2f3a;--acc:#5b8def}
@media (prefers-color-scheme: light){:root{--bg:#f4f5f7;--card:#fff;--fg:#14171f;--mut:#5b6472;--line:#dfe3ea}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--bg);border-bottom:1px solid var(--line);padding:12px 16px;display:flex;flex-wrap:wrap;gap:12px;align-items:center}
h1{font-size:18px;margin:0}h2{font-size:15px;margin:0 0 10px}h3{margin:0;font-size:14px}.muted,.count{color:var(--mut)}small{color:var(--mut)}
.tabs{display:flex;gap:4px;margin-right:auto}.tabs a{padding:6px 12px;border-radius:99px;color:var(--mut);text-decoration:none;border:1px solid transparent}
.tabs a.on{background:var(--fg);color:var(--bg)}.tabs a:not(.on):hover{border-color:var(--line)}
button,input,textarea{font:inherit}
button{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:8px;padding:7px 12px;cursor:pointer}
button:hover{border-color:var(--mut)}button:disabled{opacity:.5;cursor:wait}button.primary{background:var(--acc);border-color:var(--acc);color:#fff}
input,textarea{background:transparent;color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 8px;width:100%}
.banner{background:var(--card);border-bottom:1px solid var(--line);color:var(--mut);font-size:13px;padding:6px 16px}
.layout{display:grid;grid-template-columns:300px 1fr;gap:16px;padding:16px;align-items:start}
.layout.wide{grid-template-columns:1fr}.layout.wide aside{display:none}
@media (max-width:860px){.layout{grid-template-columns:1fr}}
aside{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;max-height:calc(100vh - 110px);overflow:auto;position:sticky;top:70px}
.vcard{display:flex;gap:10px;border:1px solid var(--line);border-radius:10px;padding:8px;margin-bottom:8px;background:var(--bg);cursor:grab}
.vcard video{width:64px;aspect-ratio:9/16;object-fit:cover;border-radius:6px;background:#000;flex:none}
.vcard .vb{min-width:0;display:flex;flex-direction:column;gap:2px}.vcard p{margin:0;font-size:12px;color:var(--mut);overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.vcard b{font:600 12px ui-monospace,Consolas,monospace}.vcard button{margin-top:auto;padding:3px 8px;font-size:12px;width:max-content}
.toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:12px}.seg{display:flex}.seg button{border-radius:0}.seg button:first-child{border-radius:8px 0 0 8px}.seg button:last-child{border-radius:0 8px 8px 0}
.seg button.on{background:var(--fg);color:var(--bg);border-color:var(--fg)}.wk{display:flex;gap:6px;align-items:center;margin-left:auto}
.week{display:grid;grid-template-columns:repeat(7,minmax(130px,1fr));gap:8px;overflow-x:auto}
.day{background:var(--card);border:1px solid var(--line);border-radius:10px;min-height:260px;padding:8px;display:flex;flex-direction:column;gap:6px}
.day.today{border-color:var(--acc)}.day.over{outline:2px dashed var(--acc)}.day h3{display:flex;justify-content:space-between}
.chip{display:flex;flex-direction:column;align-items:flex-start;gap:1px;text-align:left;width:100%;padding:6px 8px;border-radius:8px;border-left:4px solid var(--acc);cursor:grab}
.chip time{font-weight:700;font-size:13px}.chip b{font:600 11px ui-monospace,Consolas,monospace;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.chip small{font-size:11px}.chip.past{border-left-color:var(--fix)}.chip.bad{border-left-color:var(--no)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--line);font-size:14px;vertical-align:top}th{color:var(--mut);font-weight:600;font-size:12px}
tr td:first-child{white-space:nowrap}tr.trow{cursor:pointer}tr.trow:hover{background:var(--bg)}
.gal{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
.gcard{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.gcard video{width:100%;aspect-ratio:9/16;background:#000;display:block}.gcard .gb{padding:10px;display:flex;flex-direction:column;gap:6px}
.badge{display:inline-block;border:1px solid var(--line);border-radius:12px;padding:2px 8px;font-size:12px;color:var(--mut);width:max-content;max-width:100%;white-space:normal}
.badge.ok{color:var(--ok);border-color:var(--ok)}.badge.late{color:var(--fix);border-color:var(--fix)}.badge.bad{color:var(--no);border-color:var(--no)}
dialog{border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--fg);padding:0;max-width:min(760px,94vw);width:100%}
dialog::backdrop{background:#0009}.dform{display:grid;grid-template-columns:minmax(0,240px) 1fr;gap:16px;padding:16px}
@media (max-width:640px){.dform{grid-template-columns:1fr}}
.dform video{width:100%;aspect-ratio:9/16;background:#000;border-radius:10px}.df{display:flex;flex-direction:column;gap:10px;min-width:0}
.df label,fieldset{font-size:12px;color:var(--mut);display:flex;flex-direction:column;gap:4px}fieldset{border:1px solid var(--line);border-radius:8px;padding:8px}
.df fieldset label,.simple fieldset label{flex-direction:row;align-items:center;gap:8px;font-size:14px;color:var(--fg)}fieldset input{width:auto}
.row{display:flex;gap:8px;flex-wrap:wrap}.row.end{justify-content:flex-end}.simple{display:flex;flex-direction:column;gap:10px;padding:16px;min-width:min(380px,86vw)}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:var(--fg);color:var(--bg);padding:8px 14px;border-radius:99px;font-size:14px;opacity:0;pointer-events:none;transition:opacity .2s;z-index:20}
#toast.show{opacity:1}.empty{color:var(--mut);font-size:13px;padding:8px}
@media (max-width:860px){aside{position:static;max-height:45vh}}
@media (max-width:640px){
header{position:static;padding:10px 12px;gap:8px}.tabs{width:100%;margin-right:0}.count{width:100%;font-size:13px}header button{flex:1 1 auto}
.banner{display:none}.layout{padding:10px;gap:12px}
.week{grid-template-columns:1fr;overflow:visible}.day{min-height:0}.gal{grid-template-columns:1fr}
.toolbar .wk{margin-left:0;width:100%;justify-content:space-between}
table{display:block;overflow-x:auto}
dialog{width:96vw;max-width:96vw;max-height:92dvh;overflow:auto}.dform,.simple{padding:12px;min-width:0}
.dform video{max-height:50vh;object-fit:contain}
}
@media (pointer:coarse){
button{min-height:44px}.vcard button{min-height:40px;padding:6px 12px}.chip{min-height:48px}
input,textarea{font-size:16px;min-height:44px}fieldset input{min-height:0;width:22px;height:22px}
}
"""

JS = r"""
const TOKEN=(document.querySelector('meta[name=editor-token]')||{}).content||'';
const D=JSON.parse(document.getElementById('data').textContent);
let V=D.videos,SCH=D.schedule,VIEW='week',WEEK=startOfWeek(new Date()),CUR=null;
const $=s=>document.querySelector(s),pad=n=>String(n).padStart(2,'0'),WD=['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'];
const dkey=d=>d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate());
function startOfWeek(d){const x=new Date(d.getFullYear(),d.getMonth(),d.getDate());x.setDate(x.getDate()-((x.getDay()+6)%7));return x}
function addDays(d,n){const x=new Date(d);x.setDate(x.getDate()+n);return x}
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
const when=w=>new Date(w+':00'),fmt=w=>{const[d,t]=w.split('T'),p=d.split('-');return p[2]+'/'+p[1]+' '+t};
const short=n=>n.split(' ')[0].slice(0,3);
const src=id=>'/'+V[id].file+'?v='+V[id].v;
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(toast.h);toast.h=setTimeout(()=>t.classList.remove('show'),3200)}
async function api(body){
  const r=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json','X-Token':TOKEN},body:JSON.stringify(body)});
  const j=await r.json().catch(()=>({}));if(!r.ok||!j.ok)throw new Error(j.error||('erro HTTP '+r.status));
  SCH=j.schedule;V=j.videos;render();return j}
async function run(body,ok){try{const j=await api(body);toast(ok||j.message);return true}catch(e){toast('Erro: '+e.message);return false}}
function state(id){const it=SCH.items[id];if(!it)return'none';if(!V[id]||V[id].status!=='approved')return'bad';return when(it.when)<new Date()?'late':'ok'}
function nextTime(day){const used=Object.values(SCH.items).filter(i=>i.when.startsWith(day)).map(i=>i.when.slice(11));for(const t of['18:00','12:00','21:00','09:00','15:00']){if(!used.includes(t))return t}return'18:00'}
function render(){
  const ids=Object.keys(V),sch=Object.keys(SCH.items).filter(i=>V[i]);
  const queue=ids.filter(i=>V[i].status==='approved'&&!SCH.items[i]);
  const late=sch.filter(i=>state(i)==='late').length,bad=sch.filter(i=>state(i)==='bad').length;
  $('#count').textContent=sch.length+' agendados · '+queue.length+' na fila'+(late?' · '+late+' atrasados':'')+(bad?' · '+bad+' precisam reaprovar':'');
  $('#qcount').textContent='('+queue.length+')';
  $('#queue').innerHTML=queue.length?queue.map(i=>`<article class="vcard" draggable="true" data-id="${esc(i)}"><video muted preload="metadata" playsinline src="${esc(src(i))}#t=0.4"></video><div class="vb"><b>${esc(i)}</b><small>${V[i].duration}s</small><p>${esc(V[i].hook)}</p><button data-open="${esc(i)}">Agendar…</button></div></article>`).join(''):'<div class="empty">Todos os aprovados já têm data.</div>';
  document.querySelectorAll('[data-v]').forEach(b=>b.classList.toggle('on',b.dataset.v===VIEW));
  $('.layout').classList.toggle('wide',VIEW==='gallery');$('#weekNav').style.display=VIEW==='week'?'flex':'none';
  if(VIEW==='week')renderWeek();else if(VIEW==='list')renderList();else renderGallery()}
function chip(i){const it=SCH.items[i],s=state(i);return `<button class="chip ${s==='late'?'past':s==='bad'?'bad':''}" draggable="true" data-id="${esc(i)}" data-open="${esc(i)}" title="${esc(V[i]?V[i].caption:'')}"><time>${it.when.slice(11)}</time><b>${esc(i)}</b><small>${it.networks.map(short).join(' · ')}${s==='bad'?' · reaprovar':''}</small></button>`}
function renderWeek(){
  const today=dkey(new Date());$('#range').textContent=dkey(WEEK).slice(5).split('-').reverse().join('/')+' – '+dkey(addDays(WEEK,6)).slice(5).split('-').reverse().join('/');
  let h='';for(let k=0;k<7;k++){const d=addDays(WEEK,k),key=dkey(d);
    const its=Object.keys(SCH.items).filter(i=>V[i]&&SCH.items[i].when.startsWith(key)).sort((a,b)=>SCH.items[a].when.localeCompare(SCH.items[b].when));
    h+=`<div class="day ${key===today?'today':''}" data-day="${key}"><h3>${WD[k]} ${pad(d.getDate())}/${pad(d.getMonth()+1)}<small>${its.length||''}</small></h3>${its.map(chip).join('')}</div>`}
  $('#cal').innerHTML='<div class="week">'+h+'</div>'}
function renderList(){
  const its=Object.keys(SCH.items).filter(i=>V[i]).sort((a,b)=>SCH.items[a].when.localeCompare(SCH.items[b].when));
  const lab={ok:'<span class="badge ok">agendado</span>',late:'<span class="badge late">data passou (nada foi publicado)</span>',bad:'<span class="badge bad">precisa reaprovar</span>'};
  $('#cal').innerHTML=its.length?`<table><thead><tr><th>Quando</th><th>ID</th><th>Texto</th><th>Redes</th><th>Estado</th></tr></thead><tbody>${its.map(i=>`<tr class="trow" data-open="${esc(i)}"><td>${fmt(SCH.items[i].when)}</td><td><b>${esc(i)}</b></td><td>${esc(V[i].hook)}</td><td>${esc(SCH.items[i].networks.join(', '))}</td><td>${lab[state(i)]}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">Nada agendado ainda. Arraste um vídeo da fila para um dia, ou use “Distribuir automaticamente”.</div>'}
function renderGallery(){
  const ids=Object.keys(V).filter(i=>V[i].status==='approved'||SCH.items[i]);
  $('#cal').innerHTML='<div class="gal">'+ids.map(i=>{const s=state(i),it=SCH.items[i];return `<article class="gcard"><video controls preload="metadata" playsinline src="${esc(src(i))}#t=0.4"></video><div class="gb"><b style="font:600 12px ui-monospace,Consolas,monospace">${esc(i)} · ${V[i].duration}s</b><div>${esc(V[i].hook)}</div>${it?`<span class="badge ${s==='ok'?'ok':s==='late'?'late':'bad'}">${fmt(it.when)} · ${esc(it.networks.join(', '))}</span>`:'<span class="badge">sem data</span>'}<div class="row"><button data-open="${esc(i)}">${it?'Editar agenda':'Agendar…'}</button><button data-copy="${esc(i)}">Copiar legenda</button></div></div></article>`}).join('')+'</div>'}
function openDlg(id){
  if(!V[id])return;CUR=id;const it=SCH.items[id],dv=$('#dv');
  dv.src=src(id)+'#t=0.4';$('#dtitle').textContent=id+' · '+V[id].duration+'s';$('#dhook').textContent=V[id].hook;$('#dcap').value=V[id].caption;
  const tomorrow=dkey(addDays(new Date(),1));$('#dwhen').value=it?it.when:tomorrow+'T'+nextTime(tomorrow);
  $('#dnets').innerHTML='<legend>Redes</legend>'+SCH.settings.networks.map(n=>`<label><input type="checkbox" value="${esc(n)}" ${(!it||it.networks.includes(n))?'checked':''}> ${esc(n)}</label>`).join('');
  $('#drem').style.display=it?'':'none';$('#dmsg').textContent=V[id].status!=='approved'?'Este vídeo não está aprovado: reaprove na Revisão antes de agendar.':'';
  $('#dlg').showModal()}
async function copyCap(id){try{await navigator.clipboard.writeText(V[id].caption);toast('Legenda copiada')}catch(e){toast('Não consegui copiar')}}
document.addEventListener('click',e=>{
  const o=e.target.closest('[data-open]');if(o){openDlg(o.dataset.open);return}
  const c=e.target.closest('[data-copy]');if(c){copyCap(c.dataset.copy);return}
  const v=e.target.closest('[data-v]');if(v){VIEW=v.dataset.v;render()}});
$('#prev').onclick=()=>{WEEK=addDays(WEEK,-7);render()};$('#next').onclick=()=>{WEEK=addDays(WEEK,7);render()};$('#today').onclick=()=>{WEEK=startOfWeek(new Date());render()};
$('#dcopy').onclick=()=>CUR&&copyCap(CUR);
$('#dlg').addEventListener('close',()=>$('#dv').pause());
$('#dsave').onclick=async()=>{if(!CUR)return;const nets=[...document.querySelectorAll('#dnets input:checked')].map(x=>x.value);
  if(!$('#dwhen').value){toast('Escolha data e hora');return}
  if(await run({action:'set',id:CUR,when:$('#dwhen').value,networks:nets},'Agendado: '+CUR+' em '+fmt($('#dwhen').value)))$('#dlg').close()};
$('#drem').onclick=async()=>{if(CUR&&await run({action:'set',id:CUR,when:null},'Removido da agenda'))$('#dlg').close()};
/* arrastar e soltar: fila -> dia, ou dia -> dia */
document.addEventListener('dragstart',e=>{const t=e.target.closest('[data-id]');if(t){e.dataTransfer.setData('text/plain',t.dataset.id);e.dataTransfer.effectAllowed='move'}});
document.addEventListener('dragover',e=>{const d=e.target.closest('.day');if(d){e.preventDefault();d.classList.add('over')}});
document.addEventListener('dragleave',e=>{const d=e.target.closest('.day');if(d)d.classList.remove('over')});
document.addEventListener('drop',async e=>{const d=e.target.closest('.day');if(!d)return;e.preventDefault();d.classList.remove('over');
  const id=e.dataTransfer.getData('text/plain');if(!V[id])return;const it=SCH.items[id],day=d.dataset.day;
  await run({action:'set',id,when:day+'T'+(it?it.when.slice(11):nextTime(day)),networks:it?it.networks:SCH.settings.networks},'Movido: '+id+' → '+day.split('-').reverse().join('/'))});
/* distribuir automaticamente */
$('#btnAuto').onclick=()=>{$('#aStart').value=dkey(addDays(new Date(),1));
  $('#aNets').innerHTML='<legend>Redes</legend>'+SCH.settings.networks.map(n=>`<label><input type="checkbox" value="${esc(n)}" checked> ${esc(n)}</label>`).join('');$('#dlgAuto').showModal()};
$('#aGo').onclick=async()=>{const times=$('#aTimes').value.split(',').map(x=>x.trim()).filter(Boolean),nets=[...document.querySelectorAll('#aNets input:checked')].map(x=>x.value);
  if(await run({action:'auto',start:$('#aStart').value,per_day:+$('#aPer').value,times,networks:nets}))$('#dlgAuto').close()};
$('#btnNets').onclick=()=>{$('#nList').value=SCH.settings.networks.join('\n');$('#dlgNets').showModal()};
$('#nGo').onclick=async()=>{if(await run({action:'networks',networks:$('#nList').value.split('\n')}))$('#dlgNets').close()};
const qp=new URLSearchParams(location.search);if(qp.get('view'))VIEW=qp.get('view');
render();if(qp.get('open'))openDlg(qp.get('open'));
"""

TEMPLATE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="editor-token" content="__TOKEN__">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Agenda GTA VI</title><style>__CSS__</style></head><body>
<header><h1>Agenda</h1><nav class="tabs"><a href="/">Revisão</a><a class="on" href="/agenda">Agenda</a></nav>
<span class="count" id="count"></span><button id="btnAuto">Distribuir automaticamente</button><button id="btnNets">Redes…</button></header>
<div class="banner">Aqui você só organiza: <b>nada é publicado automaticamente</b> (nenhuma rede está conectada). Vídeos editados ou desaprovados na Revisão saem da fila e precisam ser reaprovados.</div>
<div class="layout">
<aside><h2>Fila <small id="qcount"></small></h2><div id="queue"></div></aside>
<section><div class="toolbar"><div class="seg"><button data-v="week">Semana</button><button data-v="list">Lista</button><button data-v="gallery">Prontos</button></div>
<div class="wk" id="weekNav"><button id="prev" aria-label="Semana anterior">←</button><b id="range"></b><button id="next" aria-label="Próxima semana">→</button><button id="today">Hoje</button></div></div>
<div id="cal"></div></section></div>
<dialog id="dlg"><form method="dialog" class="dform"><video id="dv" controls playsinline preload="metadata"></video><div class="df">
<h3 id="dtitle"></h3><div class="muted" id="dhook"></div><label>Legenda do post<textarea id="dcap" readonly rows="5"></textarea></label>
<button type="button" id="dcopy">Copiar legenda</button><label>Data e hora<input type="datetime-local" id="dwhen"></label><fieldset id="dnets"></fieldset>
<div class="row"><button type="button" class="primary" id="dsave">Salvar na agenda</button><button type="button" id="drem">Remover da agenda</button><button value="close">Fechar</button></div>
<div class="muted" id="dmsg"></div></div></form></dialog>
<dialog id="dlgAuto"><form method="dialog" class="simple"><h3>Distribuir automaticamente</h3><div class="muted">Agenda os aprovados que ainda não têm data, na ordem da fila.</div>
<label>Primeiro dia<input type="date" id="aStart"></label><label>Vídeos por dia (1 a 5)<input type="number" id="aPer" min="1" max="5" value="2"></label>
<label>Horários (separados por vírgula)<input id="aTimes" value="12:00, 18:00"></label><fieldset id="aNets"></fieldset>
<div class="row end"><button value="close">Cancelar</button><button type="button" class="primary" id="aGo">Distribuir</button></div></form></dialog>
<dialog id="dlgNets"><form method="dialog" class="simple"><h3>Redes</h3><div class="muted">Uma por linha (até 8). Servem só para organizar a agenda.</div>
<textarea id="nList" rows="6"></textarea><div class="row end"><button value="close">Cancelar</button><button type="button" class="primary" id="nGo">Salvar</button></div></form></dialog>
<div id="toast" role="status"></div>
<script id="data" type="application/json">__DATA__</script><script>__JS__</script></body></html>"""


def build_page(queue, sched, token):
    sched = norm_sched(sched)
    blob = json.dumps({"videos": videos_view(queue, sched), "schedule": sched}, ensure_ascii=False).replace("</", "<\\/")
    return (TEMPLATE.replace("__TOKEN__", token).replace("__CSS__", CSS).replace("__JS__", JS).replace("__DATA__", blob))
