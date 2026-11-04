# PTCGP API v2.0.0 — Contrato

| Campo | Valor |
|---|---|
| Base URL | `https://poketcgp-api-fd77492e0209.herokuapp.com` |
| Versão | 2.0.0 (incompatível com a 1.0.0, ver [§6](#6-migração-da-v1)) |
| Esquema formal | [openapi.json](openapi.json) (gerado do código; também em `GET /openapi.json` e na UI `GET /docs`) |
| Problemas que motivaram a versão | [API-ISSUES.md](API-ISSUES.md) |

Os exemplos abaixo são respostas reais da API rodando com a base de testes. Contagens, totais e `data_version` em produção serão outros.

---

## 1. Convenções

- **Formato:** JSON UTF-8. Datas em ISO 8601 (`"2024-10-30"`); `data_version` em UTC (`"2026-11-04T12:00:00Z"`).
- **Ausência de valor:** sempre `null`. Listas vazias (`[]`) só em `attacks` e `cost`.
- **Filtros por texto** não diferenciam maiúsculas nem acentos: `pokemon` = `Pokémon`, `fire` = `Fire`.
- **CORS:** `Access-Control-Allow-Origin: *` para `GET` e `HEAD`. O cabeçalho `ETag` fica exposto ao JavaScript.
- **Compressão:** respostas acima de 1 KB vêm em gzip quando o cliente envia `Accept-Encoding: gzip`, como fazem os navegadores.
- **Cache:** respostas `200` de `GET` trazem `ETag` e `Cache-Control: public, max-age=3600`. Se o cliente reenviar o `ETag` em `If-None-Match`, a API responde `304` sem corpo. O `ETag` muda quando os dados ou a versão da API mudam.
- **`HEAD`:** aceito em todas as rotas, com os mesmos cabeçalhos do `GET` e sem corpo.
- **Hibernação:** a instância do Heroku dorme quando fica parada, e a primeira chamada pode levar mais de 10 s. Chame `GET /meta` primeiro (resposta pequena) e mostre um estado de "carregando".

### Erros

Sempre JSON com a chave `detail`. O tipo de `detail` depende da origem do erro:

| Status | Quando | `detail` |
|---|---|---|
| `404` | Carta inexistente | string: `"Card not found"` |
| `422` | Valor fora do catálogo (`type`, `card_type`, `set`, `stage`, `rarity`, `sort`, `fields`) | **string**, com os valores aceitos |
| `422` | Parâmetro com tipo ou faixa inválida (`limit=0`, `distinct=talvez`, `metric=xyz`) | **lista** de objetos `{type, loc, msg, input, ctx}` (padrão do FastAPI) |
| `500` | Erro inesperado | string: `"Internal Server Error"` |

```json
{ "detail": "Invalid type 'Fairy'. Allowed: Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Colorless, Dragon" }
```

```json
{ "detail": [ { "type": "greater_than_equal", "loc": ["query", "limit"],
                "msg": "Input should be greater than or equal to 1", "input": "0", "ctx": { "ge": 1 } } ] }
```

> O `openapi.json` só descreve o 422 em formato de lista. Para mostrar uma mensagem, trate os dois: `typeof detail === "string" ? detail : detail.map(e => e.msg).join("; ")`.

---

## 2. Modelo de dados

### Card

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | string | não | `"<set>-<número>"`: `"A1-1"`, `"P-A-1"`. Corresponde à rota `/cards/A1/1` |
| `number` | int | não | Número da carta no set |
| `name` | string | não | `"Ho-Oh ex"` |
| `type` | string | sim | Tipo de energia (ver `/types`). `null` em Trainers. Cartas de tipo duplo vêm como `"Psychic/Fighting"` |
| `hp` | int | sim | `null` em Trainers, exceto fósseis (`40`) |
| `card_type` | `"Pokémon"` \| `"Trainer"` | não | |
| `stage` | string | sim | Pokémon: `Basic`, `Stage 1`, `Stage 2`. Trainer: `Item`, `Supporter`, `Tool`, `Stadium` |
| `evolve` | string | sim | `"Evolves from Metapod"`; `null` quando não evolui |
| `rarity` | string | sim | `◊`, `◊◊`, `◊◊◊`, `◊◊◊◊`, `☆`, `☆☆`, `☆☆☆`, `♛`… `null` em promos (sets `P-*`) |
| `ability` | [Ability](#ability) | sim | |
| `attacks` | [Attack](#attack)[] | não | `[]` em Trainers |
| `effect` | string | sim | Texto da carta Trainer; `null` em Pokémon |
| `weakness` | string | sim | Tipo de energia; `null` quando não há fraqueza |
| `retreat_cost` | int | sim | `null` em Trainers |
| `img` | string (URL) | não | Imagem `.webp` da carta |
| `set` | [CardSet](#cardset) | não | |

#### Pokémon

```json
{
  "id": "A1-260", "number": 260, "name": "Zapdos ex",
  "type": "Lightning", "hp": 130, "card_type": "Pokémon", "stage": "Basic",
  "evolve": null, "rarity": "☆☆", "ability": null,
  "attacks": [
    { "name": "Peck", "cost": ["L"], "energy_count": 1, "damage": 20,
      "damage_modifier": null, "effect": null },
    { "name": "Thundering Hurricane", "cost": ["L", "L", "L"], "energy_count": 3, "damage": 50,
      "damage_modifier": "x", "effect": "Flip 4 coins. This attack does 50 damage for each heads." }
  ],
  "effect": null, "weakness": "Lightning", "retreat_cost": 1,
  "img": "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/pocket/A1/A1_260_EN_SM.webp",
  "set": { "code": "A1", "name": "Genetic Apex", "release_date": "2024-10-30",
           "url": "https://pocket.limitlesstcg.com/cards/A1" }
}
```

#### Trainer

```json
{
  "id": "B1-213", "number": 213, "name": "Prank Spinner",
  "type": null, "hp": null, "card_type": "Trainer", "stage": "Item",
  "evolve": null, "rarity": "◊◊", "ability": null, "attacks": [],
  "effect": "A card from among both player's hands is chosen at random, revealed to the other player, and shuffled into its owner's deck.",
  "weakness": null, "retreat_cost": null,
  "img": "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/pocket/B1/B1_213_EN_SM.webp",
  "set": { "code": "B1", "name": "Mega Rising", "release_date": "2025-10-30",
           "url": "https://pocket.limitlesstcg.com/cards/B1" }
}
```

### Attack

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `name` | string | não | Só o nome, sem o dano: `"X-Scissor"` |
| `cost` | string[] | não | Símbolos de energia (ver `/types`). `[]` quando o ataque não tem custo |
| `energy_count` | int | não | `cost.length` |
| `damage` | int | sim | Dano base. `null` quando o ataque não causa dano direto |
| `damage_modifier` | `"+"` \| `"x"` | sim | `"+"`: o dano base pode aumentar (ex.: 50+). `"x"`: o dano é por ocorrência (ex.: 50 por cara na moeda). `null`: dano fixo |
| `effect` | string | sim | Texto do efeito; `null` quando não há |

Para exibir o dano como na carta: `` `${damage}${damage_modifier ?? ""}` `` → `"50+"`, `"20x"`, `"60"`.

### Ability

| Campo | Tipo | Nulo? |
|---|---|---|
| `name` | string | não |
| `text` | string | sim |

### CardSet

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `code` | string | não | `"A1"`, `"B2a"`, `"P-A"` |
| `name` | string | não | Sem o código: `"Genetic Apex"` |
| `release_date` | date | sim | `null` nos sets de promo |
| `url` | string | não | Página do set na Limitless |

---

## 3. Endpoints

| Método e rota | Resposta | Uso no dashboard |
|---|---|---|
| `GET /meta` | [Meta](#31-get-meta) | Verificação de saúde e "atualizado em" |
| `GET /stats` | [Stats](#32-get-stats) | Total de cartas (F1) e contagem por energia (F2) |
| `GET /cards/ranking` | [Ranking](#33-get-cardsranking) | Top 10 (F3) |
| `GET /types` | [TypeInfo](#34-get-types)[] | Rótulos, ordem e legenda dos tipos |
| `GET /sets` | [SetSummary](#35-get-sets)[] | Filtro por set |
| `GET /cards` | [CardPage](#36-get-cards) | Listagem, drill-down |
| `GET /cards/{set_id}/{card_id}` | [Card](#card) | Detalhe de uma carta |
| `GET /cards/search/name/{name}` | [Card](#card)[] | Busca por nome |
| `GET /cards/filter/*` | [Card](#card)[] | **Deprecated**, ver [§3.9](#39-rotas-deprecated) |

### 3.1 `GET /meta`

```json
{ "api_version": "2.0.0", "data_version": "2026-11-04T12:00:00Z",
  "source": "https://pocket.limitlesstcg.com", "total_cards": 18 }
```

`data_version` é o momento da coleta dos dados, não do deploy.

### 3.2 `GET /stats`

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `distinct` | bool | `false` | `true` conta reimpressões uma vez só (mesmo `name` e mesmos `attacks`) |

```json
{
  "total_cards": 18,
  "distinct_cards": 17,
  "by_card_type": { "Pokémon": 14, "Trainer": 4 },
  "by_type": { "Grass": 4, "Fire": 3, "Psychic": 2, "Dragon": 2, "Lightning": 1, "Colorless": 1, "Water": 1 },
  "by_set": { "A1": 4, "B1": 4, "A3": 2, "A4": 2, "A4b": 2, "A2": 1, "B2a": 1, "P-A": 1, "P-B": 1 },
  "data_version": "2026-11-04T12:00:00Z"
}
```

- `total_cards` e `distinct_cards` não mudam com `distinct`. Os três `by_*` mudam.
- Os `by_*` vêm em ordem decrescente de contagem. Uma chave só aparece se tiver contagem maior que zero: tipos sem cartas não aparecem, então use `/types` para a lista completa.
- `by_type` só conta cartas com `type` (Pokémon). Tipos duplos aparecem com a chave literal (`"Psychic/Fighting"`). Assim, a soma de `by_type` é igual a `by_card_type["Pokémon"]`.

### 3.3 `GET /cards/ranking`

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `metric` | `damage_per_energy` \| `damage` \| `hp` | `damage_per_energy` | |
| `limit` | int 1–100 | `10` | |
| `distinct` | bool | `true` | Reimpressões contam uma vez; a carta mostrada é a impressão mais antiga |
| `type` | string | — | Tipo de energia. Tipos duplos entram nos dois tipos |
| `include_variable` | bool | `true` | `false` exclui ataques com `damage_modifier` |

**Regras:**
- Só entram Pokémon. Para cada carta vale o melhor ataque segundo a métrica.
- Ataques com custo zero ou `damage: null` são ignorados. Cartas sem nenhum ataque válido ficam fora do ranking.
- Ataques `+` e `x` contam pelo dano base.
- Desempate: maior dano, depois menor custo, depois nome em ordem alfabética. Com `metric=hp`, desempata pelo nome.
- `value` é arredondado para 2 casas (`80/3` → `26.67`). O `rank` é sequencial, sem posições repetidas.

```json
{
  "metric": "damage_per_energy",
  "items": [
    {
      "rank": 1,
      "card": { "id": "A3-127", "name": "Kommo-o", "type": "Dragon",
                "img": "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/pocket/A3/A3_127_EN_SM.webp" },
      "attack": { "name": "Clanging Scales", "cost": ["L", "F"], "energy_count": 2,
                  "damage": 130, "damage_modifier": null },
      "value": 65.0,
      "printings": 1
    }
  ]
}
```

- `printings`: quantas impressões existem da carta, com qualquer valor de `distinct`.
- `attack` é `null` quando `metric=hp`:

```json
{ "metric": "hp", "items": [ { "rank": 1,
  "card": { "id": "A4-34", "name": "Ho-Oh ex", "type": "Fire", "img": "..." },
  "attack": null, "value": 150.0, "printings": 2 } ] }
```

### 3.4 `GET /types`

Lista fixa, na ordem abaixo. `symbol` é a letra usada em `Attack.cost`. Dragon não tem energia própria.

```json
[
  { "type": "Grass", "symbol": "G" }, { "type": "Fire", "symbol": "R" },
  { "type": "Water", "symbol": "W" }, { "type": "Lightning", "symbol": "L" },
  { "type": "Psychic", "symbol": "P" }, { "type": "Fighting", "symbol": "F" },
  { "type": "Darkness", "symbol": "D" }, { "type": "Metal", "symbol": "M" },
  { "type": "Colorless", "symbol": "C" }, { "type": "Dragon", "symbol": null }
]
```

### 3.5 `GET /sets`

Ordem de lançamento, do mais antigo para o mais novo. Os promos (`release_date: null`) vêm no fim.

```json
[
  { "code": "A1", "name": "Genetic Apex", "release_date": "2024-10-30", "card_count": 4 },
  { "code": "A2", "name": "Space-Time Smackdown", "release_date": "2025-01-29", "card_count": 1 },
  { "code": "P-A", "name": "Promo-A", "release_date": null, "card_count": 1 }
]
```

### 3.6 `GET /cards`

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `type` | string | — | Tipo de energia (ver `/types`). Tipos duplos entram nos dois tipos |
| `card_type` | string | — | `Pokémon` ou `Trainer` (`pokemon` também vale) |
| `set` | string | — | Código do set (ver `/sets`) |
| `stage` | string | — | `Basic`, `Stage 1`, `Stage 2`, `Item`, `Supporter`, `Tool`, `Stadium` |
| `rarity` | string | — | Valor exato do símbolo, ex. `◊◊` (codificado na URL: `%E2%97%8A%E2%97%8A`) |
| `fields` | string | — | Campos separados por vírgula, ex. `id,name,type,img`. Campos de nível superior de [Card](#card) |
| `sort` | string | ordem do catálogo | `name`, `number`, `hp`, `type`, `retreat_cost`, `set` (por lançamento). Prefixo `-` para decrescente. Nulos sempre no fim |
| `limit` | int 1–1000 | `100` | |
| `offset` | int ≥ 0 | `0` | |

Os filtros se combinam com E. Um valor fora do catálogo retorna `422` com os valores aceitos.

```
GET /cards?type=Dragon&fields=id,name,type,hp&limit=2
```

```json
{ "total": 2, "limit": 2, "offset": 0,
  "items": [ { "id": "A3-126", "name": "Hakamo-o", "type": "Dragon", "hp": 100 },
             { "id": "A3-127", "name": "Kommo-o", "type": "Dragon", "hp": 150 } ] }
```

- `total` é o número de cartas que passaram nos filtros, antes da paginação. Fim da lista: `offset + items.length >= total`.
- Sem `fields`, cada item é um [Card](#card) completo. Com `fields`, cada item tem só os campos pedidos, mas o formato de cada campo não muda.
- Para baixar o catálogo inteiro: páginas de `limit=1000` até chegar ao `total`. São 5 páginas para cerca de 4.500 cartas.

### 3.7 `GET /cards/{set_id}/{card_id}`

`/cards/A1/260` → [Card](#card) com `id: "A1-260"`. Para montar a rota a partir do `id`: `` `/cards/${card.set.code}/${card.number}` `` (não faça `split("-")`, porque `P-A-1` tem hífen no código do set).

`404` com `{"detail": "Card not found"}` quando a carta não existe.

### 3.8 `GET /cards/search/name/{name}`

Lista de [Card](#card) cujo nome contém `name`, sem diferenciar maiúsculas nem acentos. Sem paginação.

### 3.9 Rotas deprecated

Funcionam, mas vão sair em uma versão futura. Retornam `Card[]` sem paginação.

| Rota | Use no lugar |
|---|---|
| `GET /cards/filter/type/{card_type}` (filtra **energia**, não `card_type`) | `/cards?type=` |
| `GET /cards/filter/set/{set_name}` (aceita código ou nome) | `/cards?set=` |
| `GET /cards/filter/rarity/{rarity}` | `/cards?rarity=` |

---

## 4. Tipos TypeScript

Equivalentes ao `openapi.json`. Para gerar automaticamente: `npx openapi-typescript docs/openapi.json -o src/api.d.ts`.

```ts
export type EnergySymbol = "G" | "R" | "W" | "L" | "P" | "F" | "D" | "M" | "C";

export interface Attack {
  name: string;
  cost: EnergySymbol[];
  energy_count: number;
  damage: number | null;
  damage_modifier: "+" | "x" | null;
  effect: string | null;
}

export interface Ability { name: string; text: string | null; }

export interface CardSet { code: string; name: string; release_date: string | null; url: string; }

export interface Card {
  id: string;
  number: number;
  name: string;
  type: string | null;
  hp: number | null;
  card_type: "Pokémon" | "Trainer";
  stage: string | null;
  evolve: string | null;
  rarity: string | null;
  ability: Ability | null;
  attacks: Attack[];
  effect: string | null;
  weakness: string | null;
  retreat_cost: number | null;
  img: string;
  set: CardSet;
}

export interface CardPage<T = Card> { total: number; limit: number; offset: number; items: T[]; }

export interface Stats {
  total_cards: number;
  distinct_cards: number;
  by_card_type: Record<string, number>;
  by_type: Record<string, number>;
  by_set: Record<string, number>;
  data_version: string;
}

export interface RankingItem {
  rank: number;
  card: Pick<Card, "id" | "name" | "type" | "img">;
  attack: Omit<Attack, "effect" | "damage"> & { damage: number } | null;
  value: number;
  printings: number;
}

export interface Ranking { metric: "damage_per_energy" | "damage" | "hp"; items: RankingItem[]; }
export interface TypeInfo { type: string; symbol: EnergySymbol | null; }
export interface Meta { api_version: string; data_version: string; source: string; total_cards: number; }
export interface SetSummary { code: string; name: string; release_date: string | null; card_count: number; }
```

---

## 5. Receitas para o dashboard

| Necessidade | Chamada |
|---|---|
| Acordar a API e pegar "atualizado em" | `GET /meta` → `data_version` |
| Total de cartas (F1) | `GET /stats` → `total_cards` (ou `distinct_cards`) |
| Cartas por energia (F2) | `GET /stats?distinct=true` → `by_type`, com rótulos e ordem de `GET /types` |
| Top 10 dano por energia (F3) | `GET /cards/ranking` (já vem com `distinct=true` e `limit=10`) |
| Drill-down de uma barra de energia | `GET /cards?type=Fire&card_type=Pokémon&fields=id,name,img,hp&limit=1000` |

Com essas chamadas, o dashboard não precisa mais baixar o catálogo inteiro, normalizar dados nem calcular o ranking no cliente.

---

## 6. Migração da v1

| v1 | v2 |
|---|---|
| `GET /cards` → `Card[]`; sem `limit`, devolvia tudo | `GET /cards` → `{total, limit, offset, items}`; `limit` padrão **100**, máximo 1000 |
| `id: "/A1/1"` | `id: "A1-1"`; novo campo `number: 1` |
| `hp: "70"`, `retreat_cost: "1"`, `damage: "40"` | inteiros |
| `cost: "GGC"`; `"0"` no custo zero | `cost: ["G","G","C"]`; `[]` no custo zero; novo campo `energy_count` |
| `name: "X-Scissor 50+"`, `damage: null` | `name: "X-Scissor"`, `damage: 50`, `damage_modifier: "+"` |
| `evolve: "None"` | `evolve: null` |
| `weakness: "none"` | `weakness: null` |
| `attacks[].effect: ""` | `attacks[].effect: null` |
| `ability.name: "Ability: \n   Toughness Aroma"` | `ability.name: "Toughness Aroma"` |
| `set: {url, name: "Genetic Apex A1"}` | `set: {code: "A1", name: "Genetic Apex", release_date, url}` |
| — | novos campos `rarity` e `effect` (texto das Trainers) |
| 32 cartas com nome, tipo ou HP quebrados (Ho-Oh, Porygon-Z, Chien-Pao, Kommo-o…) | corrigidas |
| `GET /stats` → 500 | formato da [§3.2](#32-get-stats) |
| `GET /cards/filter/type` e `/set` → 500; `rarity` → `[]` | funcionam (deprecated) |
| — | novas rotas `/cards/ranking`, `/types`, `/meta`, `/sets` |
| Sem CORS, gzip, cache nem `HEAD` | com todos (ver [§1](#1-convenções)) |
