import hashlib
import json
import os
import unicodedata
from collections import Counter, defaultdict
from contextlib import asynccontextmanager
from datetime import date
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ValidationError, model_validator

API_VERSION = "2.1.0"
DATA_FILE = os.environ.get("CARDS_FILE", "data/cards.json")
CACHE_CONTROL = "public, max-age=3600"

# Energy types and the letter used for them in attack costs. Dragon has no energy.
TYPES = [
    ("Grass", "G"),
    ("Fire", "R"),
    ("Water", "W"),
    ("Lightning", "L"),
    ("Psychic", "P"),
    ("Fighting", "F"),
    ("Darkness", "D"),
    ("Metal", "M"),
    ("Colorless", "C"),
    ("Dragon", None),
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Attack(BaseModel):
    name: str
    cost: list[str]  # energy symbols, see /types; empty when the attack is free
    energy_count: int
    damage: Optional[int]
    damage_modifier: Optional[Literal["+", "x"]]  # "+": base damage plus a bonus; "x": damage per hit
    effect: Optional[str]


class Ability(BaseModel):
    name: str
    text: Optional[str]


class CardSet(BaseModel):
    code: str
    name: str
    release_date: Optional[date]
    url: str


class Card(BaseModel):
    id: str  # "<set code>-<number>", matches /cards/{set_id}/{card_id}
    number: int
    name: str
    type: Optional[str]  # first energy type; null for Trainers
    types: list[str]  # all energy types (two for dual-type cards); empty for Trainers
    hp: Optional[int]
    card_type: Literal["Pokémon", "Trainer"]
    stage: Optional[str]
    evolve: Optional[str]
    rarity: Optional[str]  # null for promos
    ability: Optional[Ability]
    attacks: list[Attack]
    effect: Optional[str]  # Trainer card text
    weakness: Optional[str]
    retreat_cost: Optional[int]
    img: str
    set: CardSet

    @model_validator(mode="after")
    def check_scraped_fields(self):
        if "\n" in self.name:
            raise ValueError(f"name contains leaked markup: {self.name!r}")
        if self.card_type == "Pokémon" and (not self.types or self.hp is None):
            raise ValueError("Pokémon without type or hp")
        if self.type != (self.types[0] if self.types else None) or any("/" in t for t in self.types):
            raise ValueError(f"inconsistent type {self.type!r} / types {self.types!r}")
        return self


class CardPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[Card]


class Stats(BaseModel):
    total_cards: int
    distinct_cards: int
    by_card_type: dict[str, int]
    by_type: dict[str, int]
    by_set: dict[str, int]
    data_version: str


class RankingCard(BaseModel):
    id: str
    name: str
    type: Optional[str]
    types: list[str]
    img: str


class RankingAttack(BaseModel):
    name: str
    cost: list[str]
    energy_count: int
    damage: int
    damage_modifier: Optional[Literal["+", "x"]]


class RankingItem(BaseModel):
    rank: int
    card: RankingCard
    attack: Optional[RankingAttack]  # null for metric=hp
    value: float
    printings: int


class Ranking(BaseModel):
    metric: str
    items: list[RankingItem]


class TypeInfo(BaseModel):
    type: str
    symbol: Optional[str]


class Meta(BaseModel):
    api_version: str
    data_version: str
    source: str
    total_cards: int


class SetSummary(BaseModel):
    code: str
    name: str
    release_date: Optional[date]
    card_count: int


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def printing_key(card: Card):
    """Cards with the same name and attacks are reprints of the same card."""
    return (card.name, tuple((a.name, tuple(a.cost), a.damage, a.damage_modifier, a.effect) for a in card.attacks))


def release_order(card: Card):
    """Oldest printing first; promos (no release date) last."""
    return (card.set.release_date is None, card.set.release_date or date.max, card.set.code, card.number)


class Catalog:
    def __init__(self, cards: list[Card], data_version: str, source: str):
        self.cards = cards
        self.data_version = data_version
        self.source = source
        self.by_id = {c.id: c for c in cards}
        self.dumped = {c.id: c.model_dump(mode="json") for c in cards}

        groups = defaultdict(list)
        for card in cards:
            groups[printing_key(card)].append(card)
        self.printings = {key: sorted(group, key=release_order) for key, group in groups.items()}
        # One card per group (the original printing), in catalog order.
        originals = {id(group[0]) for group in self.printings.values()}
        self.distinct = [c for c in cards if id(c) in originals]

        self.sets = {}
        for card in cards:
            self.sets.setdefault(card.set.code, card.set)
        self.stages = sorted({c.stage for c in cards if c.stage})
        self.rarities = sorted({c.rarity for c in cards if c.rarity})


def load_data(path: str = DATA_FILE) -> Catalog:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    cards, errors = [], []
    for record in raw["cards"]:
        try:
            cards.append(Card.model_validate(record))
        except ValidationError as e:
            errors.append(f"{record.get('id')}: {e.errors()[0]['msg']}")
    if errors:
        raise RuntimeError(f"{len(errors)} invalid cards in {path}:\n" + "\n".join(errors[:20]))
    return Catalog(cards, raw["data_version"], raw["source"])


catalog: Optional[Catalog] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global catalog
    catalog = load_data()
    yield


# ---------------------------------------------------------------------------
# App and middleware
# ---------------------------------------------------------------------------

app = FastAPI(
    title="PTCGP API",
    description="API for TCG Pocket Simulator - Card Database",
    version=API_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """ETag + Cache-Control for GETs. Data only changes on deploy, so the data version identifies it."""
    if request.method != "GET" or catalog is None:
        return await call_next(request)

    digest = hashlib.sha1(f"{API_VERSION}|{catalog.data_version}|{request.url.path}?{request.url.query}".encode()).hexdigest()
    etag = f'W/"{digest[:20]}"'
    headers = {"ETag": etag, "Cache-Control": CACHE_CONTROL}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)

    response = await call_next(request)
    if response.status_code == 200:
        response.headers.update(headers)
    return response


class HeadAsGet:
    """Answer HEAD like GET without a body (FastAPI routes only accept GET)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "HEAD":
            return await self.app(scope, receive, send)

        async def send_without_body(message):
            if message["type"] == "http.response.body":
                message = {**message, "body": b""}
            await send(message)

        await self.app({**scope, "method": "GET"}, receive, send_without_body)


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD"],
    allow_headers=["*"],
    expose_headers=["ETag"],
)
app.add_middleware(HeadAsGet)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def norm(value: str) -> str:
    """Case- and accent-insensitive form: 'Pokémon' -> 'pokemon'."""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold().strip()


def match_value(param: str, value: Optional[str], allowed: list[str]) -> str:
    """Return the catalog spelling of `value`, or 422 if it isn't in `allowed`."""
    for option in allowed:
        if norm(option) == norm(value):
            return option
    raise HTTPException(status_code=422, detail=f"Invalid {param} {value!r}. Allowed: {', '.join(allowed)}")


def filter_cards(
    cards: list[Card],
    type: Optional[str] = None,
    card_type: Optional[str] = None,
    set: Optional[str] = None,
    stage: Optional[str] = None,
    rarity: Optional[str] = None,
) -> list[Card]:
    if type:
        type = match_value("type", type, [t for t, _ in TYPES])
        cards = [c for c in cards if type in c.types]
    if card_type:
        card_type = match_value("card_type", card_type, ["Pokémon", "Trainer"])
        cards = [c for c in cards if c.card_type == card_type]
    if set:
        set = match_value("set", set, list(catalog.sets))
        cards = [c for c in cards if c.set.code == set]
    if stage:
        stage = match_value("stage", stage, catalog.stages)
        cards = [c for c in cards if c.stage == stage]
    if rarity:
        rarity = match_value("rarity", rarity, catalog.rarities)
        cards = [c for c in cards if c.rarity == rarity]
    return cards


SORT_KEYS = {
    "name": lambda c: c.name.lower(),
    "number": lambda c: c.number,
    "hp": lambda c: c.hp,
    "type": lambda c: c.type,
    "retreat_cost": lambda c: c.retreat_cost,
    "set": lambda c: release_order(c),
}


def sort_cards(cards: list[Card], sort: str) -> list[Card]:
    field = sort.removeprefix("-")
    if field not in SORT_KEYS:
        raise HTTPException(status_code=422, detail=f"Invalid sort {sort!r}. Allowed: {', '.join(SORT_KEYS)} (prefix '-' for descending)")
    key = SORT_KEYS[field]
    present = [c for c in cards if key(c) is not None]
    missing = [c for c in cards if key(c) is None]  # nulls always go last
    return sorted(present, key=key, reverse=sort.startswith("-")) + missing


def originals_only(cards: list[Card]) -> list[Card]:
    keep = {id(c) for c in catalog.distinct}
    return [c for c in cards if id(c) in keep]


def count_by(values) -> dict[str, int]:
    return dict(Counter(v for v in values if v is not None).most_common())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    return {"message": "PTCGP API - TCG Pocket Simulator", "version": API_VERSION}


@app.get("/cards", response_model=CardPage)
async def get_cards(
    type: Optional[str] = Query(None, description="Energy type, e.g. Fire (see /types)"),
    card_type: Optional[str] = Query(None, description="Pokémon or Trainer"),
    set: Optional[str] = Query(None, description="Set code, e.g. A1 (see /sets)"),
    stage: Optional[str] = Query(None, description="Basic, Stage 1, Stage 2, Item, Supporter, Tool, Stadium"),
    rarity: Optional[str] = Query(None, description="e.g. ◊◊, ☆, ♛"),
    fields: Optional[str] = Query(None, description="Comma-separated fields to return, e.g. id,name,type,img"),
    sort: Optional[str] = Query(None, description="name, number, hp, type, retreat_cost or set; prefix '-' for descending"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Cards in the catalog, with filters (case-insensitive), projection and the total count."""
    cards = filter_cards(catalog.cards, type, card_type, set, stage, rarity)
    if sort:
        cards = sort_cards(cards, sort)
    page = cards[offset : offset + limit]

    if fields:
        selected = [f.strip() for f in fields.split(",") if f.strip()]
        unknown = [f for f in selected if f not in Card.model_fields]
        if unknown:
            raise HTTPException(status_code=422, detail=f"Unknown fields: {', '.join(unknown)}. Allowed: {', '.join(Card.model_fields)}")
        items = [{f: catalog.dumped[c.id][f] for f in selected} for c in page]
        return JSONResponse({"total": len(cards), "limit": limit, "offset": offset, "items": items})

    return CardPage(total=len(cards), limit=limit, offset=offset, items=page)


@app.get("/cards/ranking", response_model=Ranking)
async def get_ranking(
    metric: Literal["damage_per_energy", "damage", "hp"] = "damage_per_energy",
    limit: int = Query(10, ge=1, le=100),
    distinct: bool = Query(True, description="Count reprints (same name and attacks) once"),
    type: Optional[str] = Query(None, description="Energy type (see /types)"),
    include_variable: bool = Query(True, description="Include '+'/'x' attacks at their base damage"),
):
    """Pokémon ranked by their best attack (or HP).

    Attacks with zero cost or no damage are ignored. Ties: higher damage, then lower cost, then name.
    """
    cards = catalog.distinct if distinct else catalog.cards
    cards = [c for c in filter_cards(cards, type=type) if c.card_type == "Pokémon"]

    scored = []
    for card in cards:
        if metric == "hp":
            scored.append(((-card.hp, card.name), card, None, float(card.hp)))
            continue

        attacks = [
            a for a in card.attacks
            if a.energy_count > 0 and a.damage is not None and (include_variable or a.damage_modifier is None)
        ]
        if not attacks:
            continue

        def value(a: Attack) -> float:
            return a.damage / a.energy_count if metric == "damage_per_energy" else float(a.damage)

        best = max(attacks, key=lambda a: (value(a), a.damage, -a.energy_count))
        scored.append(((-value(best), -best.damage, best.energy_count, card.name), card, best, value(best)))

    scored.sort(key=lambda s: s[0])
    items = [
        RankingItem(
            rank=i,
            card=RankingCard(id=card.id, name=card.name, type=card.type, types=card.types, img=card.img),
            attack=RankingAttack(**attack.model_dump(exclude={"effect"})) if attack else None,
            value=round(score, 2),
            printings=len(catalog.printings[printing_key(card)]),
        )
        for i, (_, card, attack, score) in enumerate(scored[:limit], start=1)
    ]
    return Ranking(metric=metric, items=items)


@app.get("/cards/search/name/{name}", response_model=list[Card])
async def search_cards_by_name(name: str):
    """Cards whose name contains `name` (case- and accent-insensitive)."""
    return [c for c in catalog.cards if norm(name) in norm(c.name)]


@app.get("/cards/filter/type/{card_type}", response_model=list[Card], deprecated=True)
async def filter_cards_by_type(card_type: str):
    """Deprecated: use /cards?type=. Filters by energy type (Fire, Water…)."""
    return filter_cards(catalog.cards, type=card_type)


@app.get("/cards/filter/rarity/{rarity}", response_model=list[Card], deprecated=True)
async def filter_cards_by_rarity(rarity: str):
    """Deprecated: use /cards?rarity=."""
    return filter_cards(catalog.cards, rarity=rarity)


@app.get("/cards/filter/set/{set_name}", response_model=list[Card], deprecated=True)
async def filter_cards_by_set(set_name: str):
    """Deprecated: use /cards?set=. Accepts the set code (A1) or its name (Genetic Apex)."""
    for code, card_set in catalog.sets.items():
        if norm(set_name) in (norm(card_set.name), norm(f"{card_set.name} {code}")):
            set_name = code
    return filter_cards(catalog.cards, set=set_name)


@app.get("/cards/{set_id}/{card_id}", response_model=Card)
async def get_card_by_id(set_id: str, card_id: str):
    """A single card, e.g. /cards/A1/1 (id A1-1)."""
    card = catalog.by_id.get(f"{set_id}-{card_id}")
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@app.get("/stats", response_model=Stats)
async def get_stats(distinct: bool = Query(False, description="Count reprints (same name and attacks) once")):
    """Card counts by card type, energy type and set."""
    cards = catalog.distinct if distinct else catalog.cards
    return Stats(
        total_cards=len(catalog.cards),
        distinct_cards=len(catalog.distinct),
        by_card_type=count_by(c.card_type for c in cards),
        by_type=count_by(t for c in cards for t in c.types),  # dual-type cards count in both
        by_set=count_by(c.set.code for c in cards),
        data_version=catalog.data_version,
    )


@app.get("/types", response_model=list[TypeInfo])
async def get_types():
    """Energy types and the symbol used for them in attack costs."""
    return [TypeInfo(type=t, symbol=s) for t, s in TYPES]


@app.get("/meta", response_model=Meta)
async def get_meta():
    """API and data versions. Cheap to call: use it as a health check."""
    return Meta(
        api_version=API_VERSION,
        data_version=catalog.data_version,
        source=catalog.source,
        total_cards=len(catalog.cards),
    )


@app.get("/sets", response_model=list[SetSummary])
async def get_sets():
    """Sets ordered by release date (promos, which have no date, last)."""
    counts = Counter(c.set.code for c in catalog.cards)
    ordered = sorted(catalog.sets.values(), key=lambda s: (s.release_date is None, s.release_date or date.max, s.code))
    return [SetSummary(code=s.code, name=s.name, release_date=s.release_date, card_count=counts[s.code]) for s in ordered]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
