"""Render a clip in the 'profile header' template (black background, round avatar + name + handle,
Portuguese text, video window below, credit label). Reuses render() from the gta6-viral pipeline.

  python scripts/profile_clip.py jobs/<id> --pick 4 --text "A polícia rastreia carro roubado 🚔"

Template location: --pipeline, or env GTA6VIRAL_PIPELINE, or the default below (the folder with
pipeline.py, profile.json and assets/). Output: <job>/edits/clip_<n>_profile.mp4 (720x1280).
"""
import argparse, importlib.util, json, os, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import load_json, tool

DEFAULT = r"C:\Users\joaot\workspace\gta6-viral\pilot"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--pick", type=int, help="candidate number from candidates.md")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--text", required=True, help="header text (Portuguese); emoji allowed")
    ap.add_argument("--credit", help="credit label; default 'Vídeo: @<channel>'")
    ap.add_argument("--bottom", help="optional white pill under the video")
    ap.add_argument("--crop", help="y0:y1 pixel rows to keep (drops facecam/overlays above/below)")
    ap.add_argument("--name"); ap.add_argument("--handle"); ap.add_argument("--avatar")
    ap.add_argument("--pipeline", default=os.environ.get("GTA6VIRAL_PIPELINE", DEFAULT))
    a = ap.parse_args()

    P = Path(a.pipeline)
    if not (P / "pipeline.py").exists():
        sys.exit(f"template pipeline not found in {P}. Pass --pipeline or set GTA6VIRAL_PIPELINE.")
    spec = importlib.util.spec_from_file_location("gta6_pipeline", P / "pipeline.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

    job = Path(a.job)
    cand = load_json(job / "candidates.json")
    src = job / "source.mp4"
    if a.pick:
        c = next((x for x in cand["candidates"] if x["n"] == a.pick), None)
        if not c: sys.exit(f"no candidate {a.pick}")
        s0, e0 = c["start"], c["end"]
    else:
        s0, e0 = a.start, a.end
    if s0 is None or e0 is None:
        sys.exit("give --pick or --start and --end")
    n = a.pick or int(s0)

    pr = json.loads((P / "profile.json").read_text(encoding="utf-8"))
    chan = cand["info"].get("uploader_id") or "@" + cand["info"].get("channel", "")
    tmp = job / "edits" / f"_raw_{n}.mp4"
    tmp.parent.mkdir(exist_ok=True)
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-ss", str(s0), "-to", str(e0), "-i", str(src),
                    "-c:v", "libx264", "-crf", "18", "-c:a", "aac", str(tmp)], check=True)
    plan = {"type": "gameplay", "hook": [], "trim_end": None,
            "crop": tuple(int(v) for v in a.crop.split(":")) if a.crop else None, "cover": None,
            "bottom_text": a.bottom, "credit": a.credit or f"Vídeo: {chan}",
            "profile": {"name": a.name or pr["name"], "handle": a.handle or pr["handle"],
                        "avatar": Path(a.avatar) if a.avatar else P / pr["avatar"],
                        "text": a.text, "emoji": None}}
    out = job / "edits" / f"clip_{n}_profile.mp4"
    m.render(tmp, plan, [], out)
    tmp.unlink(missing_ok=True)
    print(out)


if __name__ == "__main__":
    main()
