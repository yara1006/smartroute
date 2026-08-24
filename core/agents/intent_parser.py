from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from core.models import POICategory, ParsedIntent, UserConstraints


CATEGORY_KEYWORDS: dict[POICategory, list[str]] = {
    POICategory.RESTAURANT: ["吃", "美食", "餐厅", "晚饭", "午饭", "火锅", "本帮菜", "小吃", " Brunch".lower()],
    POICategory.ATTRACTION: ["景点", "逛", "拍照", "展览", "外滩", "公园", "博物馆", "打卡"],
    POICategory.SHOPPING: ["购物", "逛街", "商场", "买", "市集", "买手店"],
    POICategory.CAFE: ["咖啡", "下午茶", "茶", "甜品", "安静", "聊天"],
    POICategory.ENTERTAINMENT: ["电影", "娱乐", "密室", "live", "酒吧", "夜游", "演出"],
    POICategory.ACCOMMODATION: ["酒店", "住宿", "民宿"],
}

DISTRICTS = [
    "黄浦区",
    "浦东新区",
    "徐汇区",
    "静安区",
    "长宁区",
    "杨浦区",
    "虹桥商务区",
    "南山区",
    "福田区",
    "罗湖区",
    "宝安区",
]
DISTRICT_ALIASES = {
    "外滩": "黄浦区",
    "豫园": "黄浦区",
    "南京路": "黄浦区",
    "陆家嘴": "浦东新区",
    "徐家汇": "徐汇区",
    "武康路": "徐汇区",
    "静安寺": "静安区",
    "愚园路": "长宁区",
    "大学路": "杨浦区",
    "虹桥": "虹桥商务区",
    "深圳大学": "南山区",
    "深大": "南山区",
    "科技园": "南山区",
    "深圳湾": "南山区",
    "金地威新": "南山区",
    "华侨城": "南山区",
    "车公庙": "福田区",
    "福田": "福田区",
    "罗湖": "罗湖区",
    "宝安": "宝安区",
}


class IntentParserAgent:
    """Parse natural language trip requests into structured constraints.

    DeepSeek is used when configured, but the heuristic parser remains a full
    fallback so the hackathon demo is deterministic without external keys.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.model = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat").strip() or "deepseek-chat"
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()

    def parse(
        self,
        user_input: str,
        conversation_history: list[dict[str, str]] | None = None,
        user_profile: dict[str, Any] | None = None,
    ) -> ParsedIntent:
        rules_intent = self._parse_with_rules(user_input, user_profile=user_profile)
        if self.api_key:
            llm_intent = self._parse_with_llm(user_input, rules_intent, conversation_history, user_profile)
            if llm_intent:
                return llm_intent
        return rules_intent

    def _parse_with_rules(
        self,
        user_input: str,
        user_profile: dict[str, Any] | None = None,
    ) -> ParsedIntent:
        text = user_input.strip()
        profile = user_profile or {}
        constraints = UserConstraints()

        constraints.city = self._extract_city(text)
        constraints.total_time_hours = self._extract_hours(text)
        constraints.budget_per_person = self._extract_budget(text) or profile.get("avg_budget")
        constraints.party_size = self._extract_party_size(text)
        constraints.max_wait_minutes = self._extract_wait(text)
        constraints.start_time = self._extract_start_time(text)
        constraints.start_location = self._extract_start_location(text)
        constraints.transport_mode = self._extract_transport_mode(text)
        constraints.preferred_categories = self._extract_categories(text)
        constraints.preferred_districts = self._extract_districts(text)

        if not constraints.preferred_categories and profile.get("preferred_categories"):
            constraints.preferred_categories = [
                POICategory(c)
                for c in profile.get("preferred_categories", [])
                if c in {category.value for category in POICategory}
            ]

        style = self._extract_style(text) or profile.get("travel_style") or "休闲"
        special_requirements = self._extract_special_requirements(text)

        if "路线" in text or "规划" in text or "安排" in text or len(text) > 6:
            query_type = "路线规划"
        else:
            query_type = "单点查询"

        return ParsedIntent(
            city=constraints.city,
            query_type=query_type,
            constraints=constraints,
            extracted_preferences={
                "travel_style": style,
                "special_requirements": special_requirements,
                "raw_query": text,
                "intent_parser_source": "rules",
            },
            clarification_needed=False,
            parser_source="rules",
            parser_confidence=0.72,
            parser_reason="本地规则兜底解析，保证无 DeepSeek Key 时仍可稳定规划。",
            llm_slots={},
        )

    def _parse_with_llm(
        self,
        user_input: str,
        rules_intent: ParsedIntent,
        conversation_history: list[dict[str, str]] | None = None,
        user_profile: dict[str, Any] | None = None,
    ) -> ParsedIntent | None:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=5.0)
        system_prompt = (
            "你是美团 SmartRoute 的结构化出行需求解析器。"
            "请把用户自然语言解析为本地生活路线规划约束，只返回 JSON，不要 Markdown。"
            "如果用户没有提到某字段，返回 null 或空数组，不要编造。"
        )
        user_prompt = {
            "query": user_input,
            "conversation_history": conversation_history or [],
            "user_profile": user_profile or {},
            "rules_fallback": rules_intent.model_dump(mode="json"),
            "schema": {
                "city": "城市，如上海/深圳/北京/广州",
                "query_type": "路线规划|单点查询",
                "confidence": "0到1的小数",
                "reason": "一句中文解析理由",
                "slots": {
                    "anchor_text": "区域/地标/商户锚点",
                    "total_time_hours": "数字",
                    "budget_per_person": "数字或null",
                    "party_size": "数字",
                    "max_wait_minutes": "数字",
                    "max_walk_minutes": "数字",
                    "start_time": "HH:MM",
                    "start_location": "起点或null",
                    "transport_mode": "步行优先/短步行+打车/驾车/公交/地铁+步行等",
                    "preferred_categories": ["餐饮", "咖啡/茶饮", "景点", "娱乐", "购物"],
                    "preferred_districts": ["区域或商圈"],
                    "travel_style": "文艺/轻松/省钱/亲子/浪漫/不踩雷等",
                    "special_requirements": ["少排队", "少走路", "拍照", "优惠等"],
                },
            },
        }
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            payload = json.loads(content)
            slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
            return self._merge_llm_slots(rules_intent, payload, slots, user_input)
        except Exception:
            return None

    def _merge_llm_slots(
        self,
        rules_intent: ParsedIntent,
        payload: dict[str, Any],
        slots: dict[str, Any],
        raw_query: str,
    ) -> ParsedIntent:
        next_intent = rules_intent.model_copy(deep=True)
        constraints = next_intent.constraints

        city = str(payload.get("city") or slots.get("city") or "").strip()
        if city:
            constraints.city = city
            next_intent.city = city

        next_intent.query_type = str(payload.get("query_type") or next_intent.query_type)
        confidence = self._safe_float(payload.get("confidence"), 0.82)
        next_intent.parser_source = "llm"
        next_intent.parser_confidence = max(0.0, min(1.0, confidence))
        next_intent.parser_reason = str(payload.get("reason") or "DeepSeek 结构化解析完成。")
        next_intent.llm_slots = slots

        constraints.total_time_hours = self._safe_float(slots.get("total_time_hours"), constraints.total_time_hours)
        constraints.budget_per_person = self._safe_optional_float(slots.get("budget_per_person"), constraints.budget_per_person)
        constraints.party_size = self._safe_int(slots.get("party_size"), constraints.party_size)
        constraints.max_wait_minutes = self._safe_int(slots.get("max_wait_minutes"), constraints.max_wait_minutes)
        constraints.max_walk_minutes = self._safe_int(slots.get("max_walk_minutes"), constraints.max_walk_minutes)

        for text_field, attr in [
            ("start_time", "start_time"),
            ("start_location", "start_location"),
            ("transport_mode", "transport_mode"),
        ]:
            value = slots.get(text_field)
            if isinstance(value, str) and value.strip():
                setattr(constraints, attr, value.strip())

        categories = self._normalize_categories(slots.get("preferred_categories"))
        if categories:
            constraints.preferred_categories = categories

        districts = self._normalize_string_list(slots.get("preferred_districts"))
        if districts:
            constraints.preferred_districts = districts

        special_requirements = self._normalize_string_list(slots.get("special_requirements"))
        travel_style = slots.get("travel_style") if isinstance(slots.get("travel_style"), str) else None
        anchor_text = slots.get("anchor_text") if isinstance(slots.get("anchor_text"), str) else None
        next_intent.extracted_preferences.update(
            {
                "raw_query": raw_query,
                "travel_style": travel_style or next_intent.extracted_preferences.get("travel_style", "休闲"),
                "special_requirements": "、".join(special_requirements)
                or next_intent.extracted_preferences.get("special_requirements", "无"),
                "anchor_text": anchor_text or next_intent.extracted_preferences.get("anchor_text"),
                "intent_parser_source": "llm",
            }
        )
        return next_intent

    def _normalize_categories(self, value: Any) -> list[POICategory]:
        aliases = {
            "咖啡": "咖啡/茶饮",
            "茶饮": "咖啡/茶饮",
            "美食": "餐饮",
            "餐厅": "餐饮",
            "展览": "景点",
            "文化": "景点",
            "玩乐": "娱乐",
        }
        items = self._normalize_string_list(value)
        categories: list[POICategory] = []
        for item in items:
            category_text = aliases.get(item, item)
            try:
                category = POICategory(category_text)
            except ValueError:
                continue
            if category not in categories:
                categories.append(category)
        return categories

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        raw_items = value if isinstance(value, list) else [value]
        items: list[str] = []
        for item in raw_items:
            text = str(item).strip()
            if text and text not in items:
                items.append(text[:32])
        return items[:8]

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            parsed = float(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    def _safe_optional_float(self, value: Any, default: float | None) -> float | None:
        if value in (None, "", "null"):
            return default
        return self._safe_float(value, default or 0.0)

    def _safe_int(self, value: Any, default: int) -> int:
        try:
            parsed = int(float(value))
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    def _extract_hours(self, text: str) -> float:
        if "半天" in text:
            return 4.0
        if "一天" in text or "一日" in text:
            return 8.0
        match = re.search(r"(\d+(?:\.\d+)?)\s*(?:个)?小时", text)
        if match:
            return float(match.group(1))
        if "上午" in text or "下午" in text:
            return 3.5
        if "晚上" in text or "夜" in text:
            return 3.0
        return 4.0

    def _extract_budget(self, text: str) -> float | None:
        patterns = [
            r"(?:预算|人均|每人|不超过|以内|控制在)\s*(\d{2,5})",
            r"(\d{2,5})\s*元(?:以内|预算|每人|人均)?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        if "便宜" in text or "省钱" in text or "优惠" in text:
            return 120.0
        return None

    def _extract_party_size(self, text: str) -> int:
        number_map = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}
        match = re.search(r"(\d+)\s*(?:个)?人", text)
        if match:
            return int(match.group(1))
        for word, value in number_map.items():
            if f"{word}个人" in text or f"{word}人" in text:
                return value
        if "一家三口" in text:
            return 3
        return 2

    def _extract_wait(self, text: str) -> int:
        match = re.search(r"(?:排队|等待).*?(\d+)\s*分钟", text)
        if match:
            return int(match.group(1))
        if "不想排队" in text or "少排队" in text or "不踩雷" in text:
            return 15
        if "可以排队" in text or "热门" in text:
            return 45
        return 30

    def _extract_start_time(self, text: str) -> str:
        match = re.search(r"(\d{1,2})[:：](\d{2})", text)
        if match:
            return f"{int(match.group(1)):02d}:{match.group(2)}"
        match = re.search(r"(上午|下午|晚上|中午)?\s*(\d{1,2})\s*点", text)
        if match:
            hour = int(match.group(2))
            period = match.group(1) or ""
            if period in {"下午", "晚上"} and hour < 12:
                hour += 12
            if period == "中午" and hour < 11:
                hour += 12
            return f"{hour:02d}:00"
        if "晚饭" in text or "晚上" in text or "夜" in text:
            return "18:00"
        if "上午" in text:
            return "10:00"
        return "14:00"

    def _extract_start_location(self, text: str) -> str | None:
        match = re.search(r"(?:从|起点|出发地)[:：]?\s*([\u4e00-\u9fffA-Za-z0-9·]{2,12})", text)
        return match.group(1) if match else None

    def _extract_transport_mode(self, text: str) -> str:
        if "打车" in text or "出租" in text:
            return "打车"
        if "地铁" in text:
            return "地铁+步行"
        if "少走" in text or "老人" in text or "爸妈" in text:
            return "短步行+打车"
        return "步行+公交"

    def _extract_categories(self, text: str) -> list[POICategory]:
        categories = []
        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword.lower() in text.lower() for keyword in keywords):
                categories.append(category)
        if not categories:
            categories = [POICategory.ATTRACTION, POICategory.RESTAURANT, POICategory.CAFE]
        return categories

    def _extract_districts(self, text: str) -> list[str]:
        districts = [district for district in DISTRICTS if district in text]
        for alias, district in DISTRICT_ALIASES.items():
            if alias in text and district not in districts:
                districts.append(district)
        return districts

    def _extract_city(self, text: str) -> str:
        if any(keyword in text for keyword in ["深圳", "深大", "深圳大学", "科技园", "深圳湾", "南山", "福田", "罗湖", "金地威新", "gaga"]):
            return "深圳"
        if any(keyword in text for keyword in ["北京", "三里屯", "朝阳", "国贸"]):
            return "北京"
        if any(keyword in text for keyword in ["广州", "天河", "珠江新城"]):
            return "广州"
        return "上海"

    def _extract_style(self, text: str) -> str | None:
        styles = ["文艺", "美食", "亲子", "商务", "休闲", "探险", "浪漫", "夜游", "省钱", "不踩雷", "轻松"]
        for style in styles:
            if style in text:
                return style
        if "爸妈" in text or "老人" in text or "孩子" in text:
            return "亲子"
        if "情侣" in text or "约会" in text:
            return "浪漫"
        return None

    def _extract_special_requirements(self, text: str) -> str:
        requirements = []
        for keyword in ["不想排队", "少走路", "带老人", "带孩子", "拍照", "优惠", "不踩雷", "安静", "有设计感"]:
            if keyword in text:
                requirements.append(keyword)
        return "、".join(requirements) or "无"
