from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.agents.intent_parser import IntentParserAgent
from core.agents.poi_retriever import POIRetrieverAgent
from core.agents.route_planner import RoutePlannerAgent
from core.memory.user_profile import UserProfileManager
from core.models import POI, Route
from core.rag.vector_store import POIVectorStore
from data.seed_db import generate_mock_pois, generate_reviews
from ui.components.poi_card import render_poi_card
from ui.components.preference_panel import render_preference_panel
from ui.components.route_map import render_route_map
from ui.styles import inject_custom_css


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
POI_PATH = DATA_DIR / "pois.json"
INDEX_DIR = DATA_DIR / "local_index"

load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="SmartRoute AI",
    page_icon="SR",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_custom_css()


def ensure_data() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    if not POI_PATH.exists():
        pois = generate_mock_pois(500)
        POI_PATH.write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
        (DATA_DIR / "ugc_reviews.json").write_text(
            json.dumps(generate_reviews(pois), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


@st.cache_resource
def load_poi_database() -> dict[str, POI]:
    ensure_data()
    raw = json.loads(POI_PATH.read_text(encoding="utf-8"))
    return {item["id"]: POI(**item) for item in raw}


@st.cache_resource
def load_vector_store() -> POIVectorStore:
    ensure_data()
    store = POIVectorStore(str(INDEX_DIR))
    if store.count == 0:
        raw = json.loads(POI_PATH.read_text(encoding="utf-8"))
        store.index_pois(raw)
    return store


@st.cache_resource
def load_agents() -> dict:
    poi_db = load_poi_database()
    vector_store = load_vector_store()
    return {
        "intent_parser": IntentParserAgent(),
        "poi_retriever": POIRetrieverAgent(vector_store, poi_db),
        "route_planner": RoutePlannerAgent(poi_db),
        "profile_manager": UserProfileManager(str(DATA_DIR / "user_profiles.db")),
    }


def init_state() -> None:
    defaults = {
        "messages": [],
        "routes": [],
        "last_intent": None,
        "last_candidates": [],
        "processing": False,
        "user_id": str(uuid.uuid4())[:8],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def summarize_route(route: Route) -> str:
    return (
        f"**{route.title}**\n\n"
        f"{route.description}\n\n"
        f"时长 {route.total_time_minutes // 60}h{route.total_time_minutes % 60}m · "
        f"人均 ¥{route.total_cost_per_person:.0f} · "
        f"等待 {route.total_wait_minutes} 分钟 · "
        f"{len(route.stops)} 站"
    )


def process_user_input(user_input: str, agents: dict) -> None:
    st.session_state.processing = True
    st.session_state.messages.append({"role": "user", "content": user_input})
    profile = agents["profile_manager"].get_profile(st.session_state.user_id)

    with st.spinner("正在解析约束、搜索候选 POI、组合路线..."):
        intent = agents["intent_parser"].parse(user_input, user_profile=profile.model_dump())
        agents["profile_manager"].infer_profile_from_chat(st.session_state.user_id, intent.extracted_preferences)
        candidates = agents["poi_retriever"].retrieve(intent, user_profile=profile)
        routes = agents["route_planner"].plan(intent, candidates, user_profile=profile, n_routes=2)

    st.session_state.last_intent = intent
    st.session_state.last_candidates = candidates
    st.session_state.routes = routes
    if routes:
        reply = "已生成两条可执行路线：\n\n" + "\n\n".join(
            f"方案 {index + 1}：{summarize_route(route)}" for index, route in enumerate(routes)
        )
    else:
        reply = "当前约束下没有找到足够稳定的路线，可以放宽预算、等待时间或区域范围。"
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.processing = False
    st.rerun()


def render_sidebar(agents: dict) -> None:
    with st.sidebar:
        st.title("SmartRoute AI")
        st.caption("多约束路线规划 Agent")
        render_preference_panel(agents["profile_manager"], st.session_state.user_id)
        st.divider()
        st.markdown("**快捷场景**")
        prompts = [
            "帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队",
            "想吃上海特色，但不想排队超过15分钟，4个人，晚上6点出发",
            "带爸妈在上海玩半天，少走路，轻松一点，预算人均300",
            "下午茶加逛街，安静有设计感，最好在静安寺附近",
        ]
        for index, prompt in enumerate(prompts):
            if st.button(prompt, key=f"prompt_{index}", use_container_width=True, disabled=st.session_state.processing):
                process_user_input(prompt, agents)


def render_trace() -> None:
    intent = st.session_state.last_intent
    if not intent:
        st.info("输入一句出行需求后，这里会展示结构化约束和候选 POI。")
        return

    constraints = intent.constraints
    st.markdown("**约束解析**")
    cols = st.columns(4)
    cols[0].metric("时间", f"{constraints.total_time_hours:g} 小时")
    cols[1].metric("预算", "不限" if not constraints.budget_per_person else f"¥{constraints.budget_per_person:.0f}")
    cols[2].metric("排队", f"≤{constraints.max_wait_minutes} 分钟")
    cols[3].metric("人数", f"{constraints.party_size} 人")
    st.caption(
        "区域："
        + ("、".join(constraints.preferred_districts) if constraints.preferred_districts else "全上海")
        + " · 偏好："
        + "、".join(category.value for category in constraints.preferred_categories)
    )

    candidates = st.session_state.last_candidates[:8]
    if candidates:
        st.markdown("**候选 POI Top 8**")
        for poi, score in candidates:
            st.caption(f"{poi.name} · {poi.category.value} · {poi.district} · 评分 {poi.rating} · 检索分 {score:.2f}")


def render_routes(agents: dict) -> None:
    routes: list[Route] = st.session_state.routes
    if not routes:
        st.markdown("### 路线地图")
        render_route_map(None)
        return

    tabs = st.tabs([f"方案 {index + 1} · {route.title}" for index, route in enumerate(routes)])
    for index, (tab, route) in enumerate(zip(tabs, routes)):
        with tab:
            cols = st.columns(4)
            cols[0].metric("总时长", f"{route.total_time_minutes // 60}h{route.total_time_minutes % 60}m")
            cols[1].metric("人均", f"¥{route.total_cost_per_person:.0f}")
            cols[2].metric("等待", f"{route.total_wait_minutes}m")
            cols[3].metric("交通", f"{route.total_transit_minutes}m")
            st.caption(route.description)
            render_route_map(route)

            st.markdown("**详细行程**")
            for stop in route.stops:
                render_poi_card(stop)

            if route.highlights:
                with st.expander("路线亮点", expanded=True):
                    for item in route.highlights:
                        st.markdown(f"- {item}")
            if route.warnings:
                with st.expander("注意事项", expanded=False):
                    for item in route.warnings:
                        st.warning(item)

            feedback_cols = st.columns([1, 1, 4])
            if feedback_cols[0].button("喜欢", key=f"like_{route.id}_{index}", use_container_width=True):
                agents["profile_manager"].update_from_route(
                    st.session_state.user_id,
                    route.model_dump(mode="json"),
                    feedback=1,
                )
                st.success("已记录偏好。")
            if feedback_cols[1].button("不合适", key=f"dislike_{route.id}_{index}", use_container_width=True):
                agents["profile_manager"].update_from_route(
                    st.session_state.user_id,
                    route.model_dump(mode="json"),
                    feedback=-1,
                )
                st.info("已记录，下次会降低类似方案权重。")


def main() -> None:
    init_state()
    agents = load_agents()
    render_sidebar(agents)

    st.title("现在出发")
    st.caption("把 POI 推荐变成可执行路线：时间、预算、等待、距离一起算。")

    col_chat, col_plan = st.columns([0.95, 1.35], gap="large")

    with col_chat:
        st.markdown("### 对话")
        history = st.container(height=380)
        with history:
            if not st.session_state.messages:
                st.info("例如：帮我规划一个外滩附近的文艺下午，3小时，两个人，预算200，不想排队。")
            for message in st.session_state.messages:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])

        user_input = st.chat_input("说说时间、预算、区域和偏好")
        if user_input and not st.session_state.processing:
            process_user_input(user_input, agents)

        st.markdown("### 规划状态")
        render_trace()

    with col_plan:
        render_routes(agents)


if __name__ == "__main__":
    main()
