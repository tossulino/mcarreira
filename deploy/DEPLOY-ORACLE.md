# Publicar na Oracle Cloud (Always Free) — mcarreira.com.br

A Oracle dá uma VM **sempre ligada e de graça pra sempre**. Mas tem 2 pegadinhas (capacidade
ARM e firewall duplo) que este guia já resolve. Você faz a parte da conta/VM; eu te ajudo no resto.

---

## A. Criar a conta (você)
1. Acesse **cloud.oracle.com** → **Start for free**.
2. Preencha os dados. Pede **cartão** só para validar (não cobra nada no Always Free).
3. **Home Region**: escolha com cuidado — os recursos grátis ficam presos na região e ela **não
   muda depois**. Para o Brasil, **Brazil East (São Paulo)** dá menor latência.

## B. Criar a VM Always Free
Menu (☰) → **Compute → Instances → Create instance**:
- **Image:** Canonical **Ubuntu 22.04**.
- **Shape:** Change → **Ampere** → `VM.Standard.A1.Flex` → **1 OCPU / 6 GB** (dentro do grátis).
- **Networking:** criar nova VCN (padrão), **Assign public IPv4 = Yes**.
- **SSH keys:** "Generate a key pair for me" → **baixe a chave privada** (guarde bem!).
- **Create.** Anote o **Public IP** da instância.

> ⚠️ **"Out of host capacity" no ARM?** É comum em São Paulo. Duas saídas:
> (a) tente de novo em outro horário; ou
> (b) use a shape AMD **`VM.Standard.E2.1.Micro`** (1 OCPU / 1 GB, também Always Free e quase
> sempre disponível). Nosso app é leve — 1 GB roda de boa.

## C. Abrir as portas 80 e 443 — em DOIS lugares (a pegadinha)
A Oracle bloqueia tráfego na nuvem **e** dentro do Ubuntu. Precisa liberar nos dois.

**1) Na nuvem (Security List):**
Networking → **Virtual Cloud Networks** → sua VCN → **Security Lists** → *Default Security List*
→ **Add Ingress Rules** (crie duas):
- Source `0.0.0.0/0` · IP Protocol `TCP` · Destination Port `80`
- Source `0.0.0.0/0` · IP Protocol `TCP` · Destination Port `443`

**2) Dentro da VM (iptables)** — depois de conectar por SSH (passo D), rode:
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## D. Conectar por SSH
No seu Mac (ajuste o caminho da chave que você baixou):
```bash
chmod 400 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@SEU_IP_PUBLICO
```

## E. Apontar o domínio
No painel do **Registro.br** → `mcarreira.com.br` → Editar zona DNS:
| Tipo | Nome | Valor |
|------|------|-------|
| A | @ | SEU_IP_PUBLICO |
| A | www | SEU_IP_PUBLICO |

## F. Instalar e subir o app
A arquitetura ARM não muda nada (Python e Caddy têm build ARM). A partir daqui, siga o
**[DEPLOY.md](DEPLOY.md) do passo 2 ao 7**: instalar Python + Caddy, copiar a pasta `norte/`,
preencher `/etc/minhacarreira.env`, subir o serviço systemd, configurar o Caddyfile e cadastrar
o redirect do LinkedIn. O Caddy emite o HTTPS sozinho assim que o DNS apontar para o IP.

## Resultado
**https://mcarreira.com.br** (landing) e **https://mcarreira.com.br/app.html** (app) — de graça,
sempre ligado, com HTTPS válido.
