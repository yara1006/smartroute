from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any

from openai import OpenAI

from core.models import RouteIntentResult


ACTIVITY_KEYWORDS = {
    "餐饮": ["吃", "美食", "餐厅", "晚饭", "午饭", "火锅", "小吃", "烧烤", "brunch", "早午餐"],
    "咖啡/茶饮": ["咖啡", "茶", "下午茶", "奶茶", "甜品"],
    "景点": ["玩", "逛", "散步", "景点", "公园", "博物馆", "展", "拍照", "打卡", "citywalk"],
    "娱乐": ["电影", "酒吧", "live", "演出", "密室", "ktv", "剧本杀", "夜游"],
    "购物": ["商场", "购物", "买", "市集", "逛街"],
}

ROUTE_WORDS = ["路线", "规划", "安排", "串", "排一下", "怎么走", "怎么玩", "怎么逛", "逛吃", "吃完再", "饭后", "顺路", "一日游", "半天玩"]
TIME_WORDS = ["上午", "下午", "晚上", "今晚", "今天", "明天", "周末", "半天", "一天"]
COMPANION_WORDS = ["爸妈", "父母", "老人", "孩子", "亲子", "情侣", "朋友", "同事", "一家人"]
CONSTRAINT_WORDS = ["预算", "人均", "便宜", "贵", "不排队", "少排队", "排队", "少走路", "轻松", "室内", "雨天", "打车", "公交", "地铁"]
SINGLE_POI_WORDS = ["电话", "地址", "营业", "几点开", "几点关", "优惠", "券", "菜单", "评分", "停车", "外卖", "排号", "订座"]
PLACE_SUFFIXES = "大学|学院|公园|商圈|中心|广场|景区|景点|天地|胡同|街|路|城|湾|坊|寺|店|馆|园|站|村|镇|区"


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
        previous_intent: RouteIntentResult | None = None,
        conversation_id: str | None = None,
        user_reply_type: str = "free_text",
    ) -> RouteIntentResult:
        text = query.strip()
        context = context or {}
        conversation_id = conversation_id or previous_intent.conversation_id if previous_intent else conversation_id
        conversation_id = conversation_id or f"xiaotuan-{uuid.uuid4().hex[:8]}"
        if not text:
            return RouteIntentResult(
                action="normal_answer",
                confidence=0.0,
                reason="用户还没有输入需求",
                detected_slots={},
                planning_query=text,
                source="rules",
                conversation_id=conversation_id,
                turn_state="new",
                intent_type="empty",
            )

        signals = self._extract_signals(text, source, context)
        rules_result = self._route_with_rules(text, source, context, signals)
        llm_result = self._route_with_llm(text, source, context, signals) if self.api_key else None
        fused = self._fuse_results(text, rules_result, llm_result, signals)
        return self._complete_slots(
            query=text,
            result=fused,
            signals=signals,
            context=context,
            previous_intent=previous_intent,
            conversation_id=conversation_id,
            user_reply_type=user_reply_type,
        )

    def _route_with_llm(
        self,
        query: str,
        source: str,
        context: dict[str, Any],
        signals: dict[str, Any],
    ) -> RouteIntentResult | None:
        client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=4.0)
        system_prompt = (
            "你是美团小团 AI 的路线意图识别器。你的任务是判断是否调起 SmartRoute 路线规划插件。"
            "只返回 JSON，不要返回 Markdown。action 只能是 open_plugin、ask_confirm、normal_answer。"
            "open_plugin: 用户明确需要把多个本地生活 POI 串成可执行路线，或有时长/多活动/顺路安排等强信号。"
            "ask_confirm: 用户有本地生活地点或活动需求，但缺少路线、时长、多活动等关键要素，需要先问一句确认。"
            "normal_answer: 用户在问单店电话、地址、营业时间、菜单、优惠、评分、停车、外卖等信息。"
            "如果要素不齐，不要硬开插件，优先 ask_confirm 并给出缺失字段。"
        )
        examples = [
            {"query": "中山大学玩3小时", "action": "open_plugin", "intent_type": "route_plan", "anchor_text": "中山大学"},
            {"query": "带爸妈在金鱼胡同轻松逛半天", "action": "open_plugin", "intent_type": "route_plan", "anchor_text": "金鱼胡同"},
            {"query": "万象天地有什么好玩的", "action": "ask_confirm", "intent_type": "local_recommendation", "anchor_text": "万象天地"},
            {"query": "gaga营业到几点", "action": "normal_answer", "intent_type": "single_poi_info", "negative_reason": "营业时间查询"},
        ]
        user_prompt = {
            "query": query,
            "source": source,
            "context": context,
            "rule_signals": signals,
            "few_shot_examples": examples,
            "required_schema": {
                "action": "open_plugin|ask_confirm|normal_answer",
                "confidence": "0到1的小数",
                "intent_type": "route_plan|local_recommendation|single_poi_info|transaction|other",
                "reason": "一句中文原因",
                "anchor_text": "区域/地标/商户锚点或null",
                "activities": ["餐饮/咖啡/景点/娱乐/购物等"],
                "constraints": ["预算/排队/少走路/人群/交通等"],
                "missing_slots": ["需要追问的关键字段"],
                "negative_reason": "如果不应打开插件，写原因，否则null",
                "detected_slots": {
                    "location": "区域/地点或空",
                    "time": "时间窗口/时长或空",
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
            payload = json.loads(response.choices[0].message.content or "{}")
            result = RouteIntentResult(
                action=self._normalize_action(payload.get("action")),
                confidence=self._safe_float(payload.get("confidence"), 0.0),
                reason=str(payload.get("reason") or "LLM 判断完成"),
                detected_slots=payload.get("detected_slots") if isinstance(payload.get("detected_slots"), dict) else {},
                planning_query=str(payload.get("planning_query") or query),
                source="llm",
                intent_type=str(payload.get("intent_type") or ""),
                anchor_text=self._clean_optional(payload.get("anchor_text")),
                activities=self._string_list(payload.get("activities")),
                constraints=self._string_list(payload.get("constraints")),
                negative_reason=self._clean_optional(payload.get("negative_reason")),
                rule_signals=signals,
                llm_judgement=self._safe_payload(payload),
            )
            return self._sanitize_result(result, query)
        except Exception:
            return None

    def _route_with_rules(
        self,
        query: str,
        source: str,
        context: dict[str, Any],
        signals: dict[str, Any],
    ) -> RouteIntentResult:
        strong_route = (
            signals["route_hit"]
            or signals["duration_hit"]
            or signals["multi_activity_hit"]
            or signals["pinned_context_hit"]
            or signals["continuation_context_hit"]
        )
        local_need = signals["local_life_hit"] or bool(signals["locations"]) or signals["has_context_anchor"]
        has_location_context = bool(signals["locations"]) or signals["has_context_anchor"] or signals["pinned_context_hit"] or signals["continuation_context_hit"]
        single_info = signals["single_poi_hit"] and not (signals["route_hit"] or signals["multi_activity_hit"] or signals["duration_hit"])

        if single_info:
            action = "normal_answer"
            confidence = 0.18
            reason = "用户更像在问单店信息或交易信息，不应默认打开路线插件"
            intent_type = "single_poi_info"
            negative_reason = "单店信息查询"
        elif strong_route and local_need and has_location_context:
            action = "open_plugin"
            confidence = 0.9 if signals["duration_hit"] or signals["multi_activity_hit"] else 0.84
            reason = "用户表达了地点/活动/时长/顺路安排等路线强信号，适合直接调起路线规划插件"
            intent_type = "route_plan"
            negative_reason = None
        elif local_need:
            action = "ask_confirm"
            confidence = 0.62
            reason = "用户有本地生活需求，但路线目标、时长或多站安排还不完整，需要先确认"
            intent_type = "local_recommendation"
            negative_reason = None
        else:
            action = "normal_answer"
            confidence = 0.25
            reason = "当前问题更适合由小团普通问答处理"
            intent_type = "other"
            negative_reason = "缺少本地生活路线信号"

        missing_slots = self._missing_slots_for(action, signals)
        return RouteIntentResult(
            action=action,
            confidence=confidence,
            reason=reason,
            detected_slots={
                "location": "、".join(signals["locations"]),
                "time": "已识别" if signals["time_hit"] else "",
                "intent": "路线规划" if action == "open_plugin" else "可能路线" if action == "ask_confirm" else "普通问答",
                "activities": signals["activities"],
                "constraints": signals["constraints"],
                "missing_slots": missing_slots,
                "source_entry": source,
                "context_keys": list(context.keys()),
            },
            planning_query=self._build_planning_query(query, action),
            source="rules",
            intent_type=intent_type,
            anchor_text=signals["locations"][0] if signals["locations"] else None,
            activities=signals["activities"],
            constraints=signals["constraints"],
            negative_reason=negative_reason,
            rule_signals=signals,
        )

    def _fuse_results(
        self,
        query: str,
        rules_result: RouteIntentResult,
        llm_result: RouteIntentResult | None,
        signals: dict[str, Any],
    ) -> RouteIntentResult:
        if llm_result is None:
            result = rules_result.model_copy(update={"fusion": {"strategy": "rules_only", "final_action": rules_result.action}})
            return self._apply_core_slot_policy(query, self._sanitize_result(result, query), signals)

        single_info = signals["single_poi_hit"] and not (signals["route_hit"] or signals["multi_activity_hit"] or signals["duration_hit"])
        strong_route = (
            signals["route_hit"]
            or signals["duration_hit"]
            or signals["multi_activity_hit"]
            or signals["pinned_context_hit"]
            or signals["continuation_context_hit"]
        )
        local_need = signals["local_life_hit"] or bool(signals["locations"]) or signals["has_context_anchor"]
        has_location_context = bool(signals["locations"]) or signals["has_context_anchor"] or signals["pinned_context_hit"] or signals["continuation_context_hit"]

        chosen = llm_result
        strategy = "llm_primary"
        if single_info:
            chosen = rules_result
            strategy = "rules_guardrail_single_poi"
        elif strong_route and local_need and has_location_context and llm_result.action != "open_plugin":
            chosen = rules_result
            strategy = "rules_override_route_signal"
        elif llm_result.action == "open_plugin" and not has_location_context:
            chosen = rules_result
            strategy = "rules_guardrail_missing_location"
        elif rules_result.action == "ask_confirm" and llm_result.action == "normal_answer" and local_need:
            chosen = rules_result
            strategy = "rules_guardrail_local_need"

        confidence = max(chosen.confidence, rules_result.confidence if chosen.action == rules_result.action else chosen.confidence)
        result = chosen.model_copy(
            update={
                "confidence": min(0.96, confidence),
                "rule_signals": signals,
                "llm_judgement": llm_result.llm_judgement,
                "fusion": {
                    "strategy": strategy,
                    "rules_action": rules_result.action,
                    "llm_action": llm_result.action,
                    "final_action": chosen.action,
                    "conflict": rules_result.action != llm_result.action,
                },
            }
        )
        if not result.anchor_text and rules_result.anchor_text:
            result = result.model_copy(update={"anchor_text": rules_result.anchor_text})
        return self._apply_core_slot_policy(query, self._sanitize_result(result, query), signals)

    def _extract_signals(self, query: str, source: str, context: dict[str, Any]) -> dict[str, Any]:
        activities = [name for name, words in ACTIVITY_KEYWORDS.items() if any(word.lower() in query.lower() for word in words)]
        for poi in context.get("selected_pois") or []:
            category = poi.get("category") if isinstance(poi, dict) else getattr(poi, "category", None)
            if category and str(category) not in activities:
                activities.append(str(category))
        constraints = [word for word in CONSTRAINT_WORDS + COMPANION_WORDS if word in query]
        locations = self._extract_location_hits(query, context)
        time_phrase = self._extract_time_phrase(query)
        time_hit = bool(re.search(r"(上午|下午|晚上|今晚|今天|明天|周末|半天|一天|\d+\s*(?:个)?小时|\d{1,2}\s*点)", query))
        duration_hit = bool(re.search(r"(半天|一天|\d+\s*(?:个)?小时)", query))
        route_hit = any(word in query for word in ROUTE_WORDS)
        local_life_hit = bool(activities) or any(word in query for word in ["附近", "周边", "去哪", "好玩", "推荐"])
        single_poi_hit = any(word in query for word in SINGLE_POI_WORDS)
        multi_activity_hit = self._has_multi_activity(query, activities)
        pinned_context_hit = source in {"favorites", "favorite"} or bool(context.get("selected_pois"))
        continuation_context_hit = source in {"detail", "poi_detail"} or any(word in query for word in ["从这", "从这里", "这家店", "下一站", "后面"])
        return {
            "locations": locations,
            "time_hit": time_hit,
            "time_phrase": time_phrase,
            "duration_hit": duration_hit,
            "route_hit": route_hit,
            "local_life_hit": local_life_hit,
            "single_poi_hit": single_poi_hit,
            "multi_activity_hit": multi_activity_hit,
            "pinned_context_hit": pinned_context_hit,
            "continuation_context_hit": continuation_context_hit,
            "has_context_anchor": bool(context.get("anchor_text") or context.get("anchor_location")),
            "activities": activities,
            "constraints": constraints,
            "source_entry": source,
        }

    def _has_multi_activity(self, query: str, activities: list[str]) -> bool:
        return len(activities) >= 2 or any(word in query for word in ["再", "然后", "+", "和", "逛吃", "饭后", "吃完"])

    def _missing_slots_for(self, action: str, signals: dict[str, Any]) -> list[str]:
        if action == "normal_answer":
            return []
        return self._core_missing_slots(signals)

    def _apply_core_slot_policy(self, query: str, result: RouteIntentResult, signals: dict[str, Any]) -> RouteIntentResult:
        if result.action == "normal_answer":
            return result

        missing_slots = self._core_missing_slots(signals)
        detected_slots = dict(result.detected_slots or {})
        detected_slots["missing_slots"] = missing_slots
        if not missing_slots:
            return result.model_copy(update={"detected_slots": detected_slots})

        question = self._generate_follow_up_question(missing_slots)
        return result.model_copy(
            update={
                "action": "ask_confirm",
                "confidence": min(result.confidence, 0.69),
                "reason": f"需要补齐核心信息：{question}",
                "detected_slots": detected_slots,
                "planning_query": query,
                "follow_up_question": question,
            }
        )

    def _core_missing_slots(self, signals: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        has_location = (
            bool(signals["locations"])
            or signals["has_context_anchor"]
            or signals["pinned_context_hit"]
            or signals["continuation_context_hit"]
        )
        if not has_location:
            missing.append("location")
        if not signals["time_hit"]:
            missing.append("time")
        if not signals["activities"]:
            missing.append("activities")
        return missing

    def _generate_follow_up_question(self, missing_slots: list[str]) -> str:
        questions = {
            "location": "想在哪个区域、商圈或 POI 附近安排？",
            "time": "大概安排多久，或者什么时候去？",
            "activities": "更想吃饭、咖啡、看展、逛街还是娱乐？",
        }
        return " ".join(questions[slot] for slot in missing_slots[:2] if slot in questions)

    def _complete_slots(
        self,
        query: str,
        result: RouteIntentResult,
        signals: dict[str, Any],
        context: dict[str, Any],
        previous_intent: RouteIntentResult | None,
        conversation_id: str,
        user_reply_type: str,
    ) -> RouteIntentResult:
        is_slot_continuation = previous_intent is not None and previous_intent.turn_state == "collecting_slots"
        if result.action == "normal_answer" and not is_slot_continuation:
            return result.model_copy(
                update={
                    "conversation_id": conversation_id,
                    "turn_state": "normal_answer",
                    "filled_slots": {},
                    "missing_slots": [],
                    "clarification_question": None,
                    "clarification_options": [],
                    "merged_query": query,
                }
            )
        if result.action == "normal_answer" and is_slot_continuation:
            result = result.model_copy(
                update={
                    "action": "ask_confirm",
                    "confidence": max(result.confidence, 0.58),
                    "reason": "用户正在补充上一轮路线规划缺失信息。",
                    "intent_type": previous_intent.intent_type or "route_plan",
                }
            )

        filled_slots = self._merge_filled_slots(query, signals, context, previous_intent)
        missing_codes = self._missing_required_codes(filled_slots)
        missing_labels = [self._slot_label(code) for code in missing_codes]
        detected_slots = dict(result.detected_slots or {})
        detected_slots["missing_slots"] = missing_codes
        detected_slots["missing_slot_labels"] = missing_labels
        detected_slots["filled_slots"] = filled_slots

        merged_query = self._build_merged_query(query, filled_slots, previous_intent)
        should_open = not missing_codes and (
            result.action == "open_plugin"
            or user_reply_type in {"chip", "confirm_route"}
            or (previous_intent is not None and previous_intent.action == "ask_confirm")
        )
        if should_open:
            return result.model_copy(
                update={
                    "action": "open_plugin",
                    "confidence": max(result.confidence, 0.86),
                    "reason": "已补齐地点、时间和活动三类核心要素，可以调起 SmartRoute 生成路线。",
                    "detected_slots": detected_slots,
                    "planning_query": merged_query,
                    "conversation_id": conversation_id,
                    "turn_state": "ready_to_plan",
                    "filled_slots": filled_slots,
                    "missing_slots": [],
                    "clarification_question": None,
                    "clarification_options": [],
                    "merged_query": merged_query,
                    "anchor_text": filled_slots.get("location") or result.anchor_text,
                    "activities": filled_slots.get("activities") or result.activities,
                }
            )

        question = self._clarification_question(missing_codes, filled_slots)
        return result.model_copy(
            update={
                "action": "ask_confirm",
                "confidence": min(max(result.confidence, 0.58), 0.76),
                "reason": self._clarification_reason(missing_codes),
                "detected_slots": detected_slots,
                "planning_query": merged_query,
                "conversation_id": conversation_id,
                "turn_state": "collecting_slots",
                "filled_slots": filled_slots,
                "missing_slots": missing_codes,
                "clarification_question": question,
                "clarification_options": self._clarification_options(missing_codes, context),
                "merged_query": merged_query,
                "anchor_text": filled_slots.get("location") or result.anchor_text,
                "activities": filled_slots.get("activities") or result.activities,
            }
        )

    def _merge_filled_slots(
        self,
        query: str,
        signals: dict[str, Any],
        context: dict[str, Any],
        previous_intent: RouteIntentResult | None,
    ) -> dict[str, Any]:
        previous = dict(previous_intent.filled_slots or {}) if previous_intent else {}
        context_location = self._location_from_context(context)
        location = signals["locations"][0] if signals["locations"] else context_location or previous.get("location")
        time_value = signals.get("time_phrase") or previous.get("time")
        activities = signals["activities"] or previous.get("activities") or self._activities_from_context(context)
        constraints = list(dict.fromkeys([*(previous.get("constraints") or []), *signals["constraints"]]))
        optional = {
            "party_type": self._first_hit(query, COMPANION_WORDS) or previous.get("party_type"),
            "budget": self._extract_budget_phrase(query) or previous.get("budget"),
            "queue_tolerance": self._first_hit(query, ["不排队", "少排队", "排队"]) or previous.get("queue_tolerance"),
            "mobility": self._first_hit(query, ["少走路", "打车", "公交", "地铁", "步行"]) or previous.get("mobility"),
        }
        return {
            "location": location or "",
            "time": time_value or "",
            "activities": activities if isinstance(activities, list) else [],
            "constraints": constraints,
            **{key: value for key, value in optional.items() if value},
        }

    def _missing_required_codes(self, filled_slots: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if not filled_slots.get("location"):
            missing.append("location")
        if not filled_slots.get("time"):
            missing.append("time")
        if not filled_slots.get("activities"):
            missing.append("activities")
        return missing

    def _slot_label(self, code: str) -> str:
        return {
            "location": "地点/区域",
            "time": "时间/时长",
            "activities": "想吃/玩/逛的类型",
        }.get(code, code)

    def _clarification_reason(self, missing_codes: list[str]) -> str:
        labels = [self._slot_label(code) for code in missing_codes[:2]]
        return f"需要先确认{'、'.join(labels)}，补齐后才能生成更准确的路线。"

    def _clarification_question(self, missing_codes: list[str], filled_slots: dict[str, Any]) -> str | None:
        asking = missing_codes[:2]
        if asking == ["location"]:
            return "想在哪个区域安排？"
        if asking == ["time"]:
            return "大概安排多久，或者什么时候去？"
        if asking == ["activities"]:
            return "更想吃饭、咖啡、看展、逛街还是娱乐？"
        parts = []
        if "location" in asking:
            parts.append("在哪个区域")
        if "time" in asking:
            parts.append("大概多久")
        if "activities" in asking:
            parts.append("想吃/玩/逛什么")
        return "，".join(parts) + "？" if parts else None

    def _clarification_options(self, missing_codes: list[str], context: dict[str, Any]) -> list[str]:
        if not missing_codes:
            return []
        first = missing_codes[0]
        if first == "location":
            city = str(context.get("current_city") or context.get("city_hint") or "深圳")
            if "北京" in city:
                return ["金鱼胡同附近", "三里屯附近", "王府井附近"]
            if "上海" in city:
                return ["外滩附近", "静安寺附近", "徐家汇附近"]
            if "广州" in city:
                return ["永庆坊附近", "北京路附近", "珠江新城附近"]
            return ["深圳大学附近", "万象天地附近", "车公庙附近"]
        if first == "time":
            return ["今晚3小时", "下午3小时", "半天"]
        if first == "activities":
            return ["吃饭+散步", "咖啡+看展", "逛街+晚餐", "娱乐+夜宵"]
        return []

    def _build_merged_query(self, query: str, filled_slots: dict[str, Any], previous_intent: RouteIntentResult | None) -> str:
        parts = [
            filled_slots.get("location", ""),
            filled_slots.get("time", ""),
            "、".join(filled_slots.get("activities", [])),
            "、".join(filled_slots.get("constraints", [])),
        ]
        merged = "，".join(part for part in parts if part)
        merged = re.sub(r"(，)+", "，", merged).strip("，。,. 　")
        if not any(word in merged for word in ["路线", "规划", "安排"]):
            merged = f"{merged}，帮我规划成一条可执行路线"
        return merged

    def _location_from_context(self, context: dict[str, Any]) -> str:
        if context.get("anchor_text"):
            return clean_location_text(str(context["anchor_text"]))
        selected = context.get("selected_pois")
        if isinstance(selected, list) and selected:
            names = [str(item.get("name", "")).strip() for item in selected if isinstance(item, dict)]
            if names:
                return "、".join(names[:3])
        return ""

    def _activities_from_context(self, context: dict[str, Any]) -> list[str]:
        selected = context.get("selected_pois")
        if not isinstance(selected, list):
            return []
        categories = []
        for item in selected:
            if isinstance(item, dict) and item.get("category"):
                categories.append(str(item["category"]))
        return list(dict.fromkeys(categories))

    def _extract_time_phrase(self, query: str) -> str:
        matches = re.findall(r"(上午|下午|晚上|今晚|今天|明天|周末|半天|一天|\d+\s*(?:个)?小时|\d{1,2}\s*点)", query)
        return "".join(matches[:3])

    def _extract_budget_phrase(self, query: str) -> str:
        match = re.search(r"(?:预算|人均)?\s*(\d{2,5})\s*(?:元|块|以内|左右)?", query)
        if match and any(word in query for word in ["预算", "人均", "便宜", "贵", "元", "块"]):
            return f"人均{match.group(1)}"
        return ""

    def _first_hit(self, query: str, words: list[str]) -> str:
        return next((word for word in words if word in query), "")

    def _sanitize_result(self, result: RouteIntentResult, fallback_query: str) -> RouteIntentResult:
        action = self._normalize_action(result.action)
        confidence = max(0.0, min(1.0, result.confidence))
        if action == "open_plugin" and confidence < 0.72:
            action = "ask_confirm"
        if action == "normal_answer" and confidence > 0.68:
            confidence = 0.68
        detected_slots = dict(result.detected_slots or {})
        if result.anchor_text and not detected_slots.get("location"):
            detected_slots["location"] = result.anchor_text
        if result.activities and not detected_slots.get("activities"):
            detected_slots["activities"] = result.activities
        if result.constraints and not detected_slots.get("constraints"):
            detected_slots["constraints"] = result.constraints
        return result.model_copy(
            update={
                "action": action,
                "confidence": confidence,
                "detected_slots": detected_slots,
                "planning_query": result.planning_query.strip() or fallback_query,
            }
        )

    def _normalize_action(self, action: Any) -> str:
        if action in {"open_plugin", "ask_confirm", "normal_answer"}:
            return str(action)
        return "normal_answer"

    def _extract_location_hits(self, query: str, context: dict[str, Any] | None = None) -> list[str]:
        query_hits: list[str] = []
        context = context or {}
        patterns = [
            rf"(?:想去|要去|我要去|我想去|去|到|在)\s*([\u4e00-\u9fffA-Za-z0-9·]{{2,24}}?)(?:附近|周边|玩|逛|吃|轻松|有|推荐|怎么|半天|一天|\d+\s*(?:个)?小时|$)",
            rf"([\u4e00-\u9fffA-Za-z0-9·]{{2,24}}(?:{PLACE_SUFFIXES}))(?:附近|周边|有|推荐|怎么|玩|逛|吃|轻松|半天|一天|\d+\s*(?:个)?小时|$)",
            rf"(?:上午|下午|晚上|今晚|今天|明天|周末)?\s*([\u4e00-\u9fffA-Za-z0-9·]{{2,24}}?)(?:附近|周边)?(?:玩|逛|逛吃|吃饭|看展|看电影)\s*(?:半天|一天|\d+\s*(?:个)?小时)?",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, query, flags=re.IGNORECASE):
                location = clean_location_text(match.group(1))
                if self._looks_like_location(location) and location not in query_hits:
                    query_hits.append(location)
        if query_hits:
            return query_hits[:3]

        hits: list[str] = []
        if context.get("anchor_text"):
            context_anchor = clean_location_text(str(context["anchor_text"]))
            if self._looks_like_location(context_anchor):
                hits.append(context_anchor)
        return hits[:3]

    def _looks_like_location(self, value: str) -> bool:
        if not value or len(value) < 2:
            return False
        blocked = {"附近", "周边", "今天", "明天", "上午", "下午", "晚上", "今晚", "周末", "半天", "一天", "路线", "规划", "安排"}
        if value in blocked:
            return False
        non_location_words = [
            "什么",
            "怎么",
            "有没有",
            "多少",
            "几个",
            "小时",
            "今晚",
            "今天",
            "明天",
            "上午",
            "下午",
            "晚上",
            "几点",
            "少走路",
            "不排队",
            "少排队",
            "排队",
            "散步",
            "吃饭",
            "喝点",
            "咖啡",
            "看展",
            "逛街",
            "娱乐",
            "路线",
            "规划",
            "安排",
        ]
        if any(word in value for word in non_location_words):
            return False
        return True

    def _build_planning_query(self, query: str, action: str) -> str:
        if action == "normal_answer":
            return query
        if any(word in query for word in ["路线", "规划", "安排"]):
            return query
        return f"{query}，帮我规划成一条可执行路线"

    def _safe_float(self, value: Any, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def _clean_optional(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = clean_location_text(value)
        return cleaned or None

    def _string_list(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()][:8]

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "action",
            "confidence",
            "intent_type",
            "reason",
            "anchor_text",
            "activities",
            "constraints",
            "missing_slots",
            "negative_reason",
            "detected_slots",
        }
        return {key: payload.get(key) for key in allowed if key in payload}


def clean_location_text(value: str) -> str:
    text = value.strip("，。,. 　")
    prefixes = ["我要去", "我想去", "想去", "要去", "我去", "去", "到", "在", "我要", "我想", "想", "要", "带爸妈在", "带父母在", "今晚在"]
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if text.startswith(prefix) and len(text) > len(prefix) + 1:
                text = text[len(prefix):].strip("，。,. 　")
                changed = True
    text = re.sub(r"(?:附近|周边)?(?:玩|逛|逛吃|吃|下午茶|看展|看电影|轻松)$", "", text).strip("，。,. 　")
    return text[:24]
