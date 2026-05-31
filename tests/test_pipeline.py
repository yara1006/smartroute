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
