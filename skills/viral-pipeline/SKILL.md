---
name: viral-pipeline
description: Batch pipeline for the gta6viral page. Turns Instagram/X/YouTube GTA 6 links into 720x1280 shorts with the profile header, PT caption and credit, then review sheet, schedule and Postiz publishing. Use for "process the reels", "review sheet", "agenda", "publish", or when the user mentions reels.txt, queue.json or gta6viral.
---

# Viral pipeline (gta6viral)

Everything is in `viral/`. Read `viral/CLAUDE.md` first: it has the commands, the rules (credit, PT translation, hook) and the gotchas. Run Python scripts with `-I` from `viral/`.

- Batch: `python -I pipeline.py reels.txt [--limit N]` -> `viral/output/<id>.mp4` + `output/queue.json` (`pending_review`).
- Review and edit text: `python -I serve.py --open` (review sheet + `/agenda`).
- Publish (Postiz, dry run by default): `publish.py`. Never run it with `--yes` or `--mode now` without the user asking in that turn.
- Where we stopped: `viral/NEXT.md`.
- Schedule organization can go to the `agenda` agent (`.claude/agents/agenda.md`), which never publishes.

Profile identity (name, handle, avatar) is shared with `profile-template`: `profile/profile.json`. Single clip from a long YouTube video with the same header: use `profile-template`.

`viral/output`, `viral/work`, `viral/input` and `viral/postiz/.env` are local and git-ignored. Create `viral/postiz/.env` from `viral/postiz/README.md` (needs `JWT_SECRET`).
