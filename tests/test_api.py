import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
os.environ["CARDS_FILE"] = str(ROOT / "tests" / "fixtures" / "cards.json")

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


# P1 / E1
def test_stats(client):
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cards"] == 18
    assert body["distinct_cards"] == 17
    assert body["by_card_type"] == {"Pokémon": 14, "Trainer": 4}
    assert body["by_type"]["Fire"] == 3
    assert body["by_type"]["Dragon"] == 2
    assert body["by_set"]["A1"] == 4
    assert body["data_version"] == "2026-11-04T12:00:00Z"


def test_stats_distinct(client):
    body = client.get("/stats?distinct=true").json()
    assert body["by_card_type"]["Pokémon"] == 13
    assert body["by_type"]["Fire"] == 2


# P2 / P3 / P5 / E4
@pytest.mark.parametrize("value", ["Fire", "fire", "FIRE"])
def test_filter_by_type_case_insensitive(client, value):
    r = client.get(f"/cards?type={value}")
    assert r.status_code == 200
    assert {c["id"] for c in r.json()["items"]} == {"A4b-362", "A4-34", "B1-32"}


def test_filter_card_type_accepts_unaccented(client):
    assert client.get("/cards?card_type=pokemon").json()["total"] == 14
    assert client.get("/cards?card_type=Trainer").json()["total"] == 4


def test_filter_by_set_stage_rarity(client):
    assert client.get("/cards?set=a1").json()["total"] == 4
    assert {c["id"] for c in client.get("/cards?stage=Stage 2").json()["items"]} == {"A1-7", "A3-127"}
    assert {c["id"] for c in client.get("/cards?rarity=♛").json()["items"]} == {"A1-286"}


@pytest.mark.parametrize("query", ["type=Fairy", "card_type=Energy", "set=Z9", "rarity=Common", "sort=bogus", "fields=bogus"])
def test_invalid_values_return_422(client, query):
    r = client.get(f"/cards?{query}")
    assert r.status_code == 422
    assert "detail" in r.json()


def test_deprecated_filter_routes(client):
    assert {c["id"] for c in client.get("/cards/filter/type/Fire").json()} == {"A4b-362", "A4-34", "B1-32"}
    assert len(client.get("/cards/filter/set/A1").json()) == 4
    assert len(client.get("/cards/filter/set/Genetic Apex A1").json()) == 4
    assert len(client.get("/cards/filter/rarity/☆☆").json()) == 2
    assert client.get("/cards/filter/rarity/Common").status_code == 422


# P13 / E4
def test_pagination_envelope(client):
    body = client.get("/cards?limit=5&offset=15").json()
    assert body["total"] == 18
    assert (body["limit"], body["offset"]) == (5, 15)
    assert len(body["items"]) == 3


def test_fields_projection(client):
    body = client.get("/cards?type=Dragon&fields=id,name,type").json()
    assert body["items"] == [
        {"id": "A3-126", "name": "Hakamo-o", "type": "Dragon"},
        {"id": "A3-127", "name": "Kommo-o", "type": "Dragon"},
    ]


def test_sort(client):
    hps = [c["hp"] for c in client.get("/cards?sort=-hp&limit=1000").json()["items"]]
    assert hps[:3] == [150, 150, 150]
    assert hps[-1] is None  # trainers last


# P6 / P7 / P9 / P10 / P11 / P12 / P17
def test_card_shape(client):
    r = client.get("/cards/A3/127")
    assert r.status_code == 200
    card = r.json()
    assert card["id"] == "A3-127"
    assert card["name"] == "Kommo-o"
    assert (card["type"], card["hp"], card["card_type"], card["stage"]) == ("Dragon", 150, "Pokémon", "Stage 2")
    assert card["evolve"] == "Evolves from Hakamo-o"
    assert card["weakness"] is None
    assert card["retreat_cost"] == 2
    assert card["attacks"][0]["cost"] == ["L", "F"]
    assert card["set"] == {
        "code": "A3",
        "name": "Celestial Guardians",
        "release_date": "2025-04-30",
        "url": "https://pocket.limitlesstcg.com/cards/A3",
    }


def test_variable_damage_and_free_attack(client):
    zapdos = client.get("/cards/A1/260").json()
    assert zapdos["attacks"][1] == {
        "name": "Thundering Hurricane",
        "cost": ["L", "L", "L"],
        "energy_count": 3,
        "damage": 50,
        "damage_modifier": "x",
        "effect": "Flip 4 coins. This attack does 50 damage for each heads.",
    }
    smoochum = client.get("/cards/A4/75").json()
    assert smoochum["attacks"][0]["cost"] == []
    assert smoochum["attacks"][0]["energy_count"] == 0


def test_trainer_and_ability(client):
    assert client.get("/cards/B1/213").json()["effect"].startswith("A card from among")
    assert client.get("/cards/B1/18").json()["ability"] == {
        "name": "Toughness Aroma",
        "text": "Each of your [G] Pokémon gets +20 HP.",
    }
    assert client.get("/cards/P-A/1").json()["rarity"] is None


def test_card_not_found(client):
    r = client.get("/cards/A1/9999")
    assert r.status_code == 404
    assert r.json() == {"detail": "Card not found"}


def test_search_by_name(client):
    assert {c["id"] for c in client.get("/cards/search/name/ho-oh").json()} == {"A4b-362", "A4-34", "B1-32"}


# E2
def test_ranking_damage_per_energy(client):
    items = client.get("/cards/ranking?limit=6").json()["items"]
    assert [(i["card"]["name"], i["value"]) for i in items] == [
        ("Kommo-o", 65.0),
        ("Mewtwo ex", 37.5),
        ("Hakamo-o", 30.0),
        ("Ho-Oh ex", 26.67),
        ("Ho-Oh", 25.0),  # tie at 25: higher damage (100) beats Lilligant (50)
        ("Lilligant", 25.0),
    ]
    ho_oh_ex = items[3]
    assert ho_oh_ex["card"]["id"] == "A4-34"  # original printing
    assert ho_oh_ex["printings"] == 2
    assert ho_oh_ex["rank"] == 4
    assert ho_oh_ex["attack"] == {"name": "Phoenix Turbo", "cost": ["C", "C", "C"], "energy_count": 3, "damage": 80, "damage_modifier": None}


def test_ranking_ignores_free_attacks(client):
    names = [i["card"]["name"] for i in client.get("/cards/ranking?limit=100").json()["items"]]
    assert "Smoochum" not in names


def test_ranking_without_distinct_counts_reprints(client):
    names = [i["card"]["name"] for i in client.get("/cards/ranking?limit=100&distinct=false").json()["items"]]
    assert names.count("Ho-Oh ex") == 2


def test_ranking_exclude_variable_and_type(client):
    items = client.get("/cards/ranking?metric=damage&type=Lightning&include_variable=false").json()["items"]
    assert [(i["card"]["name"], i["attack"]["name"], i["value"]) for i in items] == [("Zapdos ex", "Peck", 20.0)]


def test_ranking_hp(client):
    items = client.get("/cards/ranking?metric=hp&limit=3").json()["items"]
    assert [(i["card"]["name"], i["value"], i["attack"]) for i in items] == [
        ("Ho-Oh ex", 150.0, None),
        ("Kommo-o", 150.0, None),
        ("Mewtwo ex", 150.0, None),
    ]


# E3 / E5 / E6
def test_types(client):
    types = client.get("/types").json()
    assert {"type": "Fire", "symbol": "R"} in types
    assert {"type": "Dragon", "symbol": None} in types


def test_meta(client):
    assert client.get("/meta").json() == {
        "api_version": main.API_VERSION,
        "data_version": "2026-11-04T12:00:00Z",
        "source": "https://pocket.limitlesstcg.com",
        "total_cards": 18,
    }


def test_sets(client):
    sets = client.get("/sets").json()
    assert sets[0] == {"code": "A1", "name": "Genetic Apex", "release_date": "2024-10-30", "card_count": 4}
    assert [s["code"] for s in sets[-2:]] == ["P-A", "P-B"]  # promos have no date


# P4 / P8 / P14 / P15 / P16
def test_cors(client):
    r = client.get("/cards?limit=1", headers={"Origin": "http://localhost:5173"})
    assert r.headers["access-control-allow-origin"] == "*"


def test_openapi_has_schemas(client):
    spec = client.get("/openapi.json").json()
    assert {"Card", "Attack", "Ability", "CardSet", "CardPage", "Stats", "Ranking"} <= set(spec["components"]["schemas"])
    ok = spec["paths"]["/cards"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok == {"$ref": "#/components/schemas/CardPage"}


def test_gzip(client):
    r = client.get("/cards?limit=1000", headers={"Accept-Encoding": "gzip"})
    assert r.headers["content-encoding"] == "gzip"


def test_etag_and_304(client):
    r = client.get("/stats")
    assert r.headers["cache-control"] == "public, max-age=3600"
    etag = r.headers["etag"]
    again = client.get("/stats", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    assert client.get("/meta").headers["etag"] != etag


def test_head(client):
    r = client.head("/cards?limit=1")
    assert r.status_code == 200
    assert r.content == b""
    assert r.headers["content-type"] == "application/json"


def test_unhandled_errors_are_json(client, monkeypatch):
    monkeypatch.setattr(main, "count_by", lambda values: 1 / 0)
    with TestClient(main.app, raise_server_exceptions=False) as c:
        r = c.get("/stats?distinct=true&x=1")
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal Server Error"}


# P7: ingestion validation
def test_load_rejects_leaked_markup(tmp_path):
    bad = (ROOT / "tests" / "fixtures" / "cards.json").read_text(encoding="utf-8")
    bad = bad.replace('"name": "Kommo-o"', '"name": "Kommo-o\\n - Dragon - 150 HP"', 1)
    path = tmp_path / "cards.json"
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(RuntimeError, match="A3-127"):
        main.load_data(str(path))


def test_real_data_is_valid():
    path = ROOT / "data" / "cards.json"
    catalog = main.load_data(str(path))
    assert len(catalog.cards) > 0
