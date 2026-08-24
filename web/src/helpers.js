import { APP_CURRENT_CITY, DEFAULT_JUDGE_ANSWERS } from "./constants.js";

export function inferCityHint(text = "") {
  if (/(深圳|深大|深圳大学|科技园|南山|金地威新|gaga|万象天地)/i.test(text)) return "深圳";
  if (/(北京|三里屯|朝阳|国贸|金鱼胡同|王府井)/.test(text)) return "北京";
  if (/(广州|天河|珠江新城|永庆坊|荔湾|北京路)/.test(text)) return "广州";
  if (/(上海|外滩|陆家嘴|南京东路|静安寺|豫园)/.test(text)) return "上海";
  return null;
}

export function cleanAnchorCandidate(value = "") {
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

export function inferAnchorText(text = "") {
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

export function isLikelyPlaceAnchor(value = "") {
  const text = value.trim();
  if (text.length < 2 || text.length > 24) return false;
  if (/(什么|怎么|多少|附近|周边|今天|下午|晚上|小时)/.test(text)) return false;
  return /(天地|中心|广场|商场|公园|大学|学院|书城|博物馆|美术馆|艺术馆|景区|古镇|步行街|购物中心|城|店)$/.test(text);
}

export function contextForScenario(scenario, nextQuery, explicitContext = null) {
  const queryText = nextQuery || scenario?.query || "";
  const base = explicitContext || scenario?.routeContext || {};
  return {
    source: base.source || scenario?.id || "manual",
    city_hint: base.city_hint || inferCityHint(queryText) || (scenario?.id === "xiaotuan" ? APP_CURRENT_CITY : null),
    anchor_text: base.anchor_text || inferAnchorText(queryText),
    anchor_location: base.anchor_location || null,
    selected_pois: base.selected_pois || [],
    transport_strategy: base.transport_strategy || null,
    fixed_start_poi_id: base.fixed_start_poi_id || null,
    pinned_policy: base.pinned_policy || null,
  };
}

export function contextForReplacement(stop, plan, activeRouteContext) {
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

export function buildJudgeProfilePayload(answers, scenario, routeContext) {
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

export function profilesForSource(profileSources, source) {
  return profileSources?.sources?.find((item) => item.source === source)?.profiles || [];
}
