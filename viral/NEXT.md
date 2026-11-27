# Para continuar (atualizado em 2026-11-23)

Regras estáveis e comandos: `viral/CLAUDE.md`. Este arquivo é só o "onde paramos".

## Estado

- Fluxo completo validado: clipe (`scripts/profile_clip.py`: template do perfil, blur, legenda PT/EN em Pricedown) -> `--queue` -> aprovar em `serve.py` -> agenda -> `publish.py --mode schedule --yes --ids ...` -> Postiz publica sozinho na Página **GTA6Viral** (Facebook Reels). Vídeos ficam no Cloudflare R2 (link público permanente, sem túnel).
- App da Meta em modo **Live**; teste com pessoa sem função no app confirmou que o Reel aparece para o público.
- **21 posts agendados no Postiz (QUEUE)**, 3 por dia às 12:00, 18:00 e 21:00 (Brasília), de 23/11 a 29/11 (o último é 29/11 21:00). Os 10 últimos (26/11 21:00 a 29/11) vêm do walkthrough do MKIceAndFire (`jobs/r97eovd1nr4-*`, ids `yt_R97EoVD1nr4_*`; fonte em inglês, `profile_clip.py --src-lang en`; legendas vindas de transcrição automática, podem ter erros). Horários são suposição (picos típicos), não dado da Página.
- **O PC e o Docker (Postiz) precisam estar ligados nesses horários.** Subir o Postiz: `cd viral/postiz && docker compose up -d`.
- Já publicados: `2123222296424755200` (artes, 22/11) e o glitch/LipaoGamer (versões antigas, restritas; os dois foram reagendados em versão nova).

## Atualização 2026-11-26: 6 posts/dia

- A partir de 27/11 são **6 posts/dia** (09, 12, 15, 18, 21, 23h, Brasília; os 3 novos horários têm minutos aleatórios). Enviados ao Postiz (QUEUE) até 29/11 23:29: 19 posts no total.
- 9 clipes novos (aprovados em 26/11): LipaoGamer (`3KBrZpmJxjY`, picks 3/5/6), Paulinho LOKO (`gL_uShKqYnk`, picks 2/3; crédito `@ModderClips`), theRadBrad (`6wY8QmounXk`, picks 4/5/6), NoAnnoyingCommentary (`SShSzzfZkvw`, pick 3). Ids `yt_<video>_<pick>`; traduções em `jobs/<job>/translations_x.json`.
- **Alerta:** o vídeo do MKIceAndFire (`R97EoVD1nr4`) foi **removido pelo uploader** (provável ação de direitos autorais). Os 10 posts dele continuam na fila do Postiz (mp4 no R2 e em `output/`). Decisão pendente: manter ou apagar esses posts no Postiz.
- Limpeza da tela Revisão: itens publicados, rejeitados e os 18 não usáveis (sem crédito, datados, >90 s) foram movidos para `output/queue_archive.json` (reversível; mp4 continuam em `output/`). `queue.json` ficou só com os 19 na fila do Postiz. Backups: `output/*.bak_pre_limpeza`.
- A lista "Fora da agenda" abaixo agora está arquivada. Para novos lotes, o fluxo `moments.py` -> `profile_clip.py` precisa de fontes novas (trends.py).
- `publish.py --ids` espera ids separados por **espaço**. Python com `-I` não acha módulos locais: `publish.py` agora insere o próprio diretório no path (aviso Telegram).

## Fora da agenda (arquivado em 2026-11-26; histórico)

- 10 reels do Instagram sem autor/crédito (`DfnmQnyo43s`, `DddUbfiIsFJ`, `Dcjo2biI9Tc`, `Dcjl1y6I4TA`, `DcjgV-II72i`, `Df41aA_NCWr`, `Df4r56cNjnJ`, `Df4klH0Nd-_`, `Df4j5gxNbIc`, `Df4gBp1tDxe`): não agendados por falta de crédito (regra: sempre creditar).
- 5 datados (lançamento de 19/11): `2122710402199158784` TOMORROW, `2120918584901677056` JUST IN, `2122843166663729152` POV hoje à noite, `2112701124205502464` primeiro comercial, `2123310526721605632` contagem regressiva.
- Mais de 90 s (limite do Reels): `2122454015762157568`, `2123051789864128512`, `2123044129311764480`.

## Como conferir os posts

- Estado no Postiz: `docker compose exec -T postiz-postgres psql -U postiz-user -d postiz-db-local -At -c "select state, \"publishDate\", \"releaseURL\" from \"Post\" order by \"publishDate\""` (rodar em `viral/postiz`). Estados: `QUEUE` (aguardando), `PUBLISHED`, `ERROR`.
- `publish.py` lê `POSTIZ_API_KEY` e `POSTIZ_URL` do ambiente ou de `viral/postiz/.env` (local, fora do git). A chave não expira: copiar uma vez de Postiz > Settings > Developers. Sempre passar `--ids`.
- `publish.py` grava `output/published.json` mesmo se o Postiz falhar depois: conferir o estado e limpar a entrada antes de reenviar.

## Lembretes / próximos passos

- **Backlog visual:** `python -I serve.py --open` e aba **Backlog** (`/backlog`, dados em `viral/backlog.json`). Os itens abaixo estão lá também.

- **R2 sem limpeza:** aplicar a regra de ciclo de vida (apagar objetos após 30 dias) no bucket `gta6viral-media` (Cloudflare > R2 > bucket > Settings > Object Lifecycle Rules). Há também arquivos de teste no bucket.
- Depois de ~1 semana de posts: usar a skill `learning-loop` (placar) para ajustar horários e tipos de conteúdo com números reais.
- **Backlog: métricas do Facebook (`viral/insights.py`).** Complexidade baixa (~1-2 dias). Plano: ler o token da Página `GTA6Viral` (ID `1474553469075412`) do Postgres do Postiz (`Integration.token`, via `docker exec`; nunca copiar para o repo/chat), chamar a Graph API (`/{page-id}/insights`: `page_follows`, `page_video_views`, alcance; `/{video-id}/video_insights` por Reel: views, watch time, retenção), cruzar com `published.json`/`schedule.json` e gravar `output/insights.json`; depois analisar com a skill `learning-loop`. Só `urllib`, como o `publish.py`.
  - **Pendente antes de começar:** confirmar com `debug_token` (app `945925955119756`) que o token tem `read_insights` e `pages_read_engagement` (o README do Postiz diz que ele pede). Na sessão de 2026-11-26 o classificador bloqueou ler o token no banco: autorizar uma consulta somente leitura (imprimir só escopos/status) em `.claude/settings.local.json`, ou rodar você mesmo. Se faltar escopo: reconectar a Página no Postiz.
  - Riscos: a Meta renomeia métricas de vídeo (tratar métrica inválida sem quebrar); Reels da época do modo Development podem vir sem dados; métricas de Reels demoram horas/dias para aparecer. Alternativa sem configurar nada: exportar o CSV em Meta Business Suite > Insights e me passar.
- Para novos clipes: `scripts/moments.py` -> `scripts/profile_clip.py ... --subs pt-en --translations <json> --queue` (traduções: fazer à mão, o Google Translate limita requisições) -> aprovar -> agendar.
- Direitos: todo material é de terceiros (crédito no vídeo e na legenda, sem autorização formal).
- Local e fora do git: `viral/postiz/.env` (segredos da Meta, do R2 e JWT), `fonts/pricedown/` (licença proíbe compartilhar), `viral/output`, `viral/work`, `viral/input`.
