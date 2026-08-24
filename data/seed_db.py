from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.rag.vector_store import POIVectorStore


RANDOM_SEED = 20260528

DISTRICTS = {
    "黄浦区": {"lat": (31.220, 31.250), "lon": (121.470, 121.510), "areas": ["外滩", "豫园", "人民广场", "南京东路"]},
    "浦东新区": {"lat": (31.200, 31.260), "lon": (121.510, 121.585), "areas": ["陆家嘴", "世纪公园", "前滩", "张江"]},
    "徐汇区": {"lat": (31.170, 31.220), "lon": (121.420, 121.475), "areas": ["武康路", "徐家汇", "衡山路", "滨江"]},
    "静安区": {"lat": (31.220, 31.255), "lon": (121.430, 121.475), "areas": ["静安寺", "南京西路", "苏河湾", "大宁"]},
    "长宁区": {"lat": (31.200, 31.235), "lon": (121.380, 121.445), "areas": ["愚园路", "虹桥路", "中山公园", "新华路"]},
    "杨浦区": {"lat": (31.250, 31.305), "lon": (121.500, 121.555), "areas": ["大学路", "五角场", "杨浦滨江", "创智天地"]},
    "虹桥商务区": {"lat": (31.180, 31.220), "lon": (121.330, 121.385), "areas": ["虹桥天地", "国家会展中心", "蟠龙天地", "虹桥枢纽"]},
}

CATEGORY_COUNTS = {
    "餐饮": 200,
    "景点": 80,
    "购物": 80,
    "咖啡/茶饮": 70,
    "娱乐": 50,
    "住宿": 20,
}

CONFIG = {
    "餐饮": {
        "prefix": ["弄堂", "云间", "海派", "梧桐", "小满", "南里", "有味", "沪上", "寻味", "春见"],
        "suffix": ["小馆", "食堂", "本帮菜", "面馆", "火锅", "烧鸟", "私房菜", "小海鲜", "茶餐厅", "融合菜"],
        "tags": ["本地人推荐", "小聚会", "不踩雷", "招牌菜", "性价比高", "适合朋友", "需要预约", "上海味道"],
        "price": (45, 260),
        "wait": (0, 55),
        "duration": (60, 95),
        "hours": ("10:30", "22:00"),
    },
    "景点": {
        "prefix": ["城市", "滨江", "梧桐", "海派", "光影", "艺文", "老街", "绿地", "记忆", "云上"],
        "suffix": ["漫步区", "展馆", "公园", "艺术中心", "观景台", "历史街区", "美术馆", "文化广场"],
        "tags": ["拍照出片", "免费", "适合散步", "城市地标", "亲子友好", "历史建筑", "雨天可去"],
        "price": (0, 120),
        "wait": (0, 25),
        "duration": (55, 120),
        "hours": ("09:00", "21:00"),
    },
    "购物": {
        "prefix": ["里弄", "新潮", "云集", "摩登", "城市", "万象", "方庭", "设计师", "精选", "有光"],
        "suffix": ["市集", "购物中心", "买手店", "生活馆", "商业街", "集合店", "奥莱", "潮流广场"],
        "tags": ["逛街", "设计感", "室内", "品牌多", "适合拍照", "小众店铺", "周末市集"],
        "price": (20, 180),
        "wait": (0, 10),
        "duration": (50, 100),
        "hours": ("10:00", "22:00"),
    },
    "咖啡/茶饮": {
        "prefix": ["转角", "梧桐下", "慢半拍", "有风", "日光", "山野", "胶片", "白昼", "巷口", "一隅"],
        "suffix": ["咖啡", "茶室", "甜品店", "烘焙所", "手冲咖啡", "下午茶", "茶饮实验室"],
        "tags": ["安静", "适合约会", "有设计感", "下午茶", "拍照出片", "适合聊天", "插座友好"],
        "price": (28, 110),
        "wait": (0, 18),
        "duration": (45, 85),
        "hours": ("09:30", "21:30"),
    },
    "娱乐": {
        "prefix": ["夜航", "星幕", "声场", "沉浸", "城市", "微醺", "剧场", "银幕", "奇遇", "玩家"],
        "suffix": ["Livehouse", "电影院", "脱口秀", "密室", "酒吧", "剧场", "桌游社", "夜游体验"],
        "tags": ["夜生活", "朋友聚会", "需预约", "氛围好", "室内", "适合年轻人", "周末热门"],
        "price": (60, 220),
        "wait": (0, 20),
        "duration": (70, 130),
        "hours": ("13:00", "23:30"),
    },
    "住宿": {
        "prefix": ["云栖", "澄光", "城市精选", "外滩旁", "里弄", "泊岸", "轻居", "悦庭"],
        "suffix": ["酒店", "民宿", "设计酒店", "公寓酒店", "精品客栈"],
        "tags": ["交通方便", "干净", "安静", "适合过夜", "近地铁", "行李寄存"],
        "price": (280, 780),
        "wait": (0, 5),
        "duration": (30, 45),
        "hours": ("00:00", "23:59"),
    },
}


def generate_mock_pois(n: int = 500) -> list[dict]:
    random.seed(RANDOM_SEED)
    pois: list[dict] = []
    category_sequence = [category for category, count in CATEGORY_COUNTS.items() for _ in range(count)]
    random.shuffle(category_sequence)

    for index, category in enumerate(category_sequence[:n], start=1):
        district = random.choice(list(DISTRICTS))
        district_config = DISTRICTS[district]
        area = random.choice(district_config["areas"])
        config = CONFIG[category]
        name = f"{random.choice(config['prefix'])}{random.choice(config['suffix'])}（{area}店）"
        lat = round(random.uniform(*district_config["lat"]), 6)
        lon = round(random.uniform(*district_config["lon"]), 6)
        price = round(random.uniform(*config["price"]))
        wait_min, wait_max = config["wait"]
        wait = random.randint(wait_min, wait_max)
        rating = min(4.9, max(3.5, random.gauss(4.18, 0.32)))
        rating = round(rating, 1)
        tags = random.sample(config["tags"], k=min(4, len(config["tags"])))
        duration = random.randint(*config["duration"])
        review_count = random.randint(120, 90000 if category in {"餐饮", "景点"} else 28000)
        ugc = build_ugc_summary(category, name, area, tags, price, wait, rating)
        pois.append(
            {
                "id": f"poi_{index:03d}",
                "name": name,
                "category": category,
                "address": f"上海市{district}{area}生活街{random.randint(1, 399)}号",
                "district": district,
                "latitude": lat,
                "longitude": lon,
                "rating": rating,
                "review_count": review_count,
                "price_per_person": price,
                "avg_wait_minutes": wait,
                "business_hours": {"open": config["hours"][0], "close": config["hours"][1]},
                "tags": tags,
                "ugc_summary": ugc,
                "phone": f"021-{random.randint(10000000, 99999999)}",
                "images": [],
                "visit_duration_minutes": duration,
            }
        )
    return pois


def build_ugc_summary(category: str, name: str, area: str, tags: list[str], price: int, wait: int, rating: float) -> str:
    tag_text = "、".join(tags[:3])
    wait_text = "基本不用等位" if wait <= 8 else f"高峰大约等待{wait}分钟"
    if category == "餐饮":
        return f"{name}在{area}附近人气稳定，主打{tag_text}。用户评价口味比较稳，人均约{price}元，{wait_text}，适合提前收藏后按路线顺路安排。"
    if category == "景点":
        return f"{name}适合城市漫步和拍照，{tag_text}是高频评价。整体评分约{rating}，游览节奏轻松，建议避开周末正午人流。"
    if category == "咖啡/茶饮":
        return f"{name}氛围安静，常被评价为{tag_text}。人均约{price}元，适合放在路线中段休息聊天，下午光线更舒服。"
    if category == "购物":
        return f"{name}适合边逛边休息，特点是{tag_text}。店铺密度高，预算弹性大，雨天或临时调整路线时很适合作为缓冲点。"
    if category == "娱乐":
        return f"{name}偏夜间体验，用户常提到{tag_text}。建议提前看场次或预约，人均约{price}元，适合朋友结尾加一站。"
    return f"{name}位置方便，评价集中在{tag_text}。适合需要行李寄存、短暂休息或跨天行程的人群，建议提前确认房态。"


def generate_reviews(pois: list[dict], limit: int = 160) -> list[dict]:
    reviews = []
    for i, poi in enumerate(pois[:limit], start=1):
        reviews.append(
            {
                "poi_id": poi["id"],
                "review_id": f"r_{i:03d}",
                "content": poi["ugc_summary"],
                "rating": max(3, round(poi["rating"])),
                "sentiment": "positive" if poi["rating"] >= 4.0 else "neutral",
                "aspects": {
                    "wait_time": "short" if poi["avg_wait_minutes"] <= 10 else "medium",
                    "price": "reasonable" if poi["price_per_person"] <= 120 else "premium",
                },
                "date": "2026-05-01",
            }
        )
    return reviews


def main() -> None:
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    pois = generate_mock_pois(500)
    (data_dir / "pois.json").write_text(json.dumps(pois, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / "ugc_reviews.json").write_text(json.dumps(generate_reviews(pois), ensure_ascii=False, indent=2), encoding="utf-8")
    store = POIVectorStore(str(data_dir / "local_index"))
    store.index_pois(pois)
    print(f"Generated {len(pois)} POIs and indexed {store.count} local documents.")


if __name__ == "__main__":
    main()
