from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import permutations

from core.models import POI, POICategory, ParsedIntent, Route, RouteStop, UserProfile
from core.rag.vector_store import haversine_km, transit_minutes


MEAL_CATEGORIES = {POICategory.RESTAURANT, POICategory.CAFE}
FOODISH_CATEGORIES = {POICategory.RESTAURANT, POICategory.CAFE}
CULTURE_CATEGORIES = {POICategory.ATTRACTION, POICategory.ENTERTAINMENT}
EXPERIENCE_CATEGORIES = {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING}
WALK_KEYWORDS = ["散步", "步行", "街区", "步行街", "公园", "广场", "商圈", "市集", "坊", "天地", "滨江", "江边"]
DRINK_KEYWORDS = ["喝点东西", "喝东西", "咖啡", "茶", "奶茶", "甜品", "下午茶", "饮品"]
MEAL_KEYWORDS = ["餐饮", "餐厅", "正餐", "吃饭", "午饭", "晚饭", "晚餐", "轻食", "粤菜", "本帮菜", "火锅", "烧烤"]
CULTURE_KEYWORDS = ["文化", "展", "展览", "馆", "博物", "美术", "艺术", "景点", "打卡"]
MULTI_RESTAURANT_KEYWORDS = ["美食探店", "餐厅打卡", "多家餐厅", "两家餐厅", "吃两家", "老字号巡游", "粤菜巡游", "吃遍"]
CORE_ROUTE_CATEGORIES = {
    POICategory.RESTAURANT,
    POICategory.CAFE,
    POICategory.ATTRACTION,
    POICategory.ENTERTAINMENT,
    POICategory.SHOPPING,
}


class RoutePlannerAgent:
    def __init__(self, poi_db: dict[str, POI]):
        self.poi_db = poi_db

    def plan(
        self,
        intent: ParsedIntent,
        candidates: list[tuple[POI, float]],
        user_profile: UserProfile | None = None,
        n_routes: int = 2,
        pinned_pois: list[POI] | None = None,
    ) -> list[Route]:
        if not candidates:
            return []
        pinned_pois = pinned_pois or []
        candidates = self._ensure_required_candidates(intent, candidates, user_profile)

        variants = [
            ("紧凑不绕路", self._sort_compact),
            ("高分体验优先", self._sort_quality),
            ("低等待轻松版", self._sort_easy),
        ]
        routes: list[Route] = []
        used_signatures: set[tuple[str, ...]] = set()

        for theme, sorter in variants:
            ordered = self._diversity_rerank(sorter(candidates), intent)
            route = self._build_route(intent, ordered, theme, pinned_pois)
            if not route:
                continue
            signature = tuple(stop.poi.id for stop in route.stops)
            if signature in used_signatures:
                continue
            used_signatures.add(signature)
            routes.append(route)
            if len(routes) >= n_routes:
                break

        return routes

    def _sort_compact(self, candidates: list[tuple[POI, float]]) -> list[tuple[POI, float]]:
        district_groups: dict[str, list[tuple[POI, float]]] = defaultdict(list)
        for item in candidates:
            district_groups[item[0].district].append(item)
        best_group = max(district_groups.values(), key=lambda group: sum(score for _, score in group))
        return sorted(best_group, key=lambda item: (-item[1], item[0].avg_wait_minutes, -item[0].rating))

    def _sort_quality(self, candidates: list[tuple[POI, float]]) -> list[tuple[POI, float]]:
        return sorted(candidates, key=lambda item: (-item[0].rating, -item[1], item[0].price_per_person))

    def _sort_easy(self, candidates: list[tuple[POI, float]]) -> list[tuple[POI, float]]:
        return sorted(candidates, key=lambda item: (item[0].avg_wait_minutes, item[0].price_per_person, -item[1]))

    def _build_route(
        self,
        intent: ParsedIntent,
        ordered_candidates: list[tuple[POI, float]],
        theme: str,
        pinned_pois: list[POI] | None = None,
    ) -> Route | None:
        constraints = intent.constraints
        selected = self._select_stops(
            intent,
            ordered_candidates,
            constraints.total_time_hours,
            constraints.budget_per_person,
            pinned_pois=pinned_pois,
        )
        selected = self._repair_selected_stops(
            intent,
            selected,
            ordered_candidates,
            max_stops=max(5 if constraints.total_time_hours >= 6 else 4 if constraints.total_time_hours >= 4 else 3, len(pinned_pois or [])),
            budget=constraints.budget_per_person,
            pinned_pois=pinned_pois,
        )
        if len(selected) < 3:
            return None
        if not selected:
            return None
        if not self._is_structure_viable(intent, selected):
            return None
        return self.build_route_from_pois(intent, selected, theme)

    def build_route_from_pois(self, intent: ParsedIntent, selected: list[POI], theme: str) -> Route | None:
        constraints = intent.constraints
        selected = self._best_itinerary_order(intent, selected)
        start_dt = datetime.strptime(constraints.start_time, "%H:%M")
        end_limit = start_dt + timedelta(hours=constraints.total_time_hours)

        stops: list[RouteStop] = []
        current = start_dt
        total_cost = 0.0
        total_wait = 0
        total_transit = 0
        warnings: list[str] = []

        for index, poi in enumerate(selected):
            move_minutes = 0
            transit_label = None
            arrival = current
            if index > 0:
                prev = selected[index - 1]
                move_minutes = transit_minutes(
                    prev.latitude,
                    prev.longitude,
                    poi.latitude,
                    poi.longitude,
                    constraints.transport_mode,
                )
                transit_label = self._transit_label(prev, poi, move_minutes, constraints.transport_mode)
                arrival = current + timedelta(minutes=move_minutes)

            if not self._is_open(poi, arrival):
                warnings.append(f"{poi.name} 当前时间可能接近非营业时段，请现场确认。")

            wait_minutes = min(poi.avg_wait_minutes, constraints.max_wait_minutes)
            if poi.avg_wait_minutes > constraints.max_wait_minutes:
                warnings.append(f"{poi.name} 常规等待约 {poi.avg_wait_minutes} 分钟，已按低等待策略压缩或建议错峰。")

            duration = max(30, min(poi.visit_duration_minutes, 100))
            departure = arrival + timedelta(minutes=wait_minutes + duration)
            if departure > end_limit:
                remaining = int((end_limit - arrival).total_seconds() // 60) - wait_minutes
                minimum_duration = 25 if len(stops) < 3 else 30
                if remaining >= minimum_duration:
                    duration = remaining
                    departure = arrival + timedelta(minutes=wait_minutes + duration)
                elif len(stops) >= 3:
                    break
                else:
                    duration = max(25, remaining)
                    departure = arrival + timedelta(minutes=wait_minutes + duration)
                    warnings.append(f"{poi.name} 为保证路线完整性已压缩停留时间，建议现场灵活调整。")

            if index > 0 and stops:
                total_transit += move_minutes
                stops[-1].transit_to_next = transit_label
                stops[-1].transit_minutes = move_minutes

            stops.append(
                RouteStop(
                    order=len(stops) + 1,
                    poi=poi,
                    arrival_time=arrival.strftime("%H:%M"),
                    departure_time=departure.strftime("%H:%M"),
                    duration_minutes=duration,
                    wait_minutes=wait_minutes,
                    tips=self._tip_for_poi(poi, intent),
                )
            )
            current = departure
            total_cost += poi.price_per_person
            total_wait += wait_minutes

        if len(stops) < 3:
            return None
        if not self._is_structure_viable(intent, [stop.poi for stop in stops]):
            return None

        total_minutes = int((current - start_dt).total_seconds() // 60)
        total_cost = round(total_cost, 1)
        title = self._title_for_route(theme, stops, intent)
        description = self._description_for_route(theme, stops, intent)
        highlights = self._highlights(stops, intent, total_wait, total_transit)

        if constraints.budget_per_person and total_cost > constraints.budget_per_person:
            warnings.append(f"当前路线人均约 ¥{total_cost:.0f}，略高于预算 ¥{constraints.budget_per_person:.0f}，可替换高价餐饮。")
        if total_minutes > constraints.total_time_hours * 60:
            warnings.append("路线接近时间上限，已优先保证 3 个 POI 串联；建议选择打车或缩短单站停留。")
        if not self._has_meal_and_culture([stop.poi for stop in stops]):
            warnings.append("当前候选 POI 类型覆盖不足，建议放宽区域或等待条件。")
        warnings.extend(self._structure_warnings(intent, [stop.poi for stop in stops]))

        return Route(
            id=str(uuid.uuid4())[:8],
            title=title,
            description=description,
            stops=stops,
            total_time_minutes=total_minutes,
            total_cost_per_person=total_cost,
            total_wait_minutes=total_wait,
            total_transit_minutes=total_transit,
            highlights=highlights,
            warnings=warnings[:4],
        )

    def _select_stops(
        self,
        intent: ParsedIntent,
        candidates: list[tuple[POI, float]],
        total_hours: float,
        budget: float | None,
        pinned_pois: list[POI] | None = None,
    ) -> list[POI]:
        pinned_pois = pinned_pois or []
        role_sequence = self._role_sequence(intent)
        base_max = 5 if total_hours >= 6 else 4 if total_hours >= 4 else 3
        if total_hours >= 3 and len(role_sequence) >= 4:
            base_max = max(base_max, 4)
        max_stops = max(len(pinned_pois), base_max)
        max_stops = min(max_stops, 5)
        selected: list[POI] = []
        running_cost = 0.0
        for poi in pinned_pois[:max_stops]:
            if poi.id in {selected_poi.id for selected_poi in selected}:
                continue
            selected.append(poi)
            running_cost += poi.price_per_person

        for role in role_sequence:
            if len(selected) >= max_stops:
                break
            if self._role_satisfied(selected, role, intent):
                continue
            running_cost = self._append_best_for_role(selected, candidates, role, running_cost, budget, intent)

        for poi, _ in candidates:
            if len(selected) >= max_stops:
                break
            if poi.id in {p.id for p in selected}:
                continue
            if not self._can_add_poi(selected, poi, intent, pinned=False):
                continue
            if budget and running_cost + poi.price_per_person > budget * 1.2 and len(selected) >= 3:
                continue
            selected.append(poi)
            running_cost += poi.price_per_person

        return self._best_itinerary_order(intent, selected)

    def _ensure_required_candidates(
        self,
        intent: ParsedIntent,
        candidates: list[tuple[POI, float]],
        user_profile: UserProfile | None,
    ) -> list[tuple[POI, float]]:
        existing_ids = {poi.id for poi, _ in candidates}
        expanded = list(candidates)

        if self._uses_live_anchor(intent, candidates):
            return sorted(expanded, key=lambda item: item[1], reverse=True)

        for group in (MEAL_CATEGORIES, CULTURE_CATEGORIES, {POICategory.SHOPPING}):
            if any(poi.category in group for poi, _ in expanded):
                continue
            for poi in self._fallback_candidates(intent, group, user_profile):
                if poi.id in existing_ids:
                    continue
                expanded.append((poi, self._fallback_score(poi, intent)))
                existing_ids.add(poi.id)
                if sum(1 for item, _ in expanded if item.category in group) >= 4:
                    break

        return sorted(expanded, key=lambda item: item[1], reverse=True)

    def _fallback_candidates(
        self,
        intent: ParsedIntent,
        categories: set[POICategory],
        user_profile: UserProfile | None,
    ) -> list[POI]:
        constraints = intent.constraints
        disliked = set(user_profile.disliked_poi_ids if user_profile else [])
        pois = [
            poi
            for poi in self.poi_db.values()
            if poi.category in categories
            and poi.category not in constraints.avoid_categories
            and poi.id not in disliked
            and (not constraints.preferred_districts or poi.district in constraints.preferred_districts)
        ]
        if not pois and constraints.preferred_districts:
            pois = [
                poi
                for poi in self.poi_db.values()
                if poi.category in categories and poi.category not in constraints.avoid_categories and poi.id not in disliked
            ]
        return sorted(
            pois,
            key=lambda poi: (
                poi.avg_wait_minutes > constraints.max_wait_minutes + 15,
                constraints.budget_per_person is not None and poi.price_per_person > constraints.budget_per_person,
                poi.avg_wait_minutes,
                -poi.rating,
                poi.price_per_person,
            ),
        )

    def _fallback_score(self, poi: POI, intent: ParsedIntent) -> float:
        constraints = intent.constraints
        score = 0.78 + poi.rating / 10
        if constraints.preferred_districts and poi.district in constraints.preferred_districts:
            score += 0.14
        if poi.avg_wait_minutes <= constraints.max_wait_minutes:
            score += 0.08
        if constraints.budget_per_person is None or poi.price_per_person <= constraints.budget_per_person:
            score += 0.05
        return round(score, 3)

    def _append_best_from_group(
        self,
        selected: list[POI],
        candidates: list[tuple[POI, float]],
        categories: set[POICategory],
        running_cost: float,
        budget: float | None,
        intent: ParsedIntent | None,
    ) -> float:
        selected_ids = {poi.id for poi in selected}
        group_items = [
            (poi, score)
            for poi, score in candidates
            if poi.category in categories
            and poi.id not in selected_ids
            and (intent is None or self._can_add_poi(selected, poi, intent, pinned=False))
        ]
        if not group_items:
            return running_cost
        affordable_items = [
            (poi, score)
            for poi, score in group_items
            if budget is None or running_cost + poi.price_per_person <= budget * 1.25
        ]
        poi = (affordable_items or group_items)[0][0]
        selected.append(poi)
        return running_cost + poi.price_per_person

    def _append_best_for_role(
        self,
        selected: list[POI],
        candidates: list[tuple[POI, float]],
        role: str,
        running_cost: float,
        budget: float | None,
        intent: ParsedIntent,
    ) -> float:
        selected_ids = {poi.id for poi in selected}
        role_items = [
            (poi, score)
            for poi, score in candidates
            if poi.id not in selected_ids
            and self._poi_matches_role(poi, role, intent)
            and self._can_add_poi(selected, poi, intent, pinned=False)
        ]
        if not role_items:
            return running_cost
        affordable_items = [
            (poi, score)
            for poi, score in role_items
            if budget is None or running_cost + poi.price_per_person <= budget * 1.25
        ]
        poi = max(affordable_items or role_items, key=lambda item: self._role_rank(item[0], item[1], role))
        selected.append(poi[0])
        return running_cost + poi[0].price_per_person

    def _query_text(self, intent: ParsedIntent) -> str:
        raw_query = str(intent.extracted_preferences.get("raw_query", ""))
        preferences = " ".join(str(value) for value in intent.extracted_preferences.values())
        return f"{raw_query} {preferences}"

    def _allows_multiple_cafes(self, intent: ParsedIntent) -> bool:
        text = self._query_text(intent)
        return any(word in text for word in ["咖啡打卡", "多家咖啡", "咖啡店巡游", "咖啡馆巡游", "咖啡路线"])

    def _allows_multiple_restaurants(self, intent: ParsedIntent) -> bool:
        text = self._query_text(intent)
        return any(word in text for word in MULTI_RESTAURANT_KEYWORDS)

    def _wants_drink(self, intent: ParsedIntent) -> bool:
        return any(word in self._query_text(intent) for word in DRINK_KEYWORDS)

    def _wants_meal(self, intent: ParsedIntent) -> bool:
        return any(word in self._query_text(intent) for word in MEAL_KEYWORDS)

    def _wants_culture(self, intent: ParsedIntent) -> bool:
        return any(word in self._query_text(intent) for word in CULTURE_KEYWORDS)

    def _wants_walk(self, intent: ParsedIntent) -> bool:
        return any(word in self._query_text(intent) for word in WALK_KEYWORDS)

    def _restaurant_limit(self, intent: ParsedIntent) -> int:
        if self._allows_multiple_restaurants(intent):
            return 3 if intent.constraints.total_time_hours >= 5 else 2
        return 1

    def _cafe_limit(self, intent: ParsedIntent) -> int:
        if self._allows_multiple_cafes(intent):
            return 3 if intent.constraints.total_time_hours < 5 else 4
        return 1

    def _fixed_start_category(self, intent: ParsedIntent, pois: list[POI] | None) -> POICategory | None:
        if intent.extracted_preferences.get("pinned_policy") != "fixed_start":
            return None
        fixed_start_id = str(intent.extracted_preferences.get("fixed_start_poi_id") or "")
        if not fixed_start_id or not pois:
            return None
        fixed_start = next((poi for poi in pois if poi.id == fixed_start_id), None)
        return fixed_start.category if fixed_start else None

    def _foodish_limit(self, intent: ParsedIntent, pois: list[POI] | None = None) -> int:
        if self._allows_multiple_restaurants(intent) or self._allows_multiple_cafes(intent):
            return max(2, self._restaurant_limit(intent) + min(1, self._cafe_limit(intent)))
        fixed_start_category = self._fixed_start_category(intent, pois)
        if fixed_start_category == POICategory.RESTAURANT:
            return 2 if self._wants_drink(intent) and POICategory.CAFE not in intent.constraints.avoid_categories else 1
        if fixed_start_category == POICategory.CAFE:
            return 2 if self._wants_meal(intent) and POICategory.RESTAURANT not in intent.constraints.avoid_categories else 1
        return 2 if self._wants_drink(intent) and self._wants_meal(intent) else 1

    def _role_sequence(self, intent: ParsedIntent) -> list[str]:
        if self._allows_multiple_cafes(intent):
            return ["drink", "drink", "culture", "walk"]
        if self._allows_multiple_restaurants(intent):
            return ["meal", "meal", "experience", "drink"]

        roles: list[str] = []
        if self._wants_culture(intent):
            roles.append("culture")
        if self._wants_walk(intent):
            roles.append("walk")
        if self._wants_drink(intent):
            roles.append("drink")
        if self._wants_meal(intent):
            roles.append("meal")

        if not any(role in {"culture", "walk", "experience"} for role in roles):
            roles.append("experience")
        if not any(role in {"meal", "drink", "food"} for role in roles):
            roles.append("food")
        if len(roles) < 3:
            for role in ("walk", "culture", "drink", "meal", "experience"):
                if role not in roles:
                    roles.append(role)
                if len(roles) >= 3:
                    break
        return roles

    def _role_satisfied(self, selected: list[POI], role: str, intent: ParsedIntent) -> bool:
        if role in {"drink", "meal"} and (self._allows_multiple_cafes(intent) or self._allows_multiple_restaurants(intent)):
            return False
        return any(self._poi_matches_role(poi, role, intent) for poi in selected)

    def _poi_matches_role(self, poi: POI, role: str, intent: ParsedIntent) -> bool:
        text = f"{poi.name} {' '.join(poi.tags)} {poi.ugc_summary}"
        if role == "meal":
            return poi.category == POICategory.RESTAURANT
        if role == "drink":
            return poi.category == POICategory.CAFE
        if role == "food":
            if self._wants_drink(intent) and not self._wants_meal(intent):
                return poi.category == POICategory.CAFE
            return poi.category in FOODISH_CATEGORIES
        if role == "culture":
            return poi.category in CULTURE_CATEGORIES
        if role == "walk":
            return poi.category == POICategory.SHOPPING or any(word in text for word in WALK_KEYWORDS)
        if role == "experience":
            return poi.category in EXPERIENCE_CATEGORIES
        return False

    def _role_rank(self, poi: POI, base_score: float, role: str) -> float:
        text = f"{poi.name} {' '.join(poi.tags)} {poi.ugc_summary}"
        role_bonus = 0.0
        if role == "walk" and any(word in text for word in WALK_KEYWORDS):
            role_bonus += 0.55
        if role == "culture" and any(word in text for word in CULTURE_KEYWORDS):
            role_bonus += 0.45
        if role == "drink" and poi.category == POICategory.CAFE:
            role_bonus += 0.35
        if role == "meal" and poi.category == POICategory.RESTAURANT:
            role_bonus += 0.35
        distance_penalty = (poi.distance_from_anchor_meters or 0) / 10000
        return base_score + role_bonus + poi.rating / 20 - distance_penalty

    def _can_add_poi(self, selected: list[POI], poi: POI, intent: ParsedIntent, pinned: bool) -> bool:
        if pinned:
            return True
        if poi.category in intent.constraints.avoid_categories:
            return False
        if poi.category not in CORE_ROUTE_CATEGORIES:
            return False
        category_count = sum(1 for item in selected if item.category == poi.category)
        foodish_count = sum(1 for item in selected if item.category in FOODISH_CATEGORIES)
        if poi.category == POICategory.RESTAURANT and category_count >= self._restaurant_limit(intent):
            return False
        if poi.category == POICategory.CAFE and category_count >= 1 and not self._allows_multiple_cafes(intent):
            return False
        if poi.category == POICategory.CAFE and category_count >= self._cafe_limit(intent):
            return False
        if poi.category in FOODISH_CATEGORIES and foodish_count >= self._foodish_limit(intent, selected):
            return False
        if category_count >= 2 and poi.category not in FOODISH_CATEGORIES:
            return False
        allows_same_category_pick = (
            poi.category == POICategory.RESTAURANT and self._allows_multiple_restaurants(intent)
        ) or (
            poi.category == POICategory.CAFE and self._allows_multiple_cafes(intent)
        )
        if selected and selected[-1].category == poi.category and not allows_same_category_pick:
            return False
        return True

    def _repair_selected_stops(
        self,
        intent: ParsedIntent,
        selected: list[POI],
        candidates: list[tuple[POI, float]],
        max_stops: int,
        budget: float | None,
        pinned_pois: list[POI] | None,
    ) -> list[POI]:
        pinned_ids = {poi.id for poi in (pinned_pois or [])}
        repaired: list[POI] = []
        running_cost = 0.0
        for poi in selected:
            if poi.id in {item.id for item in repaired}:
                continue
            if poi.id not in pinned_ids and not self._can_add_poi(repaired, poi, intent, pinned=False):
                continue
            repaired.append(poi)
            running_cost += poi.price_per_person
            if len(repaired) >= max_stops:
                break

        for role in self._role_sequence(intent):
            if len(repaired) >= max_stops:
                break
            if self._role_satisfied(repaired, role, intent):
                continue
            running_cost = self._append_best_for_role(repaired, candidates, role, running_cost, budget, intent)

        for poi, _ in candidates:
            if len(repaired) >= max_stops:
                break
            if poi.id in {item.id for item in repaired}:
                continue
            if not self._can_add_poi(repaired, poi, intent, pinned=False):
                continue
            if budget and running_cost + poi.price_per_person > budget * 1.25 and len(repaired) >= 3:
                continue
            repaired.append(poi)
            running_cost += poi.price_per_person

        return self._best_itinerary_order(intent, repaired)

    def _diversity_rerank(self, candidates: list[tuple[POI, float]], intent: ParsedIntent) -> list[tuple[POI, float]]:
        remaining = list(candidates)
        reranked: list[tuple[POI, float]] = []
        while remaining:
            def rank(item: tuple[POI, float]) -> float:
                poi, score = item
                same_category_count = sum(1 for selected, _ in reranked if selected.category == poi.category)
                foodish_count = sum(1 for selected, _ in reranked if selected.category in FOODISH_CATEGORIES)
                cafe_penalty = 1.6 if poi.category == POICategory.CAFE and same_category_count and not self._allows_multiple_cafes(intent) else 0.0
                restaurant_penalty = 1.8 if poi.category == POICategory.RESTAURANT and same_category_count and not self._allows_multiple_restaurants(intent) else 0.0
                reranked_pois = [chosen_poi for chosen_poi, _ in reranked]
                foodish_penalty = 0.8 if poi.category in FOODISH_CATEGORIES and foodish_count >= self._foodish_limit(intent, reranked_pois) else 0.0
                repeat_penalty = same_category_count * 0.38
                adjacency_penalty = 0.35 if reranked and reranked[-1][0].category == poi.category else 0.0
                coverage_bonus = 0.22 if poi.category in EXPERIENCE_CATEGORIES and not any(selected.category in EXPERIENCE_CATEGORIES for selected, _ in reranked) else 0.0
                return score + coverage_bonus - repeat_penalty - cafe_penalty - restaurant_penalty - foodish_penalty - adjacency_penalty

            chosen = max(remaining, key=rank)
            remaining.remove(chosen)
            reranked.append(chosen)
        return reranked

    def _best_itinerary_order(self, intent: ParsedIntent, pois: list[POI]) -> list[POI]:
        unique_pois = []
        seen = set()
        for poi in pois:
            if poi.id in seen:
                continue
            seen.add(poi.id)
            unique_pois.append(poi)
        if len(unique_pois) > 6:
            unique_pois = unique_pois[:6]
        fixed_start_id = str(intent.extracted_preferences.get("fixed_start_poi_id") or "")
        fixed_start = next((poi for poi in unique_pois if poi.id == fixed_start_id), None)
        if fixed_start:
            remaining_unique = [poi for poi in unique_pois if poi.id != fixed_start.id]
            if len(remaining_unique) <= 1:
                return [fixed_start, *remaining_unique]
            unique_pois = remaining_unique
        if len(unique_pois) <= 2:
            ordered = unique_pois
            return [fixed_start, *ordered] if fixed_start else ordered

        raw_query = str(intent.extracted_preferences.get("raw_query", ""))
        is_evening = any(word in raw_query for word in ["晚上", "今晚", "晚餐", "夜"])

        def order_score(order: tuple[POI, ...]) -> float:
            score = 0.0
            categories = [poi.category for poi in order]
            for index, category in enumerate(categories):
                if is_evening:
                    if index == 0 and category == POICategory.RESTAURANT:
                        score += 18
                    if index >= 1 and category in EXPERIENCE_CATEGORIES:
                        score += 10
                else:
                    if index == 0 and category in {POICategory.CAFE, POICategory.ATTRACTION, POICategory.SHOPPING}:
                        score += 12
                    if index == 1 and category in EXPERIENCE_CATEGORIES:
                        score += 10
                    if index >= 2 and category in {POICategory.RESTAURANT, POICategory.ENTERTAINMENT, POICategory.SHOPPING}:
                        score += 8
                if index > 0:
                    prev = categories[index - 1]
                    if category == prev:
                        score -= 80
                    if category in FOODISH_CATEGORIES and prev in FOODISH_CATEGORIES:
                        score -= 24
                    if category != prev:
                        score += 6
            cafe_count = categories.count(POICategory.CAFE)
            if cafe_count > 1 and not self._allows_multiple_cafes(intent):
                score -= 120 * (cafe_count - 1)
            restaurant_count = categories.count(POICategory.RESTAURANT)
            if restaurant_count > self._restaurant_limit(intent):
                score -= 140 * (restaurant_count - self._restaurant_limit(intent))
            foodish_count = sum(1 for category in categories if category in FOODISH_CATEGORIES)
            foodish_limit = self._foodish_limit(intent, list(order))
            if foodish_count > foodish_limit:
                score -= 120 * (foodish_count - foodish_limit)
            distance = sum(
                haversine_km(order[index - 1].latitude, order[index - 1].longitude, order[index].latitude, order[index].longitude)
                for index in range(1, len(order))
            )
            score -= distance * 0.7
            return score

        if fixed_start:
            best_remaining = max(permutations(unique_pois), key=lambda order: order_score((fixed_start, *order)))
            return [fixed_start, *best_remaining]
        return list(max(permutations(unique_pois), key=order_score))

    def _structure_warnings(self, intent: ParsedIntent, pois: list[POI]) -> list[str]:
        warnings: list[str] = []
        if not self._allows_multiple_cafes(intent) and sum(1 for poi in pois if poi.category == POICategory.CAFE) > 1:
            warnings.append("当前候选咖啡/茶饮过多，已尽量压缩为休息点；如需咖啡打卡可明确说明。")
        if not self._allows_multiple_restaurants(intent) and sum(1 for poi in pois if poi.category == POICategory.RESTAURANT) > 1:
            warnings.append("当前路线出现多个正餐餐厅，真实出行不建议一下午连续吃多家；可改成美食探店路线。")
        if sum(1 for poi in pois if poi.category in FOODISH_CATEGORIES) > self._foodish_limit(intent, pois):
            warnings.append("餐饮/饮品站点偏多，建议保留一个休息点，其余替换成文化或散步点。")
        if any(pois[index].category == pois[index - 1].category for index in range(1, len(pois))):
            warnings.append("路线中仍存在相邻同类站点，建议放宽区域或增加文化/娱乐类偏好。")
        return warnings

    def _has_meal_and_culture(self, pois: list[POI]) -> bool:
        categories = {poi.category for poi in pois}
        return bool(categories.intersection(MEAL_CATEGORIES)) and bool(categories.intersection(EXPERIENCE_CATEGORIES))

    def _missing_required_roles(self, intent: ParsedIntent, pois: list[POI]) -> list[str]:
        required: list[tuple[str, str]] = []
        if self._wants_drink(intent) and POICategory.CAFE not in intent.constraints.avoid_categories:
            required.append(("drink", "喝点东西/休息点"))
        if self._wants_culture(intent):
            required.append(("culture", "文化点"))
        if self._wants_walk(intent):
            required.append(("walk", "散步点"))
        if (
            self._wants_meal(intent)
            and len(pois) >= 4
            and POICategory.RESTAURANT not in intent.constraints.avoid_categories
        ):
            required.append(("meal", "正餐餐厅"))
        return [label for role, label in required if not any(self._poi_matches_role(poi, role, intent) for poi in pois)]

    def _is_structure_viable(self, intent: ParsedIntent, pois: list[POI]) -> bool:
        if len(pois) < 3:
            return False
        if not self._allows_multiple_restaurants(intent) and sum(1 for poi in pois if poi.category == POICategory.RESTAURANT) > self._restaurant_limit(intent):
            return False
        if not self._allows_multiple_cafes(intent) and sum(1 for poi in pois if poi.category == POICategory.CAFE) > self._cafe_limit(intent):
            return False
        if sum(1 for poi in pois if poi.category in FOODISH_CATEGORIES) > self._foodish_limit(intent, pois):
            return False
        if self._missing_required_roles(intent, pois):
            return False
        if not self._has_meal_and_culture(pois):
            return False
        return True

    def _uses_live_anchor(self, intent: ParsedIntent, candidates: list[tuple[POI, float]]) -> bool:
        if intent.extracted_preferences.get("anchor_text") or intent.extracted_preferences.get("anchor_source"):
            return True
        return any(poi.source in {"amap", "context"} or poi.id.startswith("local-anchor-") for poi, _ in candidates)

    def _nearest_neighbor_order(self, pois: list[POI]) -> list[POI]:
        if len(pois) <= 2:
            return pois
        remaining = pois[:]
        ordered = [remaining.pop(0)]
        while remaining:
            last = ordered[-1]
            next_poi = min(remaining, key=lambda poi: haversine_km(last.latitude, last.longitude, poi.latitude, poi.longitude))
            remaining.remove(next_poi)
            ordered.append(next_poi)
        return ordered

    def _is_open(self, poi: POI, when: datetime) -> bool:
        open_text = poi.business_hours.get("open", "00:00")
        close_text = poi.business_hours.get("close", "23:59")
        open_time = datetime.strptime(open_text, "%H:%M").time()
        close_time = datetime.strptime(close_text, "%H:%M").time()
        current = when.time()
        if open_time <= close_time:
            return open_time <= current <= close_time
        return current >= open_time or current <= close_time

    def _transit_label(self, prev: POI, poi: POI, minutes: int, mode: str) -> str:
        distance = haversine_km(prev.latitude, prev.longitude, poi.latitude, poi.longitude)
        if distance <= 1.2:
            method = "步行"
        elif "打车" in mode:
            method = "打车"
        elif "地铁" in mode:
            method = "地铁/步行"
        else:
            method = "公交/步行"
        return f"{method}约 {minutes} 分钟，距离约 {distance:.1f} km"

    def _tip_for_poi(self, poi: POI, intent: ParsedIntent) -> str:
        if poi.category == POICategory.RESTAURANT:
            return f"建议提前取号；优先点选 {poi.tags[0] if poi.tags else '招牌菜'}，避开正餐高峰更稳。"
        if poi.category == POICategory.CAFE:
            return "适合作为中途休息点，靠窗位和下午时段拍照效果更好。"
        if poi.category == POICategory.ATTRACTION:
            return "建议预留拍照和步行时间，傍晚光线更适合出片。"
        if poi.category == POICategory.SHOPPING:
            return "可以作为路线缓冲站，天气不好时也不影响体验。"
        if poi.category == POICategory.ENTERTAINMENT:
            return "建议提前确认场次或预约，避免到店等待。"
        return "到店前确认营业状态会更稳。"

    def _title_for_route(self, theme: str, stops: list[RouteStop], intent: ParsedIntent) -> str:
        district = stops[0].poi.district.replace("区", "")
        style = intent.extracted_preferences.get("travel_style", "休闲")
        return f"{district}{style}{theme}"

    def _description_for_route(self, theme: str, stops: list[RouteStop], intent: ParsedIntent) -> str:
        names = " → ".join(stop.poi.name for stop in stops[:3])
        return f"围绕{theme}组织，串联 {names}，兼顾距离、等待和预算。"

    def _highlights(self, stops: list[RouteStop], intent: ParsedIntent, total_wait: int, total_transit: int) -> list[str]:
        categories = "、".join(dict.fromkeys(stop.poi.category.value for stop in stops))
        restaurant_count = sum(1 for stop in stops if stop.poi.category == POICategory.RESTAURANT)
        cafe_count = sum(1 for stop in stops if stop.poi.category == POICategory.CAFE)
        structure = f"结构校验：正餐 {restaurant_count} 个、饮品/休息 {cafe_count} 个，避免连续餐厅凑数"
        return [
            f"覆盖 {categories}，不是单纯罗列地点",
            structure,
            f"总等待约 {total_wait} 分钟，已按用户排队容忍度过滤",
            f"路上交通约 {total_transit} 分钟，站点顺序按距离重排",
        ]
