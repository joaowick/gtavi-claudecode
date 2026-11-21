# Para continuar (escrito em 2026-11-18, à noite)

Contexto geral e regras estáveis estão no `CLAUDE.md` da raiz. Este arquivo é só o "onde paramos".

## Estado

- Pipeline aceita links do **X** e do Instagram; todo vídeo novo sai com o **perfil gta6viral** no cabeçalho, **crédito** do autor (@ no vídeo e na legenda) e legenda **EN -> PT** automática.
- Fila (`output/queue.json`): **14 aprovados, 4 rejeitados**. Inclui 4 vídeos do X aprovados (ids `2112701124205502464`, `2122454015762157568`, `2115691231041003520`, `2120918584901677056`).
- `publish.py` (Postiz, **Facebook Reels**) está escrito e testado só em **simulação**. Nunca falou com um Postiz real.
- `postiz/` tem `docker-compose.yaml`, `.env` (JWT_SECRET gerado), `dynamicconfig/` e `README.md` com o passo a passo. **Docker não estava instalado**, então nada disso foi executado.
- `serve.py` (revisão + `/agenda`) estava rodando na porta 8765; o desligar do PC derrubou. Reabrir: `.venv\Scripts\python.exe -I serve.py --open`.

## Próximos passos (em ordem)

1. Instalar **Docker Desktop** (Windows 11 Home -> WSL2). Conferir `docker --version`.
2. Em `viral/postiz/`: `docker compose up -d`, esperar ~2 min, abrir http://localhost:4007, criar conta. Depois por `DISABLE_REGISTRATION: 'true'`.
3. Criar o **app na Meta** (passos no `postiz/README.md`), preencher `FACEBOOK_APP_ID/SECRET` no `.env`, `docker compose up -d`, conectar a Página em Add Channel > Facebook.
4. Pegar a chave em Postiz > Settings > Developers e, no PowerShell:
   `$env:POSTIZ_API_KEY="..."; $env:POSTIZ_URL="http://localhost:4007/api/public/v1"`
   `.venv\Scripts\python.exe -I publish.py --list-integrations`
5. Adicionar **"Facebook Reels"** à lista de redes da `/agenda` e agendar um vídeo aprovado.
6. 1º teste real: `publish.py --mode draft --yes` (cria rascunho, **não publica**). Conferir no Postiz se o vídeo sobe como **Reel** (a doc do Postiz não tem campo explícito de Reels; confirmar).

## Problemas conhecidos / ideias

- Vídeos tipo `talk` no X: legendas por palavra saem na língua falada (inglês), sem tradução.
- Termos como "JUST IN" passam sem tradução no cabeçalho (corrigir no editor do `serve.py`).
- Tweets só de texto falham no download (esperado, o lote pula).
- Instagram: o @ do autor vem do comentário `# @perfil` no `reels.txt` (yt-dlp não entrega); não testado de ponta a ponta com reel novo.
- Direitos: boa parte do material é da Rockstar repostado por terceiros; crédito ajuda mas não resolve. Evitar clipes de vazamento.
- Só Facebook Reels está implementado em `publish.py`; Instagram/YouTube/TikTok/X são "pulados".
