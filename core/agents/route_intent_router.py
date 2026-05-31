from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI

from core.models import RouteIntentResult


class RouteIntentRouterAgent:
    """Classify whether a XiaoTuan query should open SmartRoute."""

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        self.model = os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat").strip() or "deepseek-chat"
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()

    def route(
        self,
        query: str,
        source: str = "xiaotuan",
        context: dict[str, Any] | None = None,
    ) -> RouteIntentResult:
        text = query.strip()
        if not text:
            return RouteIntentResult(
                action="normal_answer",
                confidence=0.0,
                reason="用户还没有输入需求",
                detected_slots={},
                planning_query=text,
                source="rules",
            )

        if self.api_key:
            llm_result = self._route_with_llm(text, source, context or {})
            if llm_result:
                return llm_result

        return self._route_with_rules(text, source, context or {})

    def _route_with_llm(
        self,
        query: str,
        source: str,
        context: dict[str, Any],
    ) -> RouteIntentResult | None:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=4.0)
        system_prompt = (
            "你是美团小团 AI 的路线意图识别器。判断用户是否应该调起 SmartRoute 路线规划插件。"
            "只返回 JSON，不要返回 Markdown。action 只能是 open_plugin、ask_confirm、normal_answer。"
            "open_plugin 表示明确要把多个本地生活 POI 串成路线；ask_confirm 表示可能需要路线但不明确；"
            "normal_answer 表示普通问答、单店推荐、优惠、菜品、营业时间、电话或地址。"
        )
        user_prompt = {
            "query": query,
            "source": source,
            "context": context,
            "required_schema": {
                "action": "open_plugin|ask_confirm|normal_answer",
                "confidence": "0到1的小数",
                "reason": "一句中文原因",
                "detected_slots": {
                    "location": "区域/地点或空",
                    "time": "时间窗口或空",
                    "intent": "路线/推荐/优惠/营业信息等",
                    "constraints": ["预算/排队/少走路/人群等"],
                },
                "planning_query": "如果要调起路线插件，给 SmartRoute 的完整路线规划 query；否则保留原 query",
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
            result = RouteIntentResult(
                action=self._normalize_action(payload.get("action")),
                confidence=float(payload.get("confidence", 0.0)),
                reason=str(payload.get("reason") or "LLM 判断完成"),
                detected_slots=payload.get("detected_slots") if isinstance(payload.get("detected_slots"), dict) else {},
                planning_query=str(payload.get("planning_query") or query),
                source="llm",
            )
            return self._sanitize_result(result, query)
        except Exception:
            return None

    def _route_with_rules(
        self,
        query: str,
        source: str,
        context: dict[str, Any],
    ) -> RouteIntentResult:
        location_hits = self._extract_location_hits(query)
        time_hit = bool(re.search(r"(上午|下午|晚上|今晚|明天|周末|半天|一天|\d+\s*(?:个)?小时|\d{1,2}\s*点)", query))
        duration_hit = bool(re.search(r"(半天|一天|\d+\s*(?:个)?小时)", query))
        route_hit = any(word in query for word in ["路线", "规划", "安排", "串", "怎么走", "怎么玩", "半天玩", "一日游", "吃完再", "逛逛"])
        local_life_hit = any(
            word in query
            for word in [
                "吃",
                "玩",
                "逛",
                "咖啡",
                "下午茶",
                "餐厅",
                "展",
                "景点",
                "电影",
                "酒吧",
                "市集",
                "商场",
                "外滩",
                "深圳大学",
                "深大",
                "科技园",
                "深圳湾",
            ]
        )
        constraints = [word for word in ["预算", "人均", "不排队", "少排队", "少走路", "爸妈", "老人", "孩子", "情侣"] if word in query]
        single_poi_hit = any(word in query for word in ["电话", "地址", "营业", "几点开", "优惠", "券", "菜单", "评分"])

        if single_poi_hit and not route_hit:
            action = "normal_answer"
            confidence = 0.18
            reason = "用户更像在问单店信息或交易信息，不应默认打开路线插件"
        elif route_hit and (location_hits or time_hit or local_life_hit):
            action = "open_plugin"
            confidence = 0.88
            reason = "用户表达了区域/时间/吃喝玩乐目标，并带有路线或安排意图"
        elif duration_hit and location_hits and local_life_hit:
            action = "open_plugin"
            confidence = 0.84
            reason = "用户给出了明确区域和时长，适合直接调起路线规划插件"
        elif (location_hits or time_hit) and local_life_hit:
            action = "ask_confirm"
            confidence = 0.62
            reason = "用户有本地生活出行需求，但还没有明确要求串联成路线"
        else:
            action = "normal_answer"
            confidence = 0.25
            reason = "当前问题更适合由小团普通问答处理"

        return RouteIntentResult(
            action=action,
            confidence=confidence,
            reason=reason,
            detected_slots={
                "location": "、".join(location_hits),
                "time": "已识别" if time_hit else "",
                "intent": "路线规划" if action == "open_plugin" else "可能路线" if action == "ask_confirm" else "普通问答",
                "constraints": constraints,
                "source_entry": source,
                "context_keys": list(context.keys()),
            },
            planning_query=self._build_planning_query(query, action),
            source="rules",
        )

    def _sanitize_result(self, result: RouteIntentResult, fallback_query: str) -> RouteIntentResult:
        action = self._normalize_action(result.action)
        confidence = max(0.0, min(1.0, result.confidence))
        if action == "open_plugin" and confidence < 0.72:
            action = "ask_confirm"
        if action == "normal_answer" and confidence > 0.68:
            confidence = 0.68
        return result.model_copy(
            update={
                "action": action,
                "confidence": confidence,
                "planning_query": result.planning_query.strip() or fallback_query,
            }
        )

    def _normalize_action(self, action: Any) -> str:
        if action in {"open_plugin", "ask_confirm", "normal_answer"}:
            return str(action)
        return "normal_answer"

    def _extract_location_hits(self, query: str) -> list[str]:
        candidates = [
            "外滩",
            "豫园",
            "南京路",
            "陆家嘴",
            "徐家汇",
            "武康路",
            "静安寺",
            "愚园路",
            "大学路",
            "虹桥",
            "深圳大学",
            "深大",
            "科技园",
            "深圳湾",
            "金地威新",
            "南山",
            "福田",
        ]
        return [item for item in candidates if item in query]

    def _build_planning_query(self, query: str, action: str) -> str:
        if action == "normal_answer":
            return query
        if any(word in query for word in ["路线", "规划", "安排"]):
            return query
        return f"{query}，帮我规划成一条可执行路线"
