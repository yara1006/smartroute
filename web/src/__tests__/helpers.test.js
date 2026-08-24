import { describe, it, expect } from "vitest";
import {
  inferCityHint,
  cleanAnchorCandidate,
  inferAnchorText,
  isLikelyPlaceAnchor,
  contextForScenario,
  profilesForSource,
} from "../helpers.js";

describe("inferCityHint", () => {
  it("returns 深圳 for 深圳大学", () => {
    expect(inferCityHint("深圳大学附近玩")).toBe("深圳");
  });

  it("returns 深圳 for 科技园", () => {
    expect(inferCityHint("科技园附近")).toBe("深圳");
  });

  it("returns 北京 for 三里屯", () => {
    expect(inferCityHint("三里屯下午安排")).toBe("北京");
  });

  it("returns 广州 for 永庆坊", () => {
    expect(inferCityHint("永庆坊附近")).toBe("广州");
  });

  it("returns 上海 for 外滩", () => {
    expect(inferCityHint("外滩附近")).toBe("上海");
  });

  it("returns null for unknown location", () => {
    expect(inferCityHint("随便逛逛")).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(inferCityHint("")).toBeNull();
  });
});

describe("cleanAnchorCandidate", () => {
  it("strips leading 去/想去 prefixes", () => {
    expect(cleanAnchorCandidate("想去深圳大学")).toBe("深圳大学");
  });

  it("strips leading 我要去", () => {
    expect(cleanAnchorCandidate("我要去gaga")).toBe("gaga");
  });

  it("strips surrounding punctuation", () => {
    expect(cleanAnchorCandidate("，深圳大学，")).toBe("深圳大学");
  });

  it("truncates to 24 characters", () => {
    const long = "A".repeat(30);
    expect(cleanAnchorCandidate(long).length).toBeLessThanOrEqual(24);
  });

  it("returns empty string for empty input", () => {
    expect(cleanAnchorCandidate("")).toBe("");
  });
});

describe("inferAnchorText", () => {
  it("returns 万象天地 for 深圳万象天地", () => {
    expect(inferAnchorText("深圳万象天地附近")).toBe("万象天地");
  });

  it("returns 深圳大学 for 深圳大学附近", () => {
    expect(inferAnchorText("深圳大学附近")).toBe("深圳大学");
  });

  it("extracts anchor from 附近 pattern", () => {
    const result = inferAnchorText("科技园附近玩");
    expect(result).toBe("科技园");
  });

  it("extracts anchor from 从...出发 pattern", () => {
    const result = inferAnchorText("从深圳大学出发");
    expect(result).toBe("深圳大学");
  });

  it("returns null for text without anchor", () => {
    expect(inferAnchorText("帮我安排")).toBeNull();
  });
});

describe("isLikelyPlaceAnchor", () => {
  it("returns true for 深圳大学", () => {
    expect(isLikelyPlaceAnchor("深圳大学")).toBe(true);
  });

  it("returns true for 万象天地", () => {
    expect(isLikelyPlaceAnchor("万象天地")).toBe(true);
  });

  it("returns true for 南山博物馆", () => {
    expect(isLikelyPlaceAnchor("南山博物馆")).toBe(true);
  });

  it("returns false for too short text", () => {
    expect(isLikelyPlaceAnchor("大")).toBe(false);
  });

  it("returns false for non-place words", () => {
    expect(isLikelyPlaceAnchor("下午三小时")).toBe(false);
  });

  it("returns false for words with 附近", () => {
    expect(isLikelyPlaceAnchor("附近")).toBe(false);
  });
});

describe("contextForScenario", () => {
  it("uses scenario routeContext as base", () => {
    const scenario = {
      id: "search",
      query: "深圳大学附近",
      routeContext: { source: "search", city_hint: "深圳" },
    };
    const ctx = contextForScenario(scenario);
    expect(ctx.source).toBe("search");
    expect(ctx.city_hint).toBe("深圳");
  });

  it("infers city from query when not in context", () => {
    const scenario = { id: "manual", query: "三里屯附近" };
    const ctx = contextForScenario(scenario);
    expect(ctx.city_hint).toBe("北京");
  });

  it("uses explicit context when provided", () => {
    const ctx = contextForScenario({}, "", { city_hint: "广州" });
    expect(ctx.city_hint).toBe("广州");
  });

  it("returns empty selected_pois by default", () => {
    const ctx = contextForScenario({});
    expect(ctx.selected_pois).toEqual([]);
  });
});

describe("profilesForSource", () => {
  it("returns profiles for matching source", () => {
    const data = {
      sources: [
        { source: "preset", profiles: [{ id: "a" }, { id: "b" }] },
        { source: "manual_import", profiles: [{ id: "c" }] },
      ],
    };
    expect(profilesForSource(data, "preset")).toEqual([{ id: "a" }, { id: "b" }]);
  });

  it("returns empty array for unknown source", () => {
    const data = { sources: [{ source: "preset", profiles: [] }] };
    expect(profilesForSource(data, "unknown")).toEqual([]);
  });

  it("returns empty array for null input", () => {
    expect(profilesForSource(null, "preset")).toEqual([]);
  });
});
