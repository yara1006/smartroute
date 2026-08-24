import React from "react";

export default function QueryComposer({ query, setQuery, examples, onSubmit, loading }) {
  return (
    <section className="composer">
      <div className="composer-title">
        <span>现在出发</span>
        <b>AI 本地路线智能规划</b>
      </div>
      <textarea
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="说说时间、预算、区域、同行人和偏好"
      />
      <div className="composer-actions">
        <div className="mini-chips">
          <span>低排队</span>
          <span>预算可控</span>
          <span>可替换</span>
        </div>
        <button onClick={() => onSubmit(query)} disabled={loading}>
          {loading ? "规划中" : "生成路线"}
        </button>
      </div>
      <div className="example-list">
        {examples.map((example) => (
          <button key={example} onClick={() => onSubmit(example)} disabled={loading}>
            {example}
          </button>
        ))}
      </div>
    </section>
  );
}
