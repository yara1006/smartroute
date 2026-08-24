import AMapLoader from "@amap/amap-jsapi-loader";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { AMAP_KEY, AMAP_SECURITY_JS_CODE, DEFAULT_MAP_CENTER } from "../constants.js";
import { money } from "../api.js";

export function RouteMapFallback({ route, notice }) {
  const stops = route?.stops || [];
  const bounds = useMemo(() => {
    const lats = stops.map((stop) => stop.poi.latitude);
    const lngs = stops.map((stop) => stop.poi.longitude);
    return {
      minLat: Math.min(...lats, 31.12),
      maxLat: Math.max(...lats, 31.36),
      minLng: Math.min(...lngs, 121.35),
      maxLng: Math.max(...lngs, 121.62),
    };
  }, [stops]);

  function position(poi) {
    const latRange = bounds.maxLat - bounds.minLat || 0.01;
    const lngRange = bounds.maxLng - bounds.minLng || 0.01;
    return {
      x: 14 + ((poi.longitude - bounds.minLng) / lngRange) * 72,
      y: 20 + (1 - (poi.latitude - bounds.minLat) / latRange) * 58,
    };
  }

  const points = stops.map((stop) => position(stop.poi));

  return (
    <div className="map-panel fallback-map-panel">
      <div className="map-grid" />
      <svg viewBox="0 0 100 100" className="route-svg" aria-label="路线地图">
        <path d="M5 78 C24 62, 38 64, 51 49 S75 28, 95 36" className="road" />
        <path d="M9 28 C25 31, 34 21, 49 28 S71 48, 92 42" className="road alt" />
        {points.length > 1 && (
          <polyline points={points.map((point) => `${point.x},${point.y}`).join(" ")} className="route-line" />
        )}
      </svg>
      {stops.length === 0 && <div className="empty-map">输入需求后生成路线地图</div>}
      {stops.map((stop) => {
        const point = position(stop.poi);
        return (
          <button
            className="map-marker"
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
            key={stop.poi.id}
            title={stop.poi.name}
          >
            {stop.order}
          </button>
        );
      })}
      {notice && <div className="map-fallback-note">{notice}</div>}
    </div>
  );
}

export default function RouteMap({ route }) {
  const stops = route?.stops || [];
  const mapContainerRef = useRef(null);
  const amapRef = useRef(null);
  const mapRef = useRef(null);
  const overlaysRef = useRef([]);
  const [mapError, setMapError] = useState("");
  const [mapReady, setMapReady] = useState(false);
  const stopsKey = useMemo(
    () => [
      stops.map((stop) => `${stop.poi.id}:${stop.poi.longitude}:${stop.poi.latitude}`).join("|"),
      (route?.map_polyline || []).map((point) => point.join(",")).join(";"),
    ].join("::"),
    [stops, route?.map_polyline],
  );

  useEffect(() => {
    if (!AMAP_KEY || !mapContainerRef.current) {
      return undefined;
    }

    let canceled = false;
    setMapError("");

    if (AMAP_SECURITY_JS_CODE) {
      window._AMapSecurityConfig = { securityJsCode: AMAP_SECURITY_JS_CODE };
    }

    AMapLoader.load({
      key: AMAP_KEY,
      version: "2.0",
      plugins: [],
    })
      .then((AMap) => {
        if (canceled || !mapContainerRef.current) return;
        amapRef.current = AMap;

        if (!mapRef.current) {
          mapRef.current = new AMap.Map(mapContainerRef.current, {
            center: DEFAULT_MAP_CENTER,
            zoom: 12,
            viewMode: "2D",
            resizeEnable: true,
          });
        }

        const map = mapRef.current;
        if (overlaysRef.current.length) {
          map.remove(overlaysRef.current);
          overlaysRef.current = [];
        }

        if (!stops.length) {
          map.setZoomAndCenter(12, DEFAULT_MAP_CENTER);
          setMapReady(true);
          return;
        }

        const markerPath = stops.map((stop) => [stop.poi.longitude, stop.poi.latitude]);
        const routePath = route?.map_polyline?.length > 1 ? route.map_polyline : markerPath;
        const infoWindow = new AMap.InfoWindow({
          isCustom: true,
          offset: new AMap.Pixel(0, -42),
          closeWhenClickMap: true,
        });
        const markers = stops.map((stop) => {
          const marker = new AMap.Marker({
            position: [stop.poi.longitude, stop.poi.latitude],
            anchor: "bottom-center",
            title: stop.poi.name,
            content: `<button class="amap-route-marker" aria-label="第${stop.order}站 ${stop.poi.name}"><span>${stop.order}</span></button>`,
          });
          marker.on("click", () => {
            infoWindow.setContent(`
              <div class="amap-info-card">
                <strong>${stop.poi.name}</strong>
                <span>${stop.arrival_time} - ${stop.departure_time}</span>
                <p>${stop.poi.category} · 评分 ${stop.poi.rating} · 人均 ${money(stop.poi.price_per_person)}</p>
                <p>等位 ${stop.wait_minutes}m · ${stop.poi.business_hours.open}-${stop.poi.business_hours.close}</p>
              </div>
            `);
            infoWindow.open(map, marker.getPosition());
          });
          return marker;
        });
        const overlays = [...markers];

        if (routePath.length > 1) {
          overlays.push(
            new AMap.Polyline({
              path: routePath,
              strokeColor: "#111111",
              strokeOpacity: 0.82,
              strokeWeight: 5,
              strokeStyle: "solid",
              lineJoin: "round",
              lineCap: "round",
              zIndex: 50,
            }),
          );
        }

        map.add(overlays);
        overlaysRef.current = overlays;
        if (overlays.length > 1) {
          map.setFitView(overlays, false, [26, 26, 26, 26]);
        } else {
          map.setZoomAndCenter(14, markerPath[0]);
        }
        setMapReady(true);
      })
      .catch(() => {
        setMapReady(false);
        setMapError("高德地图加载失败，已使用本地路线示意图");
      });

    return () => {
      canceled = true;
    };
  }, [stopsKey]);

  useEffect(() => {
    return () => {
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
  }, []);

  if (!AMAP_KEY) {
    return <RouteMapFallback route={route} notice="未配置高德地图 Key，已使用本地路线示意图" />;
  }

  if (mapError) {
    return <RouteMapFallback route={route} notice={mapError} />;
  }

  return (
    <div className="map-panel amap-map-panel">
      <div ref={mapContainerRef} className="amap-container" />
      {!mapReady && <div className="map-loading-note">正在加载高德地图...</div>}
      {stops.length === 0 && mapReady && <div className="map-loading-note">输入需求后生成路线地图</div>}
      <div className="map-provider-badge">高德地图</div>
    </div>
  );
}
