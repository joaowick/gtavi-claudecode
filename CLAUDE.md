# CLAUDE.md

Fork pessoal (de `joaowick`) do plugin gtavi-claudecode, usado para operar a página de Facebook **GTA6Viral** (clipes de GTA 6 em Reels).

**Ao começar uma sessão, leia `viral/NEXT.md`** (onde paramos, posts agendados, pendências) e `viral/CLAUDE.md` (comandos, regras e armadilhas do pipeline de publicação).

Estrutura:
- `scripts/` e `skills/`: ferramentas originais (moments, cut, etc.) mais as adições: `profile_clip.py` / `profile_render.py` (template do perfil, blur, legenda PT/EN estilo GTA VI) e a skill `profile-template`.
- `viral/`: pipeline de lote, revisão (`serve.py`), agenda, publicação via Postiz (`publish.py`) e o Postiz local (`viral/postiz/`, Docker).
- `profile/`: nome, handle e avatar da página (usados por tudo).
- `docs/`: política de privacidade e exclusão de dados (GitHub Pages), exigidas pela Meta.
- `fonts/`, `viral/postiz/.env`, `viral/output|work|input`, `jobs/`: locais, fora do git.

Regras: nunca publicar sem o usuário pedir; sempre usar `--ids` no `publish.py`; sempre creditar o autor original; não colocar chaves/segredos no repo nem no chat.
