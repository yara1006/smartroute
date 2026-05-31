from __future__ import annotations

import streamlit as st

from core.memory.user_profile import UserProfileManager


def render_preference_panel(profile_manager: UserProfileManager, user_id: str) -> None:
    profile = profile_manager.get_profile(user_id)

    with st.expander("个人偏好", expanded=False):
        st.caption(f"演示用户：{user_id}")
        styles = ["未设置", "文艺", "美食", "亲子", "商务", "休闲", "浪漫", "夜游", "省钱", "轻松"]
        current_style = profile.travel_style or "未设置"
        if current_style not in styles:
            current_style = "未设置"
        style = st.selectbox("出行风格", styles, index=styles.index(current_style))
        budget = st.number_input("常用人均预算", min_value=0, max_value=3000, step=20, value=int(profile.avg_budget or 200))

        if st.button("保存偏好", use_container_width=True):
            profile.travel_style = None if style == "未设置" else style
            profile.avg_budget = float(budget) if budget else None
            profile_manager.save_profile(profile)
            st.success("已保存，本次和后续推荐都会参考。")

        cols = st.columns(2)
        cols[0].metric("去过地点", len(profile.visited_poi_ids))
        cols[1].metric("历史路线", len(profile.history_routes))
        if profile.preferred_categories:
            st.caption("偏好类型：" + "、".join(profile.preferred_categories[:4]))
