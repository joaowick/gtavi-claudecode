"""Self-contained renderer for the profile-header template (ported from the gta6-viral pipeline).
Black 720x1280 canvas: round avatar + name + @handle, wrapped text (emoji in colour), video window
below, optional white pill and credit label."""
import json, re, subprocess, tempfile, zlib
from pathlib import Path

FONT = r"C\:/Windows/Fonts/arialbd.ttf"       # ffmpeg drawtext
BOLD_FONT = r"C:\Windows\Fonts\arialbd.ttf"   # Pillow
EMOJI_FONT = r"C:\Windows\Fonts\seguiemj.ttf"
PRICEDOWN = Path(__file__).parent.parent / "fonts" / "pricedown" / "Pricedown Bl.otf"   # git-ignored (EULA)


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


def make_header_png(text):
    """Draw the header text to a PNG in the temp dir. Returns (path, number_of_lines)."""
    tpng = Path(tempfile.gettempdir()) / f"hdr_{zlib.crc32(text.encode('utf-8')):08x}.png"
    return tpng, text_png(header_safe(text), tpng)


def header_filters(vin, dur, cw, ch, nlines, ai, ti, name, handle, bottom=None):
    """ffmpeg filter parts for the profile layout. vin: label of the video stream (size cw x ch);
    ai/ti: input indexes of the avatar and the text PNG. Returns (parts, last_label, win_y, fw, fh, fx)."""
    win_y = 215 + nlines * 54 + 20
    avail = 1280 - win_y - (110 if bottom else 20)
    sc = min(720 / cw, avail / ch)
    fw, fh = int(cw * sc) // 2 * 2, int(ch * sc) // 2 * 2
    fx = (720 - fw) // 2
    parts = [
        f"color=c=black:s=720x1280:d={dur}[bg0]",
        f"{vin}scale={fw}:{fh},setsar=1[fg]",
        f"[bg0][fg]overlay={fx}:{win_y}[m0]",
        f"[{ai}:v]scale=96:96,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':"
        "a='if(lte(hypot(X-48,Y-48),48),255,0)'[av]",
        "[m0][av]overlay=36:60[m1]",
        f"[m1]drawtext=fontfile='{FONT}':text='{esc(name)}':fontcolor=white:fontsize=38:x=150:y=68[m2]",
        f"[m2]drawtext=fontfile='{FONT}':text='{esc(handle)}':fontcolor=0x9aa3b2:fontsize=30:x=150:y=114[m3]",
        f"[m3][{ti}:v]overlay=36:211[tx]",
    ]
    last = "tx"
    if bottom:
        parts.append(f"[{last}]drawtext=fontfile='{FONT}':text='{esc(font_safe(bottom))}':fontcolor=black:fontsize=44:"
                     f"box=1:boxcolor=white:boxborderw=16:x=(w-text_w)/2:y={win_y + fh + 40}[bt]")
        last = "bt"
    return parts, last, win_y, fw, fh, fx


def credit_filter(last, win_y, fx):
    return lambda credit: (f"[{last}]drawtext=fontfile='{FONT}':text='{esc(font_safe(credit))}':fontcolor=white:fontsize=26:"
                           f"box=1:boxcolor=black@0.55:boxborderw=8:x={fx + 14}:y={win_y + 12}[cr]")


# (ASS style line, override tags for the second line). Colours are BGR: &H00BBGGRR.
STYLES = {
    # Vice City neon: Pricedown (fonts/pricedown, falls back to Impact) caps, white fill, hot-pink outline,
    # purple shadow; English in sunset orange.
    "gtavi": ("Style: Sub,{font},54,&H00FFFFFF,&H00FFFFFF,&H00932EFF,&H00601E3C,0,0,0,0,100,100,1,0,1,4,3,8,40,40,{y},1",
              r"\N{\fs32\i0\c&H001C9FFF&\3c&H00300F20&\bord2}"),
    "plain": ("Style: Sub,Arial,44,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,8,40,40,{y},1",
              r"\N{\fs34\b0\i1\c&H00D7FF&}"),
}


def build_subs_ass(subs, y, path, style="gtavi"):
    """Bilingual subtitles under the video. subs = [(start, end, main_text, second_text)].
    Main line: white bold; second line: smaller, italic, yellow. Anchored at the top at y."""
    def t(x):
        h, m, sec = int(x // 3600), int(x % 3600 // 60), x % 60
        return f"{h}:{m:02d}:{sec:05.2f}"

    def clean(x):
        return x.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")

    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,"
            "StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
            f"{STYLES[style][0].format(y=int(y), font='Pricedown Black' if PRICEDOWN.exists() else 'Impact')}\n\n"
            "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n")
    ev = ""
    for a, b, main, second in subs:
        txt = (clean(main).upper() if style == "gtavi" else clean(main)) + (STYLES[style][1] + clean(second) if second else "")
        ev += f"Dialogue: 0,{t(a)},{t(b)},Sub,,0,0,0,,{txt}\n"
    Path(path).write_text(head + ev, encoding="utf-8")


def render(src, out, *, name, handle, avatar, text, credit=None, bottom=None, crop=None, subs=None, sub_style="gtavi"):
    """Standalone render of one video in the profile layout. crop = (y0, y1) source pixel rows to keep."""
    w, h, dur = probe(src)
    cw, ch = (w, crop[1] - crop[0]) if crop else (w, h)
    tpng, nlines = make_header_png(text)
    vin = f"[0:v]crop=iw:{crop[1] - crop[0]}:0:{crop[0]}[s];[s]" if crop else "[0:v]"
    parts, last, win_y, fw, fh, fx = header_filters(vin, dur, cw, ch, nlines, 1, 2, name, handle, bottom)
    if credit:
        parts.append(credit_filter(last, win_y, fx)(credit))
        last = "cr"
    if subs:
        ass = Path(tempfile.gettempdir()) / f"subs_{zlib.crc32(str(out).encode()):08x}.ass"
        build_subs_ass(subs, win_y + fh + 50, ass, sub_style)
        ass_path = str(ass).replace("\\", "/").replace(":", "\\:")
        fdir = str(PRICEDOWN.parent).replace("\\", "/").replace(":", "\\:")
        parts.append(f"[{last}]ass='{ass_path}':fontsdir='{fdir}'[sb]")
        last = "sb"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-i", str(avatar), "-i", str(tpng),
                    "-filter_complex", ";".join(parts), "-map", f"[{last}]", "-map", "0:a?",
                    "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-c:a", "aac", "-shortest", str(out)],
                   check=True, capture_output=True)
