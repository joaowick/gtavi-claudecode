"""Render a clip in the 'profile header' template (black background, round avatar + name + handle,
Portuguese text, video window below, credit label). Uses scripts/profile_render.py and profile/.

  python scripts/profile_clip.py jobs/<id> --pick 4 --text "A polícia rastreia carro roubado 🚔"

Profile (name, handle, avatar): profile/profile.json. Output: <job>/edits/clip_<n>_profile.mp4 (720x1280).
"""
import argparse, json, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_json, tool
import profile_render

PROFILE = Path(__file__).parent.parent / "profile"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--pick", type=int, help="candidate number from candidates.md")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--cut", help="keep only these parts, seconds relative to the clip start, e.g. 0-11,28.5-39.8")
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
    n = a.pick or int(s0)

    pr = json.loads((PROFILE / "profile.json").read_text(encoding="utf-8"))
    chan = cand["info"].get("uploader_id") or "@" + cand["info"].get("channel", "")
    tmp = job / "edits" / f"_raw_{n}.mp4"
    tmp.parent.mkdir(exist_ok=True)
    ff = [tool("ffmpeg"), "-v", "error", "-y", "-ss", str(s0), "-to", str(e0), "-i", str(src)]
    if a.cut:
        segs = [tuple(float(v) for v in x.split("-")) for x in a.cut.split(",")]
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
        crop=tuple(int(v) for v in a.crop.split(":")) if a.crop else None)
    tmp.unlink(missing_ok=True)
    print(out)


if __name__ == "__main__":
    main()
