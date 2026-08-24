from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any


class POIVectorStore:
    """A lightweight local POI retriever.

    The competition proposal names this layer "RAG". To keep the demo stable on
    any machine, this implementation does local lexical/vector-ish retrieval and
    can be swapped for ChromaDB later without changing the agent interface.
    """

    def __init__(self, persist_dir: str = "./data/local_index"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.persist_dir / "poi_index.json"
        self.documents: list[dict[str, Any]] = []
        if self.index_path.exists():
            self.documents = json.loads(self.index_path.read_text(encoding="utf-8"))

    @property
    def count(self) -> int:
        return len(self.documents)

    def index_pois(self, pois: list[dict[str, Any]]) -> None:
        self.documents = []
        for poi in pois:
            text = self._doc_text(poi)
            self.documents.append(
                {
                    "id": poi["id"],
                    "text": text,
                    "tokens": self._tokens(text),
                    "metadata": {
                        "poi_id": poi["id"],
                        "name": poi["name"],
                        "category": poi["category"],
                        "district": poi.get("district", ""),
                        "rating": poi["rating"],
                        "price_per_person": poi["price_per_person"],
                        "avg_wait_minutes": poi["avg_wait_minutes"],
                        "latitude": poi["latitude"],
                        "longitude": poi["longitude"],
                    },
                }
            )
        self.index_path.write_text(json.dumps(self.documents, ensure_ascii=False), encoding="utf-8")

    def search(
        self,
        query: str,
        n_results: int = 10,
        category_filter: str | None = None,
        max_price: float | None = None,
        max_wait: int | None = None,
        min_rating: float = 3.5,
        exclude_ids: list[str] | None = None,
        district_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        exclude = set(exclude_ids or [])
        query_tokens = self._tokens(query)
        scored: list[dict[str, Any]] = []

        for doc in self.documents:
            meta = doc["metadata"]
            if meta["poi_id"] in exclude:
                continue
            if category_filter and meta["category"] != category_filter:
                continue
            if max_price is not None and meta["price_per_person"] > max_price:
                continue
            if max_wait is not None and meta["avg_wait_minutes"] > max_wait:
                continue
            if meta["rating"] < min_rating:
                continue
            if district_filter and meta["district"] not in district_filter:
                continue

            score = self._similarity(query_tokens, doc["tokens"])
            score += (meta["rating"] - 3.5) * 0.08
            if category_filter:
                score += 0.25
            if district_filter:
                score += 0.18
            scored.append(
                {
                    "poi_id": meta["poi_id"],
                    "relevance_score": round(score, 4),
                    "metadata": meta,
                }
            )

        scored.sort(key=lambda item: item["relevance_score"], reverse=True)
        return scored[:n_results]

    def get_nearby_pois(
        self,
        lat: float,
        lon: float,
        radius_km: float = 2.0,
        n_results: int = 20,
    ) -> list[dict[str, Any]]:
        nearby = []
        for doc in self.documents:
            meta = doc["metadata"]
            distance = haversine_km(lat, lon, meta["latitude"], meta["longitude"])
            if distance <= radius_km:
                nearby.append({"metadata": meta, "distance_km": distance})
        nearby.sort(key=lambda item: item["distance_km"])
        return nearby[:n_results]

    def _doc_text(self, poi: dict[str, Any]) -> str:
        return " ".join(
            [
                poi.get("name", ""),
                poi.get("category", ""),
                poi.get("district", ""),
                poi.get("address", ""),
                " ".join(poi.get("tags", [])),
                poi.get("ugc_summary", ""),
                str(poi.get("price_per_person", "")),
                str(poi.get("rating", "")),
            ]
        )

    def _tokens(self, text: str) -> list[str]:
        text = text.lower()
        words = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{1,4}", text)
        expanded: list[str] = []
        for word in words:
            expanded.append(word)
            if len(word) > 2 and re.fullmatch(r"[\u4e00-\u9fff]+", word):
                expanded.extend(word[i : i + 2] for i in range(len(word) - 1))
        return expanded

    def _similarity(self, query_tokens: list[str], doc_tokens: list[str]) -> float:
        if not query_tokens or not doc_tokens:
            return 0.0
        query_counter = Counter(query_tokens)
        doc_counter = Counter(doc_tokens)
        overlap = sum(min(query_counter[t], doc_counter.get(t, 0)) for t in query_counter)
        coverage = overlap / max(len(query_tokens), 1)
        density = overlap / math.sqrt(max(len(doc_tokens), 1))
        return coverage + density


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(a))


def transit_minutes(lat1: float, lon1: float, lat2: float, lon2: float, mode: str = "步行+公交") -> int:
    distance = haversine_km(lat1, lon1, lat2, lon2)
    if distance <= 1.2:
        return max(6, round(distance / 4.2 * 60))
    if "打车" in mode:
        return max(8, round(distance / 22 * 60 + 6))
    return max(12, round(distance / 16 * 60 + 8))
