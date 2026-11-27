r"""Servidor local do editor da folha de revisao.

Uso: python serve.py [--port 8765] [--open]

- Escuta SO em 127.0.0.1 (nao acessivel de outros computadores).
- A pagina leva um token; POST /api/apply/<id> sem o token certo e recusado (impede que outro site
  aberto no seu navegador mande pedidos para ca). O Host tambem e checado (anti DNS-rebinding).
- /api/apply refaz so o video indicado, a partir do que esta salvo em output/queue.json.
"""
import argparse, copy, json, mimetypes, os, re, secrets, shutil, sys, threading, webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).parent))   # python -I nao inclui a pasta do script
import agenda as A
import backlog as B
import pipeline as P
import review as R

OUT = P.OUT
QFILE = OUT / "queue.json"
SCHED_FILE = OUT / "schedule.json"
SCHED_LOCK = threading.Lock()          # a agenda nao espera um render terminar
TOKEN = secrets.token_urlsafe(24)
ACCESS_KEY = ""   # preenchido por --tunnel
LOCK = threading.Lock()                  # um render por vez (ffmpeg e pesado)
SERVE_EXT = {".mp4", ".png", ".jpg", ".jpeg", ".html"}
MAX_BODY = 60_000
EMOJI_OK = {0xFE0F, 0x200D}


def load_queue():
    return json.loads(QFILE.read_text(encoding="utf-8"))


def load_sched():
    try:
        return A.norm_sched(json.loads(SCHED_FILE.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return A.norm_sched(None)


def save_sched(s):
    tmp = SCHED_FILE.with_name("schedule.tmp.json")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SCHED_FILE)


def schedule_action(body):
    with SCHED_LOCK:
        q, s = load_queue(), load_sched()
        msg = A.apply_action(s, q, body)
        save_sched(s)
        return {"ok": True, "message": msg, "schedule": s, "videos": A.videos_view(q, s)}


def backlog_action(body):
    with SCHED_LOCK:
        d = B.load()
        msg = B.apply_action(d, body)
        B.save(d)
        return {"ok": True, "message": msg, "backlog": d}


def save_queue(q):
    shutil.copyfile(QFILE, QFILE.with_name("queue.bak.json"))      # backup antes de cada gravacao
    tmp = QFILE.with_name("queue.tmp.json")
    tmp.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, QFILE)


# ---------- validacao dos campos editaveis ----------
def line(s, n):
    return P.font_safe(str(s))[:n].strip()


def lines(arr, count, n, upper=False):
    if not isinstance(arr, list):
        raise ValueError("lista de linhas invalida")
    out = [line(x, n) for x in arr[:count]]
    out = [x.upper() if upper else x for x in out if x]
    return out


def emoji_only(s):
    s = str(s)[:12]
    return "".join(ch for ch in s if ord(ch) >= 0x2190 or ord(ch) in EMOJI_OK)


def clean_caption(s):
    s = str(s)[:2200]
    return "".join(ch for ch in s if ch == "\n" or ord(ch) >= 32).strip()


EDIT_FIELDS = ("text_pt", "emoji_pt", "bottom_text_pt", "hook_pt", "caption_pt", "profile", "cover")


def dropped(warns, label, raw, clean):
    """Avisa quais caracteres digitados foram removidos (a fonte nao desenha), em vez de sumir em silencio."""
    raw = "".join(raw) if isinstance(raw, list) else str(raw)
    clean = "".join(clean) if isinstance(clean, list) else str(clean)
    gone = sorted({ch for ch in raw if not ch.isspace() and ch not in clean})
    if gone:
        warns.append(f"{label}: removi {' '.join(gone)} (so o texto do cabecalho e o campo Emoji aceitam emoji)")


def log_edit(vid, changes, warns):
    rec = {"ts": datetime.now().isoformat(timespec="seconds"), "id": vid, "changes": changes, "warnings": warns}
    sys.stderr.write("EDIT " + json.dumps(rec, ensure_ascii=False) + "\n")
    with open(OUT / "edits.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def apply_fields(item, body, warns):
    """Aplica os campos validados em `item` (copia). Levanta ValueError se algo for invalido."""
    if not isinstance(body, dict):
        raise ValueError("corpo invalido")
    it = item
    raw = str(body.get("text_pt", ""))[:300]
    it["text_pt"] = P.header_safe(raw)[:300]                     # aceita emoji em qualquer posicao
    dropped(warns, "texto do cabecalho", raw, it["text_pt"])
    if not it["text_pt"]:
        it.pop("text_pt")
    emo = emoji_only(body.get("emoji_pt", ""))
    it["emoji_pt"] = emo
    if not emo:
        it.pop("emoji_pt")
    bt = line(body.get("bottom_text_pt", ""), 60)
    dropped(warns, "frase embaixo", body.get("bottom_text_pt", ""), bt)
    it["bottom_text_pt"] = bt
    if not bt:
        it.pop("bottom_text_pt")
    if it.get("cover"):
        it["cover"][0]["text"] = lines(body.get("cover_text", []), 2, 32)
        dropped(warns, "texto da tarja", body.get("cover_text", []), it["cover"][0]["text"])
    hp = lines(body.get("hook_pt", []), 3, 24, upper=True)
    dropped(warns, "gancho", body.get("hook_pt", []), hp)
    if hp:
        it["hook_pt"] = hp
    else:
        it.pop("hook_pt", None)
    if not it.get("text_pt") and not it.get("hook_pt"):
        raise ValueError("preencha o texto do cabecalho ou o gancho: o video ficaria sem texto")
    it["caption_pt"] = clean_caption(body.get("caption_pt", ""))
    name, handle = line(body.get("name", ""), 30), line(body.get("handle", ""), 30)
    dropped(warns, "nome", body.get("name", ""), name)
    dropped(warns, "@ do perfil", body.get("handle", ""), handle)
    if handle and not handle.startswith("@"):
        handle = "@" + handle
    if name or handle:
        prof = R.profile_defaults()
        it["profile"] = {"name": name or prof.get("name", ""), "handle": handle or prof.get("handle", "")}
    return it


def apply_edit(vid, body):
    with LOCK:
        q = load_queue()
        if vid not in q:
            raise KeyError(vid)
        warns = []
        item = apply_fields(copy.deepcopy(q[vid]), body, warns)
        tmp = OUT / f"{vid}.tmp.mp4"
        try:
            P.rebuild(vid, item, out=tmp)
            os.replace(tmp, OUT / item["file"])
        finally:
            tmp.unlink(missing_ok=True)
        item["status"] = "pending_review"
        item["edited_at"] = datetime.now().isoformat(timespec="seconds")
        changes = {k: [q[vid].get(k), item.get(k)] for k in EDIT_FIELDS if q[vid].get(k) != item.get(k)}
        log_edit(vid, changes, warns)
        q[vid] = item
        save_queue(q)
        return {"ok": True, "version": int((OUT / item["file"]).stat().st_mtime), "edit": R.edit_view(item),
                "hook": R.display_hook(item), "caption": item.get("caption_pt") or item["caption"],
                "search": R.search_text(vid, item), "warnings": warns}


# ---------- HTTP ----------
class Handler(BaseHTTPRequestHandler):
    server_version = "gta6-review"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def host_ok(self):
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return True
        # modo tunel (--tunnel): aceita o host *.trycloudflare.com, mas so com o segredo de acesso
        return bool(ACCESS_KEY) and host.lower().endswith(".trycloudflare.com") and self.tunnel_authed()

    def is_local(self):
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def tunnel_authed(self):
        m = re.search(r"(?:^|;\s*)gta_access=([\w\-]+)", self.headers.get("Cookie", ""))
        return bool(m) and secrets.compare_digest(m.group(1), ACCESS_KEY)

    def send_json(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if ACCESS_KEY and not self.is_local() and self.headers.get("Host", "").lower().endswith(".trycloudflare.com"):
            k = parse_qs(u.query).get("k", [""])[0]
            if k and secrets.compare_digest(k, ACCESS_KEY):   # 1o acesso: grava o cookie e limpa o segredo da URL
                self.send_response(302)
                self.send_header("Set-Cookie", f"gta_access={ACCESS_KEY}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=86400")
                self.send_header("Location", u.path or "/")
                self.send_header("Content-Length", "0")
                return self.end_headers()
        if not self.host_ok():
            return self.send_json(403, {"ok": False, "error": "host nao permitido"})
        path = unquote(u.path)
        if path in ("/", "/review.html"):
            data = R.build_page(load_queue(), token=TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)
        if path == "/agenda":
            data = A.build_page(load_queue(), load_sched(), TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)
        if path == "/backlog":
            data = B.build_page(TOKEN).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(data)
        f = (OUT / path.lstrip("/")).resolve()
        if OUT.resolve() not in f.parents or f.suffix.lower() not in SERVE_EXT or not f.is_file():
            return self.send_json(404, {"ok": False, "error": "nao encontrado"})
        self.serve_file(f)

    def serve_file(self, f):
        size = f.stat().st_size
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):                 # suporte a Range: o player precisa p/ avancar o video
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(size - int(m.group(2)), 0)
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(f, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass                                              # player fechou a conexao no meio

    def read_body(self):
        """Checa token, tipo e tamanho e devolve o JSON do corpo. Em falha responde o erro e devolve None."""
        if not secrets.compare_digest(self.headers.get("X-Token", ""), TOKEN):
            self.send_json(403, {"ok": False, "error": "token invalido: recarregue a pagina (F5)"})
            return None
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self.send_json(415, {"ok": False, "error": "use application/json"})
            return None
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if not 0 < n <= MAX_BODY:
            self.send_json(413, {"ok": False, "error": "pedido grande demais"})
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            self.send_json(400, {"ok": False, "error": "JSON invalido"})
            return None

    def do_POST(self):
        if not self.host_ok():
            return self.send_json(403, {"ok": False, "error": "host nao permitido"})
        path = unquote(urlparse(self.path).path)
        m = re.fullmatch(r"/api/apply/([\w\-]{1,40})", path)
        if not m and path not in ("/api/schedule", "/api/backlog"):
            return self.send_json(404, {"ok": False, "error": "rota inexistente"})
        body = self.read_body()
        if body is None:
            return
        try:
            if m:
                res = apply_edit(m.group(1), body)
            elif path == "/api/backlog":
                res = backlog_action(body)
            else:
                res = schedule_action(body)
            self.send_json(200, res)
        except KeyError:
            self.send_json(404, {"ok": False, "error": "video nao encontrado"})
        except ValueError as e:
            self.send_json(400, {"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001 - nao vaza detalhes internos para o navegador
            sys.stderr.write(f"erro em {path}: {type(e).__name__}: {e}\n")
            self.send_json(500, {"ok": False, "error": "falha ao processar (veja o terminal do servidor)"})


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # o log mostra emoji sem quebrar o console
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--tunnel", action="store_true",
                    help="aceita acesso via tunel *.trycloudflare.com, protegido por um segredo (?k=...)")
    a = ap.parse_args()
    global ACCESS_KEY
    if a.tunnel:
        ACCESS_KEY = secrets.token_urlsafe(18)
        print(f"Segredo de acesso do tunel: {ACCESS_KEY}\n"
              f"Abra no celular: https://<host-do-tunel>/?k={ACCESS_KEY}")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Editor em {url}  (Ctrl+C para parar)")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")


if __name__ == "__main__":
    main()
