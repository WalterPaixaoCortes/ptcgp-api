from fastapi import FastAPI, HTTPException, Query
from typing import List, Optional, Dict, Any
import json
import os
from pydantic import BaseModel
from contextlib import asynccontextmanager


app = FastAPI(
    title="PTCGP API",
    description="API for TCG Pocket Simulator - Card Database",
    version="1.0.0",
)


# Modelo para representar uma carta
class Card(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    rarity: Optional[str] = None
    set: Optional[str] = None
    # Adicione outros campos conforme necessário baseado na estrutura do seu cards.json


# Carregar dados do arquivo cards.json
def load_cards_data():
    try:
        with open("data/cards.json", "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="Cards data file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON format in cards data")


# Cache dos dados das cartas
cards_data = None


@app.on_event("startup")
async def startup_event():
    global cards_data
    cards_data = load_cards_data()


@app.get("/")
async def root():
    return {"message": "PTCGP API - TCG Pocket Simulator", "version": "1.0.0"}


@app.get("/cards", response_model=List[Dict[str, Any]])
async def get_all_cards(
    limit: Optional[int] = Query(
        None, ge=1, le=1000, description="Limit number of cards returned"
    ),
    offset: Optional[int] = Query(0, ge=0, description="Offset for pagination"),
):
    """Retorna todas as cartas com paginação opcional"""
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    # Se cards_data é uma lista
    if isinstance(cards_data, list):
        cards = cards_data
    # Se cards_data é um dict com uma chave que contém as cartas
    elif isinstance(cards_data, dict):
        # Assumindo que as cartas estão em uma chave como 'cards' ou similar
        cards = cards_data.get("cards", list(cards_data.values()))
    else:
        cards = []

    # Aplicar offset
    cards = cards[offset:]

    # Aplicar limit se especificado
    if limit:
        cards = cards[:limit]

    return cards


@app.get("/cards/{set_id}/{card_id}")
async def get_card_by_id(set_id: str, card_id: str):
    """Retorna uma carta específica pelo ID"""
    key = f"/{set_id}/{card_id}"
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    # Procurar carta por ID
    if isinstance(cards_data, list):
        for card in cards_data:
            if str(card.get("id")) == key:
                return card
    elif isinstance(cards_data, dict):
        # Se o ID é a chave do dict
        if key in cards_data:
            return cards_data[key]
        # Se as cartas estão em uma lista dentro do dict
        cards = cards_data.get("cards", [])
        for card in cards:
            if str(card.get("id")) == key:
                return card

    raise HTTPException(status_code=404, detail="Card not found")


@app.get("/cards/search/name/{name}")
async def search_cards_by_name(name: str):
    """Busca cartas pelo nome (busca parcial, case-insensitive)"""
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    matching_cards = []
    cards = (
        cards_data
        if isinstance(cards_data, list)
        else cards_data.get(
            "cards", list(cards_data.values()) if isinstance(cards_data, dict) else []
        )
    )

    for card in cards:
        card_name = card.get("name", "")
        if name.lower() in card_name.lower():
            matching_cards.append(card)

    return matching_cards


@app.get("/cards/filter/type/{card_type}")
async def filter_cards_by_type(card_type: str):
    """Filtra cartas por tipo"""
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    matching_cards = []
    cards = (
        cards_data
        if isinstance(cards_data, list)
        else cards_data.get(
            "cards", list(cards_data.values()) if isinstance(cards_data, dict) else []
        )
    )

    for card in cards:
        if card.get("type", "").lower() == card_type.lower():
            matching_cards.append(card)

    return matching_cards


@app.get("/cards/filter/rarity/{rarity}")
async def filter_cards_by_rarity(rarity: str):
    """Filtra cartas por raridade"""
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    matching_cards = []
    cards = (
        cards_data
        if isinstance(cards_data, list)
        else cards_data.get(
            "cards", list(cards_data.values()) if isinstance(cards_data, dict) else []
        )
    )

    for card in cards:
        if card.get("rarity", "").lower() == rarity.lower():
            matching_cards.append(card)

    return matching_cards


@app.get("/cards/filter/set/{set_name}")
async def filter_cards_by_set(set_name: str):
    """Filtra cartas por set/expansão"""
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    matching_cards = []
    cards = (
        cards_data
        if isinstance(cards_data, list)
        else cards_data.get(
            "cards", list(cards_data.values()) if isinstance(cards_data, dict) else []
        )
    )

    for card in cards:
        if card.get("set", "").lower() == set_name.lower():
            matching_cards.append(card)

    return matching_cards


@app.get("/stats")
async def get_stats():
    """Retorna estatísticas sobre a coleção de cartas"""
    if not cards_data:
        raise HTTPException(status_code=500, detail="Cards data not loaded")

    cards = (
        cards_data
        if isinstance(cards_data, list)
        else cards_data.get(
            "cards", list(cards_data.values()) if isinstance(cards_data, dict) else []
        )
    )

    total_cards = len(cards)

    # Contar por tipo
    types = {}
    rarities = {}
    sets = {}

    for card in cards:
        card_type = card.get("type", "Unknown")
        rarity = card.get("rarity", "Unknown")
        card_set = card.get("set", "Unknown")

        types[card_type] = types.get(card_type, 0) + 1
        rarities[rarity] = rarities.get(rarity, 0) + 1
        sets[card_set] = sets.get(card_set, 0) + 1

    return {
        "total_cards": total_cards,
        "types": types,
        "rarities": rarities,
        "sets": sets,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
