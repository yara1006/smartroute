from __future__ import annotations

from typing import Optional

import streamlit as st

from core.models import Route


def render_route_map(route: Optional[Route], height: int = 380) -> None:
    try:
        import folium
        from streamlit_folium import st_folium
    except ModuleNotFoundError:
        st.info("地图组件依赖尚未安装。运行 `pip install folium streamlit-folium` 后会显示交互地图。")
        return

    center_lat, center_lon = 31.2304, 121.4737
    zoom = 12
    if route and route.stops:
        center_lat = route.stops[0].poi.latitude
        center_lon = route.stops[0].poi.longitude
        zoom = 14

    m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom, tiles="CartoDB positron")

    if route and route.stops:
        coords = []
        colors = {
            "餐饮": "#e64a35",
            "景点": "#2563eb",
            "购物": "#7c3aed",
            "咖啡/茶饮": "#b7791f",
            "娱乐": "#0f766e",
            "住宿": "#64748b",
        }
        for stop in route.stops:
            poi = stop.poi
            coords.append([poi.latitude, poi.longitude])
            color = colors.get(poi.category.value, "#2563eb")
            popup_html = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; width: 220px;">
              <b>#{stop.order} {poi.name}</b><br/>
              <span style="color:#64748b">{poi.category.value} · {poi.district}</span><br/>
              评分 {poi.rating} · 人均 ¥{poi.price_per_person:.0f}<br/>
              {stop.arrival_time}-{stop.departure_time} · 等待 {stop.wait_minutes} 分钟<br/>
              <span style="color:#475569">{stop.tips[:70]}</span>
            </div>
            """
            folium.Marker(
                [poi.latitude, poi.longitude],
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=f"#{stop.order} {poi.name}",
                icon=folium.DivIcon(
                    html=f"""
                    <div style="
                      width:30px;height:30px;border-radius:50%;background:{color};
                      color:white;display:flex;align-items:center;justify-content:center;
                      font-weight:700;border:2px solid white;box-shadow:0 2px 8px rgba(15,23,42,.28);
                    ">{stop.order}</div>
                    """,
                    icon_size=(30, 30),
                    icon_anchor=(15, 15),
                ),
            ).add_to(m)

        if len(coords) > 1:
            folium.PolyLine(coords, color="#2563eb", weight=3, opacity=0.72, dash_array="8 5").add_to(m)
            m.fit_bounds(coords, padding=(32, 32))

    st_folium(m, height=height, use_container_width=True, returned_objects=[])
