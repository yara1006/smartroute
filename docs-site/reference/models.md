# 数据模型

## 核心模型

### POI

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `str` | 唯一标识 |
| `name` | `str` | 名称 |
| `category` | `str` | 类别（餐饮/景点/购物等）|
| `address` | `str` | 地址 |
| `district` | `str` | 区域 |
| `latitude` | `float` | 纬度 |
| `longitude` | `float` | 经度 |
| `rating` | `float` | 评分 |
| `price_per_person` | `int` | 人均消费 |
| `avg_wait_minutes` | `int` | 平均等待时间 |
| `tags` | `list[str]` | 标签 |
| `source` | `str` | `amap` / `seed` / `context` |

### Route

| 字段 | 类型 | 说明 |
|------|------|------|
| `title` | `str` | 路线标题 |
| `description` | `str` | 路线描述 |
| `stops` | `list[RouteStop]` | 站点列表 |
| `total_duration_minutes` | `int` | 总时长 |
| `total_cost` | `int` | 总费用 |
| `map_polyline` | `list` | 地图路径坐标 |

### RouteStop

| 字段 | 类型 | 说明 |
|------|------|------|
| `order` | `int` | 站点顺序 |
| `poi` | `POI` | 对应 POI |
| `arrival_time` | `str` | 到达时间 |
| `departure_time` | `str` | 离开时间 |
| `stay_minutes` | `int` | 停留时长 |

### UserConstraints

| 字段 | 类型 | 说明 |
|------|------|------|
| `city` | `str` | 城市 |
| `start_location` | `str` | 起点 |
| `duration_minutes` | `int` | 时间窗口 |
| `budget` | `int` | 预算 |
| `max_wait_minutes` | `int` | 最大等待时间 |
| `transport_mode` | `str` | 交通方式 |
| `preferred_categories` | `list[str]` | 偏好类别 |

### RouteContext

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | `str` | 入口来源（search/xiaotuan/favorites/detail）|
| `city_hint` | `str` | 城市提示 |
| `anchor_text` | `str` | 锚点文本 |
| `selected_pois` | `list[POI]` | 已选 POI |
| `transport_strategy` | `str` | 交通策略 |
| `fixed_start_poi_id` | `str` | 固定起点 ID |
| `pinned_policy` | `str` | 固定策略 |
