from __future__ import annotations

from core.models import POI, ParsedIntent, UserProfile
from core.rag.vector_store import POIVectorStore


CATEGORY_QUERY_TEMPLATES = {
    "餐饮": "{city} {district} {style} 特色美食 餐厅 口碑好 不踩雷",
    "景点": "{city} {district} {style} 景点 拍照 打卡 轻松游览",
    "购物": "{city} {district} {style} 购物 商场 市集 买手店",
    "咖啡/茶饮": "{city} {district} {style} 咖啡 下午茶 安静 有设计感",
    "娱乐": "{city} {district} {style} 娱乐 夜游 演出 电影",
    "住宿": "{city} {district} {style} 酒店 住宿 方便",
}


class POIRetrieverAgent:
    def __init__(self, vector_store: POIVectorStore, poi_db: dict[str, POI]):
        self.vector_store = vector_store
        self.poi_db = poi_db

    def retrieve(
        self,
        intent: ParsedIntent,
        user_profile: UserProfile | None = None,
        max_candidates: int = 28,
    ) -> list[tuple[POI, float]]:
        constraints = intent.constraints
        style = intent.extracted_preferences.get("travel_style", "休闲")
        district_text = " ".join(constraints.preferred_districts)
        raw_query = intent.extracted_preferences.get("raw_query", "")
        excluded = set(user_profile.disliked_poi_ids if user_profile else [])
        candidates: dict[str, tuple[POI, float]] = {}

        base_query = f"{intent.city} {district_text} {style} {raw_query} 口碑好 路线规划"
        main_results = self.vector_store.search(
            base_query,
            n_results=18,
            max_price=constraints.budget_per_person,
            max_wait=constraints.max_wait_minutes,
            min_rating=3.7,
            exclude_ids=list(excluded),
            district_filter=constraints.preferred_districts or None,
        )
        self._merge(candidates, main_results, 1.0)

        for category in constraints.preferred_categories:
            template = CATEGORY_QUERY_TEMPLATES[category.value]
            query = template.format(
                city=intent.city,
                district=district_text,
                style=style,
            )
            results = self.vector_store.search(
                query,
                n_results=10,
                category_filter=category.value,
                max_price=constraints.budget_per_person,
                max_wait=constraints.max_wait_minutes,
                min_rating=3.7,
                exclude_ids=list(excluded),
                district_filter=constraints.preferred_districts or None,
            )
            self._merge(candidates, results, 1.08)

        if user_profile:
            for poi_id, (poi, score) in list(candidates.items()):
                if poi_id in user_profile.liked_poi_ids:
                    candidates[poi_id] = (poi, min(score * 1.25, 3.0))
                if poi_id in user_profile.visited_poi_ids:
                    candidates[poi_id] = (poi, score * 0.68)
                if poi.category.value in user_profile.preferred_categories:
                    candidates[poi_id] = (poi, min(score * 1.12, 3.0))

        if len(candidates) < 8 and constraints.preferred_districts:
            relaxed = self.vector_store.search(
                base_query,
                n_results=18,
                max_price=constraints.budget_per_person,
                max_wait=constraints.max_wait_minutes,
                min_rating=3.6,
                exclude_ids=list(excluded),
            )
            self._merge(candidates, relaxed, 0.82)

        sorted_candidates = sorted(candidates.values(), key=lambda item: item[1], reverse=True)
        return sorted_candidates[:max_candidates]

    def _merge(self, candidates: dict[str, tuple[POI, float]], results: list[dict], boost: float) -> None:
        for result in results:
            poi_id = result["poi_id"]
            if poi_id not in self.poi_db:
                continue
            score = result["relevance_score"] * boost
            if poi_id not in candidates or score > candidates[poi_id][1]:
                candidates[poi_id] = (self.poi_db[poi_id], score)
