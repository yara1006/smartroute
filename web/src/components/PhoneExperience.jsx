import React, { useEffect, useState } from "react";
import { APP_CURRENT_CITY, FAVORITE_POIS, DETAIL_POI } from "../constants.js";
import { postJson, money, minutes, statusText, metricDelta } from "../api.js";
import { inferCityHint } from "../helpers.js";
import RouteMap from "./RouteMap.jsx";
import SmartRouteRoutePage from "./Panels.jsx";

export function TopBar({ health }) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">SR</div>
        <div>
          <strong>SmartRoute AI</strong>
          <span>美团原生路线规划 Agent</span>
        </div>
      </div>
      <div className="backend-pill">
        <span className={health?.status === "ok" ? "dot live" : "dot"} />
        <span>真实后端数据</span>
        <b>{health?.poi_count ? `${health.poi_count} POI · 高德${health?.amap_web_service === "configured" ? "已接" : "兜底"} · DeepSeek${health?.deepseek === "configured" ? "已接" : "兜底"}` : "连接中"}</b>
      </div>
    </header>
  );
}

function SmartRouteEntryCard({ title, text, action, onOpen, loading }) {
  return (
    <article className="plugin-card">
      <div className="plugin-badge">SmartRoute</div>
      <h3>{title}</h3>
      <p>{text}</p>
      <button onClick={onOpen} disabled={loading}>{loading ? "生成中" : action}</button>
    </article>
  );
}

function InlineAdjustmentResultCard({ adjustment }) {
  if (!adjustment) return null;
  return (
    <article className={`xiaotuan-adjust-card ${adjustment.adjustment_status || ""}`}>
      <div>
        <span>{statusText(adjustment.adjustment_status)}</span>
        <strong>{adjustment.adjustment_summary}</strong>
      </div>
      <div className="xiaotuan-adjust-deltas">
        <em>等位 {metricDelta(adjustment.metric_deltas?.total_wait_minutes)}</em>
        <em>人均 {metricDelta(adjustment.metric_deltas?.total_cost_per_person, "¥")}</em>
        <em>移动 {metricDelta(adjustment.metric_deltas?.total_transit_minutes)}</em>
      </div>
      {adjustment.changed_stops?.length > 0 && (
        <div className="xiaotuan-changed-stops">
          {adjustment.changed_stops.slice(0, 2).map((change) => (
            <p key={`${change.order}-${change.action}`}>
              第{change.order}站：{change.before_poi || "新增"} → {change.after_poi || "移除"}
            </p>
          ))}
        </div>
      )}
      {adjustment.suggested_relaxations?.length > 0 && (
        <div className="xiaotuan-relaxations">
          {adjustment.suggested_relaxations.slice(0, 2).map((item) => <p key={item}>{item}</p>)}
        </div>
      )}
    </article>
  );
}

function InlineRouteResultCard({ message, isLatest, onFeedback, onAdjust, loading }) {
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const routeView = message.routeView;
  const plan = message.plan;
  const route = routeView?.route;
  const stops = route?.stops || [];
  const visibleStops = expanded ? stops : stops.slice(0, 4);
  const quickAdjustments = ["少走路", "不要排队", "便宜点", "不要这么多咖啡", "换个文化点"];

  function submit(value = draft) {
    const trimmed = value.trim();
    if (!trimmed) return;
    onAdjust(trimmed, { planOverride: plan, routeViewOverride: routeView, routeContextOverride: plan?.client_route_context });
    setDraft("");
  }

  if (!routeView) {
    return (
      <article className="xiaotuan-route-card empty">
        <span>SmartRoute 已完成分析</span>
        <h3>当前没有生成完整路线</h3>
        <p>{plan?.constraint_conflicts?.join("；") || "真实地点候选不足，可以补充区域、延长时间或放宽活动类型。"}</p>
      </article>
    );
  }

  return (
    <article className="xiaotuan-route-card">
      <button className="xiaotuan-analysis done" type="button">
        <span>已完成分析</span>
        <b>›</b>
      </button>
      <p className="xiaotuan-route-summary">
        我按你的地点、时间和偏好，把附近真实 POI 串成一条可执行路线。优先避免连续同类店铺，并保留后续可调整空间。
      </p>
      <RouteMap route={route} />
      <div className="xiaotuan-route-title">
        <div>
          <span>推荐路线</span>
          <h3>{route.title}</h3>
        </div>
        <strong>{routeView.insight?.wait_status || "可执行"}</strong>
      </div>
      <div className="xiaotuan-route-metrics">
        <span>可信度 {routeView.insight?.confidence_score ?? "--"}</span>
        <span>{minutes(route.total_time_minutes)}</span>
        <span>人均 {money(route.total_cost_per_person)}</span>
        <span>等位 {route.total_wait_minutes}m</span>
      </div>
      <div className="xiaotuan-inline-stops">
        {visibleStops.map((stop) => (
          <div className="xiaotuan-inline-stop" key={`${message.id}-${stop.order}-${stop.poi.id}`}>
            <b>{stop.order}</b>
            <div>
              <h4>{stop.poi.name}</h4>
              <p>{stop.arrival_time} - {stop.departure_time} · {stop.poi.category} · 评分 {stop.poi.rating}</p>
              <small>{stop.tips || stop.poi.ugc_summary}</small>
            </div>
          </div>
        ))}
      </div>
      {stops.length > 4 && (
        <button className="xiaotuan-expand-route" type="button" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "收起路线" : `展开全部 ${stops.length} 站`}
        </button>
      )}
      <div className="xiaotuan-route-actions">
        <button type="button" onClick={() => onFeedback(1, routeView)} disabled={loading}>喜欢</button>
        <button type="button" onClick={() => onFeedback(-1, routeView)} disabled={loading}>不合适</button>
      </div>
      {isLatest && (
        <div className="xiaotuan-inline-adjust">
          <div>
            {quickAdjustments.map((item) => (
              <button key={item} type="button" onClick={() => submit(item)} disabled={loading}>{item}</button>
            ))}
          </div>
          <label>
            <input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") submit();
              }}
              placeholder="继续调整这条路线"
            />
            <button type="button" onClick={() => submit()} disabled={loading || !draft.trim()}>
              {loading ? "调整中" : "调整"}
            </button>
          </label>
        </div>
      )}
    </article>
  );
}

function SearchScene({ scenario, onOpen, loading }) {
  const historyTerms = ["粤菜", "文化点", "散步", "低排队"];
  const [searchText, setSearchText] = useState("广州永庆坊附近逛吃3小时");
  const [preview, setPreview] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");

  async function loadPreview(nextText = searchText) {
    const trimmed = nextText.trim();
    if (!trimmed) return;
    setPreviewLoading(true);
    setPreviewError("");
    try {
      const payload = await postJson("/api/search-preview", {
        query: trimmed,
        history_terms: historyTerms,
        city_hint: inferCityHint(trimmed) || scenario.routeContext?.city_hint || APP_CURRENT_CITY,
      });
      setPreview(payload);
      const defaults = (payload.route_context?.selected_pois || []).map((poi) => poi.id);
      setSelectedIds(defaults.length ? defaults : (payload.candidates || []).slice(0, 4).map((item) => item.poi.id));
    } catch (err) {
      setPreviewError(err.message || "搜索预览失败");
      setPreview(null);
      setSelectedIds([]);
    } finally {
      setPreviewLoading(false);
    }
  }

  useEffect(() => {
    loadPreview(searchText);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const candidates = preview?.candidates || [];
  const selectedPois = candidates
    .filter((item) => selectedIds.includes(item.poi.id))
    .map((item) => item.poi);
  const routeContext = preview?.route_context
    ? { ...preview.route_context, selected_pois: selectedPois }
    : scenario.routeContext;
  const routeQuery = `${searchText}，优先参考我勾选的地点生成一条可执行路线`;

  function toggleCandidate(id) {
    setSelectedIds((ids) => {
      if (ids.includes(id)) return ids.filter((item) => item !== id);
      if (ids.length >= 5) return ids;
      return [...ids, id];
    });
  }

  return (
    <div className="meituan-page">
      <div className="mt-header">
        <strong>搜索</strong>
        <span>问小团</span>
      </div>
      <label className="mt-searchbar interactive">
        <input
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") loadPreview();
          }}
          placeholder="输入商圈/地点/想法"
        />
        <button type="button" onClick={() => loadPreview()} disabled={previewLoading}>
          {previewLoading ? "搜索中" : "搜索"}
        </button>
      </label>
      <section className="mt-section">
        <h3>历史搜索</h3>
        <div className="mt-chips">
          {["永庆坊", ...historyTerms].map((term) => <span key={term}>{term}</span>)}
        </div>
      </section>
      <SmartRouteEntryCard
        title={preview?.trigger_title || "搜索后生成路线"}
        text={preview?.trigger_text || "先从搜索结果和历史偏好中召回真实 POI，再优先参考你勾选的地点生成路线。"}
        action="智能排路线"
        onOpen={() => onOpen(routeQuery, routeContext)}
        loading={loading || previewLoading}
      />
      {previewError && <p className="search-preview-error">{previewError}</p>}
      {preview?.anchor && (
        <section className="mt-section search-preview-anchor">
          <h3>当前锚点</h3>
          <p>{preview.anchor.text} · {preview.anchor.city} · {preview.anchor.source}</p>
        </section>
      )}
      <section className="mt-section">
        <h3>路线候选，可优先参考</h3>
        {candidates.length === 0 && (
          <article className="mt-list-item"><span>{previewLoading ? "正在召回附近 POI" : "暂无候选 POI"}</span><small>可换商圈</small></article>
        )}
        {candidates.slice(0, 8).map((item) => (
          <article
            className={`mt-list-item search-poi-item ${selectedIds.includes(item.poi.id) ? "checked" : ""}`}
            key={item.poi.id}
            onClick={() => toggleCandidate(item.poi.id)}
          >
            <div>
              <span>{item.poi.name}</span>
              <p>{item.poi.category} · {item.reason}</p>
            </div>
            <button type="button">{selectedIds.includes(item.poi.id) ? "已选" : "加入"}</button>
          </article>
        ))}
        {preview?.warnings?.map((warning) => <p className="search-preview-warning" key={warning}>{warning}</p>)}
      </section>
    </div>
  );
}

function XiaotuanScene({ scenario, routeIntent, conversation, onAsk, onOpen, onFeedback, onAdjust, loading, loadingLabel }) {
  const [draft, setDraft] = useState("");
  const hasMissingSlots = (routeIntent?.missing_slots?.length || routeIntent?.detected_slots?.missing_slots?.length || 0) > 0;
  const inConversation = conversation.length > 0 || Boolean(routeIntent) || loading;
  const smartRouteLoading = loading && loadingLabel.includes("SmartRoute");
  const slotLabels = {
    location: "地点/区域",
    time: "时间/时长",
    activities: "活动类型",
  };
  const lastRouteMessageId = [...conversation].reverse().find((item) => item.type === "route_result")?.id;

  useEffect(() => {
    setDraft("");
  }, [scenario.query]);

  function submitDraft() {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onAsk(trimmed);
    setDraft("");
  }

  return (
    <div className="xiaotuan-chat-page">
      <div className="xiaotuan-chat-head">
        <div className="xiaotuan-round-icon" aria-hidden="true">‹</div>
        <div className="xiaotuan-title">
          <span className="xiaotuan-avatar">小</span>
          <strong>小团</strong>
        </div>
        <div className="xiaotuan-round-icon" aria-hidden="true">≡</div>
      </div>

      <div className="xiaotuan-chat-body">
        {conversation.map((item) => {
          if (item.type === "route_result") {
            return (
              <InlineRouteResultCard
                key={item.id}
                message={item}
                isLatest={item.id === lastRouteMessageId}
                onFeedback={onFeedback}
                onAdjust={onAdjust}
                loading={loading}
              />
            );
          }
          if (item.type === "adjustment_result") {
            return <InlineAdjustmentResultCard key={item.id} adjustment={item.adjustment} />;
          }
          if (item.role === "user") {
            return (
              <div key={item.id} className="xiaotuan-user-row">
                <div className="xiaotuan-user-bubble">{item.text}</div>
              </div>
            );
          }
          return (
            <div key={item.id} className="xiaotuan-other-card">
              <strong>小团</strong>
              <p>{item.text}</p>
            </div>
          );
        })}

        {loading && (loadingLabel.includes("小团") || loadingLabel.includes("SmartRoute") || loadingLabel.includes("规划")) && (
          <button className="xiaotuan-analysis thinking" type="button" disabled>
            <span>{smartRouteLoading ? "已调用 SmartRoute" : (loadingLabel || "分析中")}</span>
            <b>›</b>
          </button>
        )}

        {routeIntent && routeIntent.action !== "open_plugin" && (
          <>
            <button className={`xiaotuan-analysis ${routeIntent.action === "normal_answer" ? "normal" : "confirm"}`} type="button" disabled>
              <span>{routeIntent.action === "normal_answer" ? "已转普通小团回答" : "需要继续确认"}</span>
              <b>›</b>
            </button>
            {hasMissingSlots && (
              <div className="xiaotuan-slot-note">
                还需要确认：{(routeIntent.missing_slots || routeIntent.detected_slots?.missing_slots || []).map((slot) => slotLabels[slot] || slot).join("、")}
              </div>
            )}
            {routeIntent.clarification_options?.length > 0 && (
              <div className="xiaotuan-inline-actions">
                {routeIntent.clarification_options.map((option) => (
                  <button key={option} onClick={() => onAsk(option, "chip")} disabled={loading}>{option}</button>
                ))}
              </div>
            )}
            {routeIntent.action === "ask_confirm" && !hasMissingSlots && (
              <div className="xiaotuan-inline-actions">
                <button onClick={() => onOpen(routeIntent.merged_query || routeIntent.planning_query)} disabled={loading}>排路线</button>
                <button disabled={loading}>只看推荐</button>
              </div>
            )}
          </>
        )}

        {!inConversation && (
          <div className="xiaotuan-empty-prompts">
            {["附近有什么好吃的", "深圳大学附近下午3小时怎么玩", "广州永庆坊逛吃3小时"].map((item) => (
              <button key={item} onClick={() => setDraft(item)}>✦ {item}</button>
            ))}
          </div>
        )}
      </div>

      <div className="xiaotuan-chat-footer">
        <button className="xiaotuan-think" type="button">✣ 深度思考</button>
        <div className="xiaotuan-input-bar">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                submitDraft();
              }
            }}
            placeholder={inConversation ? "继续补充或调整路线" : "发消息或按住说话"}
          />
          <button onClick={submitDraft} disabled={loading || !draft.trim()} title="发送">↑</button>
        </div>
      </div>
    </div>
  );
}

function FavoritesScene({ scenario, onOpen, loading }) {
  const [selectedIds, setSelectedIds] = useState(FAVORITE_POIS.slice(0, 3).map((item) => item.id));
  const selectedPois = FAVORITE_POIS.filter((item) => selectedIds.includes(item.id));
  const primaryPoi = selectedPois[0] || null;
  const selectedNames = selectedPois.map((poi) => poi.name).join("、");
  const selectedCategoryText = [...new Set(selectedPois.map((poi) => poi.category))].join("、");
  const favoriteQuery = selectedPois.length
    ? `把我收藏的${selectedNames}安排成3小时路线，预算200，不想排队`
    : scenario.query;
  const favoriteContext = {
    source: "favorites",
    city_hint: inferCityHint(selectedPois.map((poi) => `${poi.address} ${poi.district} ${poi.name}`).join(" ")) || scenario.routeContext.city_hint,
    anchor_text: primaryPoi?.name || null,
    anchor_location: primaryPoi ? { latitude: primaryPoi.latitude, longitude: primaryPoi.longitude } : null,
    selected_pois: selectedPois,
  };
  function toggle(id) {
    setSelectedIds((items) => {
      if (items.includes(id)) return items.filter((item) => item !== id);
      if (items.length >= 5) return items;
      return [...items, id];
    });
  }
  return (
    <div className="meituan-page">
      <div className="mt-header"><strong>收藏</strong><span>管理</span></div>
      <div className="mt-tabs"><b>商户</b><span>团购</span><span>商品/菜品</span><span>内容</span></div>
      <SmartRouteEntryCard
        title={`已选择 ${selectedPois.length} 个收藏地点`}
        text={selectedPois.length ? `已选 ${selectedCategoryText}；所选店铺会被优先保留，再按距离、排队和预算补齐路线。` : "先选择 2-5 个收藏地点，再把收藏夹变成一条可执行路线。"}
        action="一键排路线"
        onOpen={() => onOpen(favoriteQuery, favoriteContext)}
        loading={loading || selectedPois.length < 2}
      />
      <section className="mt-section">
        {FAVORITE_POIS.map((poi) => (
          <article className={`favorite-item selectable ${selectedIds.includes(poi.id) ? "checked" : ""}`} key={poi.id}>
            <button className="favorite-check" onClick={() => toggle(poi.id)}>{selectedIds.includes(poi.id) ? "✓" : "+"}</button>
            <div className="poi-thumb" />
            <div>
              <h3>{poi.name}</h3>
              <p>{poi.category} · {poi.district} · ¥{poi.price_per_person}/人</p>
              <span>★ {poi.rating} · {poi.source === "context" ? "可排路线" : "到店"}</span>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}

function DetailScene({ scenario, onOpen, loading }) {
  return (
    <div className="meituan-page detail-page">
      <div className="detail-hero">
        <button>‹</button>
        <div className="photo-strip"><span /><span /><span /></div>
      </div>
      <section className="detail-card">
        <h2>{DETAIL_POI.name}</h2>
        <div className="rating-row"><b>{DETAIL_POI.rating}</b><span>{DETAIL_POI.review_count}条评价</span><em>¥{DETAIL_POI.price_per_person}/人</em></div>
        <p>营业中 10:00-22:00 · 可预订 · 有宝宝椅</p>
        <p>{DETAIL_POI.address}，靠近深圳大学/科技园</p>
        <SmartRouteEntryCard
          title="从这里继续安排下一站"
          text="以当前商户为起点，补齐饭前/饭后可逛地点，形成完整路线。"
          action="从这里出发"
          onOpen={() => onOpen(scenario.query, scenario.routeContext)}
          loading={loading}
        />
      </section>
      <section className="mt-section">
        <h3>优惠</h3>
        <article className="deal-card"><strong>100 元代金券</strong><span>¥95 · 9.5折</span><button>买券</button></article>
      </section>
    </div>
  );
}

export function ScenarioSelector({ scenarios, activeScenarioId, onSelect, health }) {
  return (
    <aside className="scenario-rail">
      <div className="rail-card intro-card">
        <span>SmartRoute P0</span>
        <h1>美团 App 场景模拟器</h1>
        <p>评委先看到用户从哪里触发，再看到 SmartRoute 如何作为插件接管路线规划。</p>
      </div>
      <div className="scenario-list">
        {scenarios.map((scenario) => (
          <button
            key={scenario.id}
            className={activeScenarioId === scenario.id ? "active" : ""}
            onClick={() => onSelect(scenario)}
          >
            <strong>{scenario.title}</strong>
            <span>{scenario.subtitle}</span>
          </button>
        ))}
      </div>
      <div className="rail-card">
        <span>真实后端</span>
        <h2>{health?.poi_count ? `${health.poi_count} POI` : "连接中"}</h2>
        <p>路线、候选 POI、替换和反馈都来自 FastAPI，不使用静态假路线。</p>
      </div>
    </aside>
  );
}

export default function PhoneExperience({
  scenario,
  mode,
  plan,
  routeView,
  loading,
  routeIntent,
  xiaotuanConversation,
  onOpenRoute,
  onAskXiaotuan,
  profileMode,
  profileSource,
  profileSources,
  importedProfileId,
  onPresetProfileChange,
  onProfileSourceChange,
  onImportedProfileChange,
  onImportProfile,
  onReplace,
  onFeedback,
  onAdjust,
  onXiaotuanFeedback,
  onXiaotuanAdjust,
  adjustmentHistory,
  latestAdjustment,
  loadingLabel,
}) {
  if (mode === "route") {
    return (
      <SmartRouteRoutePage
        scenario={scenario}
        plan={plan}
        routeView={routeView}
        profileMode={profileMode}
        profileSource={profileSource}
        profileSources={profileSources}
        importedProfileId={importedProfileId}
        onPresetProfileChange={onPresetProfileChange}
        onProfileSourceChange={onProfileSourceChange}
        onImportedProfileChange={onImportedProfileChange}
        onImportProfile={onImportProfile}
        onReplace={onReplace}
        onFeedback={onFeedback}
        onAdjust={onAdjust}
        adjustmentHistory={adjustmentHistory}
        latestAdjustment={latestAdjustment}
        loading={loading}
        loadingLabel={loadingLabel}
      />
    );
  }

  return (
    <section className="phone">
      <div className="phone-status">
        <span>18:57</span>
        <span>5G</span>
      </div>
      <div className="phone-content meituan-shell">
        {scenario.id === "search" && <SearchScene scenario={scenario} onOpen={onOpenRoute} loading={loading} />}
        {scenario.id === "xiaotuan" && (
          <XiaotuanScene
            scenario={scenario}
            routeIntent={routeIntent}
            conversation={xiaotuanConversation}
            onAsk={onAskXiaotuan}
            onOpen={onOpenRoute}
            onFeedback={onXiaotuanFeedback}
            onAdjust={onXiaotuanAdjust}
            loading={loading}
            loadingLabel={loadingLabel}
          />
        )}
        {scenario.id === "favorites" && <FavoritesScene scenario={scenario} onOpen={onOpenRoute} loading={loading} />}
        {scenario.id === "detail" && <DetailScene scenario={scenario} onOpen={onOpenRoute} loading={loading} />}
      </div>
    </section>
  );
}
