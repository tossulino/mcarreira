# Publicar no Cloudflare (Pages + D1) — grátis, sem servidor, sem Node

Tudo pelo **painel** da Cloudflare. O front (HTML) vira site estático no Pages; o backend
(`functions/api/[[path]].js`) roda como função serverless; o banco é o **D1** (SQLite gerenciado).

Bundle a publicar = esta pasta `cf/` (contém `index.html`, `app.html`, `functions/` e `schema.sql`).

---

## 1. Conta + domínio na Cloudflare
1. Crie conta grátis em **dash.cloudflare.com**.
2. **Add a site** → `mcarreira.com.br` → plano Free. A Cloudflare te dá **2 nameservers**.
3. No **Registro.br** → `mcarreira.com.br` → "Alterar servidores DNS" → troque para os 2
   nameservers da Cloudflare. (Propaga em minutos a algumas horas.)

## 2. Criar o banco D1 e o esquema
1. Painel → **Storage & Databases → D1** → **Create** → nome `minhacarreira`.
2. Abra a aba **Console** do banco → cole TODO o conteúdo de **`schema.sql`** → **Run**.

## 3. Publicar o site + API (Pages, Direct Upload)
1. Painel → **Workers & Pages → Create → Pages → Upload assets**.
2. Nome do projeto: `mcarreira`.
3. **Arraste o conteúdo da pasta `cf/`** (os arquivos `index.html`, `app.html` e a pasta
   `functions/`) → **Deploy**.
   - Importante: a pasta `functions/` precisa ir junto — é ela que vira a API.
   - Se o arrastar não pegar a subpasta, compacte o conteúdo de `cf/` num `.zip` (no Finder:
     selecionar tudo → "Comprimir") e envie o zip.

## 4. Ligar o banco e os segredos
No projeto Pages → **Settings**:
- **Bindings → Add → D1 database**: variável **`DB`** → selecione `minhacarreira`.
- **Bindings → Add → Workers AI**: variável **`AI`** — IA nativa da Cloudflare, **sem chave**.
- **Variables and Secrets** (só quando for ligar o login do LinkedIn):
  - `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`
  - `LINKEDIN_REDIRECT` = `https://mcarreira.com.br/api/auth/linkedin/callback`
  - `AI_MODEL` (opcional) = `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
- **Re-deploy** (Deployments → ⋯ → Retry deployment) para as variáveis/binding valerem.

## 5. Domínio personalizado
Projeto Pages → **Custom domains → Set up a domain** → `mcarreira.com.br` (e repita para `www`).
Como o domínio já está na Cloudflare, ele configura sozinho e emite o HTTPS.

## 6. Redirect do LinkedIn
No app em **LinkedIn Developers → Auth → Authorized redirect URLs**, adicione exatamente:
`https://mcarreira.com.br/api/auth/linkedin/callback`

## Pronto
- Landing: **https://mcarreira.com.br**
- App: **https://mcarreira.com.br/app.html**

### Atualizar depois
Mexeu no código? Faça um novo **Upload assets** no projeto Pages (cria uma nova versão).
Mexeu no banco? Rode o SQL no Console do D1.

### Notas
- Custo: tudo dentro do **plano grátis** da Cloudflare (Pages ilimitado; Workers 100k req/dia;
  D1 com cota diária generosa). Para um MVP, sobra.
- Sem servidor, sem firewall, sem manutenção. Se um dia escalar muito, a base já é serverless.
