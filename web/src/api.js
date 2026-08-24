import { API_BASE } from "./constants.js";

export async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export async function postJson(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  return response.json();
}

export function money(value) {
  if (value === null || value === undefined) return "不限";
  return `¥${Math.round(value)}`;
}

export function minutes(value) {
  if (!value) return "0m";
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  return hours ? `${hours}h${mins}m` : `${mins}m`;
}

export function fieldList(constraints) {
  if (!constraints) return [];
  return [
    ["时间", `${constraints.start_time} / ${constraints.total_time_hours}h`],
    ["预算", money(constraints.budget_per_person)],
    ["排队", `≤${constraints.max_wait_minutes}m`],
    ["人数", `${constraints.party_size}人`],
    ["步行", `≤${constraints.max_walk_minutes}m`],
    ["区域", constraints.preferred_districts?.join("、") || `全${constraints.city || "城市"}`],
  ];
}

export function scoreClass(score) {
  if (score >= 85) return "good";
  if (score >= 70) return "warn";
  return "risk";
}

export function formatDelta(value, suffix = "") {
  if (value === 0) return `无变化${suffix}`;
  return `${value > 0 ? "+" : ""}${value}${suffix}`;
}

export function metricDelta(value, unit = "m") {
  if (value === 0 || value === undefined || value === null) return "无变化";
  if (unit === "¥") return `${value > 0 ? "+" : "-"}¥${Math.abs(Math.round(value))}`;
  return `${value > 0 ? "+" : ""}${value}${unit}`;
}

export function deltaTone(value, lowerIsBetter = true) {
  if (!value) return "flat";
  return (lowerIsBetter ? value < 0 : value > 0) ? "good" : "bad";
}

export function statusText(status) {
  return {
    applied: "已应用",
    partial: "部分应用",
    not_applied: "未应用",
  }[status] || "已调整";
}
