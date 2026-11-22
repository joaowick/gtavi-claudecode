r"""Publicacao via Postiz (https://postiz.com): le a agenda (output/schedule.json) e envia os videos aprovados.

Uso (a partir de viral/, com o venv):
    python -I publish.py --list-integrations                 # mostra os canais conectados no Postiz e o mapeamento
    python -I publish.py [--ids ID ...] [--network "Facebook Reels"]          # SIMULACAO: mostra o que seria enviado
    python -I publish.py --yes [--mode schedule|draft|now] [...]              # envia de verdade

Configuracao por variaveis de ambiente (a chave NAO fica no projeto):
    POSTIZ_API_KEY   chave da API (Postiz > Settings > Developers > Public API)
    POSTIZ_URL       base da API. Cloud: https://api.postiz.com/public/v1 (padrao).
                     Self-hosted: <seu-backend>/public/v1  (confira no seu Postiz; ex.: http://localhost:4007/api/public/v1)

Redes suportadas nesta versao: "Facebook Reels" (integracao Postiz `facebook`). As outras redes da agenda sao puladas.
Regras: so videos `approved`; cada (video, rede) e enviado uma vez (estado em output/published.json);
Facebook Reels aceita 3-90 s; horarios no passado so com --mode now ou draft.
"""
import argparse, json, mimetypes, os, sys, urllib.error, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "output"
DEFAULT_URL = "https://api.postiz.com/public/v1"
# nome da rede na agenda (minusculo) -> (identificador do canal no Postiz, __type das settings, duracao min/max em s)
NETWORKS = {"facebook reels": ("facebook", "facebook", (3, 90))}


class PostizError(Exception):
    pass


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------- cliente Postiz (so urllib: sem dependencias novas) ----------
class Postiz:
    def __init__(self, key, base):
        self.key, self.base = key, base.rstrip("/")

    def _call(self, method, path, body=None, headers=None):
        req = urllib.request.Request(self.base + path, data=body, method=method,
                                     headers={"Authorization": self.key, "User-Agent": "gta6-pipeline", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode("utf-8") or "null")
        except urllib.error.HTTPError as e:
            msg = {429: "limite de requisicoes por hora do Postiz (tente mais tarde)",
                   401: "chave da API invalida (POSTIZ_API_KEY)", 413: "arquivo grande demais"}.get(e.code, "")
            raise PostizError(f"HTTP {e.code} {msg} {e.read().decode('utf-8', 'replace')[:300]}".strip()) from None
        except urllib.error.URLError as e:
            raise PostizError(f"sem conexao com {self.base}: {e.reason}") from None

    def integrations(self):
        return self._call("GET", "/integrations")

    def upload(self, path):
        b = uuid.uuid4().hex
        ct = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                f"Content-Type: {ct}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
        return self._call("POST", "/upload", body, {"Content-Type": f"multipart/form-data; boundary={b}"})

    def create_post(self, payload):
        return self._call("POST", "/posts", json.dumps(payload).encode("utf-8"), {"Content-Type": "application/json"})


ENV_FILE = HERE / "postiz" / ".env"          # local, fora do git (ver .gitignore)


def setting(name):
    """Variavel de ambiente primeiro; se nao houver, a linha NAME=valor de viral/postiz/.env."""
    if os.environ.get(name):
        return os.environ[name]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            k, sep, v = line.partition("=")
            if sep and k.strip() == name and v.strip():
                return v.strip().strip("\"'")
    return None


def client():
    key = setting("POSTIZ_API_KEY")
    if not key:
        sys.exit("Defina POSTIZ_API_KEY (Postiz > Settings > Developers > Public API) no ambiente ou em "
                 "viral/postiz/.env, e, se for self-hosted, POSTIZ_URL.")
    return Postiz(key, setting("POSTIZ_URL") or DEFAULT_URL)


def find_integration(ints, ident):
    c = [i for i in ints if (i.get("identifier") or "").lower() == ident and not i.get("disabled")]
    return c[0] if c else None


# ---------- montagem do post ----------
def local_to_utc_iso(when):
    """'2026-11-20T18:00' (hora local do PC) -> '2026-11-20T21:00:00.000Z'."""
    d = datetime.strptime(when, "%Y-%m-%dT%H:%M").astimezone(timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def build_payload(item, integ_id, settings_type, media, when_iso, mode):
    text = item.get("caption_pt") or item["caption"]
    title = (item.get("text_pt") or " ".join(item.get("hook_pt") or item["hook"]))[:100]
    return {"type": mode, "date": when_iso, "shortLink": False, "tags": [],
            "posts": [{"integration": {"id": integ_id},
                       "value": [{"content": text, "image": [{"id": media["id"], "path": media["path"]}]}],
                       "settings": {"__type": settings_type, "post_type": "post", "title": title}}]}


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", nargs="*", default=[], help="so estes ids (padrao: todos os agendados)")
    ap.add_argument("--network", default="Facebook Reels", help="rede da agenda (padrao: Facebook Reels)")
    ap.add_argument("--mode", choices=["schedule", "draft", "now"], default="schedule",
                    help="schedule = agenda no Postiz na data da agenda; draft = rascunho (nao publica); now = publica ja")
    ap.add_argument("--yes", action="store_true", help="envia de verdade (sem isso: simulacao)")
    ap.add_argument("--list-integrations", action="store_true")
    a = ap.parse_args()

    if a.list_integrations:
        for i in client().integrations():
            print(f"{i.get('id')}  {i.get('identifier'):<12} {i.get('name')}" + ("  (desativado)" if i.get("disabled") else ""))
        return

    spec = NETWORKS.get(a.network.lower())
    if not spec:
        sys.exit(f"rede '{a.network}' ainda nao suportada. Suportadas: {', '.join(NETWORKS)}")
    ident, stype, (dmin, dmax) = spec

    queue, sched = load(OUT / "queue.json", {}), load(OUT / "schedule.json", {"items": {}})
    pubf = OUT / "published.json"
    pub = load(pubf, {})
    cl = client() if a.yes else None
    integ = None
    if a.yes:
        integ = find_integration(cl.integrations(), ident)
        if not integ:
            sys.exit(f"nenhum canal '{ident}' conectado no Postiz. Conecte a pagina e rode --list-integrations.")
        print(f"canal: {integ.get('name')} ({integ['id']})")

    now = datetime.now().astimezone()
    sent = skipped = failed = 0
    for vid, s in sched["items"].items():
        if (a.ids and vid not in a.ids) or a.network not in s["networks"]:
            continue
        it = queue.get(vid)
        why = None
        if not it or it.get("status") != "approved":
            why = "nao esta aprovado (reaprove na revisao)"
        elif a.network in pub.get(vid, {}):
            why = f"ja enviado ({pub[vid][a.network]['postId']})"
        elif not (OUT / it["file"]).exists():
            why = "arquivo mp4 nao existe"
        elif not dmin <= it["duration"] <= dmax:
            why = f"duracao {it['duration']}s fora de {dmin}-{dmax}s"
        elif a.mode == "schedule" and datetime.strptime(s["when"], "%Y-%m-%dT%H:%M").astimezone() <= now:
            why = f"horario {s['when']} ja passou (use --mode draft ou now)"
        if why:
            print(f"[pula] {vid}: {why}"); skipped += 1; continue

        when_iso = local_to_utc_iso(s["when"]) if a.mode == "schedule" else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if not a.yes:
            p = build_payload(it, "<id-do-canal>", stype, {"id": "<upload>", "path": "<upload>"}, when_iso, a.mode)
            print(f"[simula] {vid} -> {a.network} ({a.mode}, {s['when']})\n  arquivo: {it['file']}\n"
                  f"  legenda: {p['posts'][0]['value'][0]['content'][:140]!r}\n  titulo: {p['posts'][0]['settings']['title']!r}")
            continue
        try:
            media = cl.upload(OUT / it["file"])
            res = cl.create_post(build_payload(it, integ["id"], stype, media, when_iso, a.mode))
            pid = res[0]["postId"] if isinstance(res, list) and res else str(res)
            pub.setdefault(vid, {})[a.network] = {"postId": pid, "mode": a.mode, "when": s["when"],
                                                    "sent_at": now.isoformat(timespec="seconds")}
            save(pubf, pub)                                  # grava a cada envio: uma falha depois nao reenvia o que ja foi
            print(f"[ok] {vid} -> {a.network} ({a.mode}) postId={pid}"); sent += 1
        except (PostizError, KeyError, IndexError) as e:
            print(f"[FALHOU] {vid}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{'enviados' if a.yes else 'simulados'}: {sent if a.yes else '-'}  pulados: {skipped}  falhas: {failed}"
          + ("" if a.yes else "  (nada foi enviado; use --yes)"))


if __name__ == "__main__":
    main()
