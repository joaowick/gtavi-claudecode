# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Pipeline that turns recent GTA VI clips (mainly Instagram reels) into vertical shorts (720x1280) for social media. **Scope is GTA VI only.** Everything lives in `viral/`.

## Commands

Run from `viral/` with the system Python (`pip install -r ../requirements.txt`; ffmpeg system-wide). Use `-I` for Python:

```
python -I pipeline.py reels.txt [--limit N] [--type gameplay|talk] [--no-llm]
python -I search.py [--days 90] [--limit 20]    # YouTube search, CC-licensed only
python -I review.py [--open]                    # static review sheet (output/review.html)
python -I serve.py [--port 8765] [--open]       # local server: review sheet + text editor that re-renders a video
python -I pipeline.py --redo-fix [--ids ID...]  # re-render needs_fix items (+ given ids) from queue.json
```

No tests or linter. Verify changes by running the batch and looking at frames from `output/*.mp4`.

## How it works

- `pipeline.py` (batch): download (yt-dlp) -> Whisper transcript -> plan -> ffmpeg render -> `output/<id>.mp4` + `output/queue.json` (caption/hashtags, `status: pending_review`). Already-processed ids are skipped.
- Per-video type is decided by speech rate (`TALK_WPM`, 65 words/min; calibrated on only 15 clips, game dialogue ~55, streamer clips ~70, podcasts should be 130+):
  - `gameplay`: text hook only, **no b-roll** (the gameplay is the visual).
  - `talk` (podcast/commentary): word captions + b-roll cutaways from `viral/broll/*.mp4`.
- Hook/caption come from rules (cleaned original caption). If `ANTHROPIC_API_KEY` is set and `anthropic` is installed, `llm_plan` asks Claude instead (untested: no key was available). It falls back to rules on any error.
- `reels.txt`: one link per line. yt-dlp **cannot list Instagram profiles**, so the list is filled via the ViceScale MCP (`buscar_perfil`); only Claude can call it, a script cannot.
- Dirs: `input/` manual clips, `broll/` b-roll library, `work/<id>/` downloads, `output/` results.

## X support, credit and translation

- `reels.txt` and the CLI accept X/Twitter status links too (yt-dlp, public tweets need no login). The downloaded id is the media id, not the tweet id.
- Credit: `fetch` returns the poster (`author_of`: X `uploader_id`; Instagram yt-dlp gives only a display name + numeric id, so the `# @perfil` comment line above a link in `reels.txt` is used as fallback). `credit_line` adds "Clipe: @x" when the original text says "Clip/Video/Credit/Via: @x". Stored as `credit` in `queue.json`, appended to the caption and drawn as a small label over the video (`plan["credit"]`, kept by `rebuild`).
- The batch now always renders with the profile header (`../profile/profile.json`: avatar + name + handle): it sets `text_pt` (first sentence of the PT caption) and `caption_pt` and calls `rebuild`. `detect_window` analyses at ≤720 px wide (4K X clips ran out of memory otherwise).
- Captions detected as English (`is_english`, stopword heuristic) are translated to PT by `translate_pt`: Claude if `ANTHROPIC_API_KEY`, else the public Google Translate endpoint (sends the public post text to Google). `caption_translated` flags it; the hook is built from the translated text.

## Publishing (Postiz)

- `publish.py` sends scheduled+approved videos through the Postiz public API (`POSTIZ_API_KEY`, `POSTIZ_URL`: env vars, or lines in the git-ignored `viral/postiz/.env`; never commit the key). Only network supported so far: "Facebook Reels" (Postiz `facebook` integration, 3-90 s). Default is a **dry run**; `--yes` really sends; `--mode draft` creates a Postiz draft (safe first test), `now` publishes immediately. State per (video, network) in `output/published.json` (never resent). `--list-integrations` shows connected channels.
- Local Postiz: `viral/postiz/` (`docker-compose.yaml`, `.env` with secrets, `README.md` with setup steps). Docker was not installed when this was written, so the compose file has **not been run**. Local API base: `http://localhost:4007/api/public/v1`.
- Add "Facebook Reels" to the agenda's network list before scheduling. Untested against a real Postiz instance (no key yet): payload follows docs.postiz.com (`POST /posts`, `/upload`); Postiz's Facebook docs have no explicit Reels field, third-party docs say videos go out as Reels.

- **Verified 2026-11-22:** a real publish works (clip `yt_H1nQM59dBO8_693` -> Facebook Page `GTA6Viral`, `--mode now`). Postiz hands the video to Facebook as a `file_url`, so the upload URL must be public: with the default `http://localhost:4007` the post ends in `ERROR` ("Unknown Error", nothing is posted). Open `postiz/tunnel.ps1` first (needs `DISABLE_REGISTRATION: 'true'`, already set), publish, then `tunnel.ps1 -Stop`. Meta app needs the "Manage everything on your Page" use case for `pages_manage_posts` etc. `publish.py` writes `published.json` even if Postiz fails later: check the post state in Postiz (or its DB) and clear the entry before retrying. `--mode draft` stamps the draft with the current time, not the agenda time. Always pass `--ids`.

- **Scheduled publishing verified 2026-11-22:** with Cloudflare R2 storage (`STORAGE_PROVIDER=cloudflare` + `CLOUDFLARE_*` in `postiz/.env`, public `r2.dev` bucket URL) videos get a permanent public link, so no tunnel is needed. `publish.py --mode schedule --yes --ids <id>` queued a post that Postiz published by itself at the scheduled minute (clip `2123086044119605248`, 18:12 local). Requirements: PC on and Docker running at that time; check state with `select state, "releaseURL" from "Post"` in the postiz-postgres container. Optional: R2 lifecycle rule to delete objects after 30 days (not set; nothing deletes uploaded videos automatically).

- **Public visibility (verified 2026-11-22):** while the Meta app is in Development mode, posts it publishes are only visible to people with a role on the app (a non-role viewer was redirected to another video). After switching the app to **Live** (Meta dashboard > Publish; needs privacy policy URL `https://joaowick.github.io/gtavi-claudecode/privacy.html`, data-deletion URL `https://joaowick.github.io/gtavi-claudecode/deletion/` (https is required), app icon, category; pages live in `docs/`), a NEW scheduled post played for a non-role viewer. Posts made in Development mode stay restricted; republish if they matter. No full App Review was needed for posting to our own Page.

## Review sheet and text editor

- `serve.py` listens on 127.0.0.1 only; the page carries a random token, `POST /api/apply/<id>` needs it (`X-Token`) and a valid `Host`. The editor changes **content only** (header text, emoji, bottom pill, cover-bar text, hook, post caption, name/handle), never layout.
- `pipeline.rebuild(vid, item)` re-renders one video from what is saved in `output/queue.json` (`text_pt`, `emoji_pt`, `bottom_text_pt`, `cover`, `hook_pt`, `caption_pt`, `profile`, `crop`, `trim_end`). It reuses the stored `crop`; delete the key to force window re-detection. Auto-detection is wrong on full-frame 9:16 videos with static areas: set `no_crop: true` (done for `Df4gBp1tDxe`).
- Header layout (avatar from `profile.json` + name/handle + PT text, video below) is used whenever an item has `text_pt`. The header text is drawn as a PNG with Pillow (`text_png`: Arial Bold + Segoe UI Emoji, so emoji work anywhere in the text and lines wrap by real width); `emoji_pt` is just appended to the end. Other fields (name, bottom pill, cover bar, hook) still use ffmpeg drawtext, whose font has no emoji, so they are filtered by `font_safe` and the editor returns a warning listing what it removed. Every edit is logged to the server console and `output/edits.jsonl` (id, old/new value per field).
- `/agenda` (built by `agenda.py`, served by `serve.py`) is a schedule planner: week calendar, list, and a gallery of approved videos, drag-and-drop or per-video dialog, "distribute automatically" (N per day at given times) and a user-editable list of networks. State lives in `output/schedule.json`; API is `POST /api/schedule` (`action`: `set` | `auto` | `networks`), same token/Host checks. **It only organizes: nothing is published**, no network is connected. Only `approved` videos can be scheduled; a scheduled video that is later edited or un-approved is flagged "precisa reaprovar". Removing a network from the list also strips it from already-scheduled items. `?view=list|gallery` and `?open=<id>` deep-link into the page (handy for headless screenshots with Edge: `msedge --headless=new --screenshot=... --virtual-time-budget=5000 URL`).
- `/backlog` (built by `backlog.py`, served by `serve.py`) is the to-do board (A fazer / Em andamento / Feito, priority, add/edit/remove). State lives in `viral/backlog.json` (tracked in git, unlike `output/`); API is `POST /api/backlog` (`action`: `add` | `update` | `delete`), same token/Host checks. Put pending ideas there instead of only in NEXT.md.
- The page discards a card's saved decision when its video file changes (`data-v` = mtime). Decisions live in browser localStorage per origin (`file://` and `http://127.0.0.1:8765` are different origins) and are exported as `review_decisions_<id>.json`.
- Run python scripts with `-I` plus `sys.stdout.reconfigure(encoding="utf-8")` inside the script: `-I` ignores `PYTHONIOENCODING`, and notes with emoji crash `print` on the cp1252 console.

## Gotchas

- `broll/` should hold clean GTA VI footage. The only clip there (Rockstar "Extended Look") has burned-in subtitles, an ESRB card (first 5 s) and a logo (last 6 s); `plan_broll` skips those, but the subtitles still show.
- Source reels often carry their own burned-in title/subtitles, which collide with our hook and captions.
- Hook rule: captions are split into paragraphs; "follow/subscribe/credit" paragraphs are dropped and the first sentence of the first remaining one becomes the hook. When patching regexes through a shell heredoc, `\b` can turn into a literal backspace (0x08) that is invisible in Read and makes Edit fail; check with `grep -P "\x08"`.
- Some reels fail to download with "Instagram sent an empty media response" (seen on `Df41UsLtO3j`); the batch skips them and continues.

- `faster-whisper`'s own audio decoding breaks with the installed `av` version, so `pipeline.py` decodes audio with ffmpeg and passes a numpy array. Keep it that way.
- Signed Instagram CDN URLs from `resolver_video` expire and break if retyped even slightly ("URL signature mismatch"). Prefer yt-dlp on the reel link.
- yt-dlp no longer has `ytsearchdate`; `search.py` uses the YouTube results URL with an `sp` filter. That `sp` value does **not** actually filter by Creative Commons license (it is re-checked client-side), and CC gameplay is rare.
- Chrome/Brave cookies cannot be read on this Windows setup (DPAPI error); use an exported `cookies.txt` kept outside the project if age-gated videos are ever needed.
- Most source clips are Rockstar material reposted by third parties. Treat publishing rights as an open question before any publication step exists.

## Notificacoes Telegram (piloto, 2026-11-23)

- `notify.py`: `--test`, `--check` (le o estado dos posts em `published.json` no Postgres do Postiz via `docker exec postiz-postgres` e avisa PUBLISHED/ERROR uma vez, marcando `notified`), `--watch`. `publish.py --yes` tambem manda um resumo ao enviar/agendar.
- Config em `viral/postiz/.env` (fora do git): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (o chat_id e o do usuario, NAO o prefixo do token). Nunca colocar o token no chat.
- Tarefa do Windows `GTA6Viral-notify` roda `pythonw -I notify.py --check` a cada 5 min (sem janela, sem log). Remover: `Unregister-ScheduledTask GTA6Viral-notify -Confirm:$false`. Precisa de PC ligado e Docker rodando.
- `--check` ainda nao foi testado contra um post real.
- Horarios "humanos": `agenda.humanize` (usado em `set` e `auto`) soma 1-29 min aleatorios (nunca multiplo de 5) a qualquer horario redondo, ex.: 18:00 -> 18:17. Horarios ja quebrados (18:49) nao mudam. So vale para agendamentos novos: o que ja foi enviado ao Postiz mantem a hora enviada.
