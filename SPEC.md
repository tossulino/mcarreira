# Norte — Especificação técnica (enxuta)

> Clone do Summitfy reposicionado como **copiloto assistido** que ensina o usuário a se
> posicionar no LinkedIn. A diferença de produto vira diferença de arquitetura: **não
> guardamos a sessão do LinkedIn do usuário e não agimos na conta dele**. Isso elimina o
> ativo mais perigoso do produto original (cookie `li_at` em banco) e o maior risco (ban).

---

## 1. Princípios de arquitetura (o que muda vs. o original)

| Tema | Summitfy (observado) | Norte (decisão) |
|---|---|---|
| Ação no LinkedIn | Server-side com sessão do usuário (`connect-linkedin-action`, `boost-linkedin`) | **Assistida**: app gera o rascunho; o usuário publica/conecta com as próprias mãos. Sem credencial armazenada. |
| Integração | API interna `voyager` (viola ToS) | OAuth oficial onde existir; fora disso, deep-links + extensão opcional que **só preenche**, nunca dispara sozinha. |
| Métrica núcleo | Atividade (SSI, conexões) | **Outcome**: respostas de recrutador, conversas, entrevistas. |
| Ativo sensível | Sessões de LinkedIn de milhares de contas | Nenhuma credencial de terceiros. Risco de vazamento drasticamente menor. |
| Retenção / moat | Assinatura "faz por você" | **Mesmo moat do original**: efeito de rede da comunidade + Academy + hall da fama (ver §8 do GTM). Lock-in saudável, não aprisionamento. |

## 2. Stack

Mantém o núcleo do original (rápido de entregar), troca a camada de risco.

- **Front:** React + Vite + TypeScript, Tailwind. SPA. (Landing inicial é o `index.html` estático deste repo — zero build, serve como topo de funil.)
- **Backend:** Supabase — Postgres + Auth + Edge Functions (Deno) + Storage + Realtime.
- **IA:** LLM via Edge Function (chave server-side). Default: Claude (`claude-sonnet-4-6` para geração de conteúdo; tier mais barato para classificação).
- **Pagamento:** 1 gateway no MVP (Stripe). Hotmart/Kiwify só se o canal exigir — cada gateway é custo de manutenção.
- **Infra/edge:** Cloudflare (CDN + Turnstile anti-bot no checkout/diagnóstico).
- **Observabilidade:** Sentry + PostHog (produto/funil). Crisp para suporte.
- **Extensão (fase 2, opcional):** content-script que **pré-preenche** o compositor de post do LinkedIn e a nota de convite. O envio é sempre um clique humano. Ela lê eventos públicos da página para alimentar o painel de outcome — nunca usa a sessão para agir.

## 3. Modelo de dados (núcleo)

```
users (Supabase auth)
profiles            id, user_id, objetivo, setor, senioridade, voz_json, created_at
diagnostics         id, user_id, score, plano_json, created_at          -- topo de funil
content_drafts      id, user_id, tipo(headline|about|post|nota), input, output, status(draft|published)
content_lessons     id, draft_id, porque_json                           -- o "ensina o porquê"
outreach_queue      id, user_id, alvo_hint, nota_sugerida, status(sugerido|aprovado|enviado_manual)
outcomes            id, user_id, tipo(resposta|conversa|entrevista), origem_draft_id, data
                    -- NORTH STAR vive aqui
subscriptions       id, user_id, plano, provider, status, expires_at
billing_events      id, provider, event_id(unique), payload, processed_at  -- idempotência de webhook

-- MOAT: comunidade (efeito de rede) + Academy (conteúdo) + prova social
members             id, user_id, network_rank, streak, joined_at          -- networkRank
community_posts     id, user_id, draft_id, corpo, publicado_em            -- feed da comunidade
community_engage    id, post_id, member_id, tipo(apoio|comentario), data  -- engajamento real entre pares
hall_of_fame        id, user_id, conquista, empresa, data                 -- flywheel de prova social
academy_courses     id, slug, titulo, ordem
academy_modules     id, course_id, titulo, ordem
academy_lessons     id, module_id, titulo, corpo, recurso_url             -- conteúdo proprietário
academy_progress    id, user_id, lesson_id, concluido_em                  -- switching cost

-- COCKPIT do candidato (área logada da assinatura)
ssi_snapshots       id, user_id, score, marca, pessoas, insights, relacionamentos, captured_at
profile_score       id, user_id, strength_pct, checklist_json, updated_at
profile_suggestions id, user_id, secao, problema, sugestao_ia, porque, status(sugerido|aplicado)
job_fit             id, user_id, vaga_texto, aderencia_pct, atende_json, gaps_json, plano_json

-- MENSAGENS diretas (plataforma/mentor ↔ candidato)
threads             id, user_id, tipo(equipe|mentor), titulo, last_at, unread
direct_messages     id, thread_id, autor(candidato|equipe|mentor), autor_id, corpo, lida, created_at
```

RLS em tudo: `user_id = auth.uid()`. `billing_events` e `subscriptions` só via service role (webhook).
Conteúdo da comunidade é legível por membros ativos (policy por plano); `community_engage` é
**ação humana real** — sem auto-curtida/bot, coerente com a marca de confiança.
Mensagens: o candidato lê/escreve só nas próprias `threads`; **equipe/mentor enviam para o
candidato via role de staff** (não pela conta dele) — o `direct_messages.autor` distingue origem.

## 4. Edge Functions (núcleo)

```
diagnose-profile          -- gera score + plano a partir do input do diagnóstico (topo de funil, sem login)
generate-profile-copy     -- headline / about / experience com a voz do usuário
generate-post             -- post a partir das histórias do usuário
explain-strategy          -- gera o "porquê" pedagógico de cada sugestão  (o wedge)
suggest-outreach          -- monta fila de conexões SUGERIDAS (texto da nota), nunca envia
record-outcome            -- registra resposta/conversa/entrevista (manual ou via extensão)
billing-webhook           -- valida assinatura, idempotente, libera acesso
-- MOAT
community-feed            -- monta o feed da comunidade (posts dos membros para apoio mútuo)
community-engage          -- registra apoio/comentário REAL de um membro em outro (sem bot)
compute-network-rank      -- recalcula networkRank/streak (cron) → ranking e gamificação
academy-progress          -- marca aula concluída, libera próxima trilha
publish-hall-of-fame      -- promove quem foi contratado a destaque (alimenta prova social)
-- COCKPIT
fetch-ssi                 -- busca o SSI do LinkedIn em 1 clique e grava snapshot + benchmark da rede
score-profile             -- calcula força do perfil + checklist (foto, headline, sobre, exp, skills)
improve-profile-section   -- gera sugestão + o "porquê" para headline/sobre/experiência (assistido)
analyze-job-fit           -- cruza a vaga × perfil → nota de aderência + gaps + plano (IA recrutador)
-- MENSAGENS
list-threads              -- inbox do candidato (suas threads + não-lidas)
send-direct-message       -- candidato responde; equipe/mentor enviam ao candidato (staff role)
```

Padrão de toda function: valida JWT → checa quota/plano → chama LLM/grava → responde.
`diagnose-profile` é a exceção (público, protegido por Turnstile) porque é o ímã de lead.

## 5. Fluxos críticos

**Ativação (o gargalo nº1 do original, atacado aqui):**
```
Landing → diagnóstico grátis (sem cadastro) → resultado com valor real
        → captura e-mail/conta → onboarding define objetivo+voz
        → primeira reescrita de headline em <2 min  ("aha" rápido)
```
Não há passo "conecte seu LinkedIn" bloqueante — a maior fonte de medo/abandono do original some.

**Loop de valor recorrente:**
```
copiloto sugere post/conexão → explica o porquê → usuário publica (1 clique manual)
        → registra outcome → painel mostra entrevistas subindo → usuário aprende e volta
```

**Pagamento (igual ao original, mas 1 gateway):**
```
Stripe Checkout → webhook → billing-webhook (verifica assinatura + idempotência)
        → upsert subscriptions → libera plano. Reconciliação por e-mail no /account-setup.
```

## 6. Requisitos não-funcionais herdados da análise de produto

- **Sem credencial de terceiros em repouso.** Decisão de arquitetura, não config.
- **LGPD/GDPR:** consentimento explícito, base legal, exclusão de dados. Público BR + en.
- **Idempotência de webhook** (`billing_events.event_id` unique).
- **Instrumentação de outcome desde o dia 1** — `outcomes` é tabela de primeira classe, não afterthought. Sem ela o produto pilota cego (erro central do original).
- **Kill-switch de bundle** (igual ao original) para deploy contínuo de SPA.

## 7. O que fica fora do MVP (e por quê)

- Automação real de envio → **fora de propósito**, é o que estamos rejeitando.
- Multi-gateway → só quando um canal de venda exigir.
- App mobile → web-first; o uso é desktop (LinkedIn).
- Extensão → fase 2; o MVP funciona 100% com deep-links manuais + registro manual de outcome.

## 8. Como rodar a landing (já incluída)

```bash
cd norte
python3 -m http.server 4173    # abre http://localhost:4173
```
A landing é estática e autocontida (`index.html`), serve como topo de funil e protótipo do GTM.
O **cockpit do candidato** (área logada da assinatura) está prototipado em `cockpit.html`
(`http://localhost:4173/cockpit.html`): score SSI + pilares + benchmark, diagnóstico e aprimoramento
de perfil com IA (assistido, "ensina o porquê"), aderência à vaga e a central de mensagens diretas
(candidato ↔ equipe/mentor, com envio nos dois sentidos). O app React/Supabase é o próximo
incremento sobre estas duas telas.
