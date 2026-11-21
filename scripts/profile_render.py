"""Self-contained renderer for the profile-header template (ported from the gta6-viral pipeline).
Black 720x1280 canvas: round avatar + name + @handle, wrapped text (emoji in colour), video window
below, optional white pill and credit label."""
import json, re, subprocess, tempfile, zlib
from pathlib import Path

FONT = r"C\:/Windows/Fonts/arialbd.ttf"       # ffmpeg drawtext
BOLD_FONT = r"C:\Windows\Fonts\arialbd.ttf"   # Pillow
EMOJI_FONT = r"C:\Windows\Fonts\seguiemj.ttf"


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", str(path)],
                       check=True, capture_output=True)
    j = json.loads(r.stdout)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


def esc(s):
    return (s.replace("\\", "\\\\").replace("'", "’").replace(":", r"\:").replace("%", r"\%").replace(",", r"\,"))


def font_safe(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s!?.,'\u2019\x22\u201c\u201d:;()%/@\-]", "", s, flags=re.U)).strip()


def header_safe(s):
    keep = re.sub(r"[^\w\s!?.,'\u2019\x22\u201c\u201d:;()%/@\-\u2190-\U0010ffff\ufe0f\u200d]", "", s, flags=re.U)
    return re.sub(r"\s+", " ", keep).strip()


def is_emoji_char(ch):
    return ord(ch) >= 0x2190 or ord(ch) in (0xFE0F, 0x200D)


def text_png(text, path, size=40, max_w=648, line_h=54):
    from PIL import Image, ImageDraw, ImageFont
    tf, ef = ImageFont.truetype(BOLD_FONT, size), ImageFont.truetype(EMOJI_FONT, size)

    def runs(s):
        out = []
        for ch in s:
            f = ef if is_emoji_char(ch) else tf
            if out and out[-1][1] is f:
                out[-1][0] += ch
            else:
                out.append([ch, f])
        return out

    def width(s):
        return sum(f.getlength(x) for x, f in runs(s))

    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word).strip()
        if cur and width(trial) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    im = Image.new("RGBA", (max_w + 72, line_h * max(len(lines), 1) + 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        x, base = 0, i * line_h + 40
        for x_txt, f in runs(ln):
            d.text((x, base), x_txt, font=f, fill=(255, 255, 255, 255), anchor="ls", embedded_color=(f is ef))
            x += f.getlength(x_txt)
    im.save(path)
    return len(lines)


def render(src, out, *, name, handle, avatar, text, credit=None, bottom=None, crop=None):
    """crop = (y0, y1) pixel rows of the source to keep."""
    w, h, dur = probe(src)
    cw, ch = (w, crop[1] - crop[0]) if crop else (w, h)
    tpng = Path(tempfile.gettempdir()) / f"hdr_{zlib.crc32(text.encode('utf-8')):08x}.png"
    nlines = text_png(header_safe(text), tpng)
    win_y = 215 + nlines * 54 + 20
    avail = 1280 - win_y - (110 if bottom else 20)
    sc = min(720 / cw, avail / ch)
    fw, fh = int(cw * sc) // 2 * 2, int(ch * sc) // 2 * 2
    fx = (720 - fw) // 2
    pre = f"[0:v]crop=iw:{crop[1] - crop[0]}:0:{crop[0]}[s];[s]" if crop else "[0:v]"
    parts = [
        f"color=c=black:s=720x1280:d={dur}[bg0]",
        f"{pre}scale={fw}:{fh},setsar=1[fg]",
        f"[bg0][fg]overlay={fx}:{win_y}[m0]",
        "[1:v]scale=96:96,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(lte(hypot(X-48,Y-48),48),255,0)'[av]",
        "[m0][av]overlay=36:60[m1]",
        f"[m1]drawtext=fontfile='{FONT}':text='{esc(name)}':fontcolor=white:fontsize=38:x=150:y=68[m2]",
        f"[m2]drawtext=fontfile='{FONT}':text='{esc(handle)}':fontcolor=0x9aa3b2:fontsize=30:x=150:y=114[m3]",
        "[m3][2:v]overlay=36:211[last]",
    ]
    last = "last"
    if bottom:
        parts.append(f"[{last}]drawtext=fontfile='{FONT}':text='{esc(font_safe(bottom))}':fontcolor=black:fontsize=44:"
                     f"box=1:boxcolor=white:boxborderw=16:x=(w-text_w)/2:y={win_y + fh + 40}[bt]")
        last = "bt"
    if credit:
        parts.append(f"[{last}]drawtext=fontfile='{FONT}':text='{esc(font_safe(credit))}':fontcolor=white:fontsize=26:"
                     f"box=1:boxcolor=black@0.55:boxborderw=8:x={fx + 14}:y={win_y + 12}[cr]")
        last = "cr"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(avatar), "-i", str(tpng),
                    "-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", "0:a?",
                    "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-c:a", "aac", "-shortest", str(out)],
                   check=True, capture_output=True)
