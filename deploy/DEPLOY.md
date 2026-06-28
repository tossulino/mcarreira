# Deploy do Minha Carreira em mcarreira.com.br

Stack: o `app.py` (Python puro) rodando atrás do **Caddy** (HTTPS automático). Assume uma
VPS Ubuntu 22.04+ com IP público. Custo típico: ~US$5/mês (DigitalOcean, Hetzner, Contabo).

---

## 0. Provisionar a VPS
Crie uma VPS Ubuntu e anote o **IP público** (ex.: `203.0.113.10`). Acesse por SSH.

## 1. Apontar o DNS (no Registro.br)
Painel do Registro.br → `mcarreira.com.br` → **Editar zona DNS** → adicione:

| Tipo | Nome | Valor |
|------|------|-------|
| A    | @    | IP_DA_SUA_VPS |
| A    | www  | IP_DA_SUA_VPS |

(Propaga em minutos/horas. Alternativa: trocar os nameservers para o Cloudflare e gerenciar lá.)

## 2. Instalar dependências na VPS
```bash
sudo apt update && sudo apt install -y python3 debian-keyring debian-archive-keyring apt-transport-https curl
# Caddy (HTTPS automático)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

## 3. Subir o código
```bash
sudo mkdir -p /opt/minhacarreira
# do seu Mac, copie a pasta norte/ para a VPS:
#   rsync -av --exclude minhacarreira.db ./norte root@IP_DA_VPS:/opt/minhacarreira/
```

## 4. Configurar segredos
```bash
sudo cp /opt/minhacarreira/norte/deploy/minhacarreira.env.example /etc/minhacarreira.env
sudo nano /etc/minhacarreira.env   # preencha ANTHROPIC_API_KEY, LINKEDIN_CLIENT_ID, LINKEDIN_CLIENT_SECRET
sudo chmod 600 /etc/minhacarreira.env
```

## 5. Rodar o app como serviço
```bash
sudo cp /opt/minhacarreira/norte/deploy/minhacarreira.service /etc/systemd/system/
sudo chown -R www-data:www-data /opt/minhacarreira
sudo systemctl daemon-reload
sudo systemctl enable --now minhacarreira
sudo systemctl status minhacarreira   # deve estar "active (running)"
```

## 6. Configurar o Caddy (HTTPS)
```bash
sudo cp /opt/minhacarreira/norte/deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```
O Caddy emite o certificado sozinho assim que o DNS apontar para a VPS.

## 7. Cadastrar o redirect no LinkedIn
No app do LinkedIn Developers → Auth → adicione:
`https://mcarreira.com.br/api/auth/linkedin/callback`

## Pronto
Acesse **https://mcarreira.com.br** (landing) e **https://mcarreira.com.br/app.html** (app).

### Notas
- O banco `minhacarreira.db` fica em `/opt/minhacarreira/norte/`. Faça backup periódico.
- Logs do app: `sudo journalctl -u minhacarreira -f`.
- Atualizar o código: novo `rsync` + `sudo systemctl restart minhacarreira`.
- Para escala (muitos usuários simultâneos), migrar do `app.py`/SQLite para a stack do `SPEC.md`
  (Supabase + front em CDN). O `app.py` aguenta bem um MVP/validação.
