import { describe, it, expect } from "vitest";
import {
  DEFAULT_MAP_CENTER,
  USER_ID,
  DEFAULT_QUERY,
  APP_CURRENT_CITY,
  PROFILE_MODES,
  FAVORITE_POIS,
  DETAIL_POI,
  SCENARIOS,
  JUDGE_PROFILE_QUESTIONS,
  DEFAULT_JUDGE_ANSWERS,
  IMPORT_PROFILE_TEMPLATE,
} from "../constants.js";

describe("constants", () => {
  it("DEFAULT_MAP_CENTER is [lng, lat] for 深圳", () => {
    expect(DEFAULT_MAP_CENTER).toHaveLength(2);
    expect(DEFAULT_MAP_CENTER[0]).toBeGreaterThan(100);
    expect(DEFAULT_MAP_CENTER[1]).toBeGreaterThan(20);
  });

  it("USER_ID is a non-empty string", () => {
    expect(typeof USER_ID).toBe("string");
    expect(USER_ID.length).toBeGreaterThan(0);
  });

  it("DEFAULT_QUERY contains 路线", () => {
    expect(DEFAULT_QUERY).toContain("路线");
  });

  it("APP_CURRENT_CITY is 深圳", () => {
    expect(APP_CURRENT_CITY).toBe("深圳");
  });

  it("PROFILE_MODES has 3 modes", () => {
    expect(PROFILE_MODES).toHaveLength(3);
    expect(PROFILE_MODES).toContain("低排队务实型");
    expect(PROFILE_MODES).toContain("文艺体验型");
    expect(PROFILE_MODES).toContain("带爸妈轻松型");
  });
});

describe("FAVORITE_POIS", () => {
  it("contains 4 POIs", () => {
    expect(FAVORITE_POIS).toHaveLength(4);
  });

  it("each POI has required fields", () => {
    for (const poi of FAVORITE_POIS) {
      expect(poi).toHaveProperty("id");
      expect(poi).toHaveProperty("name");
      expect(poi).toHaveProperty("category");
      expect(poi).toHaveProperty("latitude");
      expect(poi).toHaveProperty("longitude");
      expect(poi).toHaveProperty("price_per_person");
    }
  });

  it("DETAIL_POI is the second FAVORITE_POI (gaga)", () => {
    expect(DETAIL_POI).toBe(FAVORITE_POIS[1]);
    expect(DETAIL_POI.name).toContain("gaga");
  });
});

describe("SCENARIOS", () => {
  it("contains 4 scenarios", () => {
    expect(SCENARIOS).toHaveLength(4);
  });

  it("has search, xiaotuan, favorites, detail", () => {
    const ids = SCENARIOS.map((s) => s.id);
    expect(ids).toContain("search");
    expect(ids).toContain("xiaotuan");
    expect(ids).toContain("favorites");
    expect(ids).toContain("detail");
  });

  it("each scenario has query and routeContext", () => {
    for (const s of SCENARIOS) {
      expect(typeof s.query).toBe("string");
      expect(s.routeContext).toBeDefined();
      expect(s.routeContext).toHaveProperty("source");
    }
  });

  it("detail scenario has fixed_start_poi_id", () => {
    const detail = SCENARIOS.find((s) => s.id === "detail");
    expect(detail.routeContext.fixed_start_poi_id).toBeTruthy();
    expect(detail.routeContext.pinned_policy).toBe("fixed_start");
  });
});

describe("JUDGE_PROFILE_QUESTIONS", () => {
  it("has 5 questions", () => {
    expect(JUDGE_PROFILE_QUESTIONS).toHaveLength(5);
  });

  it("each question has key, title, and 3+ options", () => {
    for (const q of JUDGE_PROFILE_QUESTIONS) {
      expect(q).toHaveProperty("key");
      expect(q).toHaveProperty("title");
      expect(q.options.length).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("DEFAULT_JUDGE_ANSWERS", () => {
  it("has all required keys", () => {
    expect(DEFAULT_JUDGE_ANSWERS).toHaveProperty("companion");
    expect(DEFAULT_JUDGE_ANSWERS).toHaveProperty("budget");
    expect(DEFAULT_JUDGE_ANSWERS).toHaveProperty("queue");
    expect(DEFAULT_JUDGE_ANSWERS).toHaveProperty("mobility");
    expect(DEFAULT_JUDGE_ANSWERS).toHaveProperty("content");
  });
});

describe("IMPORT_PROFILE_TEMPLATE", () => {
  it("is valid JSON", () => {
    const parsed = JSON.parse(IMPORT_PROFILE_TEMPLATE);
    expect(parsed).toHaveProperty("display_name");
    expect(parsed).toHaveProperty("recent_searches");
    expect(parsed).toHaveProperty("favorite_categories");
  });
});
