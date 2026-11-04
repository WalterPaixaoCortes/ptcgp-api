"""Scraper for https://pocket.limitlesstcg.com.

Writes data/cards.json in the format served by the API (see main.py).
Run from the repo root:  python scripts/scrape.py
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from random import choice

import bs4
import requests

BASE_URL = "https://pocket.limitlesstcg.com"
OUTPUT = Path(__file__).resolve().parent.parent / "data" / "cards.json"
RARITY_ALIASES = {"Crown Rare": "♛"}

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
)


def clean(text):
    """Collapse whitespace/newlines into single spaces; empty text becomes None."""
    return " ".join(text.split()) or None


def block_text(element):
    """Text of an element, treating <br> as a space (so sentences don't run together)."""
    for br in element.find_all("br"):
        br.replace_with(" ")
    return clean(element.text)


def fetch(url, retries=3):
    """GET with retries; returns the response or None after repeated failures."""
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 200:
                return response
            print(f"Status {response.status_code} on {url} (attempt {attempt}/{retries})")
        except requests.RequestException as e:
            print(f"Error on {url}: {e} (attempt {attempt}/{retries})")
        time.sleep(10 * attempt)
    return None


def parse_release_date(text):
    """'29 Oct 26' -> '2026-10-29'; promos have no date."""
    text = clean(text)
    return datetime.strptime(text, "%d %b %y").date().isoformat() if text else None


def get_sets():
    response = fetch(f"{BASE_URL}/cards")
    if response is None:
        sys.exit(f"Failed to retrieve sets from {BASE_URL}")

    table = bs4.BeautifulSoup(response.content, "html.parser").find("table", {"class": "sets-table"})
    sets = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:  # header / series sub-heading rows
            continue
        link = cells[0].find("a")
        code_span = link.find("span", {"class": "code"})
        code = clean(code_span.text)
        code_span.extract()
        sets.append(
            {
                "code": code,
                "name": clean(link.text),
                "release_date": parse_release_date(cells[1].text),
                "url": f"{BASE_URL}{link.get('href')}",
            }
        )
    return sets


def get_card_list(sets):
    card_list = []
    for card_set in sets:
        response = fetch(card_set["url"])
        if response is None:
            print(f"Failed to retrieve cards from set {card_set['code']}")
            continue

        grid = bs4.BeautifulSoup(response.content, "html.parser").find("div", {"class": "card-search-grid"})
        cards = grid.find_all("a")
        for row in cards:
            href = row.get("href")  # /cards/A1/1
            card_list.append(
                {
                    "url": f"{BASE_URL}{href}",
                    "number": int(href.rstrip("/").rsplit("/", 1)[1]),
                    "img": row.img.get("src"),
                    "set": card_set,
                }
            )
        print(f"Retrieved {len(cards)} cards from {card_set['name']} ({card_set['code']})")
        time.sleep(20)
    return card_list


def parse_attack(attack):
    info = attack.find("p", {"class": "card-text-attack-info"})
    symbol = info.find("span", {"class": "ptcg-symbol"})
    cost_text = clean(symbol.text) if symbol else None
    if symbol:
        symbol.extract()
    cost = [] if cost_text in (None, "0") else list(cost_text)

    # "Dragon Claw 60" / "X-Scissor 50+" / "Shivery Wave 20x" / "Growl"
    text = clean(info.text)
    match = re.fullmatch(r"(.*?)\s+(\d+)([+x×])?", text)
    if match:
        name, damage, modifier = match.group(1), int(match.group(2)), match.group(3)
    else:
        name, damage, modifier = text, None, None

    effect = attack.find("p", {"class": "card-text-attack-effect"})
    return {
        "name": name,
        "cost": cost,
        "energy_count": len(cost),
        "damage": damage,
        "damage_modifier": "x" if modifier == "×" else modifier,
        "effect": block_text(effect) if effect else None,
    }


def parse_card(html, item):
    page = bs4.BeautifulSoup(html, "html.parser")
    card = page.find("div", {"class": "card-details-main"})
    sections = card.find_all("div", {"class": "card-text-section"})

    # Line 1: "<name> - <type> - <hp> HP" (fossils: "<name> - 40 HP"; trainers: "<name>").
    # The name comes from its own <span>, so hyphenated names (Ho-Oh, Porygon-Z) stay intact.
    title = card.find("p", {"class": "card-text-title"})
    name_span = title.find("span", {"class": "card-text-name"})
    name = clean(name_span.text)
    name_span.extract()
    ptype = hp = None
    for part in (clean(title.text) or "").split(" - "):
        part = part.strip(" -")
        if part.endswith("HP"):
            hp = int(part.removesuffix("HP"))
        elif part:
            ptype = part

    # Line 2: "Pokémon - Stage 1 - Evolves from Jangmo-o" / "Trainer - Item"
    type_parts = clean(card.find("p", {"class": "card-text-type"}).text).split(" - ")
    card_type = type_parts[0]
    stage = type_parts[1] if len(type_parts) > 1 else None
    evolve = type_parts[2] if len(type_parts) > 2 else None

    ability = None
    ability_div = card.find("div", {"class": "card-text-ability"})
    if ability_div:
        ability_name = clean(ability_div.find("p", {"class": "card-text-ability-info"}).text)
        ability = {
            "name": ability_name.removeprefix("Ability:").strip(),
            "text": block_text(ability_div.find("p", {"class": "card-text-ability-effect"})),
        }

    attacks = [parse_attack(a) for a in card.find_all("div", {"class": "card-text-attack"})]

    # Trainer effect text lives in the second section, with no class of its own.
    effect = block_text(sections[1]) if card_type == "Trainer" and len(sections) > 1 else None

    weakness = retreat = None
    wrr = card.find("p", {"class": "card-text-wrr"})
    if wrr:
        for line in wrr.get_text("\n").split("\n"):
            line = clean(line) or ""
            if line.startswith("Weakness:"):
                weakness = line.removeprefix("Weakness:").strip()
                weakness = None if weakness.lower() == "none" else weakness
            elif line.startswith("Retreat:"):
                retreat = int(line.removeprefix("Retreat:"))

    # "Genetic Apex (A1) #1 · ◊ · Mewtwo pack". For promos the 2nd field is the
    # source ("Shop", "Premium Missions"), not a rarity.
    rarity = None
    prints = page.find("div", {"class": "prints-current-details"})
    if prints and not item["set"]["code"].startswith("P-"):
        parts = [p.strip() for p in clean(prints.text).split("·")]
        if len(parts) > 1:
            rarity = RARITY_ALIASES.get(parts[1], parts[1])

    return {
        "id": f"{item['set']['code']}-{item['number']}",
        "number": item["number"],
        "name": name,
        "type": ptype,
        "hp": hp,
        "card_type": card_type,
        "stage": stage,
        "evolve": evolve,
        "rarity": rarity,
        "ability": ability,
        "attacks": attacks,
        "effect": effect,
        "weakness": weakness,
        "retreat_cost": retreat,
        "img": item["img"],
        "set": item["set"],
    }


def get_cards(card_list):
    dataset, failed = [], []
    for i, item in enumerate(card_list, start=1):
        response = fetch(item["url"])
        if response is None:
            failed.append(item)
            continue
        try:
            dataset.append(parse_card(response.content, item))
        except Exception as e:
            print(f"Failed to parse {item['url']}: {e!r}")
            failed.append(item)

        if i % 10 == 0:
            delayed = choice([1, 3, 5, 7])
            print(f"Processed {i}/{len(card_list)} cards, sleeping for {delayed} seconds to avoid rate limiting.")
            time.sleep(delayed)

    print(f"Done: {len(dataset)} cards parsed, {len(failed)} failed.")
    for item in failed:
        print(f"  failed: {item['url']}")
    return dataset, failed


def save(dataset, path=OUTPUT):
    payload = {
        "data_version": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": BASE_URL,
        "cards": dataset,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(dataset)} cards to {path}")


if __name__ == "__main__":
    sets = get_sets()
    print(f"Found {len(sets)} sets.")
    dataset, failed = get_cards(get_card_list(sets))
    save(dataset)
    sys.exit(1 if failed else 0)
