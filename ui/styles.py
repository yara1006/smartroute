from __future__ import annotations

import streamlit as st


def inject_custom_css() -> None:
    st.markdown(
        """
<style>
  html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", sans-serif;
  }
  #MainMenu, footer { visibility: hidden; }
  .block-container { padding-top: 1.6rem; padding-bottom: 2.5rem; }
  h1, h2, h3 { letter-spacing: 0; }
  .subtle {
    color: #64748b;
    font-size: 0.95rem;
  }
  .route-shell {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 14px 16px;
    background: #fff;
  }
  .poi-card {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 13px 14px;
    margin: 8px 0;
    background: #ffffff;
  }
  .poi-header {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: flex-start;
  }
  .poi-title {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    font-weight: 700;
    color: #0f172a;
  }
  .poi-order {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: #2563eb;
    color: #fff;
    font-size: 13px;
  }
  .poi-category {
    color: #334155;
    background: #eef2ff;
    border-radius: 6px;
    padding: 2px 6px;
    font-size: 12px;
    font-weight: 600;
  }
  .poi-time {
    color: #475569;
    font-size: 13px;
    white-space: nowrap;
  }
  .poi-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 16px;
    color: #475569;
    font-size: 13px;
    margin-top: 8px;
  }
  .poi-summary {
    color: #334155;
    font-size: 13px;
    line-height: 1.55;
    margin-top: 8px;
  }
  .poi-tip, .poi-transit {
    color: #64748b;
    font-size: 12px;
    line-height: 1.5;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #f1f5f9;
  }
  [data-testid="metric-container"] {
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 10px;
  }
</style>
        """,
        unsafe_allow_html=True,
    )
