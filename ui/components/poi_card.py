from __future__ import annotations

import html

import streamlit as st

from core.models import RouteStop


def render_poi_card(stop: RouteStop) -> None:
    poi = stop.poi
    stars = "★" * max(1, round(poi.rating))
    transit = ""
    if stop.transit_to_next:
        transit = f'<div class="poi-transit">下一站：{html.escape(stop.transit_to_next)}</div>'

    st.markdown(
        f"""
<div class="poi-card">
  <div class="poi-header">
    <div class="poi-title">
      <span class="poi-order">{stop.order}</span>
      <span>{html.escape(poi.name)}</span>
      <span class="poi-category">{poi.category.value}</span>
    </div>
    <div class="poi-time">{stop.arrival_time} - {stop.departure_time}</div>
  </div>
  <div class="poi-meta">
    <span>{stars} {poi.rating}</span>
    <span>人均 ¥{poi.price_per_person:.0f}</span>
    <span>等待 {stop.wait_minutes} 分钟</span>
    <span>停留 {stop.duration_minutes} 分钟</span>
  </div>
  <div class="poi-summary">{html.escape(poi.ugc_summary)}</div>
  <div class="poi-tip">{html.escape(stop.tips)}</div>
  {transit}
</div>
        """,
        unsafe_allow_html=True,
    )
