"""Render a clip in the 'profile header' template (blurred background, round avatar + name + handle,
Portuguese text, video window below, credit label, optional PT/EN subtitles in GTA VI style). Uses scripts/profile_render.py and profile/.

  python scripts/profile_clip.py jobs/<id> --pick 4 --text "A polícia rastreia carro roubado 🚔"

Profile (name, handle, avatar): profile/profile.json. Output: <job>/edits/clip_<n>_profile.mp4 (720x1280).
"""
import argparse, json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_json, tool
import profile_render
from cut import clean
from translate import translator

PROFILE = Path(__file__).parent.parent / "profile"


def translate_retry(t_en, text, tries=5):
    """tr() swallows errors and returns the input; here we retry with backoff and fail loudly instead."""
    import time
    for i in range(tries):
        try:
            time.sleep(0.4)
            r = (t_en.translate(text) or "").strip()
            if r:
                return r
        except Exception:
            time.sleep(1.5 * (i + 1))
    sys.exit(f"translation failed for: {text!r} (rate limit?). Try again in a minute or use --subs pt.")


def make_subs(words, segs, t_en, max_words=7, known=None, src_en=False):
    """Phrases with times mapped onto the cut timeline. Split on pauses > 0.6 s / end punctuation, long ones
    in chunks of <= max_words; chunks of 1-2 words are merged into a neighbour."""
    out, off = [], 0.0
    for x, y in segs:
        part = [w for w in words if x <= w["s"] < y]
        groups, cur = [], []
        for w in part:
            if cur and (w["s"] - cur[-1]["e"] > 0.6 or cur[-1]["w"][-1:] in ".?!"):
                groups.append(cur); cur = []
            cur.append(w)
        if cur:
            groups.append(cur)
        chunks = []
        for g in groups:
            k = -(-len(g) // max_words)              # balanced split: 11 words -> 6 + 5, not 7 + 4
            size = -(-len(g) // k)
            chunks += [g[i:i + size] for i in range(0, len(g), size)]
        merged = []
        for c in chunks:
            if merged and (len(c) <= 2 or len(merged[-1]) <= 2) and len(merged[-1]) + len(c) <= max_words + 2:
                merged[-1] = merged[-1] + c
            else:
                merged.append(c)
        for ch in merged:
            pt = clean(" ".join(w["w"] for w in ch))
            if src_en:                               # spoken English: main line = Portuguese from `known`, second = original
                en, pt = pt, (known or {}).get(pt) or sys.exit(f"missing Portuguese translation for: {pt!r}")
            else:
                en = (known or {}).get(pt) or (clean(translate_retry(t_en, pt)) if t_en else "")
            a_ = ch[0]["s"] - x + off
            b_ = min(ch[-1]["e"] - x + off + 0.4, y - x + off)
            out.append([max(a_, 0.0), max(b_, a_ + 1.2), pt, en])
        off += y - x
    for i in range(len(out) - 1):                   # no overlap: end before the next phrase starts
        out[i][1] = min(out[i][1], out[i + 1][0])
    return [tuple(o) for o in out if o[1] - o[0] > 0.2]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--pick", type=int, help="candidate number from candidates.md")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--cut", help="keep only these parts, seconds relative to the clip start, e.g. 0-11,28.5-39.8")
    ap.add_argument("--subs", choices=["pt-en", "pt", "off"], default="off",
                    help="burn subtitles under the video: pt-en = Portuguese main + English second line")
    ap.add_argument("--translations", help="JSON {portuguese phrase: english} used before Google Translate; "
                                           "phrases not in it are translated online. --list-phrases prints them.")
    ap.add_argument("--src-lang", choices=["pt", "en"], default="pt",
                    help="spoken language of the source. en: --translations maps English phrase -> Portuguese; "
                         "the Portuguese goes on the main line and the original English below it")
    ap.add_argument("--list-phrases", action="store_true", help="print the subtitle phrases and stop")
    ap.add_argument("--sub-style", choices=["gtavi", "plain"], default="gtavi")
    ap.add_argument("--bg", choices=["black", "blur"], default="blur", help="canvas behind the video")
    ap.add_argument("--label", help="name used in the output file instead of the candidate number")
    ap.add_argument("--queue", action="store_true",
                    help="register the clip in viral/output/queue.json (pending_review) so it shows in the review sheet")
    ap.add_argument("--caption", help="post caption for --queue (default: header text + credit + hashtags)")
    ap.add_argument("--suffix", default="", help="added to the output name, e.g. _short")
    ap.add_argument("--text", required=True, help="header text (Portuguese); emoji allowed")
    ap.add_argument("--credit", help="credit label; default 'Vídeo: @<channel>'")
    ap.add_argument("--bottom", help="optional white pill under the video")
    ap.add_argument("--crop", help="y0:y1 pixel rows to keep (drops facecam/overlays above/below)")
    ap.add_argument("--name")
    ap.add_argument("--handle")
    ap.add_argument("--avatar")
    a = ap.parse_args()

    job = Path(a.job)
    cand = load_json(job / "candidates.json")
    src = job / "source.mp4"
    if a.pick:
        c = next((x for x in cand["candidates"] if x["n"] == a.pick), None)
        if not c:
            sys.exit(f"no candidate {a.pick}")
        s0, e0 = c["start"], c["end"]
    else:
        s0, e0 = a.start, a.end
    if s0 is None or e0 is None:
        sys.exit("give --pick or --start and --end")
    n = a.label or a.pick or int(s0)

    pr = json.loads((PROFILE / "profile.json").read_text(encoding="utf-8"))
    chan = cand["info"].get("uploader_id") or "@" + cand["info"].get("channel", "")
    tmp = job / "edits" / f"_raw_{n}.mp4"
    tmp.parent.mkdir(exist_ok=True)
    segs = [tuple(float(v) for v in x.split("-")) for x in a.cut.split(",")] if a.cut else [(0.0, e0 - s0)]
    subs = None
    if a.subs != "off":
        words = [dict(w=x["w"], s=x["s"] - s0, e=x["e"] - s0) for x in load_json(job / "transcript.json")
                 if s0 <= x["s"] < e0]
        known = load_json(Path(a.translations)) if a.translations else {}
        src_en = a.src_lang == "en"
        need = a.subs == "pt-en" and not a.list_phrases and not src_en
        subs = make_subs(words, segs, translator("en") if need else None, known=known,
                         src_en=src_en and not a.list_phrases)
        if a.list_phrases:
            print(json.dumps([x[2] for x in subs], ensure_ascii=False, indent=1))
            return
    ff = [tool("ffmpeg"), "-v", "error", "-y", "-ss", str(s0), "-to", str(e0), "-i", str(src)]
    if a.cut:
        f = "".join(f"[0:v]trim={x}:{y},setpts=PTS-STARTPTS[v{i}];[0:a]atrim={x}:{y},asetpts=PTS-STARTPTS[a{i}];"
                    for i, (x, y) in enumerate(segs))
        f += "".join(f"[v{i}][a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[v][a]"
        ff += ["-filter_complex", f, "-map", "[v]", "-map", "[a]"]
    subprocess.run(ff + ["-c:v", "libx264", "-crf", "18", "-c:a", "aac", str(tmp)], check=True)
    out = job / "edits" / f"clip_{n}_profile{a.suffix}.mp4"
    profile_render.render(
        tmp, out, name=a.name or pr["name"], handle=a.handle or pr["handle"],
        avatar=Path(a.avatar) if a.avatar else PROFILE / pr["avatar"], text=a.text,
        credit=a.credit or f"Vídeo: {chan}", bottom=a.bottom,
        crop=tuple(int(v) for v in a.crop.split(":")) if a.crop else None, subs=subs, sub_style=a.sub_style, bg=a.bg)
    tmp.unlink(missing_ok=True)
    print(out)
    if a.queue:
        register(out, cand["info"], chan, a)


def register(out, info, chan, a):
    """Copy the clip to viral/output and add it to queue.json as pending_review. Marked custom_render so the
    review editor does not re-render it with the batch layout (that would lose the cut and the subtitles)."""
    import datetime, shutil
    vroot = Path(__file__).parent.parent / "viral" / "output"
    vid = f"yt_{info['id']}_{int(a.start if a.start is not None else a.pick or 0)}"
    qfile = vroot / "queue.json"
    q = json.loads(qfile.read_text(encoding="utf-8")) if qfile.exists() else {}
    if vid in q:
        sys.exit(f"{vid} already in queue.json; remove it first to re-register")
    shutil.copy2(qfile, vroot / f"queue.bak.{datetime.datetime.now():%Y%m%d%H%M%S}.json") if qfile.exists() else None
    shutil.copy2(out, vroot / f"{vid}.mp4")
    tags = "#gta6 #gtavi #grandtheftauto6"
    caption = a.caption or "\n\n".join([a.text, f"Vídeo: {chan} (YouTube)", tags])
    w, h, dur = profile_render.probe(vroot / f"{vid}.mp4")
    q[vid] = {"source": info["webpage_url"], "file": f"{vid}.mp4", "type": "gameplay", "lang": "pt",
              "duration": round(dur, 1), "hook": [a.text], "caption": caption, "original_caption": info.get("title", ""),
              "author": chan, "credit": a.credit or f"Vídeo: {chan}", "caption_translated": False,
              "status": "pending_review", "text_pt": a.text, "hook_pt": [a.text], "caption_pt": caption,
              "custom_render": "scripts/profile_clip.py"}
    qfile.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"queued as {vid} (pending_review)")


if __name__ == "__main__":
    main()
