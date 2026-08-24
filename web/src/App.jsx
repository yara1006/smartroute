import React, { useEffect, useState } from "react";
import { DEFAULT_QUERY, USER_ID, SCENARIOS } from "./constants.js";
import { getJson, postJson, statusText, metricDelta } from "./api.js";
import {
  inferCityHint,
  inferAnchorText,
  contextForScenario,
  contextForReplacement,
  buildJudgeProfilePayload,
  profilesForSource,
} from "./helpers.js";
import { TopBar, ScenarioSelector } from "./components/PhoneExperience.jsx";
import PhoneExperience from "./components/PhoneExperience.jsx";
import { AgentPanel, ReplacePanel, JudgePreferenceModal } from "./components/Panels.jsx";

export default function App() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [examples, setExamples] = useState([DEFAULT_QUERY]);
  const [health, setHealth] = useState(null);
  const [plan, setPlan] = useState(null);
  const [selectedRouteIndex, setSelectedRouteIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingLabel, setLoadingLabel] = useState("");
  const [error, setError] = useState("");
  const [feedbackStatus, setFeedbackStatus] = useState("");
  const [replacement, setReplacement] = useState(null);
  const [activeScenarioId, setActiveScenarioId] = useState("search");
  const [phoneMode, setPhoneMode] = useState("entry");
  const [routeIntent, setRouteIntent] = useState(null);
  const [xiaotuanPendingIntent, setXiaotuanPendingIntent] = useState(null);
  const [xiaotuanConversation, setXiaotuanConversation] = useState([]);
  const [profileMode, setProfileMode] = useState("文艺体验型");
  const [profileSource, setProfileSource] = useState("preset");
  const [profileSources, setProfileSources] = useState(null);
  const [importedProfileId, setImportedProfileId] = useState("");
  const [adjustmentHistory, setAdjustmentHistory] = useState([]);
  const [latestAdjustment, setLatestAdjustment] = useState(null);
  const [activeRouteContext, setActiveRouteContext] = useState(contextForScenario(SCENARIOS[0], DEFAULT_QUERY));
  const [preferenceModalOpen, setPreferenceModalOpen] = useState(false);
  const [pendingPlan, setPendingPlan] = useState(null);
  const [sessionProfileReady, setSessionProfileReady] = useState(false);

  const activeScenario = SCENARIOS.find((scenario) => scenario.id === activeScenarioId) || SCENARIOS[0];
  const selectedRouteView = plan?.routes?.[selectedRouteIndex] || null;

  useEffect(() => {
    getJson("/api/health").then(setHealth).catch(() => setHealth({ status: "offline" }));
    getJson("/api/examples").then((data) => setExamples(data.examples || [DEFAULT_QUERY])).catch(() => {});
    refreshProfileSources();
  }, []);

  async function refreshProfileSources(preferredProfileId = importedProfileId) {
    try {
      const payload = await getJson("/api/profile-sources");
      setProfileSources(payload);
      const manualProfiles = profilesForSource(payload, "manual_import");
      if (!preferredProfileId && manualProfiles.length) {
        setImportedProfileId(manualProfiles[0].profile_id);
      }
      return payload;
    } catch {
      return null;
    }
  }

  async function generatePlan(
    nextQuery,
    openRoute = true,
    mode = profileMode,
    label = "规划中",
    source = profileSource,
    profileId = importedProfileId,
    nextRouteContext = activeRouteContext,
  ) {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setLoading(true);
    setLoadingLabel(label);
    setError("");
    setFeedbackStatus("");
    setReplacement(null);
    setLatestAdjustment(null);
    setActiveRouteContext(nextRouteContext);
    try {
      const payload = await postJson("/api/plan", {
        query: trimmed,
        user_id: USER_ID,
        n_routes: 2,
        profile_mode: mode,
        profile_source: source,
        profile_id: source === "manual_import" ? profileId : null,
        route_context: nextRouteContext,
      });
      const payloadWithContext = { ...payload, client_route_context: nextRouteContext };
      setPlan(payloadWithContext);
      setSelectedRouteIndex(0);
      setAdjustmentHistory([]);
      if (openRoute) {
        setPhoneMode("route");
      }
      return payloadWithContext;
    } catch (err) {
      setError(err.message || "生成失败");
      return null;
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  function appendXiaotuanRouteResult(payload, sourceQuery) {
    const routeView = payload?.routes?.[0] || null;
    setXiaotuanConversation((items) => [
      ...items,
      {
        id: `r-${Date.now()}`,
        role: "assistant",
        type: "route_result",
        text: routeView ? `已生成路线：${routeView.route.title}` : "当前没有生成完整路线",
        query: sourceQuery,
        plan: payload,
        routeView,
      },
    ]);
  }

  async function requestPlanWithPreference(nextQuery, explicitContext = null, label = "规划中", openRoute = true, inlineXiaotuan = false) {
    const nextContext = contextForScenario(activeScenario, nextQuery, explicitContext);
    if (!sessionProfileReady) {
      setPendingPlan({ query: nextQuery, context: nextContext, label, openRoute, inlineXiaotuan });
      setPreferenceModalOpen(true);
      return null;
    }
    const payload = await generatePlan(nextQuery, openRoute, profileMode, label, profileSource, importedProfileId, nextContext);
    if (inlineXiaotuan && payload) {
      appendXiaotuanRouteResult(payload, nextQuery);
    }
    return payload;
  }

  async function submitJudgePreference(answers) {
    const pending = pendingPlan || {
      query: query || activeScenario.query,
      context: activeRouteContext,
      label: "评委画像规划中",
      openRoute: true,
      inlineXiaotuan: false,
    };
    const { profile, transportStrategy } = buildJudgeProfilePayload(answers, activeScenario, pending.context);
    const nextContext = {
      ...pending.context,
      transport_strategy: transportStrategy,
    };
    setLoading(true);
    setLoadingLabel("生成评委即时画像");
    setError("");
    try {
      const response = await postJson("/api/profile/import", profile);
      const nextProfileId = response.profile.profile_id;
      await refreshProfileSources(nextProfileId);
      setProfileSource("manual_import");
      setImportedProfileId(nextProfileId);
      setSessionProfileReady(true);
      setPreferenceModalOpen(false);
      setPendingPlan(null);
      setFeedbackStatus("已生成评委即时画像，本次路线会按这些偏好规划。");
      const payload = await generatePlan(
        pending.query,
        pending.openRoute ?? true,
        profileMode,
        pending.label || "评委画像规划中",
        "manual_import",
        nextProfileId,
        nextContext,
      );
      if (pending.inlineXiaotuan && payload) {
        appendXiaotuanRouteResult(payload, pending.query);
      }
    } catch (err) {
      setError(err.message || "评委画像生成失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  function skipJudgePreference() {
    const pending = pendingPlan || {
      query: query || activeScenario.query,
      context: activeRouteContext,
      label: "规划中",
      openRoute: true,
      inlineXiaotuan: false,
    };
    setSessionProfileReady(true);
    setPreferenceModalOpen(false);
    setPendingPlan(null);
    generatePlan(
      pending.query,
      pending.openRoute ?? true,
      profileMode,
      pending.label || "规划中",
      profileSource,
      importedProfileId,
      pending.context,
    ).then((payload) => {
      if (pending.inlineXiaotuan && payload) {
        appendXiaotuanRouteResult(payload, pending.query);
      }
    });
  }

  function selectScenario(scenario) {
    setActiveScenarioId(scenario.id);
    setPhoneMode("entry");
    setQuery(scenario.query);
    setActiveRouteContext(contextForScenario(scenario, scenario.query));
    setRouteIntent(null);
    setXiaotuanPendingIntent(null);
    setXiaotuanConversation([]);
    setError("");
    setFeedbackStatus("");
    setReplacement(null);
    setLatestAdjustment(null);
  }

  function changeProfileMode(nextMode) {
    setProfileMode(nextMode);
    setProfileSource("preset");
    if (query) {
      generatePlan(query, true, nextMode, "画像切换中", "preset", null, activeRouteContext);
    }
  }

  function changeProfileSource(nextSource) {
    setProfileSource(nextSource);
    if (nextSource === "preset") {
      generatePlan(query, true, profileMode, "画像切换中", "preset", null, activeRouteContext);
      return;
    }
    const manualProfiles = profilesForSource(profileSources, "manual_import");
    const nextProfileId = importedProfileId || manualProfiles[0]?.profile_id || "";
    if (nextProfileId) {
      setImportedProfileId(nextProfileId);
      generatePlan(query, true, profileMode, "脱敏画像加载中", "manual_import", nextProfileId, activeRouteContext);
    }
  }

  function changeImportedProfile(nextProfileId) {
    setImportedProfileId(nextProfileId);
    setProfileSource("manual_import");
    if (query) {
      generatePlan(query, true, profileMode, "脱敏画像切换中", "manual_import", nextProfileId, activeRouteContext);
    }
  }

  async function importManualProfile(payload, clientError = "") {
    if (clientError) {
      setError(clientError);
      return;
    }
    setLoading(true);
    setLoadingLabel("导入脱敏画像");
    setError("");
    setFeedbackStatus("");
    try {
      const response = await postJson("/api/profile/import", payload);
      const nextProfileId = response.profile.profile_id;
      await refreshProfileSources(nextProfileId);
      setProfileSource("manual_import");
      setImportedProfileId(nextProfileId);
      setFeedbackStatus(response.safety_notice || "脱敏画像已导入。");
      await generatePlan(query || DEFAULT_QUERY, true, profileMode, "脱敏画像规划中", "manual_import", nextProfileId, activeRouteContext);
    } catch (err) {
      setError(err.message || "画像导入失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  async function askXiaotuan(nextQuery, replyType = "free_text") {
    const trimmed = nextQuery.trim();
    if (!trimmed) return;
    const previousIntent = xiaotuanPendingIntent
      || ((routeIntent?.turn_state === "collecting_slots" || routeIntent?.missing_slots?.length > 0) ? routeIntent : null);
    const previousQuery = previousIntent?.merged_query || previousIntent?.planning_query || "";
    const currentAnchor = inferAnchorText(trimmed);
    const previousLocation = previousIntent?.filled_slots?.location || null;
    const contextAnchor = currentAnchor || previousLocation || null;
    const contextCity = inferCityHint(trimmed)
      || inferCityHint(currentAnchor || "")
      || (previousIntent ? inferCityHint(previousQuery) : null)
      || (previousIntent ? activeRouteContext?.city_hint : null)
      || activeScenario.routeContext?.city_hint
      || "深圳";
    setQuery(previousQuery || trimmed);
    setLoading(true);
    setLoadingLabel("小团识别中");
    setError("");
    setXiaotuanConversation((items) => [...items, { id: `u-${Date.now()}`, role: "user", text: trimmed }]);
    try {
      const payload = await postJson("/api/route-intent", {
        query: trimmed,
        source: "xiaotuan",
        conversation_id: previousIntent?.conversation_id || null,
        previous_intent: previousIntent,
        user_reply_type: replyType,
        context: {
          entry: "问小团",
          current_city: contextCity,
          anchor_text: contextAnchor,
          previous_filled_slots: previousIntent?.filled_slots || null,
          product: "meituan",
        },
      });
      setRouteIntent(payload);
      if (payload.turn_state === "collecting_slots" || payload.missing_slots?.length > 0) {
        setXiaotuanPendingIntent(payload);
      } else {
        setXiaotuanPendingIntent(null);
      }
      const assistantText = payload.clarification_question
        || (payload.action === "open_plugin" ? "信息已经补齐，我来帮你生成路线。" : payload.reason);
      setXiaotuanConversation((items) => [...items, { id: `a-${Date.now()}`, role: "assistant", text: assistantText }]);
      if (payload.action === "open_plugin") {
        const planningQuery = payload.merged_query || payload.planning_query || trimmed;
        const plannedAnchor = payload.filled_slots?.location || inferAnchorText(planningQuery) || currentAnchor;
        const nextContext = contextForScenario(activeScenario, planningQuery, {
          source: "xiaotuan",
          city_hint: inferCityHint(planningQuery) || inferCityHint(plannedAnchor || "") || contextCity,
          anchor_text: plannedAnchor,
        });
        setXiaotuanPendingIntent(null);
        const routePayload = await generatePlan(
          planningQuery,
          false,
          profileMode,
          "SmartRoute 调用中",
          profileSource,
          importedProfileId,
          nextContext,
        );
        if (routePayload) {
          appendXiaotuanRouteResult(routePayload, planningQuery);
        }
      }
    } catch (err) {
      setError(err.message || "意图识别失败");
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  async function openXiaotuanInlineRoute(nextQuery, explicitContext = null) {
    const planningQuery = nextQuery || routeIntent?.merged_query || routeIntent?.planning_query || query;
    const plannedAnchor = routeIntent?.filled_slots?.location || inferAnchorText(planningQuery);
    const nextContext = contextForScenario(activeScenario, planningQuery, {
      source: "xiaotuan",
      city_hint: inferCityHint(planningQuery) || inferCityHint(plannedAnchor || "") || activeScenario.routeContext?.city_hint || "深圳",
      anchor_text: plannedAnchor,
      ...(explicitContext || {}),
    });
    const routePayload = await generatePlan(
      planningQuery,
      false,
      profileMode,
      "SmartRoute 调用中",
      profileSource,
      importedProfileId,
      nextContext,
    );
    if (routePayload) {
      appendXiaotuanRouteResult(routePayload, planningQuery);
    }
  }

  async function adjustRoute(instruction, options = {}) {
    const basePlan = options.planOverride || plan;
    const baseRouteView = options.routeViewOverride || selectedRouteView;
    if (!baseRouteView || !basePlan) return;
    setLoading(true);
    setLoadingLabel("局部调整中");
    setError("");
    setFeedbackStatus("");
    try {
      const requestRouteContext = options.routeContextOverride || basePlan.client_route_context || activeRouteContext;
      const payload = await postJson("/api/adjust", {
        query: basePlan.query || query,
        instruction,
        route: baseRouteView.route,
        user_id: USER_ID,
        profile_mode: profileMode,
        profile_source: profileSource,
        profile_id: profileSource === "manual_import" ? importedProfileId : null,
        route_context: requestRouteContext,
      });
      const baseRoutes = basePlan.routes || [];
      const matchingIndex = baseRoutes.findIndex((routeView) => routeView.route.id === baseRouteView.route.id);
      const updateIndex = matchingIndex >= 0 ? matchingIndex : selectedRouteIndex;
      const nextRoutes = baseRoutes.map((routeView, index) => (
        index === updateIndex ? payload.route : routeView
      ));
      if (!nextRoutes.length) {
        nextRoutes.push(payload.route);
      }
      const nextPlan = {
        ...basePlan,
        routes: nextRoutes,
        client_route_context: requestRouteContext,
        planning_time_ms: payload.planning_time_ms,
        follow_up_question: payload.follow_up_question,
        follow_up: payload.follow_up,
        constraint_conflicts: payload.constraint_conflicts,
        route_completeness: payload.route_completeness,
        trace: [...(basePlan.trace || []), `实时调整：${payload.adjustment_summary}`],
        tool_trace: basePlan.tool_trace || [],
      };
      setPlan({
        ...nextPlan,
      });
      setSelectedRouteIndex(Math.max(0, updateIndex));
      setLatestAdjustment(payload);
      setFeedbackStatus(`${statusText(payload.adjustment_status)}：${payload.adjustment_summary}`);
      const deltas = payload.metric_deltas || {};
      setAdjustmentHistory((items) => [
        ...items,
        `${payload.adjustment_history_item}（等位 ${metricDelta(deltas.total_wait_minutes)} / 人均 ${metricDelta(deltas.total_cost_per_person, "¥")} / 移动 ${metricDelta(deltas.total_transit_minutes)}）`,
      ]);
      if (options.appendToXiaotuan) {
        setXiaotuanConversation((items) => [
          ...items,
          {
            id: `adj-${Date.now()}`,
            role: "assistant",
            type: "adjustment_result",
            text: payload.adjustment_summary,
            adjustment: payload,
          },
          {
            id: `r-${Date.now() + 1}`,
            role: "assistant",
            type: "route_result",
            text: `已调整路线：${payload.route.route.title}`,
            query: basePlan.query || query,
            plan: nextPlan,
            routeView: payload.route,
          },
        ]);
      }
      return payload;
    } catch (err) {
      setError(err.message || "调整失败");
      return null;
    } finally {
      setLoading(false);
      setLoadingLabel("");
    }
  }

  function adjustRouteFromXiaotuan(instruction, options = {}) {
    return adjustRoute(instruction, { ...options, appendToXiaotuan: true });
  }

  async function sendFeedback(value, routeViewOverride = null) {
    const targetRouteView = routeViewOverride || selectedRouteView;
    if (!targetRouteView) return;
    setFeedbackStatus("写入中...");
    try {
      await postJson("/api/feedback", {
        user_id: USER_ID,
        route: targetRouteView.route,
        feedback: value,
      });
      setFeedbackStatus(value === 1 ? "已记录喜欢，下次会提高相似 POI 权重。" : "已记录不合适，下次会降低相似路线。");
    } catch (err) {
      setFeedbackStatus(err.message || "反馈写入失败");
    }
  }

  async function openReplace(stop) {
    if (!selectedRouteView || !plan) return;
    setReplacement({ loading: true, stop, options: [] });
    setLoadingLabel("搜索替换项");
    try {
      const payload = await postJson("/api/replace", {
        query: plan.query,
        route: selectedRouteView.route,
        stop_order: stop.order,
        user_id: USER_ID,
        profile_mode: profileMode,
        profile_source: profileSource,
        profile_id: profileSource === "manual_import" ? importedProfileId : null,
        route_context: contextForReplacement(stop, plan, activeRouteContext),
      });
      setReplacement({ loading: false, stop, options: payload.options || [] });
    } catch (err) {
      setReplacement({ loading: false, stop, options: [], error: err.message });
    } finally {
      setLoadingLabel("");
    }
  }

  function applyReplacement(option) {
    if (!plan || !selectedRouteView || !replacement) return;
    const oldStop = replacement.stop;
      const nextRoutes = plan.routes.map((routeView, index) => {
      if (index !== selectedRouteIndex) return routeView;
      const route = JSON.parse(JSON.stringify(routeView.route));
      const stop = route.stops.find((item) => item.order === oldStop.order);
      if (!stop) return routeView;
      const oldPrice = stop.poi.price_per_person;
      const oldWait = stop.wait_minutes;
      stop.poi = option.poi;
      stop.wait_minutes = option.poi.avg_wait_minutes;
      stop.duration_minutes = Math.max(30, Math.min(option.poi.visit_duration_minutes, 100));
      stop.tips = "已按同类 POI 替换，预算与等待指标同步更新。";
      route.id = `${route.id}-r${oldStop.order}`;
      route.total_cost_per_person = Math.round((route.total_cost_per_person + option.poi.price_per_person - oldPrice) * 10) / 10;
      route.total_wait_minutes = Math.max(0, route.total_wait_minutes + option.poi.avg_wait_minutes - oldWait);
      route.description = `已将第 ${oldStop.order} 站替换为 ${option.poi.name}，用于演示可执行路线的即时调整。`;
      return {
        ...routeView,
        route,
        insight: {
          ...routeView.insight,
          route_id: route.id,
          explanation: `替换影响：${option.impact_summary}。`,
        },
      };
    });
    setPlan({ ...plan, routes: nextRoutes });
    setLatestAdjustment(null);
    setAdjustmentHistory((items) => [...items, `替换站点：${option.impact_summary}`]);
    setReplacement(null);
  }

  return (
    <main>
      <TopBar health={health} />

      {error && <div className="error-banner">{error}</div>}
      {feedbackStatus && <div className="feedback-toast">{feedbackStatus}</div>}

      <div className="demo-layout">
        <ScenarioSelector
          scenarios={SCENARIOS}
          activeScenarioId={activeScenarioId}
          onSelect={selectScenario}
          health={health}
        />
        <PhoneExperience
          scenario={activeScenario}
          mode={phoneMode}
          plan={plan}
          routeView={selectedRouteView}
          loading={loading}
          xiaotuanConversation={xiaotuanConversation}
          routeIntent={routeIntent}
          onOpenRoute={(nextQuery, explicitContext) => {
            if (activeScenario.id === "xiaotuan") {
              openXiaotuanInlineRoute(nextQuery, explicitContext);
              return;
            }
            requestPlanWithPreference(nextQuery, explicitContext, "规划中");
          }}
          onAskXiaotuan={askXiaotuan}
          profileMode={profileMode}
          profileSource={profileSource}
          profileSources={profileSources}
          importedProfileId={importedProfileId}
          onPresetProfileChange={changeProfileMode}
          onProfileSourceChange={changeProfileSource}
          onImportedProfileChange={changeImportedProfile}
          onImportProfile={importManualProfile}
          onReplace={openReplace}
          onFeedback={sendFeedback}
          onAdjust={adjustRoute}
          onXiaotuanFeedback={sendFeedback}
          onXiaotuanAdjust={adjustRouteFromXiaotuan}
          adjustmentHistory={adjustmentHistory}
          latestAdjustment={latestAdjustment}
          loadingLabel={loadingLabel}
        />
        <AgentPanel
          scenario={activeScenario}
          routeIntent={routeIntent}
          plan={plan}
          routeView={selectedRouteView}
          routes={plan?.routes || []}
          selectedRouteIndex={selectedRouteIndex}
          setSelectedRouteIndex={setSelectedRouteIndex}
          adjustmentHistory={adjustmentHistory}
          latestAdjustment={latestAdjustment}
        />
      </div>
      <ReplacePanel replacement={replacement} onClose={() => setReplacement(null)} onApply={applyReplacement} />
      <JudgePreferenceModal
        open={preferenceModalOpen}
        scenario={activeScenario}
        pendingQuery={pendingPlan?.query}
        onSubmit={submitJudgePreference}
        onSkip={skipJudgePreference}
        loading={loading}
      />
    </main>
  );
}
