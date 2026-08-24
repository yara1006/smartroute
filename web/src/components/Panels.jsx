import React, { useEffect, useState } from "react";
import { PROFILE_MODES, IMPORT_PROFILE_TEMPLATE, JUDGE_PROFILE_QUESTIONS, DEFAULT_JUDGE_ANSWERS } from "../constants.js";
import { money, minutes, fieldList, scoreClass, formatDelta, deltaTone, metricDelta, statusText } from "../api.js";
import { profilesForSource } from "../helpers.js";
import RouteMap from "./RouteMap.jsx";

export function MetricStrip({ routeView }) {
  if (!routeView) return null;
  const route = routeView.route;
  const insight = routeView.insight;
  return (
    <div className="metrics-strip">
      <div>
        <span>可信度</span>
        <strong className={scoreClass(insight.confidence_score)}>{insight.confidence_score}</strong>
      </div>
      <div>
        <span>总时长</span>
        <strong>{minutes(route.total_time_minutes)}</strong>
      </div>
      <div>
        <span>人均</span>
        <strong>{money(route.total_cost_per_person)}</strong>
      </div>
      <div>
        <span>等位</span>
        <strong>{route.total_wait_minutes}m</strong>
      </div>
    </div>
  );
}

export function ConstraintPanel({ constraints }) {
  return (
    <section className="panel compact">
      <div className="section-head">
        <h2>约束确认</h2>
        <span>来自后端解析</span>
      </div>
      <div className="constraint-grid">
        {fieldList(constraints).map(([label, value]) => (
          <div className="constraint" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="category-row">
        {(constraints?.preferred_categories || []).map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>
    </section>
  );
}

export function RouteSelector({ routes, selectedRouteIndex, setSelectedRouteIndex }) {
  if (!routes?.length) return null;
  return (
    <div className="route-selector">
      {routes.map((routeView, index) => (
        <button
          className={selectedRouteIndex === index ? "active" : ""}
          onClick={() => setSelectedRouteIndex(index)}
          key={routeView.route.id}
        >
          <strong>方案 {index + 1}</strong>
          <span>{routeView.route.title}</span>
        </button>
      ))}
    </div>
  );
}

export function Timeline({ routeView, onReplace }) {
  if (!routeView) {
    return <div className="empty-state">后端返回路线后，这里会展示逐站行程。</div>;
  }

  return (
    <div className="timeline">
      {routeView.route.stops.map((stop) => (
        <article className="stop-card" key={`${stop.order}-${stop.poi.id}`}>
          <div className="stop-node">{stop.order}</div>
          <div className="stop-main">
            <div className="stop-top">
              <div>
                <span>{stop.arrival_time} - {stop.departure_time}</span>
                <h3>{stop.poi.name}</h3>
              </div>
              <button onClick={() => onReplace(stop)}>替换</button>
            </div>
            <p>{stop.poi.ugc_summary}</p>
            <div className="stop-meta">
              <span>{stop.poi.category}</span>
              <span>{stop.poi.source === "amap" ? "高德POI" : stop.poi.source === "context" ? "入口已选" : "本地兜底"}</span>
              <span>评分 {stop.poi.rating}</span>
              <span>等位 {stop.wait_minutes}m</span>
              <span>人均 {money(stop.poi.price_per_person)}</span>
              <span>{stop.poi.business_hours.open}-{stop.poi.business_hours.close}</span>
            </div>
            {stop.transit_to_next && <div className="transit-note">{stop.transit_to_next}</div>}
          </div>
        </article>
      ))}
    </div>
  );
}

export function CandidatePanel({ candidates }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>候选 POI</h2>
        <span>RAG Top {candidates?.length || 0}</span>
      </div>
      <div className="candidate-list">
        {(candidates || []).slice(0, 8).map((candidate) => (
          <article key={candidate.poi.id}>
            <div>
              <h3>{candidate.poi.name}</h3>
              <p>{candidate.reason}</p>
            </div>
            <strong>{candidate.score.toFixed(2)}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}

export function TracePanel({ trace }) {
  return (
    <section className="panel">
      <div className="section-head">
        <h2>生成过程</h2>
        <span>可答辩展示</span>
      </div>
      <ol className="trace-list">
        {(trace || []).map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ol>
    </section>
  );
}

export function ToolTracePanel({ title = "ToolUse Trace", steps }) {
  if (!steps?.length) return null;
  return (
    <section className="panel">
      <div className="section-head">
        <h2>{title}</h2>
        <span>ReAct / ToolUse</span>
      </div>
      <div className="tool-trace">
        {steps.map((step, index) => (
          <article key={`${step.step}-${step.tool}-${index}`} className={step.status}>
            <div>
              <span>{step.step}</span>
              <strong>{step.tool}</strong>
              <em>{step.status}</em>
            </div>
            <p>{step.input}</p>
            <small>{step.output}</small>
          </article>
        ))}
      </div>
    </section>
  );
}

export function InsightPanel({ routeView }) {
  if (!routeView) return null;
  const insight = routeView.insight;
  return (
    <section className="panel">
      <div className="section-head">
        <h2>路线解释</h2>
        <span>不是黑盒推荐</span>
      </div>
      <div className="confidence-card">
        <div className="confidence-ring">
          <strong>{insight.confidence_score}</strong>
          <span>score</span>
        </div>
        <p>{insight.explanation}</p>
      </div>
      <div className="hit-list">
        {insight.constraint_hits.map((hit) => (
          <span key={hit}>{hit}</span>
        ))}
      </div>
      <div className="fit-grid">
        <div>
          <span>排队</span>
          <strong>{insight.wait_status}</strong>
        </div>
        <div>
          <span>步行</span>
          <strong>{insight.walk_intensity}</strong>
        </div>
        <div>
          <span>人群</span>
          <strong>{insight.crowd_fit}</strong>
        </div>
        <div>
          <span>天气</span>
          <strong>{insight.weather_fit}</strong>
        </div>
      </div>
      {insight.risks.length > 0 && (
        <div className="risk-box">
          {insight.risks.map((risk) => (
            <p key={risk}>{risk}</p>
          ))}
        </div>
      )}
    </section>
  );
}

export function CompareTable({ routes, selectedRouteIndex, setSelectedRouteIndex }) {
  if (!routes?.length) return null;
  return (
    <section className="panel wide">
      <div className="section-head">
        <h2>多方案对比</h2>
        <span>时间 / 预算 / 等待 / 步行</span>
      </div>
      <div className="compare-table">
        {routes.map((routeView, index) => (
          <button
            className={selectedRouteIndex === index ? "active" : ""}
            key={routeView.route.id}
            onClick={() => setSelectedRouteIndex(index)}
          >
            <span>方案 {index + 1}</span>
            <strong>{routeView.route.title}</strong>
            <em>{routeView.insight.confidence_score} 分</em>
            <small>{minutes(routeView.route.total_time_minutes)} · {money(routeView.route.total_cost_per_person)} · 等 {routeView.route.total_wait_minutes}m</small>
          </button>
        ))}
      </div>
    </section>
  );
}

export function ReplacePanel({ replacement, onClose, onApply }) {
  if (!replacement) return null;
  return (
    <aside className="replace-panel">
      <div className="replace-head">
        <div>
          <span>替换站点</span>
          <h2>同类 POI 实时替换</h2>
        </div>
        <button onClick={onClose}>×</button>
      </div>
      {replacement.loading && <div className="empty-state">正在从后端搜索替换项...</div>}
      {!replacement.loading && replacement.options.length === 0 && <div className="empty-state">当前约束下没有更稳的同类替换项。</div>}
      <div className="replacement-list">
        {replacement.options.map((option) => (
          <article key={option.poi.id}>
            <div>
              <h3>{option.poi.name}</h3>
              <p>{option.impact_summary}</p>
              <span>评分 {option.poi.rating} · {option.poi.district} · {option.poi.business_hours.open}-{option.poi.business_hours.close}</span>
            </div>
            <button onClick={() => onApply(option)}>
              应用
              <small>{formatDelta(option.cost_delta, "元")} / {formatDelta(option.wait_delta, "m")}</small>
            </button>
          </article>
        ))}
      </div>
    </aside>
  );
}

export function ProfileImportPanel({ onImport, loading }) {
  const [draft, setDraft] = useState(IMPORT_PROFILE_TEMPLATE);
  const [expanded, setExpanded] = useState(false);

  async function submit() {
    let parsed;
    try {
      parsed = JSON.parse(draft);
    } catch {
      onImport(null, "JSON 格式不正确，请检查逗号和引号。");
      return;
    }
    onImport(parsed);
  }

  return (
    <section className="profile-import-panel">
      <button className="import-toggle" onClick={() => setExpanded((value) => !value)}>
        {expanded ? "收起导入" : "导入脱敏画像"}
      </button>
      {expanded && (
        <>
          <p>只粘贴搜索词、收藏、浏览偏好等脱敏信息；不要粘贴账号、手机号、cookie、订单号。</p>
          <textarea value={draft} onChange={(event) => setDraft(event.target.value)} />
          <button className="import-submit" onClick={submit} disabled={loading}>
            {loading ? "导入中" : "保存并使用"}
          </button>
        </>
      )}
    </section>
  );
}

export function ProfileModeControl({
  profileMode,
  profileSource,
  profileSources,
  importedProfileId,
  onPresetChange,
  onSourceChange,
  onImportedProfileChange,
  onImportProfile,
  loading,
}) {
  const importedProfiles = profilesForSource(profileSources, "manual_import");
  return (
    <div className="profile-control">
      <div className="profile-source-tabs">
        <button className={profileSource === "preset" ? "active" : ""} onClick={() => onSourceChange("preset")}>
          模拟画像
        </button>
        <button className={profileSource === "manual_import" ? "active" : ""} onClick={() => onSourceChange("manual_import")}>
          评委/脱敏画像
        </button>
      </div>
      {profileSource === "preset" && (
        <div className="profile-switch">
          {PROFILE_MODES.map((mode) => (
            <button key={mode} className={profileMode === mode ? "active" : ""} onClick={() => onPresetChange(mode)}>
              {mode}
            </button>
          ))}
        </div>
      )}
      {profileSource === "manual_import" && (
        <>
          <div className="manual-profile-list">
            {importedProfiles.map((profile) => (
              <button
                key={profile.profile_id}
                className={importedProfileId === profile.profile_id ? "active" : ""}
                onClick={() => onImportedProfileChange(profile.profile_id)}
              >
                <strong>{profile.display_name}</strong>
                <span>{profile.signal_count} 信号</span>
              </button>
            ))}
            {!importedProfiles.length && <div className="empty-state">还没有脱敏画像，先导入一份样本。</div>}
          </div>
          <ProfileImportPanel onImport={onImportProfile} loading={loading} />
        </>
      )}
    </div>
  );
}

export function ProfileSummary({ context, sourceDescription, signalCount }) {
  if (!context) return null;
  return (
    <section className="profile-summary">
      <span>美团画像</span>
      <p>{context.summary}</p>
      {sourceDescription && <strong>{sourceDescription}</strong>}
      <div>
        {(context.search_preferences || []).slice(0, 4).map((item) => (
          <em key={item}>{item}</em>
        ))}
        {signalCount > 0 && <em>{signalCount} 个信号</em>}
      </div>
    </section>
  );
}

export function ProfileInfluencePanel({ influences, compact = false }) {
  if (!influences?.length) return null;
  return (
    <section className={compact ? "profile-influence compact" : "profile-influence"}>
      <span>为什么这样推荐</span>
      <div className="influence-chain-label">画像信号 → 召回加权 → 路线变化</div>
      {influences.slice(0, compact ? 3 : 5).map((item) => (
        <article key={`${item.signal}-${item.source}`}>
          <div>
            <strong>{item.signal}</strong>
            <em>{item.weight}权重</em>
          </div>
          <p>{item.source}</p>
          <small>{item.effect}</small>
          {item.matched_pois?.length > 0 && (
            <div className="influence-pois">
              {item.matched_pois.slice(0, 3).map((name) => <b key={name}>{name}</b>)}
            </div>
          )}
        </article>
      ))}
    </section>
  );
}

export function P1Status({ plan }) {
  if (!plan) return null;
  return (
    <div className="p1-status">
      <div>
        <span>规划耗时</span>
        <strong>{plan.planning_time_ms ?? 0}ms</strong>
      </div>
      <div>
        <span>完整性</span>
        <strong>{plan.route_completeness?.is_complete ? "已满足" : "需优化"}</strong>
      </div>
      <div>
        <span>冲突</span>
        <strong>{plan.constraint_conflicts?.length || 0}</strong>
      </div>
    </div>
  );
}

export function FollowUpCard({ followUp, fallbackQuestion, onPick, loading }) {
  const question = followUp?.question || fallbackQuestion;
  if (!question) return null;
  const options = followUp?.options?.length
    ? followUp.options
    : ["少排队", "便宜点", "文艺一点", "少走路"].map((label) => ({ label, instruction: label }));
  return (
    <section className="follow-card">
      <span>继续优化</span>
      <p>{question}</p>
      <div>
        {options.map((option) => (
          <button key={`${option.label}-${option.instruction}`} onClick={() => onPick(option.instruction)} disabled={loading}>
            <strong>{option.label}</strong>
            {option.expected_effect && <small>{option.expected_effect}</small>}
          </button>
        ))}
      </div>
      {followUp?.reason && <em>{followUp.reason}</em>}
    </section>
  );
}

export function AdjustmentResultCard({ adjustment }) {
  if (!adjustment) return null;
  const deltas = adjustment.metric_deltas || {};
  return (
    <section className={`adjust-result ${adjustment.adjustment_status || ""}`}>
      <div className="adjust-result-head">
        <span>{statusText(adjustment.adjustment_status)}</span>
        <strong>{adjustment.adjustment_summary}</strong>
      </div>
      <div className="delta-grid">
        <div className={deltaTone(deltas.total_wait_minutes)}>
          <span>等位</span>
          <strong>{metricDelta(deltas.total_wait_minutes)}</strong>
        </div>
        <div className={deltaTone(deltas.total_cost_per_person)}>
          <span>人均</span>
          <strong>{metricDelta(deltas.total_cost_per_person, "¥")}</strong>
        </div>
        <div className={deltaTone(deltas.total_transit_minutes)}>
          <span>移动</span>
          <strong>{metricDelta(deltas.total_transit_minutes)}</strong>
        </div>
      </div>
      {adjustment.changed_stops?.length > 0 && (
        <div className="changed-stops">
          {adjustment.changed_stops.slice(0, 3).map((change) => (
            <p key={`${change.order}-${change.action}`}>
              第{change.order}站：{change.before_poi || "新增"} → {change.after_poi || "移除"}
            </p>
          ))}
        </div>
      )}
      {adjustment.suggested_relaxations?.length > 0 && (
        <div className="relaxation-list">
          {adjustment.suggested_relaxations.map((item) => <p key={item}>{item}</p>)}
        </div>
      )}
    </section>
  );
}

export function RouteLoadingState({ label }) {
  if (!label) return null;
  return <div className="route-loading-state">{label}...</div>;
}

export function AdjustComposer({ onSubmit, loading }) {
  const [draft, setDraft] = useState("");
  const quickAdjustments = ["少走路", "不要排队", "便宜点", "不要这么多咖啡", "不要这么多餐厅", "加展览", "换个重点"];
  function submit(value = draft) {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setDraft("");
  }
  return (
    <section className="adjust-composer">
      <div className="adjust-quick-row">
        {quickAdjustments.map((item) => (
          <button type="button" key={item} onClick={() => submit(item)} disabled={loading}>{item}</button>
        ))}
      </div>
      <div className="adjust-input-row">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="继续说：少走路一点 / 换便宜点 / 不要排队"
          onKeyDown={(event) => {
            if (event.key === "Enter") submit();
          }}
        />
        <button type="button" onClick={() => submit()} disabled={loading || !draft.trim()}>{loading ? "调整中" : "调整"}</button>
      </div>
    </section>
  );
}

export function AdjustmentHistory({ history }) {
  if (!history.length) return null;
  return (
    <section className="adjust-history">
      <span>调整历史</span>
      {history.slice(-3).map((item, index) => (
        <p key={`${item}-${index}`}>{item}</p>
      ))}
    </section>
  );
}

export function JudgePreferenceModal({ open, scenario, pendingQuery, onSubmit, onSkip, loading }) {
  const [answers, setAnswers] = useState(DEFAULT_JUDGE_ANSWERS);

  useEffect(() => {
    if (open) setAnswers(DEFAULT_JUDGE_ANSWERS);
  }, [open]);

  if (!open) return null;
  return (
    <div className="preference-modal-backdrop">
      <section className="preference-modal">
        <div className="preference-modal-head">
          <span>SmartRoute 个性化路线偏好</span>
          <h2>先用 10 秒生成你的本次画像</h2>
          <p>{scenario.title}入口 · {pendingQuery || scenario.query}</p>
        </div>
        <div className="preference-question-grid">
          {JUDGE_PROFILE_QUESTIONS.map((question) => (
            <div key={question.key} className="preference-question">
              <strong>{question.title}</strong>
              <div>
                {question.options.map((option) => (
                  <button
                    key={option}
                    className={answers[question.key] === option ? "active" : ""}
                    onClick={() => setAnswers((current) => ({ ...current, [question.key]: option }))}
                  >
                    {option}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="preference-modal-actions">
          <button className="secondary" onClick={onSkip} disabled={loading}>跳过，直接规划</button>
          <button onClick={() => onSubmit(answers)} disabled={loading}>
            {loading ? "生成中" : "使用本次画像规划"}
          </button>
        </div>
        <p className="privacy-note">只生成本次演示画像，不读取真实美团账号、手机号、cookie、订单或精确住址。</p>
      </section>
    </div>
  );
}

export function AgentPanel({
  scenario,
  routeIntent,
  plan,
  routeView,
  routes,
  selectedRouteIndex,
  setSelectedRouteIndex,
  adjustmentHistory,
  latestAdjustment,
}) {
  return (
    <aside className="agent-panel">
      <section className="panel">
        <div className="section-head">
          <h2>Agent 解释面板</h2>
          <span>{scenario.title}</span>
        </div>
        <div className="agent-context">
          <div>
            <span>入口来源</span>
            <strong>{scenario.title} · {scenario.subtitle}</strong>
          </div>
          <div>
            <span>用户上下文</span>
            <p>{scenario.context}</p>
          </div>
          <div>
            <span>触发方式</span>
            <p>{scenario.trigger}</p>
          </div>
          <div>
            <span>产品定位</span>
            <p>小团 AI 是入口和通用对话层；SmartRoute 是被小团、搜索、收藏和详情页调起的路线执行 Agent。</p>
          </div>
          <div>
            <span>执行链路</span>
            <p>小团识别路线意图 → SmartRoute 调用 POI/地图/画像工具 → 输出可调整的可执行路线。</p>
          </div>
          {plan?.intent?.extracted_preferences?.anchor_text && (
            <div>
              <span>地图锚点</span>
              <p>{plan.intent.extracted_preferences.anchor_text} · {plan.intent.city}</p>
            </div>
          )}
        </div>
      </section>

      {scenario.id === "xiaotuan" && (
        <section className="panel">
          <div className="section-head">
            <h2>小团意图识别</h2>
            <span>{routeIntent ? routeIntent.source : "等待输入"}</span>
          </div>
          {routeIntent ? (
            <div className="intent-summary">
              <strong>{routeIntent.action}</strong>
              <span>{(routeIntent.confidence * 100).toFixed(0)}%</span>
              <p>{routeIntent.reason}</p>
              {routeIntent.fusion?.strategy && (
                <div className="intent-fusion">
                  <b>最终融合</b>
                  <span>{routeIntent.fusion.strategy}</span>
                  {routeIntent.fusion.conflict && <em>LLM 与规则有分歧</em>}
                </div>
              )}
              <div className="hit-list">
                {Object.entries(routeIntent.detected_slots || {}).slice(0, 6).map(([key, value]) => (
                  <span key={key}>{key}: {Array.isArray(value) ? value.join("、") : value || "无"}</span>
                ))}
              </div>
              {routeIntent.rule_signals && (
                <div className="intent-signal-grid">
                  {[
                    ["地点", routeIntent.rule_signals.locations?.join("、") || "未识别"],
                    ["活动", routeIntent.rule_signals.activities?.join("、") || "未识别"],
                    ["路线动词", routeIntent.rule_signals.route_hit ? "命中" : "未命中"],
                    ["时长", routeIntent.rule_signals.duration_hit ? "命中" : "未命中"],
                    ["多活动", routeIntent.rule_signals.multi_activity_hit ? "命中" : "未命中"],
                    ["单店信息", routeIntent.rule_signals.single_poi_hit ? "命中" : "未命中"],
                  ].map(([label, value]) => (
                    <div key={label}>
                      <span>{label}</span>
                      <strong>{value}</strong>
                    </div>
                  ))}
                </div>
              )}
              {routeIntent.llm_judgement && (
                <div className="intent-llm-box">
                  <b>LLM 判断</b>
                  <p>{routeIntent.llm_judgement.action || "unknown"} · {routeIntent.llm_judgement.intent_type || "未分类"}</p>
                  {routeIntent.llm_judgement.negative_reason && <p>不调起原因：{routeIntent.llm_judgement.negative_reason}</p>}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">小团输入后会先判断 open_plugin / ask_confirm / normal_answer。</div>
          )}
        </section>
      )}

      {plan?.meituan_user_context && (
        <section className="panel">
          <div className="section-head">
            <h2>美团用户画像</h2>
            <span>{plan.profile_mode}</span>
          </div>
          <div className="agent-context">
            <div>
              <span>画像摘要</span>
              <p>{plan.meituan_user_context.summary}</p>
            </div>
            <div>
              <span>画像来源</span>
              <p>{plan.profile_source_description || "模拟画像"}{plan.profile_source === "manual_import" ? " · 脱敏导入" : ""}</p>
            </div>
            <div>
              <span>偏好信号</span>
              <p>{[...(plan.meituan_user_context.search_preferences || []), ...(plan.meituan_user_context.browsed_tags || [])].slice(0, 6).join("、")}</p>
            </div>
            <div>
              <span>P1 指标</span>
              <p>耗时 {plan.planning_time_ms}ms · 冲突 {plan.constraint_conflicts?.length || 0} 个 · {plan.route_completeness?.is_complete ? "路线完整" : "需继续优化"}</p>
            </div>
            <div>
              <span>LLM 解析</span>
              <p>{plan.intent?.parser_source || "rules"} · 置信度 {Math.round((plan.intent?.parser_confidence || 0) * 100)}% · {plan.intent?.parser_reason}</p>
            </div>
            <div>
              <span>交通策略</span>
              <p>{plan.intent?.constraints?.transport_mode || "步行+公交"} · {routeView?.route?.transit_segments?.some((item) => String(item.source || "").startsWith("amap")) ? "高德真实分段" : "本地估算/降级"}</p>
            </div>
          </div>
        </section>
      )}

      {plan?.profile_influence?.length > 0 && (
        <section className="panel">
          <div className="section-head">
            <h2>画像影响链路</h2>
            <span>信号 → 召回 → 路线</span>
          </div>
          <ProfileInfluencePanel influences={plan.profile_influence} />
        </section>
      )}

      <section className="panel demo-script-panel">
        <div className="section-head">
          <h2>演示脚本</h2>
          <span>交付日</span>
        </div>
        <ol className="trace-list">
          <li>搜索页先展示真实候选 POI，再勾选 2-5 个地点生成路线。</li>
          <li>POI 详情页从 gaga 出发时，确认第 1 站固定不被排序挪走。</li>
          <li>小团只负责识别意图，SmartRoute 负责约束规划、地图、调整和反馈闭环。</li>
          <li>展示调整状态、站点变化、等待/预算/移动 delta。</li>
        </ol>
      </section>

      {latestAdjustment && (
        <section className="panel">
          <div className="section-head">
            <h2>调整结果</h2>
            <span>{statusText(latestAdjustment.adjustment_status)}</span>
          </div>
          <AdjustmentResultCard adjustment={latestAdjustment} />
        </section>
      )}

      <ToolTracePanel title="路线 ToolUse Trace" steps={plan?.tool_trace || []} />
      <ToolTracePanel title="调整 ToolUse Trace" steps={latestAdjustment?.tool_trace || []} />

      {adjustmentHistory.length > 0 && (
        <section className="panel">
          <div className="section-head">
            <h2>调整历史</h2>
            <span>{adjustmentHistory.length} 次</span>
          </div>
          <ol className="trace-list">
            {adjustmentHistory.map((item) => <li key={item}>{item}</li>)}
          </ol>
        </section>
      )}

      <TracePanel trace={plan?.trace || []} />
      <InsightPanel routeView={routeView} />
      <CandidatePanel candidates={plan?.candidates || []} />
      <CompareTable routes={routes || []} selectedRouteIndex={selectedRouteIndex} setSelectedRouteIndex={setSelectedRouteIndex} />
    </aside>
  );
}

function SmartRouteRoutePage({
  scenario,
  plan,
  routeView,
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
  adjustmentHistory,
  latestAdjustment,
  loading,
  loadingLabel,
}) {
  const constraints = plan?.intent?.constraints;
  return (
    <section className="phone">
      <div className="phone-status">
        <span>18:57</span>
        <span>5G</span>
      </div>
      <div className="phone-appbar">
        <strong>SmartRoute</strong>
        <span>{scenario.title}调起</span>
      </div>
      <div className="phone-content">
        <ProfileModeControl
          profileMode={profileMode}
          profileSource={profileSource}
          profileSources={profileSources}
          importedProfileId={importedProfileId}
          onPresetChange={onPresetProfileChange}
          onSourceChange={onProfileSourceChange}
          onImportedProfileChange={onImportedProfileChange}
          onImportProfile={onImportProfile}
          loading={loading}
        />
        <ProfileSummary
          context={plan?.meituan_user_context}
          sourceDescription={plan?.profile_source_description}
          signalCount={plan?.profile_signal_count}
        />
        <ProfileInfluencePanel influences={plan?.profile_influence} compact />
        <P1Status plan={plan} />
        <RouteLoadingState label={loadingLabel} />
        {constraints && (
          <div className="phone-chips">
            {fieldList(constraints).slice(0, 5).map(([label, value]) => (
              <span key={label}>{label} {value}</span>
            ))}
          </div>
        )}
        {routeView && (
          <>
            <MetricStrip routeView={routeView} />
            <RouteMap route={routeView.route} />
            <div className="phone-route-head">
              <div>
                <span>推荐路线</span>
                <h2>{routeView.route.title}</h2>
              </div>
              <strong>{routeView.insight.wait_status}</strong>
            </div>
            <Timeline routeView={routeView} onReplace={onReplace} />
            <div className="feedback-row">
              <button onClick={() => onFeedback(1)}>喜欢</button>
              <button onClick={() => onFeedback(-1)}>不合适</button>
            </div>
            <AdjustmentResultCard adjustment={latestAdjustment} />
            <FollowUpCard followUp={plan?.follow_up} fallbackQuestion={plan?.follow_up_question} onPick={onAdjust} loading={loading} />
            <AdjustComposer onSubmit={onAdjust} loading={loading} />
            <AdjustmentHistory history={adjustmentHistory} />
          </>
        )}
        {!routeView && (
          <div className="empty-state">
            {plan?.constraint_conflicts?.length
              ? `当前没有完整路线：${plan.constraint_conflicts.join("；")}`
              : "正在等待 SmartRoute 生成路线..."}
          </div>
        )}
      </div>
    </section>
  );
}

export default SmartRouteRoutePage;
