import AMapLoader from "@amap/amap-jsapi-loader";
import React, { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? "" : "http://127.0.0.1:8000");
const AMAP_KEY = import.meta.env.VITE_AMAP_KEY || "";
const AMAP_SECURITY_JS_CODE = import.meta.env.VITE_AMAP_SECURITY_JS_CODE || "";
const DEFAULT_MAP_CENTER = [113.93646, 22.53332];
const USER_ID = "product-demo-user";
const DEFAULT_QUERY = "我下午要去深圳大学附近玩3个小时，帮我规划一个路线";
const APP_CURRENT_CITY = "深圳";
const PROFILE_MODES = ["低排队务实型", "文艺体验型", "带爸妈轻松型"];
const FAVORITE_POIS = [
  {
    id: "fav-seed-coffee",
    name: "seed by seed 囍得咖啡酒馆",
    category: "咖啡/茶饮",
    address: "深圳市南山区科技园科苑路",
    district: "南山区",
    latitude: 22.54118,
    longitude: 113.94471,
    rating: 4.5,
    review_count: 213,
    price_per_person: 37,
    avg_wait_minutes: 8,
    business_hours: { open: "09:30", close: "22:00" },
    tags: ["咖啡", "安静", "科技园"],
    ugc_summary: "收藏夹中的咖啡休息点，适合路线中段补给。",
    visit_duration_minutes: 45,
    source: "context",
  },
  {
    id: "fav-gaga-jdw",
    name: "gaga（金地威新中心店）",
    category: "餐饮",
    address: "深圳市南山区高新南环路金地威新中心",
    district: "南山区",
    latitude: 22.53461,
    longitude: 113.94016,
    rating: 4.5,
    review_count: 1661,
    price_per_person: 78,
    avg_wait_minutes: 16,
    business_hours: { open: "10:00", close: "22:00" },
    tags: ["轻食", "拍照", "可预订"],
    ugc_summary: "当前收藏的正餐/轻食点，可作为饭前饭后路线锚点。",
    visit_duration_minutes: 65,
    source: "context",
  },
  {
    id: "fav-nanshan-museum",
    name: "南山博物馆",
    category: "景点",
    address: "深圳市南山区南山大道",
    district: "南山区",
    latitude: 22.52983,
    longitude: 113.93042,
    rating: 4.7,
    review_count: 3200,
    price_per_person: 0,
    avg_wait_minutes: 6,
    business_hours: { open: "10:00", close: "18:00" },
    tags: ["展览", "室内", "文化"],
    ugc_summary: "收藏夹中的文化体验点，适合补足餐饮 + 文化路线结构。",
    visit_duration_minutes: 55,
    source: "context",
  },
  {
    id: "fav-vientiane-world",
    name: "深圳万象天地",
    category: "购物",
    address: "深圳市南山区深南大道9668号",
    district: "南山区",
    latitude: 22.53975,
    longitude: 113.95344,
    rating: 4.6,
    review_count: 5200,
    price_per_person: 80,
    avg_wait_minutes: 5,
    business_hours: { open: "10:00", close: "22:30" },
    tags: ["商场", "室内", "雨天可去"],
    ugc_summary: "收藏夹中的室内缓冲站，适合天气不好或少走路需求。",
    visit_duration_minutes: 45,
    source: "context",
  },
];
const DETAIL_POI = FAVORITE_POIS[1];
const IMPORT_PROFILE_TEMPLATE = JSON.stringify({
  display_name: "Xiangyue 脱敏样本",
  recent_searches: ["外滩展览", "咖啡", "下午茶", "拍照出片"],
  favorite_pois: ["seed by seed 囍得咖啡酒馆", "海派光影展馆"],
  browsed_pois: ["安静", "有设计感", "城市地标"],
  favorite_categories: ["咖啡/茶饮", "景点"],
  favorite_districts: ["黄浦区", "徐汇区"],
  frequent_districts: ["黄浦区"],
  budget_preference: 220,
  max_wait_preference: 18,
  walk_preference: "适中",
  coupon_sensitive: false,
}, null, 2);

const JUDGE_PROFILE_QUESTIONS = [
  {
    key: "companion",
    title: "同行人群",
    options: ["朋友", "情侣", "带爸妈", "亲子"],
  },
  {
    key: "budget",
    title: "预算区间",
    options: ["省钱优先", "中等预算", "体验优先"],
  },
  {
    key: "queue",
    title: "排队容忍",
    options: ["尽量不排队", "可等15分钟", "热门也可以"],
  },
  {
    key: "mobility",
    title: "移动方式",
    options: ["少走路", "步行可接受", "公交地铁", "打车优先"],
  },
  {
    key: "content",
    title: "内容偏好",
    options: ["咖啡/茶饮", "展览文化", "本地美食", "娱乐玩乐", "商场室内"],
  },
];

const DEFAULT_JUDGE_ANSWERS = {
  companion: "朋友",
  budget: "中等预算",
  queue: "可等15分钟",
  mobility: "步行可接受",
  content: "咖啡/茶饮",
};

const SCENARIOS = [
  {
    id: "search",
    title: "搜索页",
    subtitle: "未知 POI 发现",
    query: "我下午要去深圳大学附近玩3个小时，帮我规划一个路线",
    context: "搜索词：深圳大学 附近 下午怎么玩；用户还没有明确选店",
    trigger: "搜索结果插入 SmartRoute 卡片",
    routeContext: { source: "search", city_hint: "深圳", anchor_text: "深圳大学" },
  },
  {
    id: "xiaotuan",
    title: "问小团",
    subtitle: "LLM 意图识别",
    query: "我下午要去深圳大学附近玩3个小时",
    context: "通用小团对话；先判断是否应该调起路线插件",
    trigger: "路线意图高/中/低置信分流",
    routeContext: { source: "xiaotuan", city_hint: APP_CURRENT_CITY },
  },
  {
    id: "favorites",
    title: "收藏夹",
    subtitle: "已知多个 POI",
    query: "把我收藏的深圳大学附近咖啡、gaga、南山博物馆安排成3小时路线，预算200，不想排队",
    context: "收藏了深圳大学/科技园附近咖啡、轻食、博物馆、商场等多个地点",
    trigger: "收藏夹顶部一键排路线",
    routeContext: { source: "favorites", city_hint: "深圳", anchor_text: "深圳大学" },
  },
  {
    id: "detail",
    title: "POI 详情页",
    subtitle: "从单点延展",
    query: "从gaga金地威新中心店出发，安排晚饭前后顺路可逛的路线，少走路",
    context: "用户正在浏览某个商户详情页",
    trigger: "从这里出发 / 加入路线",
    routeContext: {
      source: "detail",
      city_hint: "深圳",
      anchor_text: "gaga金地威新中心店",
      anchor_location: { latitude: DETAIL_POI.latitude, longitude: DETAIL_POI.longitude },
      selected_pois: [DETAIL_POI],
    },
  },
];

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

async function postJson(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

function money(value) {
  if (value === null || value === undefined) return "不限";
  return `¥${Math.round(value)}`;
}

function minutes(value) {
  if (!value) return "0m";
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  return hours ? `${hours}h${mins}m` : `${mins}m`;
}

function fieldList(constraints) {
  if (!constraints) return [];
  return [
    ["时间", `${constraints.start_time} / ${constraints.total_time_hours}h`],
    ["预算", money(constraints.budget_per_person)],
    ["排队", `≤${constraints.max_wait_minutes}m`],
    ["人数", `${constraints.party_size}人`],
    ["步行", `≤${constraints.max_walk_minutes}m`],
    ["区域", constraints.preferred_districts?.join("、") || `全${constraints.city || "城市"}`],
  ];
}

function scoreClass(score) {
  if (score >= 85) return "good";
  if (score >= 70) return "warn";
  return "risk";
}

function formatDelta(value, suffix = "") {
  if (value === 0) return `无变化${suffix}`;
  return `${value > 0 ? "+" : ""}${value}${suffix}`;
}

function metricDelta(value, unit = "m") {
  if (value === 0 || value === undefined || value === null) return "无变化";
  if (unit === "¥") return `${value > 0 ? "+" : "-"}¥${Math.abs(Math.round(value))}`;
  return `${value > 0 ? "+" : ""}${value}${unit}`;
}

function deltaTone(value, lowerIsBetter = true) {
  if (!value) return "flat";
  return (lowerIsBetter ? value < 0 : value > 0) ? "good" : "bad";
}

function statusText(status) {
  return {
    applied: "已应用",
    partial: "部分应用",
    not_applied: "未应用",
  }[status] || "已调整";
}

function TopBar({ health }) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">SR</div>
        <div>
          <strong>SmartRoute AI</strong>
          <span>美团原生路线规划 Agent</span>
        </div>
      </div>
      <div className="backend-pill">
        <span className={health?.status === "ok" ? "dot live" : "dot"} />
        <span>真实后端数据</span>
        <b>{health?.poi_count ? `${health.poi_count} POI · 高德${health?.amap_web_service === "configured" ? "已接" : "兜底"} · DeepSeek${health?.deepseek === "configured" ? "已接" : "兜底"}` : "连接中"}</b>
      </div>
    </header>
  );
}

function RouteMapFallback({ route, notice }) {
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

function RouteMap({ route }) {
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

function MetricStrip({ routeView }) {
  if (!routeView) return null;
  const route = routeView.route;
  const insight = routeView.insight;
  return (
    <div className="metrics-strip">
      <div>
        <span>可信度</span>
        <strong className={scoreClass(insight.confidence_score)}>{insight.confidence_score}</strong>
      </div>
      <div>
        <span>总时长</span>
        <strong>{minutes(route.total_time_minutes)}</strong>
      </div>
      <div>
        <span>人均</span>
        <strong>{money(route.total_cost_per_person)}</strong>
      </div>
      <div>
        <span>等位</span>
        <strong>{route.total_wait_minutes}m</strong>
      </div>
    </div>
  );
}

function QueryComposer({ query, setQuery, examples, onSubmit, loading }) {
  return (
    <section className="composer">
      <div className="composer-title">
        <span>现在出发</span>
        <b>AI 本地路线智能规划</b>
      </div>
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="说说时间、预算、区域、同行人和偏好"
      />
      <div className="composer-actions">
        <div className="mini-chips">
          <span>低排队</span>
          <span>预算可控</span>
          <span>可替换</span>
        </div>
        <button onClick={() => onSubmit(query)} disabled={loading}>
          {loading ? "规划中" : "生成路线"}
        </button>
      </div>
      <div className="example-list">
        {examples.map((example) => (
          <button key={example} onClick={() => onSubmit(example)} disabled={loading}>
            {example}
          </button>
        ))}
      </div>
    </section>
  );
}

function ConstraintPanel({ constraints }) {
  return (
    <section className="panel compact">
      <div className="section-head">
        <h2>约束确认</h2>
        <span>来自后端解析</span>
      </div>
      <div className="constraint-grid">
        {fieldList(constraints).map(([label, value]) => (
          <div className="constraint" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="category-row">
        {(constraints?.preferred_categories || []).map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </section>
  );
}

function RouteSelector({ routes, selectedRouteIndex, setSelectedRouteIndex }) {
  if (!routes?.length) return null;
  return (
    <div className="route-selector">
      {routes.map((routeView, index) => (
        <button
          className={selectedRouteIndex === index ? "active" : ""}
          onClick={() => setSelectedRouteIndex(index)}
          key={routeView.route.id}
        >
          <strong>方案 {index + 1}</strong>
          <span>{routeView.route.title}</span>
        </button>
      ))}
    </div>
  );
}

function Timeline({ routeView, onReplace }) {
  if (!routeView) {
    return <div className="empty-state">后端返回路线后，这里会展示逐站行程。</div>;
  }

  return (
    <div className="timeline">
      {routeView.route.stops.map((stop) => (
        <article className="stop-card" key={`${stop.order}-${stop.poi.id}`}>
          <div className="stop-node">{stop.order}</div>
          <div className="stop-main">
            <div className="stop-top">
              <div>
                <span>{stop.arrival_time} - {stop.departure_time}</span>
                <h3>{stop.poi.name}</h3>
              </div>
              <button onClick={() => onReplace(stop)}>替换</button>
            </div>
            <p>{stop.poi.ugc_summary}</p>
            <div className="stop-meta">
              <span>{stop.poi.category}</span>
              <span>{stop.poi.source === "amap" ? "高德POI" : stop.poi.source === "context" ? "入口已选" : "本地兜底"}</span>
              <span>评分 {stop.poi.rating}</span>
              <span>等位 {stop.wait_minutes}m</span>
              <span>人均 {money(stop.poi.price_per_person)}</span>
              <span>{stop.poi.business_hours.open}-{stop.poi.business_hours.close}</span>
            </div>
            {stop.transit_to_next && <div className="transit-note">{stop.transit_to_next}</div>}
          </div>
        </article>
      ))}
    </div>
  );
}

function ScenarioSelector({ scenarios, activeScenarioId, onSelect, health }) {
  return (
    <aside className="scenario-rail">
      <div className="rail-card intro-card">
        <span>SmartRoute P0</span>
        <h1>美团 App 场景模拟器</h1>
        <p>评委先看到用户从哪里触发，再看到 SmartRoute 如何作为插件接管路线规划。</p>
      </div>
      <div className="scenario-list">
        {scenarios.map((scenario) => (
          <button
            key={scenario.id}
            className={activeScenarioId === scenario.id ? "active" : ""}
            onClick={() => onSelect(scenario)}
          >
            <strong>{scenario.title}</strong>
            <span>{scenario.subtitle}</span>
          </button>
        ))}
      </div>
      <div className="rail-card">
        <span>真实后端</span>
        <h2>{health?.poi_count ? `${health.poi_count} POI` : "连接中"}</h2>
        <p>路线、候选 POI、替换和反馈都来自 FastAPI，不使用静态假路线。</p>
      </div>
    </aside>
  );
}

function SmartRouteEntryCard({ title, text, action, onOpen, loading }) {
  return (
    <article className="plugin-card">
      <div className="plugin-badge">SmartRoute</div>
      <h3>{title}</h3>
      <p>{text}</p>
      <button onClick={onOpen} disabled={loading}>{loading ? "生成中" : action}</button>
    </article>
  );
}

function SearchScene({ scenario, onOpen, loading }) {
  return (
    <div className="meituan-page">
      <div className="mt-header">
        <strong>搜索</strong>
        <span>问小团</span>
      </div>
      <div className="mt-searchbar">深圳大学 附近 下午怎么玩 <b>搜索</b></div>
      <section className="mt-section">
        <h3>历史搜索</h3>
        <div className="mt-chips">
          <span>深圳大学</span><span>咖啡</span><span>展览</span><span>轻食</span>
        </div>
      </section>
      <SmartRouteEntryCard
        title="已找到可串联地点"
        text="根据深圳大学、下午、3 小时，从附近商户和文化/娱乐 POI 中生成不绕路路线。"
        action="智能排路线"
        onOpen={() => onOpen(scenario.query, scenario.routeContext)}
        loading={loading}
      />
      <section className="mt-section">
        <h3>美团热搜</h3>
        {["深大附近咖啡低排队", "南山博物馆展览", "科技园轻食晚餐"].map((item) => (
          <article className="mt-list-item" key={item}><span>{item}</span><small>热度上升</small></article>
        ))}
      </section>
    </div>
  );
}

function XiaotuanScene({ scenario, routeIntent, conversation, onAsk, onOpen, loading }) {
  const [draft, setDraft] = useState("");
  const hasMissingSlots = (routeIntent?.missing_slots?.length || routeIntent?.detected_slots?.missing_slots?.length || 0) > 0;
  const inConversation = conversation.length > 0 || Boolean(routeIntent) || loading;

  useEffect(() => {
    setDraft("");
  }, [scenario.query]);

  function submitDraft() {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onAsk(trimmed);
    setDraft("");
  }

  const heroComposer = (
    <div className="xiaotuan-hero-composer">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="附近有什么好吃的？"
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submitDraft();
        }}
      />
      <button onClick={submitDraft} disabled={loading || !draft.trim()}>
        {loading ? "识别中" : "发送"}
      </button>
    </div>
  );
  const chatComposer = (
    <div className="xiaotuan-chat-composer">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="继续补充地点、时间或活动"
        onKeyDown={(event) => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") submitDraft();
          if (event.key === "Enter" && !event.shiftKey && !event.metaKey && !event.ctrlKey) {
            event.preventDefault();
            submitDraft();
          }
        }}
      />
      <button onClick={submitDraft} disabled={loading || !draft.trim()}>
        {loading ? "识别中" : "发送"}
      </button>
    </div>
  );

  return (
    <div className={`meituan-page xiaotuan-page ${inConversation ? "chatting" : "idle"}`}>
      <div className="mt-header">
        <span>搜索</span>
        <strong>问小团</strong>
      </div>
      {!inConversation && heroComposer}
      {conversation.length > 0 && (
        <section className="xiaotuan-thread">
          {conversation.slice(-6).map((item) => (
            <div key={item.id} className={`xiaotuan-bubble ${item.role}`}>
              <span>{item.role === "user" ? "你" : "小团"}</span>
              <p>{item.text}</p>
            </div>
          ))}
        </section>
      )}
      {!inConversation && (
        <section className="mt-section xiaotuan-suggestions">
          <h3>试试这样问</h3>
          <div className="xiaotuan-prompts">
            {["附近有什么好吃的", "深圳大学附近下午3小时怎么玩", "外滩下午3小时怎么玩"].map((item) => (
              <button key={item} onClick={() => setDraft(item)}>✦ {item}</button>
            ))}
          </div>
        </section>
      )}
      {routeIntent && (
        <section className={`intent-card ${routeIntent.action}`}>
          <span>{routeIntent.source === "llm" ? "DeepSeek 意图识别" : "规则兜底识别"} · {(routeIntent.confidence * 100).toFixed(0)}%</span>
          <h3>
            {routeIntent.action === "open_plugin" && "识别为路线规划需求"}
            {routeIntent.action === "ask_confirm" && "要不要排成路线？"}
            {routeIntent.action === "normal_answer" && "先按普通小团回答"}
          </h3>
          <p>{routeIntent.reason}</p>
          {routeIntent.detected_slots?.missing_slots?.length > 0 && (
            <div className="missing-slots">
              还需要确认：{routeIntent.detected_slots.missing_slots.join("、")}
            </div>
          )}
          {routeIntent.clarification_question && <p className="clarification-question">{routeIntent.clarification_question}</p>}
          {routeIntent.clarification_options?.length > 0 && (
            <div className="clarification-options">
              {routeIntent.clarification_options.map((option) => (
                <button key={option} onClick={() => onAsk(option, "chip")} disabled={loading}>{option}</button>
              ))}
            </div>
          )}
          {routeIntent.action === "ask_confirm" && !hasMissingSlots && (
            <div className="intent-actions">
              <button onClick={() => onOpen(routeIntent.merged_query || routeIntent.planning_query)} disabled={loading}>排路线</button>
              <button>只看推荐</button>
            </div>
          )}
          {routeIntent.action === "normal_answer" && (
            <SmartRouteEntryCard
              title="也可以排成路线"
              text="如果你想把推荐地点串起来，SmartRoute 可以继续接手。"
              action="把这些地点排成路线"
              onOpen={() => onOpen(`${draft}，帮我规划成一条可执行路线`)}
              loading={loading}
            />
          )}
        </section>
      )}
      {inConversation && chatComposer}
    </div>
  );
}

function FavoritesScene({ scenario, onOpen, loading }) {
  const [selectedIds, setSelectedIds] = useState(FAVORITE_POIS.slice(0, 3).map((item) => item.id));
  const selectedPois = FAVORITE_POIS.filter((item) => selectedIds.includes(item.id));
  function toggle(id) {
    setSelectedIds((items) => {
      if (items.includes(id)) return items.filter((item) => item !== id);
      if (items.length >= 5) return items;
      return [...items, id];
    });
  }
  return (
    <div className="meituan-page">
      <div className="mt-header"><strong>收藏</strong><span>管理</span></div>
      <div className="mt-tabs"><b>商户</b><span>团购</span><span>商品/菜品</span><span>内容</span></div>
      <SmartRouteEntryCard
        title={`已选择 ${selectedPois.length} 个收藏地点`}
        text="按距离、营业时间、排队和预算，把收藏夹变成一条可执行路线；所选店铺会被优先保留。"
        action="一键排路线"
        onOpen={() => onOpen(scenario.query, { ...scenario.routeContext, selected_pois: selectedPois })}
        loading={loading || selectedPois.length < 2}
      />
      <section className="mt-section">
        {FAVORITE_POIS.map((poi) => (
          <article className={`favorite-item selectable ${selectedIds.includes(poi.id) ? "checked" : ""}`} key={poi.id}>
            <button className="favorite-check" onClick={() => toggle(poi.id)}>{selectedIds.includes(poi.id) ? "✓" : "+"}</button>
            <div className="poi-thumb" />
            <div>
              <h3>{poi.name}</h3>
              <p>{poi.category} · {poi.district} · ¥{poi.price_per_person}/人</p>
              <span>★ {poi.rating} · {poi.source === "context" ? "可排路线" : "到店"}</span>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function DetailScene({ scenario, onOpen, loading }) {
  return (
    <div className="meituan-page detail-page">
      <div className="detail-hero">
        <button>‹</button>
        <div className="photo-strip"><span /><span /><span /></div>
      </div>
      <section className="detail-card">
        <h2>{DETAIL_POI.name}</h2>
        <div className="rating-row"><b>{DETAIL_POI.rating}</b><span>{DETAIL_POI.review_count}条评价</span><em>¥{DETAIL_POI.price_per_person}/人</em></div>
        <p>营业中 10:00-22:00 · 可预订 · 有宝宝椅</p>
        <p>{DETAIL_POI.address}，靠近深圳大学/科技园</p>
        <SmartRouteEntryCard
          title="从这里继续安排下一站"
          text="以当前商户为起点，补齐饭前/饭后可逛地点，形成完整路线。"
          action="从这里出发"
          onOpen={() => onOpen(scenario.query, scenario.routeContext)}
          loading={loading}
        />
      </section>
      <section className="mt-section">
        <h3>优惠</h3>
        <article className="deal-card"><strong>100 元代金券</strong><span>¥95 · 9.5折</span><button>买券</button></article>
      </section>
    </div>
  );
}

function profilesForSource(profileSources, source) {
  return profileSources?.sources?.find((item) => item.source === source)?.profiles || [];
}

function ProfileImportPanel({ onImport, loading }) {
  const [draft, setDraft] = useState(IMPORT_PROFILE_TEMPLATE);
  const [expanded, setExpanded] = useState(false);

  async function submit() {
    let parsed;
    try {
      parsed = JSON.parse(draft);
    } catch {
      onImport(null, "JSON 格式不正确，请检查逗号和引号。");
      return;
    }
    onImport(parsed);
  }

  return (
    <section className="profile-import-panel">
      <button className="import-toggle" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "收起导入" : "导入脱敏画像"}
      </button>
      {expanded && (
        <>
          <p>只粘贴搜索词、收藏、浏览偏好等脱敏信息；不要粘贴账号、手机号、cookie、订单号。</p>
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
          <button className="import-submit" onClick={submit} disabled={loading}>
            {loading ? "导入中" : "保存并使用"}
          </button>
        </>
      )}
    </section>
  );
}

function JudgePreferenceModal({ open, scenario, pendingQuery, onSubmit, onSkip, loading }) {
  const [answers, setAnswers] = useState(DEFAULT_JUDGE_ANSWERS);

  useEffect(() => {
    if (open) setAnswers(DEFAULT_JUDGE_ANSWERS);
  }, [open]);

  if (!open) return null;
  return (
    <div className="preference-modal-backdrop">
      <section className="preference-modal">
        <div className="preference-modal-head">
          <span>SmartRoute 个性化路线偏好</span>
          <h2>先用 10 秒生成你的本次画像</h2>
          <p>{scenario.title}入口 · {pendingQuery || scenario.query}</p>
        </div>
        <div className="preference-question-grid">
          {JUDGE_PROFILE_QUESTIONS.map((question) => (
            <div key={question.key} className="preference-question">
              <strong>{question.title}</strong>
              <div>
                {question.options.map((option) => (
                  <button
                    key={option}
                    className={answers[question.key] === option ? "active" : ""}
                    onClick={() => setAnswers((current) => ({ ...current, [question.key]: option }))}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="preference-modal-actions">
          <button className="secondary" onClick={onSkip} disabled={loading}>跳过，直接规划</button>
          <button onClick={() => onSubmit(answers)} disabled={loading}>
            {loading ? "生成中" : "使用本次画像规划"}
          </button>
        </div>
        <p className="privacy-note">只生成本次演示画像，不读取真实美团账号、手机号、cookie、订单或精确住址。</p>
      </section>
    </div>
  );
}

function ProfileModeControl({
  profileMode,
  profileSource,
  profileSources,
  importedProfileId,
  onPresetChange,
  onSourceChange,
  onImportedProfileChange,
  onImportProfile,
  loading,
}) {
  const importedProfiles = profilesForSource(profileSources, "manual_import");
  return (
    <div className="profile-control">
      <div className="profile-source-tabs">
        <button className={profileSource === "preset" ? "active" : ""} onClick={() => onSourceChange("preset")}>
          模拟画像
        </button>
        <button className={profileSource === "manual_import" ? "active" : ""} onClick={() => onSourceChange("manual_import")}>
          评委/脱敏画像
        </button>
      </div>
      {profileSource === "preset" && (
        <div className="profile-switch">
          {PROFILE_MODES.map((mode) => (
            <button key={mode} className={profileMode === mode ? "active" : ""} onClick={() => onPresetChange(mode)}>
              {mode}
            </button>
          ))}
        </div>
      )}
      {profileSource === "manual_import" && (
        <>
          <div className="manual-profile-list">
            {importedProfiles.map((profile) => (
              <button
                key={profile.profile_id}
                className={importedProfileId === profile.profile_id ? "active" : ""}
                onClick={() => onImportedProfileChange(profile.profile_id)}
              >
                <strong>{profile.display_name}</strong>
                <span>{profile.signal_count} 信号</span>
              </button>
            ))}
            {!importedProfiles.length && <div className="empty-state">还没有脱敏画像，先导入一份样本。</div>}
          </div>
          <ProfileImportPanel onImport={onImportProfile} loading={loading} />
        </>
      )}
    </div>
  );
}

function ProfileSummary({ context, sourceDescription, signalCount }) {
  if (!context) return null;
  return (
    <section className="profile-summary">
      <span>美团画像</span>
      <p>{context.summary}</p>
      {sourceDescription && <strong>{sourceDescription}</strong>}
      <div>
        {(context.search_preferences || []).slice(0, 4).map((item) => (
          <em key={item}>{item}</em>
        ))}
        {signalCount > 0 && <em>{signalCount} 个信号</em>}
      </div>
    </section>
  );
}

function ProfileInfluencePanel({ influences, compact = false }) {
  if (!influences?.length) return null;
  return (
    <section className={compact ? "profile-influence compact" : "profile-influence"}>
      <span>为什么这样推荐</span>
      <div className="influence-chain-label">画像信号 → 召回加权 → 路线变化</div>
      {influences.slice(0, compact ? 3 : 5).map((item) => (
        <article key={`${item.signal}-${item.source}`}>
          <div>
            <strong>{item.signal}</strong>
            <em>{item.weight}权重</em>
          </div>
          <p>{item.source}</p>
          <small>{item.effect}</small>
          {item.matched_pois?.length > 0 && (
            <div className="influence-pois">
              {item.matched_pois.slice(0, 3).map((name) => <b key={name}>{name}</b>)}
            </div>
          )}
        </article>
      ))}
    </section>
  );
}

function P1Status({ plan }) {
  if (!plan) return null;
  return (
    <div className="p1-status">
      <div>
        <span>规划耗时</span>
        <strong>{plan.planning_time_ms ?? 0}ms</strong>
      </div>
      <div>
        <span>完整性</span>
        <strong>{plan.route_completeness?.is_complete ? "已满足" : "需优化"}</strong>
      </div>
      <div>
        <span>冲突</span>
        <strong>{plan.constraint_conflicts?.length || 0}</strong>
      </div>
    </div>
  );
}

function FollowUpCard({ followUp, fallbackQuestion, onPick, loading }) {
  const question = followUp?.question || fallbackQuestion;
  if (!question) return null;
  const options = followUp?.options?.length
    ? followUp.options
    : ["少排队", "便宜点", "文艺一点", "少走路"].map((label) => ({ label, instruction: label }));
  return (
    <section className="follow-card">
      <span>继续优化</span>
      <p>{question}</p>
      <div>
        {options.map((option) => (
          <button key={`${option.label}-${option.instruction}`} onClick={() => onPick(option.instruction)} disabled={loading}>
            <strong>{option.label}</strong>
            {option.expected_effect && <small>{option.expected_effect}</small>}
          </button>
        ))}
      </div>
      {followUp?.reason && <em>{followUp.reason}</em>}
    </section>
  );
}

function AdjustmentResultCard({ adjustment }) {
  if (!adjustment) return null;
  const deltas = adjustment.metric_deltas || {};
  return (
    <section className={`adjust-result ${adjustment.adjustment_status || ""}`}>
      <div className="adjust-result-head">
        <span>{statusText(adjustment.adjustment_status)}</span>
        <strong>{adjustment.adjustment_summary}</strong>
      </div>
      <div className="delta-grid">
        <div className={deltaTone(deltas.total_wait_minutes)}>
          <span>等位</span>
          <strong>{metricDelta(deltas.total_wait_minutes)}</strong>
        </div>
        <div className={deltaTone(deltas.total_cost_per_person)}>
          <span>人均</span>
          <strong>{metricDelta(deltas.total_cost_per_person, "¥")}</strong>
        </div>
        <div className={deltaTone(deltas.total_transit_minutes)}>
          <span>移动</span>
          <strong>{metricDelta(deltas.total_transit_minutes)}</strong>
        </div>
      </div>
      {adjustment.changed_stops?.length > 0 && (
        <div className="changed-stops">
          {adjustment.changed_stops.slice(0, 3).map((change) => (
            <p key={`${change.order}-${change.action}`}>
              第{change.order}站：{change.before_poi || "新增"} → {change.after_poi || "移除"}
            </p>
          ))}
        </div>
      )}
      {adjustment.suggested_relaxations?.length > 0 && (
        <div className="relaxation-list">
          {adjustment.suggested_relaxations.map((item) => <p key={item}>{item}</p>)}
        </div>
      )}
    </section>
  );
}

function RouteLoadingState({ label }) {
  if (!label) return null;
  return <div className="route-loading-state">{label}...</div>;
}

function AdjustComposer({ onSubmit, loading }) {
  const [draft, setDraft] = useState("");
  const quickAdjustments = ["少走路", "不要排队", "便宜点", "不要这么多咖啡", "不要这么多餐厅", "加展览", "换个重点"];
  function submit(value = draft) {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setDraft("");
  }
  return (
    <section className="adjust-composer">
      <div className="adjust-quick-row">
        {quickAdjustments.map((item) => (
          <button type="button" key={item} onClick={() => submit(item)} disabled={loading}>{item}</button>
        ))}
      </div>
      <div className="adjust-input-row">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="继续说：少走路一点 / 换便宜点 / 不要排队"
          onKeyDown={(event) => {
            if (event.key === "Enter") submit();
          }}
        />
        <button type="button" onClick={() => submit()} disabled={loading || !draft.trim()}>{loading ? "调整中" : "调整"}</button>
      </div>
    </section>
  );
}

function AdjustmentHistory({ history }) {
  if (!history.length) return null;
  return (
    <section className="adjust-history">
      <span>调整历史</span>
      {history.slice(-3).map((item, index) => (
        <p key={`${item}-${index}`}>{item}</p>
      ))}
    </section>
  );
}

function SmartRouteRoutePage({
  scenario,
  plan,
  routeView,
  profileMode,
  profileSource,
  profileSources,
  importedProfileId,
  onPresetProfileChange,
  onProfileSourceChange,
  onImportedProfileChange,
  onImportProfile,
  onReplace,
  onFeedback,
  onAdjust,
  adjustmentHistory,
  latestAdjustment,
  loading,
  loadingLabel,
}) {
  const constraints = plan?.intent?.constraints;
  return (
    <section className="phone">
      <div className="phone-status">
        <span>18:57</span>
        <span>5G</span>
      </div>
      <div className="phone-appbar">
        <strong>SmartRoute</strong>
        <span>{scenario.title}调起</span>
      </div>
      <div className="phone-content">
        <ProfileModeControl
          profileMode={profileMode}
          profileSource={profileSource}
          profileSources={profileSources}
          importedProfileId={importedProfileId}
          onPresetChange={onPresetProfileChange}
          onSourceChange={onProfileSourceChange}
          onImportedProfileChange={onImportedProfileChange}
          onImportProfile={onImportProfile}
          loading={loading}
        />
        <ProfileSummary
          context={plan?.meituan_user_context}
          sourceDescription={plan?.profile_source_description}
          signalCount={plan?.profile_signal_count}
        />
        <ProfileInfluencePanel influences={plan?.profile_influence} compact />
        <P1Status plan={plan} />
        <RouteLoadingState label={loadingLabel} />
        {constraints && (
          <div className="phone-chips">
            {fieldList(constraints).slice(0, 5).map(([label, value]) => (
              <span key={label}>{label} {value}</span>
            ))}
          </div>
        )}
        {routeView && (
          <>
            <MetricStrip routeView={routeView} />
            <RouteMap route={routeView.route} />
            <div className="phone-route-head">
              <div>
                <span>推荐路线</span>
                <h2>{routeView.route.title}</h2>
              </div>
              <strong>{routeView.insight.wait_status}</strong>
            </div>
            <Timeline routeView={routeView} onReplace={onReplace} />
            <div className="feedback-row">
              <button onClick={() => onFeedback(1)}>喜欢</button>
              <button onClick={() => onFeedback(-1)}>不合适</button>
            </div>
            <AdjustmentResultCard adjustment={latestAdjustment} />
            <FollowUpCard followUp={plan?.follow_up} fallbackQuestion={plan?.follow_up_question} onPick={onAdjust} loading={loading} />
            <AdjustComposer onSubmit={onAdjust} loading={loading} />
            <AdjustmentHistory history={adjustmentHistory} />
          </>
        )}
        {!routeView && (
          <div className="empty-state">
            {plan?.constraint_conflicts?.length
              ? `当前没有完整路线：${plan.constraint_conflicts.join("；")}`
              : "正在等待 SmartRoute 生成路线..."}
          </div>
        )}
      </div>
    </section>
  );
}

function PhoneExperience({
  scenario,
  mode,
  plan,
  routeView,
  loading,
  routeIntent,
  xiaotuanConversation,
  onOpenRoute,
  onAskXiaotuan,
  profileMode,
  profileSource,
  profileSources,
  importedProfileId,
  onPresetProfileChange,
  onProfileSourceChange,
  onImportedProfileChange,
  onImportProfile,
  onReplace,
  onFeedback,
  onAdjust,
  adjustmentHistory,
  latestAdjustment,
  loadingLabel,
}) {
  if (mode === "route") {
    return (
      <SmartRouteRoutePage
        scenario={scenario}
        plan={plan}
        routeView={routeView}
        profileMode={profileMode}
        profileSource={profileSource}
        profileSources={profileSources}
        importedProfileId={importedProfileId}
        onPresetProfileChange={onPresetProfileChange}
        onProfileSourceChange={onProfileSourceChange}
        onImportedProfileChange={onImportedProfileChange}
        onImportProfile={onImportProfile}
        onReplace={onReplace}
        onFeedback={onFeedback}
        onAdjust={onAdjust}
        adjustmentHistory={adjustmentHistory}
        latestAdjustment={latestAdjustment}
        loading={loading}
        loadingLabel={loadingLabel}
      />
    );
  }

  return (
    <section className="phone">
      <div className="phone-status">
        <span>18:57</span>
        <span>5G</span>
      </div>
      <div className="phone-content meituan-shell">
        {scenario.id === "search" && <SearchScene scenario={scenario} onOpen={onOpenRoute} loading={loading} />}
        {scenario.id === "xiaotuan" && (
          <XiaotuanScene
            scenario={scenario}
            routeIntent={routeIntent}
            conversation={xiaotuanConversation}
            onAsk={onAskXiaotuan}
            onOpen={onOpenRoute}
            loading={loading}
          />
        )}
        {scenario.id === "favorites" && <FavoritesScene scenario={scenario} onOpen={onOpenRoute} loading={loading} />}
        {scenario.id === "detail" && <DetailScene scenario={scenario} onOpen={onOpenRoute} loading={loading} />}
      </div>
    </section>
  );
}

function CandidatePanel({ candidates }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>候选 POI</h2>
        <span>RAG Top {candidates?.length || 0}</span>
      </div>
      <div className="candidate-list">
        {(candidates || []).slice(0, 8).map((candidate) => (
          <article key={candidate.poi.id}>
            <div>
              <h3>{candidate.poi.name}</h3>
              <p>{candidate.reason}</p>
            </div>
            <strong>{candidate.score.toFixed(2)}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}

function TracePanel({ trace }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>生成过程</h2>
        <span>可答辩展示</span>
      </div>
      <ol className="trace-list">
        {(trace || []).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ol>
    </section>
  );
}

function ToolTracePanel({ title = "ToolUse Trace", steps }) {
  if (!steps?.length) return null;
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{title}</h2>
        <span>ReAct / ToolUse</span>
      </div>
      <div className="tool-trace">
        {steps.map((step, index) => (
          <article key={`${step.step}-${step.tool}-${index}`} className={step.status}>
            <div>
              <span>{step.step}</span>
              <strong>{step.tool}</strong>
              <em>{step.status}</em>
            </div>
            <p>{step.input}</p>
            <small>{step.output}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

function InsightPanel({ routeView }) {
  if (!routeView) return null;
  const insight = routeView.insight;
  return (
    <section className="panel">
      <div className="section-head">
        <h2>路线解释</h2>
        <span>不是黑盒推荐</span>
      </div>
      <div className="confidence-card">
        <div className="confidence-ring">
          <strong>{insight.confidence_score}</strong>
          <span>score</span>
        </div>
        <p>{insight.explanation}</p>
      </div>
      <div className="hit-list">
        {insight.constraint_hits.map((hit) => (
          <span key={hit}>{hit}</span>
        ))}
      </div>
      <div className="fit-grid">
        <div>
          <span>排队</span>
          <strong>{insight.wait_status}</strong>
        </div>
        <div>
          <span>步行</span>
          <strong>{insight.walk_intensity}</strong>
        </div>
        <div>
          <span>人群</span>
          <strong>{insight.crowd_fit}</strong>
        </div>
        <div>
          <span>天气</span>
          <strong>{insight.weather_fit}</strong>
        </div>
      </div>
      {insight.risks.length > 0 && (
        <div className="risk-box">
          {insight.risks.map((risk) => (
            <p key={risk}>{risk}</p>
          ))}
        </div>
      )}
    </section>
  );
}

function CompareTable({ routes, selectedRouteIndex, setSelectedRouteIndex }) {
  if (!routes?.length) return null;
  return (
    <section className="panel wide">
      <div className="section-head">
        <h2>多方案对比</h2>
        <span>时间 / 预算 / 等待 / 步行</span>
      </div>
      <div className="compare-table">
        {routes.map((routeView, index) => (
          <button
            className={selectedRouteIndex === index ? "active" : ""}
            key={routeView.route.id}
            onClick={() => setSelectedRouteIndex(index)}
          >
            <span>方案 {index + 1}</span>
            <strong>{routeView.route.title}</strong>
            <em>{routeView.insight.confidence_score} 分</em>
            <small>{minutes(routeView.route.total_time_minutes)} · {money(routeView.route.total_cost_per_person)} · 等 {routeView.route.total_wait_minutes}m</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function ReplacePanel({ replacement, onClose, onApply }) {
  if (!replacement) return null;
  return (
    <aside className="replace-panel">
      <div className="replace-head">
        <div>
          <span>替换站点</span>
          <h2>同类 POI 实时替换</h2>
        </div>
        <button onClick={onClose}>×</button>
      </div>
      {replacement.loading && <div className="empty-state">正在从后端搜索替换项...</div>}
      {!replacement.loading && replacement.options.length === 0 && <div className="empty-state">当前约束下没有更稳的同类替换项。</div>}
      <div className="replacement-list">
        {replacement.options.map((option) => (
          <article key={option.poi.id}>
            <div>
              <h3>{option.poi.name}</h3>
              <p>{option.impact_summary}</p>
              <span>评分 {option.poi.rating} · {option.poi.district} · {option.poi.business_hours.open}-{option.poi.business_hours.close}</span>
            </div>
            <button onClick={() => onApply(option)}>
              应用
              <small>{formatDelta(option.cost_delta, "元")} / {formatDelta(option.wait_delta, "m")}</small>
            </button>
          </article>
        ))}
      </div>
    </aside>
  );
}

function AgentPanel({
  scenario,
  routeIntent,
  plan,
  routeView,
  routes,
  selectedRouteIndex,
  setSelectedRouteIndex,
  adjustmentHistory,
  latestAdjustment,
}) {
  return (
    <aside className="agent-panel">
      <section className="panel">
        <div className="section-head">
          <h2>Agent 解释面板</h2>
          <span>{scenario.title}</span>
        </div>
        <div className="agent-context">
          <div>
            <span>入口来源</span>
            <strong>{scenario.title} · {scenario.subtitle}</strong>
          </div>
          <div>
            <span>用户上下文</span>
            <p>{scenario.context}</p>
          </div>
          <div>
            <span>触发方式</span>
            <p>{scenario.trigger}</p>
          </div>
          {plan?.intent?.extracted_preferences?.anchor_text && (
            <div>
              <span>地图锚点</span>
              <p>{plan.intent.extracted_preferences.anchor_text} · {plan.intent.city}</p>
            </div>
          )}
        </div>
      </section>

      {scenario.id === "xiaotuan" && (
        <section className="panel">
          <div className="section-head">
            <h2>小团意图识别</h2>
            <span>{routeIntent ? routeIntent.source : "等待输入"}</span>
          </div>
          {routeIntent ? (
            <div className="intent-summary">
              <strong>{routeIntent.action}</strong>
              <span>{(routeIntent.confidence * 100).toFixed(0)}%</span>
              <p>{routeIntent.reason}</p>
              {routeIntent.fusion?.strategy && (
                <div className="intent-fusion">
                  <b>最终融合</b>
                  <span>{routeIntent.fusion.strategy}</span>
                  {routeIntent.fusion.conflict && <em>LLM 与规则有分歧</em>}
                </div>
              )}
              <div className="hit-list">
                {Object.entries(routeIntent.detected_slots || {}).slice(0, 6).map(([key, value]) => (
                  <span key={key}>{key}: {Array.isArray(value) ? value.join("、") : value || "无"}</span>
                ))}
              </div>
              {routeIntent.rule_signals && (
                <div className="intent-signal-grid">
                  {[
                    ["地点", routeIntent.rule_signals.locations?.join("、") || "未识别"],
                    ["活动", routeIntent.rule_signals.activities?.join("、") || "未识别"],
                    ["路线动词", routeIntent.rule_signals.route_hit ? "命中" : "未命中"],
                    ["时长", routeIntent.rule_signals.duration_hit ? "命中" : "未命中"],
                    ["多活动", routeIntent.rule_signals.multi_activity_hit ? "命中" : "未命中"],
                    ["单店信息", routeIntent.rule_signals.single_poi_hit ? "命中" : "未命中"],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span>{label}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              )}
              {routeIntent.llm_judgement && (
                <div className="intent-llm-box">
                  <b>LLM 判断</b>
                  <p>{routeIntent.llm_judgement.action || "unknown"} · {routeIntent.llm_judgement.intent_type || "未分类"}</p>
                  {routeIntent.llm_judgement.negative_reason && <p>不调起原因：{routeIntent.llm_judgement.negative_reason}</p>}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">小团输入后会先判断 open_plugin / ask_confirm / normal_answer。</div>
          )}
        </section>
      )}

      {plan?.meituan_user_context && (
        <section className="panel">
          <div className="section-head">
            <h2>美团用户画像</h2>
            <span>{plan.profile_mode}</span>
          </div>
          <div className="agent-context">
            <div>
              <span>画像摘要</span>
              <p>{plan.meituan_user_context.summary}</p>
            </div>
            <div>
              <span>画像来源</span>
              <p>{plan.profile_source_description || "模拟画像"}{plan.profile_source === "manual_import" ? " · 脱敏导入" : ""}</p>
            </div>
            <div>
              <span>偏好信号</span>
              <p>{[...(plan.meituan_user_context.search_preferences || []), ...(plan.meituan_user_context.browsed_tags || [])].slice(0, 6).join("、")}</p>
            </div>
            <div>
              <span>P1 指标</span>
              <p>耗时 {plan.planning_time_ms}ms · 冲突 {plan.constraint_conflicts?.length || 0} 个 · {plan.route_completeness?.is_complete ? "路线完整" : "需继续优化"}</p>
            </div>
            <div>
              <span>LLM 解析</span>
              <p>{plan.intent?.parser_source || "rules"} · 置信度 {Math.round((plan.intent?.parser_confidence || 0) * 100)}% · {plan.intent?.parser_reason}</p>
            </div>
            <div>
              <span>交通策略</span>
              <p>{plan.intent?.constraints?.transport_mode || "步行+公交"} · {routeView?.route?.transit_segments?.some((item) => String(item.source || "").startsWith("amap")) ? "高德真实分段" : "本地估算/降级"}</p>
            </div>
          </div>
        </section>
      )}

      {plan?.profile_influence?.length > 0 && (
        <section className="panel">
          <div className="section-head">
            <h2>画像影响链路</h2>
            <span>信号 → 召回 → 路线</span>
          </div>
          <ProfileInfluencePanel influences={plan.profile_influence} />
        </section>
      )}

      <section className="panel demo-script-panel">
        <div className="section-head">
          <h2>演示脚本</h2>
          <span>P1b 闭环</span>
        </div>
        <ol className="trace-list">
          <li>同一句 query 切换三种画像，观察 POI、解释和指标变化。</li>
          <li>点击追问卡里的“少走路 / 不要排队 / 便宜点”。</li>
          <li>展示调整状态、站点变化、等待/预算/移动 delta。</li>
          <li>若无法改善，展示放宽预算、排队、区域或时间的补救建议。</li>
        </ol>
      </section>

      {latestAdjustment && (
        <section className="panel">
          <div className="section-head">
            <h2>调整结果</h2>
            <span>{statusText(latestAdjustment.adjustment_status)}</span>
          </div>
          <AdjustmentResultCard adjustment={latestAdjustment} />
        </section>
      )}

      <ToolTracePanel title="路线 ToolUse Trace" steps={plan?.tool_trace || []} />
      <ToolTracePanel title="调整 ToolUse Trace" steps={latestAdjustment?.tool_trace || []} />

      {adjustmentHistory.length > 0 && (
        <section className="panel">
          <div className="section-head">
            <h2>调整历史</h2>
            <span>{adjustmentHistory.length} 次</span>
          </div>
          <ol className="trace-list">
            {adjustmentHistory.map((item) => <li key={item}>{item}</li>)}
          </ol>
        </section>
      )}

      <TracePanel trace={plan?.trace || []} />
      <InsightPanel routeView={routeView} />
      <CandidatePanel candidates={plan?.candidates || []} />
      <CompareTable routes={routes || []} selectedRouteIndex={selectedRouteIndex} setSelectedRouteIndex={setSelectedRouteIndex} />
    </aside>
  );
}

function inferCityHint(text = "") {
  if (/(深圳|深大|深圳大学|科技园|南山|金地威新|gaga|万象天地)/i.test(text)) return "深圳";
  if (/(北京|三里屯|朝阳|国贸)/.test(text)) return "北京";
  if (/(广州|天河|珠江新城)/.test(text)) return "广州";
  if (/(上海|外滩|陆家嘴|南京东路|静安寺|豫园)/.test(text)) return "上海";
  return null;
}

function cleanAnchorCandidate(value = "") {
  let text = value.trim().replace(/^[，。,. 　]+|[，。,. 　]+$/g, "");
  const prefixes = ["我要去", "我想去", "想去", "要去", "我去", "去", "到", "在", "我要", "我想", "想", "要"];
  let changed = true;
  while (changed) {
    changed = false;
    for (const prefix of prefixes) {
      if (text.startsWith(prefix) && text.length > prefix.length + 1) {
        text = text.slice(prefix.length).trim().replace(/^[，。,. 　]+|[，。,. 　]+$/g, "");
        changed = true;
      }
    }
  }
  return text.slice(0, 24);
}

function inferAnchorText(text = "") {
  const known = ["深圳万象天地", "万象天地", "深圳大学", "深大", "金地威新中心", "gaga", "科技园", "深圳湾", "外滩", "南京东路", "陆家嘴", "静安寺"];
  const hit = known.find((item) => text.includes(item));
  if (hit) return hit === "深圳万象天地" ? "万象天地" : hit;
  if (text.includes("附近")) {
    const prefix = text.split("附近")[0].trim();
    return cleanAnchorCandidate(prefix.slice(-18)) || null;
  }
  if (text.includes("周边")) {
    const prefix = text.split("周边")[0].trim();
    return cleanAnchorCandidate(prefix.slice(-18)) || null;
  }
  if (text.includes("从") && text.includes("出发")) {
    return cleanAnchorCandidate(text.split("从")[1].split("出发")[0]) || null;
  }
  for (const marker of ["，", ",", "。", "帮我", "给我", "规划", "安排", "路线"]) {
    if (text.includes(marker)) {
      const candidate = cleanAnchorCandidate(text.split(marker)[0]);
      if (isLikelyPlaceAnchor(candidate)) return candidate;
    }
  }
  return null;
}

function isLikelyPlaceAnchor(value = "") {
  const text = value.trim();
  if (text.length < 2 || text.length > 24) return false;
  if (/(什么|怎么|多少|附近|周边|今天|下午|晚上|小时)/.test(text)) return false;
  return /(天地|中心|广场|商场|公园|大学|学院|书城|博物馆|美术馆|艺术馆|景区|古镇|步行街|购物中心|城|店)$/.test(text);
}

function contextForScenario(scenario, nextQuery, explicitContext = null) {
  const queryText = nextQuery || scenario?.query || "";
  const base = explicitContext || scenario?.routeContext || {};
  return {
    source: base.source || scenario?.id || "manual",
    city_hint: base.city_hint || inferCityHint(queryText) || (scenario?.id === "xiaotuan" ? APP_CURRENT_CITY : null),
    anchor_text: base.anchor_text || inferAnchorText(queryText),
    anchor_location: base.anchor_location || null,
    selected_pois: base.selected_pois || [],
    transport_strategy: base.transport_strategy || null,
  };
}

function contextForReplacement(stop, plan, activeRouteContext) {
  return {
    ...(activeRouteContext || {}),
    source: "replace",
    city_hint: plan?.intent?.city || activeRouteContext?.city_hint || stop?.poi?.district || null,
    anchor_text: stop?.poi?.name || activeRouteContext?.anchor_text || null,
    anchor_location: stop?.poi
      ? {
          latitude: stop.poi.latitude,
          longitude: stop.poi.longitude,
        }
      : activeRouteContext?.anchor_location || null,
    selected_pois: [],
    transport_strategy: activeRouteContext?.transport_strategy || plan?.intent?.constraints?.transport_mode || null,
  };
}

function buildJudgeProfilePayload(answers, scenario, routeContext) {
  const categoryMap = {
    "咖啡/茶饮": ["咖啡/茶饮"],
    "展览文化": ["景点"],
    "本地美食": ["餐饮"],
    "娱乐玩乐": ["娱乐"],
    "商场室内": ["购物", "咖啡/茶饮"],
  };
  const budgetMap = {
    "省钱优先": 120,
    "中等预算": 220,
    "体验优先": 360,
  };
  const waitMap = {
    "尽量不排队": 8,
    "可等15分钟": 15,
    "热门也可以": 35,
  };
  const walkMap = {
    "少走路": "少走路",
    "步行可接受": "适中",
    "公交地铁": "公交地铁优先",
    "打车优先": "少走路",
  };
  const transportMap = {
    "少走路": "短步行+打车",
    "步行可接受": "步行优先",
    "公交地铁": "公交/地铁优先",
    "打车优先": "打车优先",
  };
  const content = answers.content || DEFAULT_JUDGE_ANSWERS.content;
  const companion = answers.companion || DEFAULT_JUDGE_ANSWERS.companion;
  const budget = answers.budget || DEFAULT_JUDGE_ANSWERS.budget;
  const queue = answers.queue || DEFAULT_JUDGE_ANSWERS.queue;
  const mobility = answers.mobility || DEFAULT_JUDGE_ANSWERS.mobility;
  const area = routeContext?.anchor_text || routeContext?.city_hint || "当前位置";
  const categories = categoryMap[content] || ["餐饮", "景点"];
  return {
    profile: {
      profile_id: "judge-session",
      display_name: "评委即时画像",
      recent_searches: [area, content, companion, mobility, queue],
      favorite_pois: [`${area}附近${content}`, `${scenario.title}入口偏好`],
      browsed_pois: [content, companion, budget, queue, mobility],
      favorite_categories: categories,
      favorite_districts: routeContext?.city_hint ? [routeContext.city_hint] : [],
      frequent_districts: routeContext?.city_hint ? [routeContext.city_hint] : [],
      budget_preference: budgetMap[budget] || 220,
      max_wait_preference: waitMap[queue] || 15,
      walk_preference: walkMap[mobility] || "适中",
      coupon_sensitive: budget === "省钱优先",
    },
    transportStrategy: transportMap[mobility] || "步行优先",
  };
}

export default function App() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [examples, setExamples] = useState([DEFAULT_QUERY]);
  const [health, setHealth] = useState(null);
  const [plan, setPlan] = useState(null);
  const [selectedRouteIndex, setSelectedRouteIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("");
  const [error, setError] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [replacement, setReplacement] = useState(null);
  const [activeScenarioId, setActiveScenarioId] = useState("search");
  const [phoneMode, setPhoneMode] = useState("entry");
  const [routeIntent, setRouteIntent] = useState(null);
  const [xiaotuanConversation, setXiaotuanConversation] = useState([]);
  const [profileMode, setProfileMode] = useState("文艺体验型");
  const [profileSource, setProfileSource] = useState("preset");
  const [profileSources, setProfileSources] = useState(null);
  const [importedProfileId, setImportedProfileId] = useState("");
  const [adjustmentHistory, setAdjustmentHistory] = useState([]);
  const [latestAdjustment, setLatestAdjustment] = useState(null);
  const [activeRouteContext, setActiveRouteContext] = useState(contextForScenario(SCENARIOS[0], DEFAULT_QUERY));
  const [preferenceModalOpen, setPreferenceModalOpen] = useState(false);
  const [pendingPlan, setPendingPlan] = useState(null);
  const [sessionProfileReady, setSessionProfileReady] = useState(false);

  const activeScenario = SCENARIOS.find((scenario) => scenario.id === activeScenarioId) || SCENARIOS[0];
  const selectedRouteView = plan?.routes?.[selectedRouteIndex] || null;

  useEffect(() => {
    getJson("/api/health").then(setHealth).catch(() => setHealth({ status: "offline" }));
    getJson("/api/examples").then((data) => setExamples(data.examples || [DEFAULT_QUERY])).catch(() => {});
    refreshProfileSources();
  }, []);

  async function refreshProfileSources(preferredProfileId = importedProfileId) {
    try {
      const payload = await getJson("/api/profile-sources");
      setProfileSources(payload);
      const manualProfiles = profilesForSource(payload, "manual_import");
      if (!preferredProfileId && manualProfiles.length) {
        setImportedProfileId(manualProfiles[0].profile_id);
      }
      return payload;
    } catch {
      return null;
    }
  }

  async function generatePlan(
    nextQuery,
    openRoute = true,
    mode = profileMode,
    label = "规划中",
    source = profileSource,
    profileId = importedProfileId,
    nextRouteContext = activeRouteContext,
  ) {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setLoading(true);
    setLoadingLabel(label);
    setError("");
    setFeedbackStatus("");
    setReplacement(null);
    setLatestAdjustment(null);
    setActiveRouteContext(nextRouteContext);
    try {
      const payload = await postJson("/api/plan", {
        query: trimmed,
        user_id: USER_ID,
        n_routes: 2,
        profile_mode: mode,
        profile_source: source,
        profile_id: source === "manual_import" ? profileId : null,
        route_context: nextRouteContext,
      });
      setPlan(payload);
      setSelectedRouteIndex(0);
      setAdjustmentHistory([]);
      if (openRoute) {
        setPhoneMode("route");
      }
    } catch (err) {
      setError(err.message || "生成失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  async function requestPlanWithPreference(nextQuery, explicitContext = null, label = "规划中") {
    const nextContext = contextForScenario(activeScenario, nextQuery, explicitContext);
    if (!sessionProfileReady) {
      setPendingPlan({ query: nextQuery, context: nextContext, label });
      setPreferenceModalOpen(true);
      return;
    }
    await generatePlan(nextQuery, true, profileMode, label, profileSource, importedProfileId, nextContext);
  }

  async function submitJudgePreference(answers) {
    const pending = pendingPlan || {
      query: query || activeScenario.query,
      context: activeRouteContext,
      label: "评委画像规划中",
    };
    const { profile, transportStrategy } = buildJudgeProfilePayload(answers, activeScenario, pending.context);
    const nextContext = {
      ...pending.context,
      transport_strategy: transportStrategy,
    };
    setLoading(true);
    setLoadingLabel("生成评委即时画像");
    setError("");
    try {
      const response = await postJson("/api/profile/import", profile);
      const nextProfileId = response.profile.profile_id;
      await refreshProfileSources(nextProfileId);
      setProfileSource("manual_import");
      setImportedProfileId(nextProfileId);
      setSessionProfileReady(true);
      setPreferenceModalOpen(false);
      setPendingPlan(null);
      setFeedbackStatus("已生成评委即时画像，本次路线会按这些偏好规划。");
      await generatePlan(pending.query, true, profileMode, pending.label || "评委画像规划中", "manual_import", nextProfileId, nextContext);
    } catch (err) {
      setError(err.message || "评委画像生成失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  function skipJudgePreference() {
    const pending = pendingPlan || {
      query: query || activeScenario.query,
      context: activeRouteContext,
      label: "规划中",
    };
    setSessionProfileReady(true);
    setPreferenceModalOpen(false);
    setPendingPlan(null);
    generatePlan(pending.query, true, profileMode, pending.label || "规划中", profileSource, importedProfileId, pending.context);
  }

  function selectScenario(scenario) {
    setActiveScenarioId(scenario.id);
    setPhoneMode("entry");
    setQuery(scenario.query);
    setActiveRouteContext(contextForScenario(scenario, scenario.query));
    setRouteIntent(null);
    setXiaotuanConversation([]);
    setError("");
    setFeedbackStatus("");
    setReplacement(null);
    setLatestAdjustment(null);
  }

  function changeProfileMode(nextMode) {
    setProfileMode(nextMode);
    setProfileSource("preset");
    if (query) {
      generatePlan(query, true, nextMode, "画像切换中", "preset", null, activeRouteContext);
    }
  }

  function changeProfileSource(nextSource) {
    setProfileSource(nextSource);
    if (nextSource === "preset") {
      generatePlan(query, true, profileMode, "画像切换中", "preset", null, activeRouteContext);
      return;
    }
    const manualProfiles = profilesForSource(profileSources, "manual_import");
    const nextProfileId = importedProfileId || manualProfiles[0]?.profile_id || "";
    if (nextProfileId) {
      setImportedProfileId(nextProfileId);
      generatePlan(query, true, profileMode, "脱敏画像加载中", "manual_import", nextProfileId, activeRouteContext);
    }
  }

  function changeImportedProfile(nextProfileId) {
    setImportedProfileId(nextProfileId);
    setProfileSource("manual_import");
    if (query) {
      generatePlan(query, true, profileMode, "脱敏画像切换中", "manual_import", nextProfileId, activeRouteContext);
    }
  }

  async function importManualProfile(payload, clientError = "") {
    if (clientError) {
      setError(clientError);
      return;
    }
    setLoading(true);
    setLoadingLabel("导入脱敏画像");
    setError("");
    setFeedbackStatus("");
    try {
      const response = await postJson("/api/profile/import", payload);
      const nextProfileId = response.profile.profile_id;
      await refreshProfileSources(nextProfileId);
      setProfileSource("manual_import");
      setImportedProfileId(nextProfileId);
      setFeedbackStatus(response.safety_notice || "脱敏画像已导入。");
      await generatePlan(query || DEFAULT_QUERY, true, profileMode, "脱敏画像规划中", "manual_import", nextProfileId, activeRouteContext);
    } catch (err) {
      setError(err.message || "画像导入失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  async function askXiaotuan(nextQuery, replyType = "free_text") {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    const previousIntent = routeIntent?.turn_state === "collecting_slots" ? routeIntent : null;
    setQuery(trimmed);
    setLoading(true);
    setLoadingLabel("小团识别中");
    setError("");
    setXiaotuanConversation((items) => [...items, { id: `u-${Date.now()}`, role: "user", text: trimmed }]);
    try {
      const payload = await postJson("/api/route-intent", {
        query: trimmed,
        source: "xiaotuan",
        conversation_id: previousIntent?.conversation_id || null,
        previous_intent: previousIntent,
        user_reply_type: replyType,
        context: {
          entry: "问小团",
          current_city: inferCityHint(trimmed) || activeRouteContext?.city_hint || activeScenario.routeContext?.city_hint || APP_CURRENT_CITY,
          product: "meituan",
        },
      });
      setRouteIntent(payload);
      const assistantText = payload.clarification_question
        || (payload.action === "open_plugin" ? "信息已经补齐，我来帮你生成路线。" : payload.reason);
      setXiaotuanConversation((items) => [...items, { id: `a-${Date.now()}`, role: "assistant", text: assistantText }]);
      if (payload.action === "open_plugin") {
        const planningQuery = payload.merged_query || payload.planning_query || trimmed;
        const nextContext = contextForScenario(activeScenario, planningQuery, {
          source: "xiaotuan",
          city_hint: inferCityHint(planningQuery) || activeRouteContext?.city_hint || activeScenario.routeContext?.city_hint || APP_CURRENT_CITY,
          anchor_text: payload.filled_slots?.location || inferAnchorText(planningQuery),
        });
        await requestPlanWithPreference(planningQuery, nextContext, "规划中");
      }
    } catch (err) {
      setError(err.message || "意图识别失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  async function adjustRoute(instruction) {
    if (!selectedRouteView || !plan) return;
    setLoading(true);
    setLoadingLabel("局部调整中");
    setError("");
    setFeedbackStatus("");
    try {
      const payload = await postJson("/api/adjust", {
        query: plan.query || query,
        instruction,
        route: selectedRouteView.route,
        user_id: USER_ID,
        profile_mode: profileMode,
        profile_source: profileSource,
        profile_id: profileSource === "manual_import" ? importedProfileId : null,
        route_context: activeRouteContext,
      });
      const nextRoutes = plan.routes.map((routeView, index) => (
        index === selectedRouteIndex ? payload.route : routeView
      ));
      setPlan({
        ...plan,
        routes: nextRoutes,
        planning_time_ms: payload.planning_time_ms,
        follow_up_question: payload.follow_up_question,
        follow_up: payload.follow_up,
        constraint_conflicts: payload.constraint_conflicts,
        route_completeness: payload.route_completeness,
        trace: [...(plan.trace || []), `实时调整：${payload.adjustment_summary}`],
        tool_trace: plan.tool_trace || [],
      });
      setLatestAdjustment(payload);
      setFeedbackStatus(`${statusText(payload.adjustment_status)}：${payload.adjustment_summary}`);
      const deltas = payload.metric_deltas || {};
      setAdjustmentHistory((items) => [
        ...items,
        `${payload.adjustment_history_item}（等位 ${metricDelta(deltas.total_wait_minutes)} / 人均 ${metricDelta(deltas.total_cost_per_person, "¥")} / 移动 ${metricDelta(deltas.total_transit_minutes)}）`,
      ]);
    } catch (err) {
      setError(err.message || "调整失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  async function sendFeedback(value) {
    if (!selectedRouteView) return;
    setFeedbackStatus("写入中...");
    try {
      await postJson("/api/feedback", {
        user_id: USER_ID,
        route: selectedRouteView.route,
        feedback: value,
      });
      setFeedbackStatus(value === 1 ? "已记录喜欢，下次会提高相似 POI 权重。" : "已记录不合适，下次会降低相似路线。");
    } catch (err) {
      setFeedbackStatus(err.message || "反馈写入失败");
    }
  }

  async function openReplace(stop) {
    if (!selectedRouteView || !plan) return;
    setReplacement({ loading: true, stop, options: [] });
    setLoadingLabel("搜索替换项");
    try {
      const payload = await postJson("/api/replace", {
        query: plan.query,
        route: selectedRouteView.route,
        stop_order: stop.order,
        user_id: USER_ID,
        profile_mode: profileMode,
        profile_source: profileSource,
        profile_id: profileSource === "manual_import" ? importedProfileId : null,
        route_context: contextForReplacement(stop, plan, activeRouteContext),
      });
      setReplacement({ loading: false, stop, options: payload.options || [] });
    } catch (err) {
      setReplacement({ loading: false, stop, options: [], error: err.message });
    } finally {
      setLoadingLabel("");
    }
  }

  function applyReplacement(option) {
    if (!plan || !selectedRouteView || !replacement) return;
    const oldStop = replacement.stop;
      const nextRoutes = plan.routes.map((routeView, index) => {
      if (index !== selectedRouteIndex) return routeView;
      const route = JSON.parse(JSON.stringify(routeView.route));
      const stop = route.stops.find((item) => item.order === oldStop.order);
      if (!stop) return routeView;
      const oldPrice = stop.poi.price_per_person;
      const oldWait = stop.wait_minutes;
      stop.poi = option.poi;
      stop.wait_minutes = option.poi.avg_wait_minutes;
      stop.duration_minutes = Math.max(30, Math.min(option.poi.visit_duration_minutes, 100));
      stop.tips = "已按同类 POI 替换，预算与等待指标同步更新。";
      route.id = `${route.id}-r${oldStop.order}`;
      route.total_cost_per_person = Math.round((route.total_cost_per_person + option.poi.price_per_person - oldPrice) * 10) / 10;
      route.total_wait_minutes = Math.max(0, route.total_wait_minutes + option.poi.avg_wait_minutes - oldWait);
      route.description = `已将第 ${oldStop.order} 站替换为 ${option.poi.name}，用于演示可执行路线的即时调整。`;
      return {
        ...routeView,
        route,
        insight: {
          ...routeView.insight,
          route_id: route.id,
          explanation: `替换影响：${option.impact_summary}。`,
        },
      };
    });
    setPlan({ ...plan, routes: nextRoutes });
    setLatestAdjustment(null);
    setAdjustmentHistory((items) => [...items, `替换站点：${option.impact_summary}`]);
    setReplacement(null);
  }

  return (
    <main>
      <TopBar health={health} />

      {error && <div className="error-banner">{error}</div>}
      {feedbackStatus && <div className="feedback-toast">{feedbackStatus}</div>}

      <div className="demo-layout">
        <ScenarioSelector
          scenarios={SCENARIOS}
          activeScenarioId={activeScenarioId}
          onSelect={selectScenario}
          health={health}
        />
        <PhoneExperience
          scenario={activeScenario}
          mode={phoneMode}
          plan={plan}
          routeView={selectedRouteView}
          loading={loading}
          xiaotuanConversation={xiaotuanConversation}
          routeIntent={routeIntent}
          onOpenRoute={(nextQuery, explicitContext) => {
            requestPlanWithPreference(nextQuery, explicitContext, "规划中");
          }}
          onAskXiaotuan={askXiaotuan}
          profileMode={profileMode}
          profileSource={profileSource}
          profileSources={profileSources}
          importedProfileId={importedProfileId}
          onPresetProfileChange={changeProfileMode}
          onProfileSourceChange={changeProfileSource}
          onImportedProfileChange={changeImportedProfile}
          onImportProfile={importManualProfile}
          onReplace={openReplace}
          onFeedback={sendFeedback}
          onAdjust={adjustRoute}
          adjustmentHistory={adjustmentHistory}
          latestAdjustment={latestAdjustment}
          loadingLabel={loadingLabel}
        />
        <AgentPanel
          scenario={activeScenario}
          routeIntent={routeIntent}
          plan={plan}
          routeView={selectedRouteView}
          routes={plan?.routes || []}
          selectedRouteIndex={selectedRouteIndex}
          setSelectedRouteIndex={setSelectedRouteIndex}
          adjustmentHistory={adjustmentHistory}
          latestAdjustment={latestAdjustment}
        />
      </div>
      <ReplacePanel replacement={replacement} onClose={() => setReplacement(null)} onApply={applyReplacement} />
      <JudgePreferenceModal
        open={preferenceModalOpen}
        scenario={activeScenario}
        pendingQuery={pendingPlan?.query}
        onSubmit={submitJudgePreference}
        onSkip={skipJudgePreference}
        loading={loading}
      />
    </main>
  );
}
