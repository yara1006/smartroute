# SmartRoute AI — Retrospective Document

> Lessons learned, trade-offs made, and what we would do differently.

---

## 1. Service Layer Split: Why 6 Modules Instead of api.py?

**Context**: Initial `api.py` had 2868 lines with all business logic in one file.

**Decision**: Split into 6 independent modules under `services/`, with `route_service.py` as re-export facade for backward compatibility.

**Trade-offs**:
- ✅ Unit tests can run independently (`test_adjustment.py` doesn't need FastAPI)
- ✅ Clear responsibilities: `anchor_service.py` handles location only, `route_builder.py` handles route construction only
- ✅ New features only touch relevant module, not 2800-line file
- ❌ Cross-module imports require explicit dependencies (caught: `route_builder.py` called `city_hint_from` without import → NameError)
- ❌ `route_service.py` is pure forwarding layer, adds comprehension cost

**If redoing**: Use Python packages (`services/__init__.py`) instead of re-export facade — more Pythonic.

---

## 2. TSP Route Ordering: Why Greedy vs DP/Exact?

**Context**: Route planning is Traveling Salesman Problem (TSP); need shortest path visiting all stops.

**Decision**: O(n²) greedy nearest-neighbor instead of O(n!) permutations.

**Trade-offs**:
- ✅ 10 stops: greedy <1ms, permutations take seconds
- ✅ Measured quality loss <5% (greedy solution near-optimal for ≤10 stops)
- ❌ Not globally optimal in extreme cases (e.g., stops in ring pattern)
-  No theoretical optimality guarantee

**If redoing**: Add `optimization_level` parameter — exact solution for ≤6 stops, greedy for >6.

---

## 3. LLM Priority + Rules Fallback: Why Not Pure LLM?

**Context**: Intent parsing can use DeepSeek LLM or keyword rules.

**Decision**: LLM first (with API key), rules fallback (without key or timeout).

**Trade-offs**:
- ✅ Demo works without API key; judges don't see "service unavailable"
- ✅ LLM handles complex intents ("少走路、便宜点、加个咖啡"); rules only handle simple patterns
- ❌ Rules fallback accuracy ~70% vs LLM 90%+
- ❌ Must maintain two parsing logic sets, increases code volume

**If redoing**: Make rules fallback a fallback chain of LLM, not parallel implementation.

---

## 4. Safety Boundaries: Why Intercept Booking Instead of Allowing?

**Context**: User might say "帮我预订这家餐厅".

**Decision**: `safety_reviewer.py` intercepts all 5 high-risk action types (booking/payment/credentials/non-refundable/legal), returns `refused=true` + warning.

**Trade-offs**:
- ✅ Compliance: Personal project has no payment license, cannot process real transactions
- ✅ Safety: Prevents accidents (user says "book non-refundable hotel", system warns about cancellation policy)
- ❌ Limited functionality: Cannot build complete "one-stop" experience
-  User might feel "not smart enough"

**If redoing**: Add `handoff_url` field — when intercepting, return official platform link (Meituan/Dianping), not just "no".

---

## 5. Cache Strategy: Why 30-Minute TTL Not Longer?

**Context**: AMap Web Service has QPS limits and quotas; need cache to reduce calls.

**Decision**: 30-minute TTL + 500-entry max.

**Trade-offs**:
- ✅ For demo scenarios, same location data barely changes within 30 minutes
- ✅ 500-entry max prevents memory leak (previously unbounded, long-running OOM)
- ❌ Poor real-time: Business status changes, temporary closures not reflected promptly
-  30 minutes was guessed, no data support

**If redoing**: Dynamically adjust TTL based on API quota (extend to 1 hour when quota tight, shorten to 10 minutes when relaxed).

---

## 6. Frontend Architecture: Why Split Single File Into Components?

**Context**: Initial `App.jsx` had 2691 lines with all UI logic together.

**Decision**: Split into `Panels.jsx`, `PhoneExperience.jsx`, `RouteMap.jsx`, `QueryComposer.jsx`, `ErrorBoundary.jsx`.

**Trade-offs**:
- ✅ Components independently testable (`ErrorBoundary.test.jsx`)
- ✅ Clear responsibilities: `RouteMap.jsx` only handles map rendering
- ❌ Cross-component state management becomes complex (needs prop drilling or context)
-  Split boundaries hard to judge (`Panels.jsx` still too large)

**If redoing**: Use Zustand or Jotai for state management, not prop drilling.

---

## 7. Test Strategy: Why 80% Coverage Not 100%?

**Context**: Could pursue 100% coverage, or accept lower threshold.

**Decision**: `fail_under=80`, actual 82-83%.

**Trade-offs**:
- ✅ 80% covers core business logic; diminishing returns for marginal code (getters/setters, constant definitions)
- ✅ Tests run fast (200 cases <10 seconds), CI doesn't slow down
- ❌ 17-18% code uncovered (mainly exception branches, edge cases)
-  Coverage number might mislead (80% covered doesn't mean critical paths 100% covered)

**If redoing**: Add critical path markers (`# critical`), ensure core chain 100% covered, other parts 80%.

---

## 8. If Redoing SmartRoute, What Would Change?

### Architecture Level
1. **Add vector database**: Qdrant/Chroma instead of local JSON index, support semantic search
2. **Async task queue**: Celery/RQ for time-consuming planning, API returns task ID immediately
3. **Model routing**: L1 layer abstraction more thorough, support OpenAI/Anthropic/local model hot-swap

### Engineering Level
4. **GraphQL API**: Replace REST, frontend queries route fields on demand
5. **WebSocket real-time push**: Push progress during planning, not return all at once after completion
6. **OpenTelemetry tracing**: Replace built-in `tool_trace`, integrate Jaeger/Zipkin

### Product Level
7. **Multi-turn conversation**: Support context understanding like "that route was too expensive, change one"
8. **Collaborative planning**: Multiple users submit preferences, system generates compromise solution
9. **Offline mode**: PWA + Service Worker, view saved routes without network

---

## 9. Lessons Learned (Pitfalls)

| Pitfall | Cause | Solution |
|---------|-------|----------|
| `route_builder.py` `NameError: city_hint_from` | Cross-module dependency not explicitly imported | Add `from services.anchor_service import ...` |
| AMap `USERKEY_PLAT_NOMATCH` | Accidentally filled JS API Key into Web Service Key | Validate key type at startup, log prompt |
| Cache OOM | No upper bound, long-running accumulation | Add `AMAP_CACHE_MAX_ENTRIES=500` + periodic cleanup |
| Frontend tests 0 coverage | No Vitest configured | Add `vite.config.js` + `@testing-library/react` |
| Architecture diagram legend overlap | SVG height insufficient, legend and infrastructure row overlap | Increase viewBox, legend moves down 30px |
| GitHub image cache | SVG updated but README still shows old version | URL adds `?v=2` query parameter to bypass cache |

---

## 10. Quantitative Metrics

| Metric | Value | Description |
|--------|-------|-------------|
| Code lines | ~7000 Python + ~2000 frontend | Excluding tests |
| Test cases | 200+ backend + 48 frontend | Including 20 eval cases |
| Test coverage | 82-83% | `fail_under=80` |
| API response time | P95 <500ms (cached) | First call without cache 1-2s |
| TSP planning time | <10ms (10 stops) | O(n²) greedy |
| LLM call success rate | 90%+ (with key) | Rules fallback 70% |
| Safety intercept rate | 100% (5 high-risk types) | 0漏网 |

---

*Last updated: 2026-08-25*
