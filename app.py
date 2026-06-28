#!/usr/bin/env python3
"""
Minha Carreira — backend funcional (Python stdlib, sem dependencias externas).
- SQLite para persistencia
- API JSON em /api/*
- Auth real (signup/login, senha com PBKDF2, sessao por token)
- IA via Claude (API da Anthropic) lendo ANTHROPIC_API_KEY do ambiente
- Serve os arquivos estaticos (index.html, app.html, cockpit.html)

Rodar:  ANTHROPIC_API_KEY=sk-... python3 app.py
        (sem a chave, os endpoints de IA respondem com aviso)
"""
import os, json, sqlite3, secrets, hashlib, urllib.request, urllib.error, urllib.parse, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(ROOT, "minhacarreira.db")
PORT = int(os.environ.get("PORT", "4173"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("MC_MODEL", "claude-sonnet-4-6")
LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
LINKEDIN_REDIRECT = os.environ.get("LINKEDIN_REDIRECT", "http://localhost:4173/api/auth/linkedin/callback")
OAUTH_STATES = set()

# ---------------------------------------------------------------- DB
def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY, email TEXT UNIQUE, name TEXT,
      pw_salt TEXT, pw_hash TEXT, linkedin_sub TEXT, picture TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS profiles(
      user_id INTEGER PRIMARY KEY, objetivo TEXT, setor TEXT, senioridade TEXT,
      voz TEXT, headline TEXT, sobre TEXT,
      respostas INTEGER DEFAULT 0, conversas INTEGER DEFAULT 0, entrevistas INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS ssi_snapshots(
      id INTEGER PRIMARY KEY, user_id INTEGER, score INTEGER,
      marca INTEGER, pessoas INTEGER, insights INTEGER, relacionamentos INTEGER,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS suggestions(
      id INTEGER PRIMARY KEY, user_id INTEGER, secao TEXT, sugestao TEXT, porque TEXT,
      status TEXT DEFAULT 'sugerido', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS threads(
      id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, role TEXT, color TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY, thread_id INTEGER, author TEXT, body TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS jobfit(
      id INTEGER PRIMARY KEY, user_id INTEGER, vaga TEXT, aderencia INTEGER,
      atende TEXT, gaps TEXT, plano TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS leads(
      id INTEGER PRIMARY KEY, email TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    for col in ("linkedin_sub TEXT", "picture TEXT"):
        try: c.execute("ALTER TABLE users ADD COLUMN " + col)
        except Exception: pass
    c.commit(); c.close()

# ---------------------------------------------------------------- auth
def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 100_000).hex()
    return salt, h

def seed_user(c, uid, name):
    # Dados reais começam vazios — nada de SSI/outcomes fictícios.
    c.execute("INSERT INTO profiles(user_id,objetivo,setor,senioridade,voz,headline,sobre,respostas,conversas,entrevistas)"
              " VALUES(?,?,?,?,?,?,?,?,?,?)",
              (uid, "", "", "", "", "", "", 0, 0, 0))
    fname = (name.split()[0] if name else "candidato")
    cur = c.execute("INSERT INTO threads(user_id,name,role,color) VALUES(?,?,?,?)",
              (uid, "Equipe Minha Carreira", "Onboarding", "#0A66C2"))
    tid = cur.lastrowid
    c.execute("INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)",
              (tid, "equipe", f"Bem-vindo, {fname}! Seu cockpit está conectado ao LinkedIn. Próximos passos: informe seu SSI atual em 'Visão geral' → Atualizar (pegue em linkedin.com/sales/ssi) e peça à IA para criar sua headline em 'Meu perfil'."))


# ---------------------------------------------------------------- LinkedIn OAuth
def li_token(code):
    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": LINKEDIN_REDIRECT,
        "client_id": LINKEDIN_CLIENT_ID, "client_secret": LINKEDIN_CLIENT_SECRET}).encode()
    req = urllib.request.Request("https://www.linkedin.com/oauth/v2/accessToken", data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]

def li_userinfo(tok):
    req = urllib.request.Request("https://api.linkedin.com/v2/userinfo")
    req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def upsert_linkedin_user(c, sub, name, email, picture):
    row = None
    if sub:
        row = c.execute("SELECT * FROM users WHERE linkedin_sub=?", (sub,)).fetchone()
    if not row and email:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if row:
        c.execute("UPDATE users SET linkedin_sub=?, picture=?, name=CASE WHEN name='' OR name IS NULL THEN ? ELSE name END WHERE id=?",
                  (sub, picture, name, row["id"]))
        return row["id"]
    cur = c.execute("INSERT INTO users(email,name,linkedin_sub,picture,pw_salt,pw_hash) VALUES(?,?,?,?,?,?)",
                    (email, name, sub, picture, "", ""))
    uid = cur.lastrowid
    seed_user(c, uid, name)
    return uid

# ---------------------------------------------------------------- Claude
def claude(system, user, max_tokens=900):
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY não configurada no ambiente do servidor.")
    body = json.dumps({
        "model": MODEL, "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST")
    req.add_header("x-api-key", ANTHROPIC_API_KEY)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return "".join(p.get("text", "") for p in data.get("content", []))

def claude_json(system, user, max_tokens=900):
    txt = claude(system + " Responda APENAS com JSON válido, sem texto fora do JSON.", user, max_tokens)
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0) if m else txt)

# ---------------------------------------------------------------- HTTP handler
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, obj, code=200):
        out = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def _redirect(self, url):
        self.send_response(302); self.send_header("Location", url); self.end_headers()

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n: return {}
        try: return json.loads(self.rfile.read(n) or b"{}")
        except Exception: return {}

    def _user(self, c):
        tok = (self.headers.get("Authorization", "") or "").replace("Bearer ", "").strip()
        if not tok: return None
        row = c.execute("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?", (tok,)).fetchone()
        return row

    # ----- static
    def _static(self):
        path = self.path.split("?")[0]
        if path == "/": path = "/index.html"
        fn = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not fn.startswith(ROOT) or not os.path.isfile(fn):
            self.send_error(404); return
        ctype = "text/html; charset=utf-8" if fn.endswith(".html") else \
                "application/javascript" if fn.endswith(".js") else \
                "text/css" if fn.endswith(".css") else "application/octet-stream"
        with open(fn, "rb") as f: data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if not self.path.startswith("/api/"): return self._static()
        c = db()
        try: self.route_get(c)
        except Exception as e: self._json({"error": str(e)}, 500)
        finally: c.close()

    def do_POST(self): self._dispatch("POST")
    def do_PUT(self): self._dispatch("PUT")

    def _dispatch(self, method):
        if not self.path.startswith("/api/"): return self.send_error(404)
        c = db()
        try: self.route_write(c, method)
        except Exception as e: self._json({"error": str(e)}, 500)
        finally: c.commit(); c.close()

    # ----- GET routes
    def route_get(self, c):
        p = self.path.split("?")[0]

        if p == "/api/auth/linkedin/start":
            if not LINKEDIN_CLIENT_ID:
                return self._redirect("/app.html?error=linkedin_off")
            st = secrets.token_urlsafe(16); OAUTH_STATES.add(st)
            url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
                "response_type": "code", "client_id": LINKEDIN_CLIENT_ID,
                "redirect_uri": LINKEDIN_REDIRECT, "scope": "openid profile email", "state": st})
            return self._redirect(url)

        if p == "/api/auth/linkedin/callback":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = (q.get("code") or [""])[0]
            OAUTH_STATES.discard((q.get("state") or [""])[0])
            if not code:
                return self._redirect("/app.html?error=linkedin_denied")
            try:
                info = li_userinfo(li_token(code))
            except Exception:
                return self._redirect("/app.html?error=linkedin_fail")
            uid = upsert_linkedin_user(c, info.get("sub", ""), info.get("name", ""),
                                       (info.get("email") or "").strip().lower(), info.get("picture", ""))
            sess = secrets.token_urlsafe(32)
            c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (sess, uid)); c.commit()
            return self._redirect("/app.html?token=" + sess)

        u = self._user(c)
        if p == "/api/me":
            if not u: return self._json({"error": "unauth"}, 401)
            pr = c.execute("SELECT * FROM profiles WHERE user_id=?", (u["id"],)).fetchone()
            return self._json({"user": {"id": u["id"], "name": u["name"], "email": u["email"],
                                        "picture": (u["picture"] if "picture" in u.keys() else "")},
                               "profile": dict(pr) if pr else {}})
        if p == "/api/overview":
            if not u: return self._json({"error": "unauth"}, 401)
            return self._json(self.overview(c, u))
        if p == "/api/threads":
            if not u: return self._json({"error": "unauth"}, 401)
            return self._json({"threads": self.threads(c, u)})
        if p == "/api/messages":
            if not u: return self._json({"error": "unauth"}, 401)
            tid = self.path.split("thread=")[-1]
            rows = c.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY id", (tid,)).fetchall()
            return self._json({"messages": [dict(r) for r in rows]})
        return self._json({"error": "not found"}, 404)

    def overview(self, c, u):
        s = c.execute("SELECT * FROM ssi_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 1", (u["id"],)).fetchone()
        pr = c.execute("SELECT * FROM profiles WHERE user_id=?", (u["id"],)).fetchone()
        return {"ssi": dict(s) if s else {}, "profile": dict(pr) if pr else {},
                "threads": self.threads(c, u), "ai_enabled": bool(ANTHROPIC_API_KEY)}

    def threads(self, c, u):
        out = []
        for t in c.execute("SELECT * FROM threads WHERE user_id=? ORDER BY id", (u["id"],)).fetchall():
            last = c.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY id DESC LIMIT 1", (t["id"],)).fetchone()
            d = dict(t); d["last"] = dict(last) if last else None
            d["msgs"] = [dict(m) for m in c.execute("SELECT * FROM messages WHERE thread_id=? ORDER BY id", (t["id"],)).fetchall()]
            out.append(d)
        return out

    # ----- write routes
    def route_write(self, c, method):
        p = self.path.split("?")[0]
        b = self._body()

        if p == "/api/signup":
            email = (b.get("email") or "").strip().lower(); name = (b.get("name") or "").strip()
            pw = b.get("password") or ""
            if not email or not pw: return self._json({"error": "email e senha obrigatórios"}, 400)
            if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                return self._json({"error": "e-mail já cadastrado"}, 409)
            salt, h = hash_pw(pw)
            cur = c.execute("INSERT INTO users(email,name,pw_salt,pw_hash) VALUES(?,?,?,?)", (email, name, salt, h))
            uid = cur.lastrowid; seed_user(c, uid, name)
            tok = secrets.token_urlsafe(32)
            c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (tok, uid))
            return self._json({"token": tok, "user": {"id": uid, "name": name, "email": email}})

        if p == "/api/login":
            email = (b.get("email") or "").strip().lower(); pw = b.get("password") or ""
            row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not row: return self._json({"error": "credenciais inválidas"}, 401)
            _, h = hash_pw(pw, row["pw_salt"])
            if h != row["pw_hash"]: return self._json({"error": "credenciais inválidas"}, 401)
            tok = secrets.token_urlsafe(32)
            c.execute("INSERT INTO sessions(token,user_id) VALUES(?,?)", (tok, row["id"]))
            return self._json({"token": tok, "user": {"id": row["id"], "name": row["name"], "email": row["email"]}})

        if p == "/api/lead":
            c.execute("INSERT INTO leads(email) VALUES(?)", ((b.get("email") or "").strip().lower(),))
            return self._json({"ok": True})

        # ----- auth required below
        u = self._user(c)
        if not u: return self._json({"error": "unauth"}, 401)

        if p == "/api/logout":
            tok = (self.headers.get("Authorization", "") or "").replace("Bearer ", "").strip()
            c.execute("DELETE FROM sessions WHERE token=?", (tok,)); return self._json({"ok": True})

        if p == "/api/profile" and method == "PUT":
            fields = {k: b[k] for k in ("objetivo", "setor", "senioridade", "voz", "headline", "sobre") if k in b}
            if fields:
                sets = ",".join(f"{k}=?" for k in fields)
                c.execute(f"UPDATE profiles SET {sets} WHERE user_id=?", (*fields.values(), u["id"]))
            return self._json({"ok": True})

        if p == "/api/ssi/refresh":
            vals = {k: int(b.get(k, 0)) for k in ("marca", "pessoas", "insights", "relacionamentos")}
            total = sum(vals.values())
            c.execute("INSERT INTO ssi_snapshots(user_id,score,marca,pessoas,insights,relacionamentos) VALUES(?,?,?,?,?,?)",
                      (u["id"], total, vals["marca"], vals["pessoas"], vals["insights"], vals["relacionamentos"]))
            return self._json({"ok": True, "score": total, **vals})

        if p == "/api/ai/improve":
            pr = c.execute("SELECT * FROM profiles WHERE user_id=?", (u["id"],)).fetchone()
            secao = b.get("section", "headline")
            ctx = f"Setor: {pr['setor']}. Senioridade: {pr['senioridade']}. Objetivo: {pr['objetivo']}. Headline atual: {pr['headline']}. Sobre atual: {pr['sobre'] or '(vazio)'}."
            sysp = ("Você é um copiloto de carreira que melhora perfis de LinkedIn em português do Brasil e ENSINA o porquê. "
                    "Gere uma sugestão concreta e curta para a seção pedida, com a voz autêntica do profissional. "
                    'Campos do JSON: {"sugestao": "...", "porque": "explicação curta do raciocínio"}')
            usr = f"Seção a melhorar: {secao}. Contexto do profissional: {ctx}. Texto atual: {b.get('current','')}"
            try: out = claude_json(sysp, usr, 700)
            except Exception as e: return self._json({"error": str(e)}, 502)
            c.execute("INSERT INTO suggestions(user_id,secao,sugestao,porque) VALUES(?,?,?,?)",
                      (u["id"], secao, out.get("sugestao", ""), out.get("porque", "")))
            return self._json(out)

        if p == "/api/profile/apply":
            secao = b.get("section"); val = b.get("value", "")
            if secao in ("headline", "sobre"):
                c.execute(f"UPDATE profiles SET {secao}=? WHERE user_id=?", (val, u["id"]))
            return self._json({"ok": True})

        if p == "/api/ai/jobfit":
            pr = c.execute("SELECT * FROM profiles WHERE user_id=?", (u["id"],)).fetchone()
            sysp = ("Você atua como um recrutador profissional. Cruze a vaga com o perfil do candidato e avalie a aderência em PT-BR. "
                    'Campos do JSON: {"aderencia": <0-100 int>, "atende": ["..."], "gaps": ["..."], "plano": ["passo 1","passo 2","passo 3"]}')
            usr = f"VAGA:\n{b.get('vaga','')}\n\nPERFIL DO CANDIDATO:\nHeadline: {pr['headline']}\nSobre: {pr['sobre']}\nSetor: {pr['setor']}\nSenioridade: {pr['senioridade']}\nObjetivo: {pr['objetivo']}"
            try: out = claude_json(sysp, usr, 1100)
            except Exception as e: return self._json({"error": str(e)}, 502)
            c.execute("INSERT INTO jobfit(user_id,vaga,aderencia,atende,gaps,plano) VALUES(?,?,?,?,?,?)",
                      (u["id"], b.get("vaga", ""), int(out.get("aderencia", 0)),
                       json.dumps(out.get("atende", [])), json.dumps(out.get("gaps", [])), json.dumps(out.get("plano", []))))
            return self._json(out)

        if p == "/api/ai/post":
            pr = c.execute("SELECT * FROM profiles WHERE user_id=?", (u["id"],)).fetchone()
            sysp = "Você é um copiloto que escreve posts de LinkedIn em PT-BR com a voz autêntica do profissional, focados em autoridade e resultado (sem clichê). Devolva só o texto do post."
            usr = f"Tema: {b.get('topic','')}. Tom: {b.get('tone','profissional e direto')}. Setor: {pr['setor']}. Senioridade: {pr['senioridade']}."
            try: post = claude(sysp, usr, 700)
            except Exception as e: return self._json({"error": str(e)}, 502)
            return self._json({"post": post})

        if p == "/api/messages":
            tid = b.get("thread"); body = (b.get("body") or "").strip()
            if not body: return self._json({"error": "vazio"}, 400)
            c.execute("INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)", (tid, "candidato", body))
            return self._json({"ok": True})

        if p == "/api/team-message":
            tid = b.get("thread"); body = (b.get("body") or "").strip()
            if not tid:
                t = c.execute("SELECT id FROM threads WHERE user_id=? AND role='Onboarding' LIMIT 1", (u["id"],)).fetchone()
                tid = t["id"] if t else None
            if not body or not tid: return self._json({"error": "vazio"}, 400)
            c.execute("INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)", (tid, "equipe", body))
            return self._json({"ok": True})

        return self._json({"error": "not found"}, 404)


def main():
    init_db()
    print(f"Minha Carreira rodando em http://localhost:{PORT}")
    print(f"  IA Claude: {'ATIVA (' + MODEL + ')' if ANTHROPIC_API_KEY else 'inativa — defina ANTHROPIC_API_KEY'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()

if __name__ == "__main__":
    main()
