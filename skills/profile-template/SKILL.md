---
name: profile-template
description: Render a clip in the user's own profile template (black background, round avatar + name + @handle, Portuguese text, video window below, credit label, 720x1280). Use when the user wants the clip "with my profile", "no template do perfil", "gta6viral style", or a ready-to-post clip with the page header.
---

# Profile template

Default look: blurred background (`--bg black` for plain black), GTA VI subtitles in Pricedown when `fonts/pricedown/` exists (git-ignored, EULA forbids sharing the file; falls back to Impact).

The template is self-contained: `scripts/profile_render.py` (renderer) and `profile/profile.json` + `profile/avatar.png` (name, handle, avatar; edit them to change the page identity). Shared with `viral/pipeline.py`, which imports its header helpers, so there is one layout implementation.

## Steps

1. Have a job with candidates (`moment-finder` / `scripts/moments.py`). Pick a candidate.
2. Write the header text in Portuguese: one sentence saying what happens on screen, at most 2 emoji. Do not put words in the creator's mouth. Use `hook-writer` for options.
3. Run:
   ```
   python scripts/profile_clip.py jobs/<id> --pick <n> --text "A polícia rastreia carro roubado no GTA 6 🚔"
   ```
   Subtitles: `--subs pt-en` (PT main, EN second line) with `--translations file.json` ({pt phrase: en}; `--list-phrases` prints the phrases; Google Translate rate-limits fast, so translating them yourself is safest). `--cut "0-11,28.5-39.8"` joins parts (seconds relative to the clip start). `--label` names the file, `--queue` registers the clip in `viral/output/queue.json` as `pending_review` (then review/approve in `viral/serve.py`; the editor will not re-render it, by design).
   Optional: `--credit "Vídeo: @canal"` (default is the source channel), `--bottom "texto"` (white pill under the video), `--crop y0:y1` (keep only those pixel rows, to drop a facecam), `--name/--handle/--avatar`, `--start/--end` instead of `--pick`.
4. Output: `jobs/<id>/edits/clip_<n>_profile.mp4` (720x1280). Extract one frame with ffmpeg and look at it before saying it is done.

## Notes

- Windows fonts (Arial Bold, Segoe UI Emoji) and Pillow are required (`pip install pillow`).
- Horizontal sources fill only about a third of the height. That is the template's design. Use `--crop` if a facecam sits on the video.
- No word-by-word captions in this layout. For captions use `clip-cutter`.
- Always credit the original creator. Nothing is posted automatically.
