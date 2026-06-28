// Backend serverless do Minha Carreira — Cloudflare Pages Function + D1.
// Porta o app.py (Python) para JS. Bind do D1 = "DB". Segredos via env (painel da Cloudflare).

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json; charset=utf-8" } });
const redirect = (loc) => new Response(null, { status: 302, headers: { Location: loc } });
const hex = (buf) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (h) => new Uint8Array(h.match(/.{1,2}/g).map((b) => parseInt(b, 16)));
const newToken = () => hex(crypto.getRandomValues(new Uint8Array(24)));

async function pbkdf2(pw, saltBytes) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(pw), "PBKDF2", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits({ name: "PBKDF2", salt: saltBytes, iterations: 100000, hash: "SHA-256" }, key, 256);
  return hex(bits);
}
async function hashPw(pw) { const salt = crypto.getRandomValues(new Uint8Array(16)); return { salt: hex(salt), hash: await pbkdf2(pw, salt) }; }
async function verifyPw(pw, saltHex, hashHex) { return (await pbkdf2(pw, unhex(saltHex))) === hashHex; }

async function userFromAuth(env, request) {
  const tok = (request.headers.get("Authorization") || "").replace("Bearer ", "").trim();
  if (!tok) return null;
  return await env.DB.prepare("SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?").bind(tok).first();
}

async function seedUser(env, uid, name) {
  const fname = (name || "").split(" ")[0] || "candidato";
  await env.DB.prepare("INSERT INTO profiles(user_id,objetivo,setor,senioridade,voz,headline,sobre,respostas,conversas,entrevistas) VALUES(?,?,?,?,?,?,?,0,0,0)")
    .bind(uid, "", "", "", "", "", "").run();
  const t = await env.DB.prepare("INSERT INTO threads(user_id,name,role,color) VALUES(?,?,?,?)")
    .bind(uid, "Equipe Minha Carreira", "Onboarding", "#0A66C2").run();
  await env.DB.prepare("INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)")
    .bind(t.meta.last_row_id, "equipe",
      `Bem-vindo, ${fname}! Seu cockpit está conectado ao LinkedIn. Informe seu SSI em 'Visão geral' → Atualizar (pegue em linkedin.com/sales/ssi) e peça à IA para criar sua headline em 'Meu perfil'.`).run();
}

async function ai(env, system, user, maxTokens = 900) {
  if (!env.AI) throw new Error("Workers AI (binding 'AI') não configurado no servidor.");
  const model = env.AI_MODEL || "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
  const resp = await env.AI.run(model, {
    messages: [{ role: "system", content: system }, { role: "user", content: user }],
    max_tokens: maxTokens,
  });
  return (resp && (resp.response || resp.result)) || "";
}
async function aiJson(env, system, user, maxTokens = 1000) {
  const txt = await ai(env, system + " Responda APENAS com JSON válido, sem nenhum texto fora do JSON.", user, maxTokens);
  const m = txt.match(/\{[\s\S]*\}/);
  return JSON.parse(m ? m[0] : txt);
}

async function overview(env, u) {
  const s = await env.DB.prepare("SELECT * FROM ssi_snapshots WHERE user_id=? ORDER BY id DESC LIMIT 1").bind(u.id).first();
  const pr = await env.DB.prepare("SELECT * FROM profiles WHERE user_id=?").bind(u.id).first();
  return { ssi: s || {}, profile: pr || {}, threads: await listThreads(env, u), ai_enabled: !!env.AI };
}
async function listThreads(env, u) {
  const { results } = await env.DB.prepare("SELECT * FROM threads WHERE user_id=? ORDER BY id").bind(u.id).all();
  const out = [];
  for (const t of results || []) {
    const msgs = (await env.DB.prepare("SELECT * FROM messages WHERE thread_id=? ORDER BY id").bind(t.id).all()).results || [];
    out.push({ ...t, last: msgs.length ? msgs[msgs.length - 1] : null, msgs });
  }
  return out;
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);
  const p = url.pathname;
  const method = request.method;
  const redirectUri = env.LINKEDIN_REDIRECT || url.origin + "/api/auth/linkedin/callback";

  try {
    // ---------- LinkedIn OAuth ----------
    if (p === "/api/auth/linkedin/start") {
      if (!env.LINKEDIN_CLIENT_ID) return redirect("/app.html?error=linkedin_off");
      const u = "https://www.linkedin.com/oauth/v2/authorization?" + new URLSearchParams({
        response_type: "code", client_id: env.LINKEDIN_CLIENT_ID, redirect_uri: redirectUri,
        scope: "openid profile email", state: newToken(),
      });
      return redirect(u);
    }
    if (p === "/api/auth/linkedin/callback") {
      const code = url.searchParams.get("code");
      if (!code) return redirect("/app.html?error=linkedin_denied");
      let info;
      try {
        const tr = await fetch("https://www.linkedin.com/oauth/v2/accessToken", {
          method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
          body: new URLSearchParams({ grant_type: "authorization_code", code, redirect_uri: redirectUri, client_id: env.LINKEDIN_CLIENT_ID, client_secret: env.LINKEDIN_CLIENT_SECRET }),
        });
        const tj = await tr.json();
        const ur = await fetch("https://api.linkedin.com/v2/userinfo", { headers: { Authorization: "Bearer " + tj.access_token } });
        info = await ur.json();
      } catch (e) { return redirect("/app.html?error=linkedin_fail"); }
      const sub = info.sub || "", email = (info.email || "").toLowerCase(), name = info.name || "", pic = info.picture || "";
      let row = sub ? await env.DB.prepare("SELECT * FROM users WHERE linkedin_sub=?").bind(sub).first() : null;
      if (!row && email) row = await env.DB.prepare("SELECT * FROM users WHERE email=?").bind(email).first();
      let uid;
      if (row) {
        uid = row.id;
        await env.DB.prepare("UPDATE users SET linkedin_sub=?, picture=?, name=CASE WHEN name='' OR name IS NULL THEN ? ELSE name END WHERE id=?").bind(sub, pic, name, uid).run();
      } else {
        const r = await env.DB.prepare("INSERT INTO users(email,name,linkedin_sub,picture,pw_salt,pw_hash) VALUES(?,?,?,?,?,?)").bind(email, name, sub, pic, "", "").run();
        uid = r.meta.last_row_id; await seedUser(env, uid, name);
      }
      const tok = newToken();
      await env.DB.prepare("INSERT INTO sessions(token,user_id) VALUES(?,?)").bind(tok, uid).run();
      return redirect("/app.html?token=" + tok);
    }

    const body = (method === "POST" || method === "PUT") ? await request.json().catch(() => ({})) : {};

    // ---------- público ----------
    if (p === "/api/signup") {
      const email = (body.email || "").trim().toLowerCase(), name = (body.name || "").trim(), pw = body.password || "";
      if (!email || !pw) return json({ error: "email e senha obrigatórios" }, 400);
      if (await env.DB.prepare("SELECT 1 FROM users WHERE email=?").bind(email).first()) return json({ error: "e-mail já cadastrado" }, 409);
      const { salt, hash } = await hashPw(pw);
      const r = await env.DB.prepare("INSERT INTO users(email,name,pw_salt,pw_hash) VALUES(?,?,?,?)").bind(email, name, salt, hash).run();
      const uid = r.meta.last_row_id; await seedUser(env, uid, name);
      const tok = newToken();
      await env.DB.prepare("INSERT INTO sessions(token,user_id) VALUES(?,?)").bind(tok, uid).run();
      return json({ token: tok, user: { id: uid, name, email } });
    }
    if (p === "/api/login") {
      const email = (body.email || "").trim().toLowerCase(), pw = body.password || "";
      const row = await env.DB.prepare("SELECT * FROM users WHERE email=?").bind(email).first();
      if (!row || !row.pw_hash) return json({ error: "credenciais inválidas" }, 401);
      if (!(await verifyPw(pw, row.pw_salt, row.pw_hash))) return json({ error: "credenciais inválidas" }, 401);
      const tok = newToken();
      await env.DB.prepare("INSERT INTO sessions(token,user_id) VALUES(?,?)").bind(tok, row.id).run();
      return json({ token: tok, user: { id: row.id, name: row.name, email: row.email } });
    }
    if (p === "/api/lead") {
      await env.DB.prepare("INSERT INTO leads(email) VALUES(?)").bind((body.email || "").trim().toLowerCase()).run();
      return json({ ok: true });
    }

    // ---------- GET autenticado (sem corpo) ----------
    const u = await userFromAuth(env, request);
    if (p === "/api/me") {
      if (!u) return json({ error: "unauth" }, 401);
      const pr = await env.DB.prepare("SELECT * FROM profiles WHERE user_id=?").bind(u.id).first();
      return json({ user: { id: u.id, name: u.name, email: u.email, picture: u.picture || "" }, profile: pr || {} });
    }
    if (p === "/api/overview") { if (!u) return json({ error: "unauth" }, 401); return json(await overview(env, u)); }
    if (p === "/api/threads") { if (!u) return json({ error: "unauth" }, 401); return json({ threads: await listThreads(env, u) }); }
    if (p === "/api/messages" && method === "GET") {
      if (!u) return json({ error: "unauth" }, 401);
      const tid = url.searchParams.get("thread");
      const { results } = await env.DB.prepare("SELECT * FROM messages WHERE thread_id=? ORDER BY id").bind(tid).all();
      return json({ messages: results || [] });
    }

    if (!u) return json({ error: "unauth" }, 401);

    // ---------- escrita autenticada ----------
    if (p === "/api/logout") {
      const tok = (request.headers.get("Authorization") || "").replace("Bearer ", "").trim();
      await env.DB.prepare("DELETE FROM sessions WHERE token=?").bind(tok).run();
      return json({ ok: true });
    }
    if (p === "/api/profile" && method === "PUT") {
      const fields = ["objetivo", "setor", "senioridade", "voz", "headline", "sobre"].filter((k) => k in body);
      if (fields.length) {
        const sets = fields.map((k) => k + "=?").join(",");
        await env.DB.prepare(`UPDATE profiles SET ${sets} WHERE user_id=?`).bind(...fields.map((k) => body[k]), u.id).run();
      }
      return json({ ok: true });
    }
    if (p === "/api/ssi/refresh") {
      const v = { marca: +body.marca || 0, pessoas: +body.pessoas || 0, insights: +body.insights || 0, relacionamentos: +body.relacionamentos || 0 };
      const total = v.marca + v.pessoas + v.insights + v.relacionamentos;
      await env.DB.prepare("INSERT INTO ssi_snapshots(user_id,score,marca,pessoas,insights,relacionamentos) VALUES(?,?,?,?,?,?)").bind(u.id, total, v.marca, v.pessoas, v.insights, v.relacionamentos).run();
      return json({ ok: true, score: total, ...v });
    }
    if (p === "/api/profile/apply") {
      const sec = body.section;
      if (sec === "headline" || sec === "sobre") await env.DB.prepare(`UPDATE profiles SET ${sec}=? WHERE user_id=?`).bind(body.value || "", u.id).run();
      return json({ ok: true });
    }
    if (p === "/api/ai/improve") {
      const pr = await env.DB.prepare("SELECT * FROM profiles WHERE user_id=?").bind(u.id).first();
      const sec = body.section || "headline";
      const sys = 'Você é um copiloto de carreira que melhora perfis de LinkedIn em PT-BR e ENSINA o porquê. Gere uma sugestão concreta e curta para a seção pedida, com a voz autêntica do profissional. Campos do JSON: {"sugestao":"...","porque":"..."}';
      const usr = `Seção: ${sec}. Setor: ${pr.setor}. Senioridade: ${pr.senioridade}. Objetivo: ${pr.objetivo}. Headline atual: ${pr.headline}. Sobre atual: ${pr.sobre || "(vazio)"}. Texto atual: ${body.current || ""}`;
      let out; try { out = await aiJson(env, sys, usr, 700); } catch (e) { return json({ error: e.message }, 502); }
      await env.DB.prepare("INSERT INTO suggestions(user_id,secao,sugestao,porque) VALUES(?,?,?,?)").bind(u.id, sec, out.sugestao || "", out.porque || "").run();
      return json(out);
    }
    if (p === "/api/ai/jobfit") {
      const pr = await env.DB.prepare("SELECT * FROM profiles WHERE user_id=?").bind(u.id).first();
      const sys = 'Você atua como um recrutador profissional. Cruze a vaga com o perfil e avalie a aderência em PT-BR. Campos do JSON: {"aderencia":<0-100 int>,"atende":["..."],"gaps":["..."],"plano":["passo 1","passo 2","passo 3"]}';
      const usr = `VAGA:\n${body.vaga || ""}\n\nPERFIL:\nHeadline: ${pr.headline}\nSobre: ${pr.sobre}\nSetor: ${pr.setor}\nSenioridade: ${pr.senioridade}\nObjetivo: ${pr.objetivo}`;
      let out; try { out = await aiJson(env, sys, usr, 1100); } catch (e) { return json({ error: e.message }, 502); }
      await env.DB.prepare("INSERT INTO jobfit(user_id,vaga,aderencia,atende,gaps,plano) VALUES(?,?,?,?,?,?)")
        .bind(u.id, body.vaga || "", parseInt(out.aderencia || 0), JSON.stringify(out.atende || []), JSON.stringify(out.gaps || []), JSON.stringify(out.plano || [])).run();
      return json(out);
    }
    if (p === "/api/ai/post") {
      const pr = await env.DB.prepare("SELECT * FROM profiles WHERE user_id=?").bind(u.id).first();
      const sys = "Você é um copiloto que escreve posts de LinkedIn em PT-BR com a voz autêntica do profissional, focados em autoridade e resultado (sem clichê). Devolva só o texto do post.";
      const usr = `Tema: ${body.topic || ""}. Tom: ${body.tone || "profissional e direto"}. Setor: ${pr.setor}. Senioridade: ${pr.senioridade}.`;
      let post; try { post = await ai(env, sys, usr, 700); } catch (e) { return json({ error: e.message }, 502); }
      return json({ post });
    }
    if (p === "/api/messages" && method === "POST") {
      const tid = body.thread, b = (body.body || "").trim();
      if (!b) return json({ error: "vazio" }, 400);
      await env.DB.prepare("INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)").bind(tid, "candidato", b).run();
      return json({ ok: true });
    }
    if (p === "/api/team-message") {
      let tid = body.thread; const b = (body.body || "").trim();
      if (!tid) { const t = await env.DB.prepare("SELECT id FROM threads WHERE user_id=? AND role='Onboarding' LIMIT 1").bind(u.id).first(); tid = t ? t.id : null; }
      if (!b || !tid) return json({ error: "vazio" }, 400);
      await env.DB.prepare("INSERT INTO messages(thread_id,author,body) VALUES(?,?,?)").bind(tid, "equipe", b).run();
      return json({ ok: true });
    }

    return json({ error: "not found" }, 404);
  } catch (e) {
    return json({ error: String(e) }, 500);
  }
}
