# Norte

O copiloto que te ensina a ser encontrado no LinkedIn — sem robô, sem risco de ban.

Clone reposicionado do Summitfy. Em vez de automação "faz por você" (que pede a conta do
LinkedIn do usuário, mede vaidade e arrisca ban), Norte é um **copiloto assistido**: escreve
*com* o usuário, ensina o porquê de cada movimento e mede **resultado** (respostas e entrevistas).

## Conteúdo deste repositório

| Arquivo | O que é |
|---|---|
| `app.py` | **Backend funcional** (Python puro): SQLite, API JSON, auth real, integração Claude. Serve a landing e o app. |
| `app.html` | **App funcional** com login → cockpit, ligado à API por `fetch` (IA real, dados persistidos). Em `/app.html`. |
| `index.html` | Landing page — topo de funil e protótipo do GTM (lead capture ligado à API). |
| `cockpit.html` | Protótipo estático do cockpit (dados mock) — referência de design. `app.html` é a versão funcional. |
| `SPEC.md` | Especificação técnica do clone (stack, modelo de dados, edge functions, fluxos). |
| `GTM.md` | Plano de go-to-market: ICP, funil PLG, pricing, canais, North Star, moat, lançamento 90 dias. |

## Rodar a versão funcional (app + backend)

O `app.py` é um backend completo em Python puro (sem instalar nada): SQLite, API JSON,
login real e integração com o Claude. Ele também serve a landing e o app.

```bash
cd norte
# COM IA real (recomendado — você define a chave, ela nunca fica no código):
ANTHROPIC_API_KEY="sua-chave-da-anthropic" python3 app.py

# OU sem IA (tudo funciona, menos os 3 recursos de IA, que avisam que estão off):
python3 app.py
```

Depois abra:
- App (login/cadastro → cockpit): http://localhost:4173/app.html
- Landing: http://localhost:4173/

O banco fica em `minhacarreira.db` (criado no primeiro run). Modelo do Claude configurável
via `MC_MODEL` (padrão `claude-sonnet-4-6`). Porta via `PORT` (padrão 4173).

### Conectar ao LinkedIn (login oficial — OAuth / OpenID Connect)

A identidade do candidato (nome, foto, e-mail) vem **real** do LinkedIn, de forma sancionada.
Importante: a API oficial do LinkedIn **não** expõe SSI nem perfil completo — esses campos
começam vazios e são preenchidos por você (SSI manual + perfil com a IA). Sem scraping, sem
guardar sessão, sem risco de ban.

Passo a passo (uma vez):
1. Acesse https://www.linkedin.com/developers/apps → **Create app** (precisa associar a uma
   LinkedIn Page — pode criar uma simples).
2. Aba **Products** → adicione **"Sign In with LinkedIn using OpenID Connect"**.
3. Aba **Auth** → em *Authorized redirect URLs* adicione exatamente:
   `http://localhost:4173/api/auth/linkedin/callback`
4. Copie o **Client ID** e o **Client Secret**.
5. Rode o servidor com as variáveis (você define; nunca ficam no código):

```bash
cd norte
LINKEDIN_CLIENT_ID="xxxx" \
LINKEDIN_CLIENT_SECRET="yyyy" \
ANTHROPIC_API_KEY="sua-chave-claude" \
python3 app.py
```

Abra http://localhost:4173/app.html e clique em **Entrar com LinkedIn**. Sem as variáveis do
LinkedIn, o botão avisa que não está configurado (o login por e-mail continua funcionando).

## Domínio e deploy (produção)

Domínio do produto: **mcarreira.com.br** — registrado no Registro.br (titular Guilherme Tossulino).

Dois caminhos de deploy:

- **Cloudflare (escolhido — grátis, serverless, sem servidor):** pasta **[`cf/`](cf/)** com o
  backend portado para Pages Functions + D1. Publica pelo painel, sem Node. Guia:
  **[`cf/DEPLOY-CLOUDFLARE.md`](cf/DEPLOY-CLOUDFLARE.md)**.
- **VPS com o `app.py` Python:** kit em **[`deploy/`](deploy/)** (`Caddyfile`, systemd, env) +
  guias **[`deploy/DEPLOY-ORACLE.md`](deploy/DEPLOY-ORACLE.md)** e **[`deploy/DEPLOY.md`](deploy/DEPLOY.md)**.

Resumo: VPS → DNS (registro A → IP) → instalar Python + Caddy → copiar `norte/` → preencher
`/etc/minhacarreira.env` → subir o serviço → Caddy emite o TLS sozinho → cadastrar o redirect
`https://mcarreira.com.br/api/auth/linkedin/callback` no app do LinkedIn.

> Para escala real (muitos usuários), migrar o backend para a stack do `SPEC.md` (Supabase) e
> hospedar o front em CDN — o `app.py` é ótimo para validar e rodar o MVP.

### O que é funcional de verdade
- Cadastro/login com senha (PBKDF2) e sessão por token.
- Cockpit com dados persistidos: SSI (4 pilares), perfil, outcomes.
- IA real (Claude): aprimorar headline/sobre (com o "porquê"), aderência à vaga (IA-recrutador),
  gerar post — tudo em `app.py` → `/api/ai/*`.
- Mensagens diretas persistidas, nos dois sentidos (candidato ↔ equipe/mentor).
- Captura de lead na landing → tabela `leads`.

## A tese em uma frase

O Summitfy vende um robô que assusta e mede o que não importa. Norte vende confiança e
resultado: começa de graça, prova valor antes de cobrar e deixa a pessoa melhor de verdade.
