from __future__ import annotations

import os
import re
from typing import Any

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

    A heuristic parser is intentionally kept as the default path. It makes the
    hackathon demo deterministic, while leaving room for DeepSeek enhancement.
    """

    def parse(
        self,
        user_input: str,
        conversation_history: list[dict[str, str]] | None = None,
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
            },
            clarification_needed=False,
        )

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
