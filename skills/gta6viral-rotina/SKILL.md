---
name: gta6viral-rotina
description: Rotina completa da página GTA6Viral (Facebook Reels). Use quando o usuário pedir "faça a rotina", "rotina de hoje", "confira os posts", "ache vídeos novos", "produza os clipes de hoje" ou "agende a semana". Confere os posts, vasculha vídeos brutos novos, propõe clipes, produz, aprova, agenda e publica, sempre com o usuário decidindo.
---

# Rotina GTA6Viral

Leia antes `CLAUDE.md` (raiz), `viral/NEXT.md` (onde paramos) e `viral/CLAUDE.md` (comandos e armadilhas). Rode a partir da raiz do repo.

## Regras que valem em todos os passos

- **Nunca publique nem agende sem o usuário pedir naquela vez.** Aprovar é decisão dele.
- Sempre `--ids` no `publish.py`. Sempre simulação antes do `--yes`.
- **Sempre creditar o autor original.** Sem autor identificado: não use. Sem permissão do criador: avise o risco.
- Facebook Reels: 3 a 90 s. Evite conteúdo datado (lançamento já passou).
- Chaves e segredos nunca vão para o Git nem para o chat.
- Traduções das legendas: faça à mão (o Google Translate limita requisições) e salve em `jobs/<id>/translations_en.json`.
- Texto do cabeçalho: uma frase em português que descreva o que acontece (no máximo 2 emoji). Nunca invente fala do criador.

## 1. Conferir o que já foi agendado e publicado

Em `viral/postiz`:

```
docker compose ps                       # Postiz de pé? se não: docker compose up -d
docker compose exec -T postiz-postgres psql -U postiz-user -d postiz-db-local -At -F' | ' -c "select state, to_char(\"publishDate\" at time zone 'UTC' at time zone 'America/Sao_Paulo','DD/MM HH24:MI'), \"releaseURL\", left(coalesce(error,''),120) from \"Post\" where \"deletedAt\" is null order by \"publishDate\""
```

Estados: `QUEUE` (aguardando), `PUBLISHED`, `ERROR`. Para cada `ERROR`: ler o erro, limpar a entrada em `viral/output/published.json` e propor reenvio. Resuma em uma tabela e diga quantos dias de fila restam.

## 2. Descoberta de vídeos brutos novos

Objetivo: achar material novo para a fila. Fontes, em ordem:

1. **Canais autorizados:** `viral/watchlist.md` (canais cujo criador deu permissão). Prioridade máxima.
2. **Tendências do YouTube:** `python scripts/trends.py --query "gta 6" --hours 24 --limit 10`. Ranqueia por views/hora.
3. **Lives:** `python scripts/streams.py --query "gta 6"` (não testado).
4. **Instagram:** via a ferramenta ViceScale `buscar_perfil` (só o Claude chama; scripts não). Coloque os links em `viral/reels.txt` (não testado neste fluxo).

Filtre: tema atual, 3 a 90 s de trecho aproveitável, autor identificável. Descarte o que já está em `viral/output/queue.json`, `published.json` ou `jobs/`. Apresente uma lista curta e peça ao usuário que escolha de qual fonte seguir.

## 3. Achar os momentos e propor 3 clipes (esperar a escolha)

```
python scripts/moments.py "<url>" --top 5        # baixa, transcreve (CPU: ~5 min por 15 min de vídeo) e pontua
```

Leia `jobs/<id>/candidates.md`. **Proponha 3 clipes** (vídeo, trecho, por que prende, texto do cabeçalho sugerido) e **espere o usuário escolher**. Se houver 15 s ou mais de trecho sem fala, ofereça a versão curta com `--cut`.

## 4. Produzir

```
python scripts/profile_clip.py jobs/<id> --start <s> --end <s> --text "<cabeçalho>" \
  --subs pt-en --translations jobs/<id>/translations_en.json --label <nome> --queue
```

- Descubra as frases com `--list-phrases` e escreva o JSON de traduções antes de rodar.
- Padrões: fundo blur e legenda Pricedown (se `fonts/pricedown/` existir; senão Impact). `--bg black` para fundo preto.
- Emenda de partes: `--cut "0-11,28.5-39.8"` (segundos relativos ao início do trecho; se usou `--start`, some o deslocamento).
- **Confira um frame** (e a duração) antes de dizer que está pronto. Você não assiste ao vídeo: diga isso e peça que o usuário veja.
- `--queue` registra em `viral/output/queue.json` como `pending_review`.

## 5. Aprovação (o usuário decide)

`cd viral && python -I serve.py --open`. O usuário aprova na folha de revisão e exporta o JSON de decisões (`review_decisions_*.json` em Downloads). Compare com `queue.json` e aplique só as diferenças (faça backup antes). Não aprove por ele.

## 6. Agendar (só as aprovadas)

Elegíveis: `approved`, crédito presente, 3 a 90 s, ainda não publicadas. Horários padrão: **12:00, 18:00 e 21:00** (Brasília), 3 por dia, começando no próximo dia livre (suposição de pico; ajuste com o placar quando houver dados).

Use `viral/agenda.py`:

```python
import agenda; agenda.apply_action(sched, queue, {"action": "set", "id": vid, "when": "AAAA-MM-DDTHH:MM", "networks": ["Facebook Reels"]})
```

(backup de `output/schedule.json` antes; a rede precisa ser "Facebook Reels"). Mostre a tabela dia/hora/título ao usuário.

## 7. Publicar (só com o "pode" do usuário)

```
cd viral
python -I publish.py --ids <ids> --mode schedule           # simulação
python -I publish.py --ids <ids> --mode schedule --yes     # envia ao Postiz
```

O Postiz publica sozinho na hora marcada, com os vídeos no R2 (link público). **O PC e o Docker precisam estar ligados** nos horários. A chave vem de `viral/postiz/.env`. Depois confira que os posts entraram em `QUEUE` (passo 1).

## 8. Fechar

Atualize `viral/NEXT.md` (o que está agendado, o que ficou de fora, pendências) e faça o commit e o push. Lembre o usuário dos pendentes: regra de 30 dias do R2, decisões sobre itens fora da agenda.
