# 配置说明

## 集中配置

所有配置通过 `core/config.py` 的 `Settings` 单例管理，环境变量从项目根目录 `.env` 自动加载。

```python
from core.config import get_settings

settings = get_settings()
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key，用于 LLM 意图解析 | 空（规则兜底）|
| `DEEPSEEK_CHAT_MODEL` | DeepSeek 聊天模型名称 | `deepseek-chat` |
| `DEEPSEEK_ROUTE_MODEL` | DeepSeek 路线推理模型 | `deepseek-reasoner` |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com` |
| `AMAP_WEB_SERVICE_KEY` | 高德 Web 服务 Key（注意：必须是"Web服务"类型）| 空（本地兜底）|
| `CORS_ORIGINS` | CORS 允许的来源，逗号分隔 | `*` |

## 数据路径

| 路径 | 说明 |
|------|------|
| `data/pois.json` | 本地 POI 数据 |
| `data/ugc_reviews.json` | 本地 UGC 评价 |
| `data/local_index/poi_index.json` | 本地向量索引 |
| `data/user_profiles.db` | SQLite 用户画像 |
| `data/profile_imports.json` | 脱敏导入画像记录 |

## 如何判断 Key 是否生效

启动后端后访问 `/api/health`，返回：

```json
{
  "status": "ok",
  "deepseek_enabled": true,
  "amap_enabled": true
}
```

`deepseek_enabled=true` 表示 DeepSeek Key 已配置；`amap_enabled=true` 表示高德 Key 已配置。
