"""Busca videos recentes de GTA 6 (licenca Creative Commons) e descarta os com narracao.

Uso: python search.py [--queries ...] [--days 90] [--min-dur 60] [--max-dur 3600]
                      [--min-views 200] [--limit 20]
                      [--cookies-browser firefox|chrome|edge] [--cookies-file cookies.txt]
                      [--no-speech-check]
Saida: candidates.json (apenas videos aprovados) e rejected.json (com o motivo).
"""
import argparse, json, tempfile, datetime as dt
from pathlib import Path
from urllib.parse import quote_plus
import yt_dlp
from yt_dlp.utils import download_range_func

DEFAULT_QUERIES = [
    "GTA 6 gameplay", "GTA 6 gameplay no commentary", "GTA VI gameplay", "GTA 6 gameplay 4K",
    "GTA 6 Vice City gameplay", "GTA 6 Leonida", "GTA 6 free roam", "GTA 6 police chase",
    "GTA 6 map exploration", "GTA 6 graphics", "GTA 6 physics", "GTA 6 mission",
    "GTA 6 ambient", "GTA 6 cinematic", "GTA 6 drive", "GTA 6 walkthrough no commentary",
]
# titulos com estes termos tendem a ter narracao/opiniao -> descartados antes de baixar audio
EXCLUDE = ("reaction", "react", "review", "explained", "theory", "theories", "breakdown",
           "analysis", "rumor", "leak", "news", "update", "podcast", "tier list", "ranking",
           "trailer 3", "trailer 2", "trailer 1", "guide", "settings", "tutorial", "how to",
           "commentary")
EXCLUDE_OK = ("no commentary", "without commentary", "sem comentário", "sem narração")

WINDOW_S = 30           # tamanho de cada amostra de audio
MAX_WORDS_PER_WINDOW = 12  # acima disso a amostra conta como "tem fala"
_whisper = None


def has_narration(ydl_opts, vid, duration):
    """Baixa 2 janelas de 30 s (em ~25% e ~60% do video) e transcreve com Whisper+VAD."""
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
    words_total = 0
    for frac in (0.25, 0.60):
        start = int(duration * frac)
        with tempfile.TemporaryDirectory() as tmp:
            opts = {**ydl_opts, "format": "bestaudio/best", "outtmpl": f"{tmp}/a.%(ext)s",
                    "download_ranges": download_range_func(None, [(start, start + WINDOW_S)]),
                    "force_keyframes_at_cuts": True, "noprogress": True}
            with yt_dlp.YoutubeDL(opts) as d:
                d.download([f"https://www.youtube.com/watch?v={vid}"])
            files = list(Path(tmp).glob("a.*"))
            if not files:
                continue
            segs, _ = _whisper.transcribe(str(files[0]), vad_filter=True, beam_size=1)
            words_total += sum(len(s.text.split()) for s in segs)
    return words_total > MAX_WORDS_PER_WINDOW, words_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES)
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--min-dur", type=int, default=60)
    ap.add_argument("--max-dur", type=int, default=3600)
    ap.add_argument("--min-views", type=int, default=200)
    ap.add_argument("--limit", type=int, default=20, help="resultados por busca")
    ap.add_argument("--cookies-browser", help="firefox, chrome, edge... (videos com restricao de idade)")
    ap.add_argument("--cookies-file", help="cookies.txt no formato Netscape")
    ap.add_argument("--no-speech-check", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).parent / "candidates.json"))
    a = ap.parse_args()

    base = {"quiet": True, "no_warnings": True, "ignoreerrors": True}
    if a.cookies_browser:
        base["cookiesfrombrowser"] = (a.cookies_browser,)
    if a.cookies_file:
        base["cookiefile"] = a.cookies_file

    cutoff = dt.date.today() - dt.timedelta(days=a.days)
    flat = {**base, "skip_download": True, "extract_flat": True, "playlistend": a.limit}
    full = {**base, "skip_download": True}
    seen, found, rejected = set(), [], []

    def reject(e, why):
        rejected.append({"id": e["id"], "title": e.get("title"), "why": why})

    with yt_dlp.YoutubeDL(flat) as ydl_flat, yt_dlp.YoutubeDL(full) as ydl:
        for q in a.queries:
            # sp=CAISBBABYAE%3D => ordena por data de upload, so videos, so licenca Creative Commons
            url = f"https://www.youtube.com/results?search_query={quote_plus(q)}&sp=CAISBBABYAE%253D"
            listing = ydl_flat.extract_info(url, download=False)
            for item in (listing or {}).get("entries", []) or []:
                if not item or item["id"] in seen:
                    continue
                seen.add(item["id"])
                e = ydl.extract_info(f"https://www.youtube.com/watch?v={item['id']}", download=False)
                if not e:
                    rejected.append({"id": item["id"], "title": item.get("title"), "why": "metadata indisponivel (idade/privado?)"})
                    continue
                ud = e.get("upload_date")
                date = dt.datetime.strptime(ud, "%Y%m%d").date() if ud else None
                dur, views = e.get("duration") or 0, e.get("view_count") or 0
                t = (e.get("title") or "").lower()
                if any(w in t for w in EXCLUDE) and not any(ok in t for ok in EXCLUDE_OK):
                    reject(e, "titulo sugere narracao/opiniao"); continue
                if "creative commons" not in (e.get("license") or "").lower():
                    reject(e, "licenca nao e CC"); continue
                if date and date < cutoff:
                    reject(e, "antigo"); continue
                if not (a.min_dur <= dur <= a.max_dur) or views < a.min_views:
                    reject(e, "duracao/views fora do filtro"); continue
                words = None
                if not a.no_speech_check:
                    talks, words = has_narration(base, e["id"], dur)
                    if talks:
                        reject(e, f"narracao detectada ({words} palavras em 2x{WINDOW_S}s)"); continue
                found.append({
                    "id": e["id"], "title": e.get("title"), "channel": e.get("channel"),
                    "url": e.get("webpage_url"), "upload_date": str(date), "duration": dur,
                    "views": views, "license": e.get("license"), "words_sampled": words, "query": q,
                })

    found.sort(key=lambda x: x["views"], reverse=True)
    Path(a.out).write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(a.out).with_name("rejected.json").write_text(json.dumps(rejected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(found)} aprovados, {len(rejected)} rejeitados -> {a.out}")
    for f in found[:15]:
        print(f"{f['views']:>9,}v  {f['duration']//60:>3}min  {f['upload_date']}  {f['channel']}: {f['title'][:70]}")


if __name__ == "__main__":
    main()
