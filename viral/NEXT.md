# Para continuar (atualizado em 2026-11-23)

Regras estáveis e comandos: `viral/CLAUDE.md`. Este arquivo é só o "onde paramos".

## Estado

- Fluxo completo validado: clipe (`scripts/profile_clip.py`: template do perfil, blur, legenda PT/EN em Pricedown) -> `--queue` -> aprovar em `serve.py` -> agenda -> `publish.py --mode schedule --yes --ids ...` -> Postiz publica sozinho na Página **GTA6Viral** (Facebook Reels). Vídeos ficam no Cloudflare R2 (link público permanente, sem túnel).
- App da Meta em modo **Live**; teste com pessoa sem função no app confirmou que o Reel aparece para o público.
- **21 posts agendados no Postiz (QUEUE)**, 3 por dia às 12:00, 18:00 e 21:00 (Brasília), de 23/11 a 29/11 (o último é 29/11 21:00). Os 10 últimos (26/11 21:00 a 29/11) vêm do walkthrough do MKIceAndFire (`jobs/r97eovd1nr4-*`, ids `yt_R97EoVD1nr4_*`; fonte em inglês, `profile_clip.py --src-lang en`; legendas vindas de transcrição automática, podem ter erros). Horários são suposição (picos típicos), não dado da Página.
- **O PC e o Docker (Postiz) precisam estar ligados nesses horários.** Subir o Postiz: `cd viral/postiz && docker compose up -d`.
- Já publicados: `2123222296424755200` (artes, 22/11) e o glitch/LipaoGamer (versões antigas, restritas; os dois foram reagendados em versão nova).

## Fora da agenda (decisão pendente do usuário)

- 10 reels do Instagram sem autor/crédito (`DfnmQnyo43s`, `DddUbfiIsFJ`, `Dcjo2biI9Tc`, `Dcjl1y6I4TA`, `DcjgV-II72i`, `Df41aA_NCWr`, `Df4r56cNjnJ`, `Df4klH0Nd-_`, `Df4j5gxNbIc`, `Df4gBp1tDxe`): não agendados por falta de crédito (regra: sempre creditar).
- 5 datados (lançamento de 19/11): `2122710402199158784` TOMORROW, `2120918584901677056` JUST IN, `2122843166663729152` POV hoje à noite, `2112701124205502464` primeiro comercial, `2123310526721605632` contagem regressiva.
- Mais de 90 s (limite do Reels): `2122454015762157568`, `2123051789864128512`, `2123044129311764480`.

## Como conferir os posts

- Estado no Postiz: `docker compose exec -T postiz-postgres psql -U postiz-user -d postiz-db-local -At -c "select state, \"publishDate\", \"releaseURL\" from \"Post\" order by \"publishDate\""` (rodar em `viral/postiz`). Estados: `QUEUE` (aguardando), `PUBLISHED`, `ERROR`.
- `publish.py` lê `POSTIZ_API_KEY` e `POSTIZ_URL` do ambiente ou de `viral/postiz/.env` (local, fora do git). A chave não expira: copiar uma vez de Postiz > Settings > Developers. Sempre passar `--ids`.
- `publish.py` grava `output/published.json` mesmo se o Postiz falhar depois: conferir o estado e limpar a entrada antes de reenviar.

## Lembretes / próximos passos

- **R2 sem limpeza:** aplicar a regra de ciclo de vida (apagar objetos após 30 dias) no bucket `gta6viral-media` (Cloudflare > R2 > bucket > Settings > Object Lifecycle Rules). Há também arquivos de teste no bucket.
- Depois de ~1 semana de posts: usar a skill `learning-loop` (placar) para ajustar horários e tipos de conteúdo com números reais.
- Para novos clipes: `scripts/moments.py` -> `scripts/profile_clip.py ... --subs pt-en --translations <json> --queue` (traduções: fazer à mão, o Google Translate limita requisições) -> aprovar -> agendar.
- Direitos: todo material é de terceiros (crédito no vídeo e na legenda, sem autorização formal).
- Local e fora do git: `viral/postiz/.env` (segredos da Meta, do R2 e JWT), `fonts/pricedown/` (licença proíbe compartilhar), `viral/output`, `viral/work`, `viral/input`.
