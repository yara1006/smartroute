from core.agents.intent_parser import IntentParserAgent
from core.agents.poi_retriever import POIRetrieverAgent
from core.agents.route_planner import RoutePlannerAgent
from core.models import POI, POICategory
from core.rag.vector_store import POIVectorStore
from data.seed_db import generate_mock_pois


def test_pipeline_generates_route(tmp_path):
    pois_raw = generate_mock_pois(80)
    poi_db = {item["id"]: POI(**item) for item in pois_raw}
    store = POIVectorStore(str(tmp_path / "index"))
    store.index_pois(pois_raw)

    intent = IntentParserAgent().parse("帮我规划一个上海外滩附近的文艺下午，时间3小时，两个人，预算200，不想排队")
    candidates = POIRetrieverAgent(store, poi_db).retrieve(intent)
    routes = RoutePlannerAgent(poi_db).plan(intent, candidates, n_routes=2)

    assert candidates
    assert routes
    assert routes[0].stops
    assert len(routes[0].stops) >= 3
    categories = {stop.poi.category for stop in routes[0].stops}
    assert categories.intersection({POICategory.RESTAURANT, POICategory.CAFE})
    assert categories.intersection({POICategory.ATTRACTION, POICategory.ENTERTAINMENT})
    assert routes[0].total_time_minutes <= 3 * 60 + 45


def make_test_poi(name, category, index, price=60, wait=8, rating=4.6):
    return POI(
        id=f"test-{index}",
        name=name,
        category=category,
        address="深圳福田",
        district="深圳",
        latitude=22.54 + index * 0.002,
        longitude=114.05 + index * 0.002,
        rating=rating,
        review_count=500,
        price_per_person=price,
        avg_wait_minutes=wait,
        business_hours={"open": "09:00", "close": "22:00"},
        tags=[category.value],
        ugc_summary=f"{name} 适合路线规划",
        visit_duration_minutes=45,
        source="amap",
    )


def test_route_planner_avoids_consecutive_cafes_by_default():
    pois = [
        make_test_poi("星巴克", POICategory.CAFE, 1, rating=4.8),
        make_test_poi("NEST PANCAKE CAFE", POICategory.CAFE, 2, rating=4.7),
        make_test_poi("抱抱小狗咖啡", POICategory.CAFE, 3, rating=4.6),
        make_test_poi("福田红树林生态公园科普展馆", POICategory.ATTRACTION, 4, price=20),
        make_test_poi("深业上城生活中心", POICategory.SHOPPING, 5, price=30),
        make_test_poi("福田轻食餐厅", POICategory.RESTAURANT, 6, price=90),
    ]
    intent = IntentParserAgent().parse("福田文艺下午3小时")
    candidates = [(poi, 5.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in pois}).plan(intent, candidates, n_routes=1)

    assert routes
    stops = routes[0].stops
    categories = [stop.poi.category for stop in stops]
    assert categories.count(POICategory.CAFE) <= 1
    assert not any(categories[index] == categories[index - 1] for index in range(1, len(categories)))
    assert any(category in {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING} for category in categories)


def test_route_planner_allows_explicit_coffee_hopping():
    pois = [
        make_test_poi("精品咖啡一号", POICategory.CAFE, 1, rating=4.8),
        make_test_poi("精品咖啡二号", POICategory.CAFE, 2, rating=4.7),
        make_test_poi("精品咖啡三号", POICategory.CAFE, 3, rating=4.6),
        make_test_poi("城市展馆", POICategory.ATTRACTION, 4, price=20),
    ]
    intent = IntentParserAgent().parse("福田咖啡店巡游3小时")
    candidates = [(poi, 5.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in pois}).plan(intent, candidates, n_routes=1)

    assert routes
    categories = [stop.poi.category for stop in routes[0].stops]
    assert categories.count(POICategory.CAFE) >= 2


def test_route_planner_caps_restaurants_for_realistic_afternoon():
    pois = [
        make_test_poi("陈添记西关老字号", POICategory.RESTAURANT, 1, price=85, rating=4.9),
        make_test_poi("东湖酒楼粤菜老字号", POICategory.RESTAURANT, 2, price=110, rating=4.8),
        make_test_poi("凤小馆顺德菜", POICategory.RESTAURANT, 3, price=95, rating=4.7),
        make_test_poi("永庆坊街角茶饮", POICategory.CAFE, 4, price=35, rating=4.5),
        make_test_poi("粤剧艺术博物馆", POICategory.ATTRACTION, 5, price=20, rating=4.6),
        make_test_poi("永庆坊历史街区", POICategory.SHOPPING, 6, price=20, rating=4.5),
    ]
    intent = IntentParserAgent().parse("我想在广州永庆坊附近逛3个小时，想喝点东西但不要连续安排咖啡馆，最好有一个文化点和一个适合散步的地方")
    candidates = [(poi, 8.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in pois}).plan(intent, candidates, n_routes=1)

    assert routes
    categories = [stop.poi.category for stop in routes[0].stops]
    assert categories.count(POICategory.RESTAURANT) <= 1
    assert categories.count(POICategory.CAFE) == 1
    assert any(category in {POICategory.ATTRACTION, POICategory.ENTERTAINMENT} for category in categories)
    assert any(category == POICategory.SHOPPING for category in categories)


def test_route_planner_does_not_pad_route_with_multiple_restaurants():
    pois = [
        make_test_poi("陈添记西关老字号", POICategory.RESTAURANT, 1, price=85, rating=4.9),
        make_test_poi("东湖酒楼粤菜老字号", POICategory.RESTAURANT, 2, price=110, rating=4.8),
        make_test_poi("凤小馆顺德菜", POICategory.RESTAURANT, 3, price=95, rating=4.7),
        make_test_poi("珠影市三宫影城", POICategory.ENTERTAINMENT, 4, price=50, rating=4.6),
    ]
    intent = IntentParserAgent().parse("我想在广州永庆坊附近逛3个小时，想喝点东西，有文化点和散步地方")
    candidates = [(poi, 8.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in pois}).plan(intent, candidates, n_routes=1)

    assert routes == []


def test_route_planner_allows_explicit_restaurant_hopping():
    pois = [
        make_test_poi("老字号粤菜一店", POICategory.RESTAURANT, 1, price=90, rating=4.8),
        make_test_poi("老字号粤菜二店", POICategory.RESTAURANT, 2, price=95, rating=4.7),
        make_test_poi("永庆坊街区文化点", POICategory.ATTRACTION, 3, price=20, rating=4.6),
        make_test_poi("永庆坊街角茶饮", POICategory.CAFE, 4, price=35, rating=4.5),
    ]
    intent = IntentParserAgent().parse("广州永庆坊粤菜探店4小时，想吃两家老字号")
    candidates = [(poi, 7.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in pois}).plan(intent, candidates, n_routes=1)

    assert routes
    categories = [stop.poi.category for stop in routes[0].stops]
    assert categories.count(POICategory.RESTAURANT) >= 2
    assert any(category in {POICategory.ATTRACTION, POICategory.ENTERTAINMENT} for category in categories)


def test_route_planner_limits_coffee_bias_for_casual_long_route():
    pois = [
        make_test_poi("红门咖啡", POICategory.CAFE, 1, price=42, rating=4.9),
        make_test_poi("CAFE FLOWERYARDS", POICategory.CAFE, 2, price=48, rating=4.8),
        make_test_poi("西关84 History Art Cafe", POICategory.CAFE, 3, price=52, rating=4.7),
        make_test_poi("永庆坊", POICategory.ATTRACTION, 4, price=0, rating=4.8),
        make_test_poi("粤剧艺术博物馆", POICategory.ATTRACTION, 5, price=20, rating=4.7),
        make_test_poi("荔湾湖公园散步点", POICategory.SHOPPING, 6, price=10, rating=4.5),
        make_test_poi("西关粤菜小馆", POICategory.RESTAURANT, 7, price=90, rating=4.6),
    ]
    intent = IntentParserAgent().parse("广州永庆坊附近逛吃5小时，用户画像偏向咖啡店")
    candidates = [(poi, 9.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in pois}).plan(intent, candidates, n_routes=1)

    assert routes
    categories = [stop.poi.category for stop in routes[0].stops]
    assert categories.count(POICategory.CAFE) <= 1
    assert categories.count(POICategory.RESTAURANT) <= 1
    assert any(category in {POICategory.ATTRACTION, POICategory.ENTERTAINMENT, POICategory.SHOPPING} for category in categories)


def test_fixed_restaurant_start_counts_as_meal_but_allows_explicit_drink_stop():
    gaga = make_test_poi("gaga（金地威新中心店）", POICategory.RESTAURANT, 1, price=78, rating=4.5)
    gaga.id = "fav-gaga-jdw"
    pois = [
        make_test_poi("科技园咖啡休息点", POICategory.CAFE, 2, price=42, rating=4.7),
        make_test_poi("深圳湾艺文空间", POICategory.ATTRACTION, 3, price=20, rating=4.6),
        make_test_poi("科技园街区漫步", POICategory.SHOPPING, 4, price=20, rating=4.6),
        make_test_poi("另一家轻食餐厅", POICategory.RESTAURANT, 5, price=88, rating=4.8),
    ]
    intent = IntentParserAgent().parse("从gaga金地威新中心店出发，下午4小时想喝点东西，有文化点和散步地方")
    intent.extracted_preferences["fixed_start_poi_id"] = "fav-gaga-jdw"
    intent.extracted_preferences["pinned_policy"] = "fixed_start"
    intent.extracted_preferences["raw_query"] = "从gaga金地威新中心店出发，下午4小时想喝点东西，有文化点和散步地方"
    candidates = [(poi, 8.0 - index * 0.1) for index, poi in enumerate(pois)]
    routes = RoutePlannerAgent({poi.id: poi for poi in [gaga, *pois]}).plan(
        intent,
        candidates,
        pinned_pois=[gaga],
        n_routes=1,
    )

    assert routes
    categories = [stop.poi.category for stop in routes[0].stops]
    assert routes[0].stops[0].poi.id == "fav-gaga-jdw"
    assert categories.count(POICategory.RESTAURANT) == 1
    assert categories.count(POICategory.CAFE) == 1
    assert any(category in {POICategory.ATTRACTION, POICategory.SHOPPING} for category in categories)
