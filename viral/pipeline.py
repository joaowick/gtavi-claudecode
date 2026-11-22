r"""Pipeline em lote: reels -> shorts verticais de GTA VI prontos para revisar.

Uso:
    python pipeline.py reels.txt [--limit 5] [--type gameplay|talk] [--no-llm]
    python pipeline.py input/meu_clipe.mp4          (arquivos locais tambem valem)

reels.txt: um link do Instagram/TikTok/YouTube por linha ('#' comenta a linha).

Decisao automatica por video:
  gameplay (pouca/nenhuma fala)  -> gancho de texto, SEM b-roll (gameplay ja e o visual)
  talk     (podcast/comentario)  -> legendas por palavra + cortes de b-roll de broll/

Saida: output/<id>.mp4 e output/queue.json (legenda + hashtags de cada short, p/ publicar depois).
Com ANTHROPIC_API_KEY (e `pip install anthropic`) o gancho/legenda vem do Claude; sem ela, de regras.
"""
import argparse, json, os, re, subprocess, sys, textwrap
from pathlib import Path

HERE = Path(__file__).parent
PROFILE = HERE.parent / "profile"
sys.path.insert(0, str(HERE.parent / "scripts"))   # python -I nao inclui pastas extras
from profile_render import FONT, probe, esc, font_safe, header_safe, make_header_png, header_filters, credit_filter  # noqa: E402
WORK, OUT, BROLL = HERE / "work", HERE / "output", HERE / "broll"
TALK_WPM = 65            # palavras/min acima disso => conteudo falado. Calibrado em 15 clipes: dialogo de trailer ~55, clipes de streamer ~70; podcast deve ficar em 130+
HASHTAGS = "#gta6 #gtavi #grandtheftauto6"


# ---------- utilidades ----------
def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, **kw)


def detect_window(path, thresh=6.0):
    """Acha as linhas (y0, y1) onde o gameplay se mexe, ignorando texto/perfil parados em volta.
    Devolve None se a imagem ja e tela cheia (janela >= 90% da altura)."""
    import numpy as np
    w0, h0, _ = probe(path)
    k = min(1.0, 720 / w0)                               # analisa em escala reduzida (4K estoura a memoria)
    w, h = int(w0 * k) // 2 * 2, int(h0 * k) // 2 * 2
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps=3,scale={w}:{h},format=gray",
               "-f", "rawvideo", "-"]).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    rows = fr.std(axis=0).mean(axis=1) > thresh        # variacao temporal por linha
    best, start = (0, 0), None
    for y in range(h + 1):
        on = y < h and rows[y]
        if on and start is None:
            start = y
        elif not on and start is not None:
            best = max(best, (start, y), key=lambda r: r[1] - r[0])
            start = None
    if best[1] - best[0] >= 0.9 * h or best[1] - best[0] < 0.1 * h:
        return None
    return int(best[0] / k) + 2, int(best[1] / k) - 2                     # margem p/ nao pegar borda preta


# ---------- 1) obter o video ----------
def fetch(src):
    """Retorna (id, caminho_do_mp4, descricao_original)."""
    if Path(src).exists():
        p = Path(src)
        return p.stem, p, ""
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "merge_output_format": "mp4",
            "outtmpl": str(WORK / "%(id)s" / "src.%(ext)s")}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(src, download=True)
    vid = info["id"]
    return vid, WORK / vid / "src.mp4", info.get("description") or info.get("title") or "", author_of(info)


def author_of(info):
    """Quem postou o video na plataforma de origem (X: uploader_id; Instagram: uploader = username)."""
    ie = (info.get("extractor_key") or "").lower()
    cands = [info.get("uploader"), info.get("uploader_id")] if "instagram" in ie else [info.get("uploader_id"), info.get("channel")]
    h = next((c.lstrip("@") for c in cands if c and re.fullmatch(r"@?[A-Za-z_][\w.]{0,39}", c)), "")   # nome com espaco/id numerico nao serve de @
    return {"handle": f"@{h}" if h else "", "name": info.get("uploader") or "", "platform": ie}


CLIP_BY = re.compile(r"\b(?:clip|video|vídeo|credits?|cr[eé]ditos?|via|source|fonte)\s*(?:by|de|:)?\s*:?\s*\(?\s*(@\w{1,30})", re.I)


def credit_line(author, desc):
    """'Vídeo: @postador' (+ ' · clipe: @autor' se o texto original creditar outra pessoa)."""
    me = author.get("handle", "")
    line = f"Vídeo: {me}" if me else ""
    m = CLIP_BY.search(desc or "")
    if m and m.group(1).lower() != me.lower():
        line += (" · " if line else "") + f"Clipe: {m.group(1)}"
    return line


# ---------- traducao EN -> PT ----------
EN_WORDS = {"the", "and", "is", "of", "to", "in", "this", "that", "for", "with", "on", "it", "was", "are", "has", "have",
            "just", "new", "first", "from", "be", "at", "an", "its", "it's", "you", "we", "will", "not", "no"}
PT_WORDS = {"o", "a", "os", "as", "de", "do", "da", "e", "que", "um", "uma", "para", "com", "em", "não", "nao", "é", "foi", "mais"}


def is_english(text):
    ws = re.findall(r"[a-zA-Z’']+", text.lower())
    if len(ws) < 3:
        return False
    en, pt = sum(w in EN_WORDS for w in ws), sum(w in PT_WORDS for w in ws)
    return en >= 2 and en > pt


def translate_pt(text):
    """EN -> PT-BR. Claude (se houver ANTHROPIC_API_KEY); senao endpoint publico do Google Translate.
    Devolve None se nada funcionou (o chamador mantem o original e sinaliza)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            m = anthropic.Anthropic().messages.create(
                model="claude-haiku-5-5", max_tokens=800,
                messages=[{"role": "user", "content": "Traduza para portugues do Brasil, natural, mantendo nomes proprios, "
                           "numeros e emoji. Responda SOMENTE com a traducao:\n\n" + text}])
            return m.content[0].text.strip()
        except Exception as e:  # noqa: BLE001
            print(f"   (traducao via Claude falhou: {type(e).__name__})")
    try:
        import urllib.parse, urllib.request
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=pt&dt=t&q="
               + urllib.parse.quote(text))
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            return "".join(seg[0] for seg in json.loads(r.read().decode("utf-8"))[0]).strip()
    except Exception as e:  # noqa: BLE001
        print(f"   (traducao indisponivel: {type(e).__name__})")
        return None


# ---------- 2) transcricao ----------
_model = None


def transcribe(path):
    global _model
    import numpy as np
    from faster_whisper import WhisperModel
    if _model is None:
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    raw = run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"]).stdout
    segs, info = _model.transcribe(np.frombuffer(raw, dtype=np.float32), word_timestamps=True, vad_filter=True)
    words = [{"w": w.word.strip(), "s": w.start, "e": w.end} for s in segs for w in (s.words or [])]
    return words, info.language


# ---------- 3) plano: tipo + gancho + legenda ----------
CTA = re.compile(r"\b(follow|subscribe|link in bio|dm us|turn on notifications)\b", re.I)
CREDIT = re.compile(r"\s*(credits?|source|via|posted on)\b", re.I)


def clean_caption(desc):
    """Legenda original -> lista de paragrafos limpos (sem chamada de perfil, credito, emoji, #, @)."""
    paras = []
    for p in re.split(r"\n+", desc):
        if CTA.search(p) or CREDIT.match(p):          # 'FOLLOW @X FOR MORE...' nao e gancho
            continue
        p = re.sub(r"(credits?|posted on ig by)\s*:?.*$", "", p, flags=re.I)   # credito no fim da linha
        p = re.sub(r"https?://\S+", "", p)                                           # links (t.co dos tweets)
        p = re.sub(r"\(?\s*(?:clip|video|vídeo|via|source)\s*(?:by|:)?\s*:?\s*@\w+\s*\)?", "", p, flags=re.I)   # "(Clip: @fulano)"
        p = re.sub(r"[#@]\S+", "", p)
        p = re.sub(r"[^\w\s!?.,'’\-]", "", p, flags=re.U)                  # remove emojis
        p = re.sub(r"\s+", " ", p).strip(" .,-")
        if p:
            paras.append(p)
    return paras


def heuristic_plan(desc, words, dur, author=None):
    wpm = len(words) / max(dur, 1) * 60
    kind = "talk" if wpm >= TALK_WPM else "gameplay"
    paras = clean_caption(desc)
    translated = False
    if paras and is_english(" ".join(paras)):                 # legenda em ingles -> portugues (gancho tambem)
        tr = translate_pt("\n".join(paras))
        if tr:
            paras, translated = [p.strip() for p in tr.split("\n") if p.strip()], True
    credit = credit_line(author or {}, desc)
    first = re.split(r"(?<=[.!?])\s", paras[0])[0] if paras else ""      # gancho = 1a frase do 1o paragrafo
    base = first or ("GTA VI" if kind == "gameplay" else "")
    hook = textwrap.wrap(textwrap.shorten(base.upper(), 60, placeholder="..."), 22)[:3]
    body = "\n\n".join(paras + ([credit] if credit else []))
    return {"type": kind, "hook": hook, "caption": (body + "\n\n" + HASHTAGS).strip(), "credit": credit,
            "lead": textwrap.shorten(first or "GTA VI", 110, placeholder="..."), "translated": translated}


def llm_plan(desc, words, dur, fallback):
    """Pede ao Claude gancho/legenda. Qualquer falha cai no plano por regras."""
    try:
        import anthropic
        client = anthropic.Anthropic()
        transcript = " ".join(w["w"] for w in words)[:3000]
        msg = client.messages.create(
            model="claude-haiku-5-5", max_tokens=400,
            messages=[{"role": "user", "content":
                f"Short vertical sobre GTA VI. Tipo detectado: {fallback['type']}. Duracao {dur:.0f}s.\n"
                f"Legenda original: {desc[:500]}\nTranscricao: {transcript or '(sem fala)'}\n\n"
                'Responda SOMENTE JSON: {"hook":["linha1","linha2"],"caption":"legenda do post com hashtags"}. '
                "hook: ate 3 linhas de ate 22 caracteres, MAIUSCULAS, chamativo, sem inventar fatos."}])
        data = json.loads(re.search(r"\{.*\}", msg.content[0].text, re.S).group(0))
        cap = data["caption"]
        if fallback.get("credit") and fallback["credit"] not in cap:      # crédito nunca se perde
            cap = cap.replace(HASHTAGS, "").rstrip() + "\n\n" + fallback["credit"] + "\n\n" + HASHTAGS
        return {**fallback, "hook": [l.upper() for l in data["hook"][:3]], "caption": cap}
    except Exception as e:  # noqa: BLE001 - falha do LLM nunca derruba o lote
        print(f"   (LLM indisponivel, usando regras: {type(e).__name__})")
        return fallback


# ---------- 4) renderizacao ----------
def caption_chunks(words, n=3):
    for i in range(0, len(words), n):
        g = words[i:i + n]
        yield " ".join(x["w"] for x in g), g[0]["s"], g[-1]["e"]


def plan_broll(words, dur, clips):
    """Cortes de 3 s a cada ~8 s, comecando depois do gancho; clips em rodizio."""
    if not clips:
        return []
    cuts, t, k = [], 5.0, 0
    while t + 3 <= dur - 1:
        clip = clips[k % len(clips)]
        _, _, cdur = probe(clip)
        # pula 5 s do inicio (cartao ESRB) e 6 s do fim (logo); avanca 4 s a cada reuso do clipe
        span = max(cdur - 5 - 6 - 3, 0)
        ini = 5 + ((4.0 * (k // len(clips))) % span if span else 0)
        cuts.append((clip, t, 3.0, ini))
        t, k = t + 8.0, k + 1
    return cuts


def render(src, plan, words, out):
    w, h, dur = probe(src)
    dur = min(dur, plan.get("trim_end") or dur)
    parts, inputs = [], ["-i", str(src)]
    vin, ratio = "[0:v]", w / h
    if plan.get("cover"):  # tarja preta (com texto opcional) sobre texto gravado no video de origem
        chain = []
        for c in plan["cover"]:
            chain.append(f"drawbox=x={c['x']}:y={c['y']}:w={c['w']}:h={c['h']}:color={c.get('color', 'black')}:t=fill")
            tl, sz = c.get("text", []), c.get("size", 64)
            top = c["y"] + (c["h"] - len(tl) * sz * 1.25) / 2
            for i, line in enumerate(tl):
                chain.append(f"drawtext=fontfile='{FONT}':text='{esc(line)}':fontcolor={c.get('fontcolor', 'white')}:fontsize={sz}:"
                             f"x='{c['x']}+({c['w']}-text_w)/2':y={top + i * sz * 1.25:.0f}")
        parts.append(f"[0:v]{','.join(chain)}[cv]")
        vin = "[cv]"
    if plan.get("crop"):   # recorta so a janela do gameplay (tira texto/perfil do reel de origem)
        y0, y1 = plan["crop"]
        parts.append(f"{vin}crop=iw:{y1 - y0}:0:{y0}[s]")
        vin, ratio = "[s]", w / (y1 - y0)
    prof = plan.get("profile")
    if prof:
        # layout "como o original": fundo preto, cabecalho (avatar redondo + nome + @) + texto, janela do video abaixo
        txt = prof["text"] + (" " + prof["emoji"] if prof.get("emoji") else "")   # emoji_pt = emoji no fim do texto
        tpng, nlines = make_header_png(txt)
        cw, ch = (w, plan["crop"][1] - plan["crop"][0]) if plan.get("crop") else (w, h)
        inputs += ["-i", str(prof["avatar"]), "-i", str(tpng)]
        ai = len(inputs) // 2 - 2
        hparts, last, win_y, fw, fh, fx = header_filters(vin, dur, cw, ch, nlines, ai, ai + 1, prof["name"], prof["handle"],
                                                         plan.get("bottom_text"))
        parts += hparts
    else:
        if abs(ratio - 9 / 16) < 0.02:
            parts.append(f"{vin}scale=720:1280,setsar=1[m]")
        else:  # horizontal/janela: video centralizado sobre fundo desfocado
            parts.append(f"{vin}split[a][c];[a]scale=720:1280:force_original_aspect_ratio=increase,"
                         "crop=720:1280,boxblur=25:5[bg];[c]scale=720:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[m]")
        last = "m"
    if plan["type"] == "talk":
        for i, (clip, at, d, ini) in enumerate(plan_broll(words, dur, sorted(BROLL.glob("*.mp4")))):
            inputs += ["-i", str(clip)]
            n = len(inputs) // 2 - 1
            parts.append(f"[{n}:v]trim={ini}:{ini + d},setpts=PTS-STARTPTS+{at}/TB,"
                         f"crop='min(iw,ih*9/16)':ih,scale=720:1280,setsar=1[b{i}]")
            parts.append(f"[{last}][b{i}]overlay=enable='between(t,{at},{at + d})':eof_action=pass[o{i}]")
            last = f"o{i}"
    for i, line in enumerate([] if prof else plan["hook"]):   # com cabecalho, o texto ja esta no cabecalho
        parts.append(f"[{last}]drawtext=fontfile='{FONT}':text='{esc(line)}':fontcolor=white:fontsize=54:"
                     f"borderw=6:bordercolor=black:x=(w-text_w)/2:y=h*0.10+{i}*72:enable='between(t,0,3.5)'[h{i}]")
        last = f"h{i}"
    if plan.get("credit"):   # selo discreto de credito ao autor original, durante o video todo
        cy = f"{win_y + 12}" if prof else "h*0.93"
        cx = f"{fx + 14}" if prof else "(w-text_w)/2"
        parts.append(f"[{last}]drawtext=fontfile='{FONT}':text='{esc(font_safe(plan['credit']))}':fontcolor=white:fontsize=26:"
                     f"box=1:boxcolor=black@0.55:boxborderw=8:x={cx}:y={cy}[cr]")
        last = "cr"
    if plan["type"] == "talk":
        for i, (txt, s, e) in enumerate(caption_chunks(words)):
            parts.append(f"[{last}]drawtext=fontfile='{FONT}':text='{esc(txt.upper())}':fontcolor=yellow:fontsize=60:"
                         f"borderw=6:bordercolor=black:x=(w-text_w)/2:y=h*0.72:enable='between(t,{s:.2f},{e:.2f})'[c{i}]")
            last = f"c{i}"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(parts),
         "-map", f"[{last}]", "-map", "0:a?", "-c:v", "libx264", "-crf", "20", "-preset", "fast",
         "-c:a", "aac", "-shortest", *(["-t", str(plan["trim_end"])] if plan.get("trim_end") else []),
         str(out)])


def rebuild(vid, item, out=None):
    """Refaz o short de um item do queue.json usando so o que esta salvo nele.
    Reaproveita o recorte ja calculado (item["crop"]); se nunca houve, detecta uma vez e guarda."""
    if item.get("custom_render"):
        raise ValueError(f"este clipe foi renderizado por {item['custom_render']} (cortes e legendas); "
                         "refaca por la, nao pelo editor")
    src = WORK / vid / "src.mp4"
    words = transcribe(src)[0] if item["type"] == "talk" else []
    if "crop" not in item:
        old = (item.get("fixes_applied") or {}).get("crop", "?")
        if old != "?":
            item["crop"] = old                      # itens refeitos antes do editor: mantem o recorte
        else:
            item["crop"] = None if item.get("no_crop") else detect_window(src)
    crop = tuple(item["crop"]) if item["crop"] else None
    item["crop"] = list(crop) if crop else None
    plan = {"type": item["type"], "hook": item.get("hook_pt") or item["hook"], "trim_end": item.get("trim_end"),
            "crop": crop, "cover": item.get("cover"), "bottom_text": item.get("bottom_text_pt"),
            "credit": item.get("credit")}
    if item.get("text_pt"):                          # cabecalho de perfil com o texto em portugues
        pr = json.loads((PROFILE / "profile.json").read_text(encoding="utf-8"))
        pr.update(item.get("profile") or {})
        plan["profile"] = {"name": pr["name"], "handle": pr["handle"], "avatar": PROFILE / pr["avatar"],
                           "text": item["text_pt"], "emoji": item.get("emoji_pt")}
    render(src, plan, words, out or OUT / item["file"])
    item["fixes_applied"] = {"crop": item["crop"], "trim_end": plan["trim_end"],
                             "profile_header": bool(plan.get("profile")), "lang": "pt"}
    return plan


# ---------- orquestracao ----------
def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # notas com emoji nao derrubam o print
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", help="reels.txt ou links/arquivos")
    ap.add_argument("--ids", nargs="*", default=[], help="com --redo-fix: refaz tambem estes ids (ex.: aprovados)")
    ap.add_argument("--redo-fix", action="store_true",
                    help="refaz os itens de queue.json com status needs_fix (recorte automatico da janela + trim_end)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--type", choices=["gameplay", "talk"], help="forca o tipo (ignora a deteccao)")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()

    srcs, hint = [], {}              # hint: link -> @perfil do comentario "# @perfil" acima dele (Instagram nao entrega o @ via yt-dlp)
    for s in a.sources:
        p = Path(s)
        if p.suffix == ".txt" and p.exists():
            cur = ""
            for l in p.read_text(encoding="utf-8").splitlines():
                l = l.strip()
                if l.startswith("#"):
                    m = re.match(r"#\s*(@\w[\w.]*)", l)
                    cur = m.group(1) if m else cur
                elif l:
                    srcs.append(l); hint[l] = cur
        else:
            srcs.append(s)
    if a.limit:
        srcs = srcs[:a.limit]

    WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
    qfile = OUT / "queue.json"
    queue = json.loads(qfile.read_text(encoding="utf-8")) if qfile.exists() else {}
    use_llm = not a.no_llm and bool(os.environ.get("ANTHROPIC_API_KEY"))

    if a.redo_fix:
        for vid, item in queue.items():
            if item.get("status") != "needs_fix" and vid not in a.ids:
                continue
            print(f"[fix] {vid}: {item.get('review_note', '')}")
            try:
                plan = rebuild(vid, item)
                item["status"] = "pending_review"       # volta p/ nova revisao
                print(f"   ok: crop={plan['crop']} trim_end={plan['trim_end']}")
            except Exception as e:  # noqa: BLE001
                print(f"   FALHOU: {type(e).__name__}: {str(e)[:200]}")
        qfile.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    if not srcs:
        ap.error("informe reels.txt/links ou use --redo-fix")

    ok = fail = 0
    for n, src in enumerate(srcs, 1):
        print(f"[{n}/{len(srcs)}] {src}")
        try:
            vid, path, desc, author = fetch(src)
            if not author["handle"] and hint.get(src):
                author["handle"] = hint[src]
            if vid in queue and (OUT / f"{vid}.mp4").exists():
                print("   ja processado, pulando"); continue
            words, lang = transcribe(path)
            _, _, dur = probe(path)
            plan = heuristic_plan(desc, words, dur, author)
            if a.type:
                plan["type"] = a.type
            if use_llm:
                plan = llm_plan(desc, words, dur, plan)
            item = {"source": src, "file": f"{vid}.mp4", "type": plan["type"], "lang": lang,
                    "duration": round(dur, 1), "hook": plan["hook"], "caption": plan["caption"],
                    "original_caption": desc, "author": author, "credit": plan.get("credit", ""),
                    "caption_translated": plan.get("translated", False), "status": "pending_review",
                    "text_pt": plan["lead"], "caption_pt": plan["caption"]}   # sempre com o perfil (profile.json) no cabecalho
            rebuild(vid, item)
            queue[vid] = item
            qfile.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"   ok: {plan['type']} | gancho: {' / '.join(plan['hook'])} | {len(words)} palavras")
            ok += 1
        except Exception as e:  # noqa: BLE001 - um video ruim nao derruba o lote
            print(f"   FALHOU: {type(e).__name__}: {str(e)[:200]}")
            fail += 1
    print(f"\nconcluido: {ok} ok, {fail} falhas -> {OUT}")


if __name__ == "__main__":
    main()
