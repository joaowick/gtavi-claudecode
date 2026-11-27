"""Avisos no Telegram (piloto).

    python -I notify.py --test            manda uma mensagem de teste
    python -I notify.py --check           confere o estado dos posts enviados ao Postiz e avisa PUBLISHED/ERROR (uma vez cada)
    python -I notify.py --watch [--every 120]   repete o --check ate Ctrl+C

Config (env ou viral/postiz/.env, fora do git): TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
O estado vem do banco do Postiz (docker exec postiz-postgres), como descrito em CLAUDE.md.
"""
import argparse, json, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from publish import OUT, load, save, setting  # noqa: E402


def send(text):
    """Manda texto ao Telegram. Nunca levanta: aviso nao pode derrubar a publicacao. Retorna True/False."""
    tok, chat = setting("TELEGRAM_BOT_TOKEN"), setting("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("[telegram] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nao configurados; aviso ignorado")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        try:
            desc = json.loads(e.read().decode("utf-8")).get("description", "")
        except Exception:  # noqa: BLE001
            desc = ""
        dica = {401: "token invalido (confira TELEGRAM_BOT_TOKEN)",
                400: "chat nao encontrado: mande uma mensagem ao bot primeiro e confira TELEGRAM_CHAT_ID",
                403: "o bot foi bloqueado ou nunca iniciado: abra o bot e toque em Start",
                404: "token com formato errado (deve ser 123456:ABC..., sem aspas nem 'bot' na frente)"}.get(e.code, "")
        print(f"[telegram] HTTP {e.code} {desc} {dica}".strip())
        return False
    except Exception as e:  # noqa: BLE001
        print(f"[telegram] falhou:{type(e).__name__}")  # sem str(e): a URL carrega o token
        return False


def post_states(ids):
    """{postId: (state, releaseURL)} lido do Postgres do Postiz."""
    if not ids:
        return {}
    lst = ",".join("'" + i.replace("'", "") + "'" for i in ids)
    q = f"select id, state, coalesce(\"releaseURL\", '') from \"Post\" where id in ({lst})"
    out = subprocess.run(["docker", "exec", "postiz-postgres", "psql", "-U", "postiz-user", "-d", "postiz-db-local",
                          "-At", "-F", "|", "-c", q], capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError("docker/psql falhou: " + out.stderr.strip()[:200])
    res = {}
    for line in out.stdout.splitlines():
        pid, state, url = (line.split("|") + ["", ""])[:3]
        res[pid] = (state, url)
    return res


def check():
    pubf = OUT / "published.json"
    pub = load(pubf, {})
    todo = {e["postId"]: (vid, net, e) for vid, nets in pub.items() for net, e in nets.items()
            if e.get("mode") != "draft" and not e.get("notified")}
    if not todo:
        return 0
    states = post_states(list(todo))
    n = 0
    for pid, (vid, net, e) in todo.items():
        state, url = states.get(pid, (None, ""))
        if state == "PUBLISHED":
            msg = f"✅ Publicado ({net})\n{vid}\n{url}".strip()
        elif state == "ERROR":
            msg = f"❌ ERRO ao publicar ({net})\n{vid}\nPost {pid}: confira no Postiz e limpe a entrada em published.json antes de tentar de novo."
        else:
            continue                      # QUEUE/ainda nao saiu: tenta na proxima
        if send(msg):
            e["notified"] = state
            save(pubf, pub)
            n += 1
    return n


def main():
    if sys.stdout:                      # pythonw (tarefa agendada) nao tem stdout
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--every", type=int, default=120, help="segundos entre checagens no --watch")
    a = ap.parse_args()
    if a.test:
        print("enviado" if send("🔔 GTA6Viral: teste de notificacao OK") else "NAO enviado")
    elif a.check:
        print(f"avisos enviados: {check()}")
    elif a.watch:
        print(f"observando a cada {a.every}s (Ctrl+C para sair)")
        while True:
            try:
                n = check()
                if n:
                    print(f"{time.strftime('%H:%M')} avisos: {n}")
            except Exception as e:  # noqa: BLE001
                print(f"{time.strftime('%H:%M')} erro: {e}")
            time.sleep(a.every)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
