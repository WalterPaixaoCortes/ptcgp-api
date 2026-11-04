# PTCGP API — Problemas encontrados e endpoints propostos

| Campo | Valor |
|---|---|
| API | PTCGP API v1.0.0 — `https://poketcgp-api-fd77492e0209.herokuapp.com` |
| Data dos testes | 2026-11-04 |
| Contexto | Levantamento feito para construir o dashboard descrito em [PRD.md](PRD.md) |

Todos os problemas podem ser reproduzidos com os comandos `curl` mostrados. Os volumes citados referem-se aos 2.419 registros que `GET /cards` retornou na data dos testes.

---

## 1. Resumo

| Severidade | Qtd. | Problemas |
|---|---|---|
| 🔴 Crítica | 4 | P1 `/stats` quebrado · P2 filtro por tipo quebrado · P3 filtro por set quebrado · P4 sem CORS |
| 🟠 Alta | 4 | P5 filtro por raridade sem dados · P6 dano variável no nome do ataque · P7 registros com HTML vazado · P8 contrato OpenAPI sem esquema |
| 🟡 Média | 6 | P9 números como string · P10 nulos representados de forma inconsistente · P11 espaços e quebras de linha no nome de habilidades · P12 set sem código e sem data · P13 sem total na paginação · P14 hibernação do Heroku |
| ⚪ Baixa | 3 | P15 sem cabeçalhos de cache · P16 `HEAD` retorna 405 · P17 formato do `id` diferente da rota |

**Impacto no dashboard:** só `GET /cards` funciona de forma confiável. Por isso o dashboard baixa o catálogo inteiro (~1,2 MB) e refaz no cliente contagens, normalização e ranking, que deveriam ser responsabilidade da API.

---

## 2. Problemas

### 🔴 P1 — `GET /stats` retorna 500

```bash
curl -i https://poketcgp-api-fd77492e0209.herokuapp.com/stats
# HTTP/2 500 — corpo: "Internal Server Error" (texto puro, não JSON)
```

- **Esperado:** estatísticas da coleção, conforme a descrição no OpenAPI ("Retorna estatísticas sobre a coleção de cartas").
- **Impacto:** seria a fonte natural do total de cartas e da contagem por energia (F1 e F2 do PRD). Sem ele, os dois números são calculados no cliente.
- **Sugestão:** corrigir a exceção e devolver o esquema proposto em [E1](#e1--get-stats-corrigido-e-com-esquema). Os erros também deveriam voltar em JSON (`{"detail": ...}`), como já acontece no 404 e no 422.

### 🔴 P2 — `GET /cards/filter/type/{card_type}` retorna 500 para qualquer valor

```bash
curl -i https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/type/Fire      # 500
curl -i https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/type/fire      # 500
curl -i https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/type/Pok%C3%A9mon # 500
curl -i https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/type/Trainer   # 500
```

- **Ambiguidade:** o parâmetro se chama `card_type`, mas os dados têm dois campos possíveis: `type` (energia: `Fire`, `Water`…) e `card_type` (`Pokémon`/`Trainer`). Não dá para saber qual deles o endpoint deveria filtrar.
- **Sugestão:** corrigir o erro e deixar o campo explícito. O ideal é passar a usar parâmetros de query em `/cards` (ver [E4](#e4--get-cards-com-filtros-projeção-e-total)).

### 🔴 P3 — `GET /cards/filter/set/{set_name}` retorna 500

```bash
curl -i https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/set/A1                     # 500
curl -i "https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/set/Genetic%20Apex%20A1"  # 500
```

- Falha tanto com o código do set quanto com o nome completo.
- **Sugestão:** corrigir e aceitar o código do set (`A1`), que é estável. Ver também P12.

### 🔴 P4 — Sem CORS

```bash
curl -s -D - -o /dev/null "https://poketcgp-api-fd77492e0209.herokuapp.com/cards?limit=1" \
  -H 'Origin: http://localhost:5173' | grep -i access-control
# (nenhum cabeçalho)
```

- **Impacto:** um front-end no navegador (React, Vue, HTML estático) não consegue consumir a API diretamente. Isso obriga a ter um backend ou proxy só para repassar as chamadas.
- **Sugestão:** como a API é pública e só de leitura, habilitar `CORSMiddleware` do FastAPI com `allow_origins=["*"]` e `allow_methods=["GET"]`.

### 🟠 P5 — Filtro por raridade sempre retorna `[]`, e não existe campo de raridade

```bash
curl -s https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/rarity/Common  # []
curl -s https://poketcgp-api-fd77492e0209.herokuapp.com/cards/filter/rarity/ex      # []
```

- Nenhum registro de `/cards` tem um campo `rarity`, então o filtro nunca encontra nada. Não há erro: o endpoint só responde vazio, o que esconde a falha.
- **Sugestão:** incluir `rarity` nos dados (◊, ◊◊, ◊◊◊, ◊◊◊◊, ☆, ☆☆, ☆☆☆, ♛). Enquanto o campo não existir, remover o endpoint ou fazê-lo retornar 501.

### 🟠 P6 — Dano variável fica só no nome do ataque

```json
{ "cost": "GGC", "name": "X-Scissor 50+", "damage": null,
  "effect": "Flip a coin. If heads, this attack does 50 more damage." }
```

- **Volume:** 375 ataques (283 com `+`, 92 com `x`) vêm com `damage: null` e o valor dentro do `name`.
- **Impacto:** quem lê `damage` conclui que o ataque não causa dano. Para corrigir, o consumidor precisa extrair o número do nome com uma regex (`(\d+)[+x]\s*$`) e limpar o nome antes de exibir.
- **Sugestão:** separar em campos próprios:

```json
{ "name": "X-Scissor", "damage": 50, "damage_modifier": "+",
  "cost": ["G", "G", "C"], "energy_count": 3, "effect": "..." }
```

### 🟠 P7 — Registros com HTML vazado no nome

```json
{ "id": "/A3/127",
  "name": "Kommo-o\n              - Dragon               - 150 HP",
  "type": null, "hp": null, "stage": null,
  "card_type": "Pokémon\n              - Stage 2\n            \n   - Evolves from\n                Hakamo-o" }
```

- **Volume:** 18 registros. São 12 Pokémon (Ho-Oh, Ho-Oh ex ×6, Porygon-Z ×2, Jangmo-o, Hakamo-o, Kommo-o) e 6 fósseis (Old Amber ×4, Helix Fossil, Dome Fossil). Nos IDs `/A3/126` e `/A3/127`, o campo `card_type` também vem corrompido.
- **Causa provável:** o scraper não encontra o elemento de tipo/HP no HTML de origem (provavelmente por variação de layout) e acaba gravando o texto bruto do bloco.
- **Impacto:** essas cartas somem da contagem por energia. Fire perde 7, Colorless 2 e Dragon 3, e aparecem 12 Pokémon "sem tipo". Elas também ficam com nome errado no ranking: o Kommo-o, que é o 10º do top 10 do PRD, só aparece corretamente depois da normalização.
- **Sugestão:** corrigir o scraper e adicionar uma validação na ingestão que rejeite nomes contendo `\n` e Pokémon com `type`/`hp` nulos.

### 🟠 P8 — OpenAPI sem esquema de resposta

- `/cards` declara `array` de `object` com `additionalProperties: true`. Os outros endpoints declaram `schema: {}`.
- **Impacto:** o `/docs` não mostra campos, tipos nem quais valores podem ser nulos. Também não dá para gerar clientes tipados nem validar respostas em testes de contrato. Todo o modelo de dados do PRD (§2.3) teve de ser descoberto baixando o catálogo inteiro.
- **Sugestão:** definir modelos Pydantic (`Card`, `Attack`, `Ability`, `Set`) e usar `response_model` nas rotas.

### 🟡 P9 — Números em formato string

- `hp` (`"90"`), `retreat_cost` (`"2"`) e `attacks[].damage` (`"60"`) vêm como string.
- O custo do ataque é uma string compactada (`"GGC"`), com `"0"` para custo zero (15 ataques). Quem consome precisa conhecer o código de cada letra (`R` = Fire, `L` = Lightning…), e isso não está documentado.
- **Sugestão:** retornar inteiros. Para o custo, usar uma lista de tipos (`["Grass","Grass","Colorless"]` ou `["G","G","C"]`, com o mapeamento documentado), vazia quando o custo é zero.

### 🟡 P10 — Nulos representados de forma inconsistente

| Campo | Representações de "vazio" encontradas |
|---|---|
| `evolve` | String `"None"` (1.410×) e `null` (2×) |
| `weakness` | `null` (208×) e string `"none"` (49×) |
| `attacks` | `[]` (Treinadores) |
| `attacks[].effect` | `""` (1.093×) |
| `ability` | `null` |

- **Impacto:** cada campo exige um tratamento diferente. Testar `if card["evolve"]` é verdadeiro para `"None"`.
- **Sugestão:** usar `null` como único valor de ausência em todos os campos.

### 🟡 P11 — Espaços e quebras de linha no nome de habilidades

```json
{ "name": "Ability: \n                         Toughness Aroma", "text": "..." }
```

- **Volume:** 292 habilidades. O nome vem com prefixo fixo e espaços vazados do HTML.
- **Sugestão:** `{"name": "Toughness Aroma", "text": "..."}`.

### 🟡 P12 — Set sem código e sem data

- Hoje: `"set": {"url": "...", "name": "Genetic Apex A1"}`. O código (`A1`) só aparece junto do nome ou dentro do `id`.
- **Impacto:** para agrupar ou filtrar por set, é preciso extrair o código do texto. Também não dá para ordenar os sets por lançamento.
- **Sugestão:** `"set": {"code": "A1", "name": "Genetic Apex", "release_date": "2024-10-30", "url": "..."}`.

### 🟡 P13 — Paginação sem total

```bash
curl -s "https://poketcgp-api-fd77492e0209.herokuapp.com/cards?offset=99999"  # []
```

- A resposta é um array puro, sem informar o total de registros. O cliente só sabe que chegou ao fim quando recebe uma página vazia. Além disso, `/cards` sem `limit` devolve tudo de uma vez, mas com `limit` o máximo é 1000.
- **Sugestão:** um envelope `{"total": 2419, "limit": 100, "offset": 0, "items": [...]}` ou o cabeçalho `X-Total-Count`.

### 🟡 P14 — Hibernação do Heroku

- A primeira chamada levou **11,3 s**. Com a API já ativa, as chamadas levaram de 2,1 s a 3,5 s para ~1,2 MB.
- **Sugestão:** manter a instância ativa, compactar as respostas (`GZipMiddleware`) e oferecer projeção de campos (E4) para reduzir o tamanho.

### ⚪ P15 — Sem cabeçalhos de cache

- Não há `Cache-Control`, `ETag` nem `Last-Modified`. Os clientes não têm como saber se os dados mudaram e acabam baixando tudo de novo.
- **Sugestão:** `ETag` baseado na versão dos dados (ver E5) e `Cache-Control: public, max-age=3600`.

### ⚪ P16 — `HEAD` retorna 405

```bash
curl -I "https://poketcgp-api-fd77492e0209.herokuapp.com/cards?limit=1"  # HTTP/2 405
```

- Ferramentas de monitoramento e de verificação de links costumam usar `HEAD`.
- **Sugestão:** aceitar `HEAD` nas rotas `GET`.

### ⚪ P17 — Formato do `id` diferente da rota

- O `id` vem como `"/B1/1"`, com barra inicial, mas a rota é `/cards/{set_id}/{card_id}` (`/cards/B1/1`). Não há campo com o número da carta separado.
- **Sugestão:** `"id": "B1-1"` (ou `"set_code": "B1", "number": 1`).

---

## 3. Endpoints propostos para o dashboard

Os endpoints abaixo levariam para o servidor as regras de cálculo que o PRD hoje coloca no cliente. A prioridade indica o quanto cada um simplifica a implementação. Os valores nos exemplos são os números de referência do PRD.

| ID | Endpoint | Atende | Prioridade |
|---|---|---|---|
| E1 | `GET /stats` (corrigido) | F1, F2 | Essencial |
| E2 | `GET /cards/ranking` | F3 | Essencial |
| E3 | `GET /types` | F2 (rótulos e ordem), legenda | Desejável |
| E4 | `GET /cards` com filtros, projeção e total | Drill-down, tamanho da resposta | Desejável |
| E5 | `GET /meta` | Rodapé "atualizado em", cache | Desejável |
| E6 | `GET /sets` | Filtro por set (futuro) | Opcional |

### E1 — `GET /stats` (corrigido e com esquema)

Substitui o download completo para os indicadores F1 e F2.

**Parâmetros:** `distinct` (bool, padrão `false`). Quando `true`, conta cada carta uma única vez, ignorando reimpressões com mesmo nome e mesmos ataques.

```json
{
  "total_cards": 2419,
  "distinct_cards": 1379,
  "by_card_type": { "Pokémon": 2211, "Trainer": 208 },
  "by_type": {
    "Water": 339, "Grass": 314, "Colorless": 308, "Psychic": 271,
    "Fighting": 256, "Lightning": 192, "Fire": 190, "Darkness": 190,
    "Metal": 117, "Dragon": 34
  },
  "by_set": { "A4b": 379, "B1": 331, "A1": 286, "...": 0 },
  "data_version": "2026-11-04T14:07:00Z"
}
```

> Uma alternativa mais genérica é `GET /stats/count?group_by=type|card_type|set|stage|rarity`, que retorna `[{"key": "Water", "count": 339}, ...]`.

### E2 — `GET /cards/ranking`

Faz no servidor o cálculo de dano por energia, que hoje exige tratar P6, P7, P9 e as reimpressões.

**Parâmetros:**

| Parâmetro | Valores | Padrão |
|---|---|---|
| `metric` | `damage_per_energy`, `damage`, `hp` | `damage_per_energy` |
| `limit` | 1–100 | 10 |
| `distinct` | `true` / `false` | `true` |
| `type` | tipo de energia (opcional) | — |
| `include_variable` | inclui ataques `+`/`x` pelo valor base | `true` |

**Regras:** usa o melhor ataque da carta e ignora ataques de custo zero ou sem dano. Em caso de empate, vence o maior dano, depois o menor custo, depois o nome em ordem alfabética. São as mesmas regras do PRD (R3.1–R3.6).

```json
{
  "metric": "damage_per_energy",
  "items": [
    {
      "rank": 1,
      "card": { "id": "A2-89", "name": "Rampardos", "type": "Fighting",
                "img": "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/pocket/A2/A2_089_EN_SM.webp" },
      "attack": { "name": "Head Smash", "cost": ["F"], "energy_count": 1,
                  "damage": 130, "damage_modifier": null },
      "value": 130.0,
      "printings": 1
    }
  ]
}
```

### E3 — `GET /types`

Catálogo dos tipos de energia, com o símbolo usado em `cost`. O cliente deixa de precisar conhecer a codificação de letras (P9) e o dashboard tem uma lista confiável de categorias.

```json
[
  { "type": "Grass",     "symbol": "G" },
  { "type": "Fire",      "symbol": "R" },
  { "type": "Water",     "symbol": "W" },
  { "type": "Lightning", "symbol": "L" },
  { "type": "Psychic",   "symbol": "P" },
  { "type": "Fighting",  "symbol": "F" },
  { "type": "Darkness",  "symbol": "D" },
  { "type": "Metal",     "symbol": "M" },
  { "type": "Colorless", "symbol": "C" },
  { "type": "Dragon",    "symbol": null }
]
```

### E4 — `GET /cards` com filtros, projeção e total

Substitui os endpoints quebrados `/cards/filter/*` (P2, P3, P5) e resolve P13.

```
GET /cards?type=Fire&card_type=Pokémon&set=A1&stage=Basic&rarity=◊◊
          &fields=id,name,type,img&limit=100&offset=0&sort=name
```

```json
{ "total": 190, "limit": 100, "offset": 0, "items": [ { "id": "A1-33", "name": "Charmander", "type": "Fire", "img": "..." } ] }
```

- `fields` reduz a resposta. Para a tabela do top 10, por exemplo, só são necessários `id`, `name`, `type`, `img` e `attacks`.
- Os filtros aceitam valores sem diferenciar maiúsculas e retornam 422 para valores fora do catálogo (E3), em vez de 500.

### E5 — `GET /meta`

```json
{ "api_version": "1.0.0", "data_version": "2026-11-04T14:07:00Z",
  "source": "https://pocket.limitlesstcg.com", "total_cards": 2419 }
```

- Fornece o "atualizado em" do rodapé (R4.4 do PRD).
- Funciona como verificação de saúde barata: o dashboard pode chamar `/meta` primeiro, mostrar um estado de "acordando a API" (P14) e só depois buscar os dados.
- `data_version` também pode servir de base para o `ETag` (P15).

### E6 — `GET /sets`

```json
[ { "code": "A1", "name": "Genetic Apex", "release_date": "2024-10-30", "card_count": 286 } ]
```

- Permite um filtro por set com nomes legíveis e ordenados por lançamento (fora do escopo da v1 do PRD).
- Depende de P12.

---

## 4. Ordem sugerida de correção

1. **P4 (CORS)**: uma linha de configuração, que libera clientes no navegador.
2. **P1, P2, P3**: corrigir os 500 e devolver erros em JSON.
3. **P6, P7**: corrigir o scraper e a ingestão. Isso conserta os dados na origem e beneficia todos os consumidores.
4. **P8, P9, P10**: modelos Pydantic e `response_model`. Fixam o contrato e eliminam as inconsistências de tipo.
5. **E1, E2**: com os dados já limpos, os endpoints do dashboard ficam simples de implementar.
6. Demais itens, conforme houver capacidade.
