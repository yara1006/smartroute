export const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.PROD ? "" : "http://127.0.0.1:8000");
export const AMAP_KEY = import.meta.env.VITE_AMAP_KEY || "";
export const AMAP_SECURITY_JS_CODE = import.meta.env.VITE_AMAP_SECURITY_JS_CODE || "";
export const DEFAULT_MAP_CENTER = [113.93646, 22.53332];
export const USER_ID = "product-demo-user";
export const DEFAULT_QUERY = "我下午要去深圳大学附近玩3个小时，帮我规划一个路线";
export const APP_CURRENT_CITY = "深圳";
export const PROFILE_MODES = ["低排队务实型", "文艺体验型", "带爸妈轻松型"];

export const FAVORITE_POIS = [
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

export const DETAIL_POI = FAVORITE_POIS[1];

export const IMPORT_PROFILE_TEMPLATE = JSON.stringify({
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

export const JUDGE_PROFILE_QUESTIONS = [
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

export const DEFAULT_JUDGE_ANSWERS = {
  companion: "朋友",
  budget: "中等预算",
  queue: "可等15分钟",
  mobility: "步行可接受",
  content: "咖啡/茶饮",
};

export const SCENARIOS = [
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
      fixed_start_poi_id: DETAIL_POI.id,
      pinned_policy: "fixed_start",
    },
  },
];
