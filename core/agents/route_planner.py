from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from core.models import POI, POICategory, ParsedIntent, Route, RouteStop, UserProfile
from core.rag.vector_store import haversine_km, transit_minutes


MEAL_CATEGORIES = {POICategory.RESTAURANT, POICategory.CAFE}
CULTURE_CATEGORIES = {POICategory.ATTRACTION, POICategory.ENTERTAINMENT}


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
            ordered = sorter(candidates)
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
            ordered_candidates,
            constraints.total_time_hours,
            constraints.budget_per_person,
            pinned_pois=pinned_pois,
        )
        if len(selected) < 3:
            selected = self._nearest_neighbor_order([poi for poi, _ in ordered_candidates[:3]])
        if not selected:
            return None
        return self.build_route_from_pois(intent, selected, theme)

    def build_route_from_pois(self, intent: ParsedIntent, selected: list[POI], theme: str) -> Route | None:
        constraints = intent.constraints
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
        candidates: list[tuple[POI, float]],
        total_hours: float,
        budget: float | None,
        pinned_pois: list[POI] | None = None,
    ) -> list[POI]:
        pinned_pois = pinned_pois or []
        max_stops = max(len(pinned_pois), 5 if total_hours >= 6 else 4 if total_hours >= 4 else 3)
        max_stops = min(max_stops, 5)
        selected: list[POI] = []
        running_cost = 0.0
        for poi in pinned_pois[:max_stops]:
            if poi.id in {selected_poi.id for selected_poi in selected}:
                continue
            selected.append(poi)
            running_cost += poi.price_per_person

        if len(selected) < max_stops:
            running_cost = self._append_best_from_group(selected, candidates, MEAL_CATEGORIES, running_cost, budget)
        if len(selected) < max_stops:
            running_cost = self._append_best_from_group(selected, candidates, CULTURE_CATEGORIES, running_cost, budget)

        for poi, _ in candidates:
            if len(selected) >= max_stops:
                break
            if poi.id in {p.id for p in selected}:
                continue
            if budget and running_cost + poi.price_per_person > budget * 1.2 and len(selected) >= 3:
                continue
            selected.append(poi)
            running_cost += poi.price_per_person

        if len(selected) < 3:
            for poi, _ in candidates:
                if poi.id in {p.id for p in selected}:
                    continue
                selected.append(poi)
                if len(selected) >= 3:
                    break

        return self._nearest_neighbor_order(selected)

    def _ensure_required_candidates(
        self,
        intent: ParsedIntent,
        candidates: list[tuple[POI, float]],
        user_profile: UserProfile | None,
    ) -> list[tuple[POI, float]]:
        existing_ids = {poi.id for poi, _ in candidates}
        expanded = list(candidates)

        for group in (MEAL_CATEGORIES, CULTURE_CATEGORIES):
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
            and poi.id not in disliked
            and (not constraints.preferred_districts or poi.district in constraints.preferred_districts)
        ]
        if not pois and constraints.preferred_districts:
            pois = [poi for poi in self.poi_db.values() if poi.category in categories and poi.id not in disliked]
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
    ) -> float:
        selected_ids = {poi.id for poi in selected}
        group_items = [(poi, score) for poi, score in candidates if poi.category in categories and poi.id not in selected_ids]
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

    def _has_meal_and_culture(self, pois: list[POI]) -> bool:
        categories = {poi.category for poi in pois}
        return bool(categories.intersection(MEAL_CATEGORIES)) and bool(categories.intersection(CULTURE_CATEGORIES))

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
        return [
            f"覆盖 {categories}，不是单纯罗列地点",
            f"总等待约 {total_wait} 分钟，已按用户排队容忍度过滤",
            f"路上交通约 {total_transit} 分钟，站点顺序按距离重排",
        ]
