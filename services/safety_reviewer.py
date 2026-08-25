"""SmartRoute Safety Reviewer — High-risk action detection and interception.

Implements safety boundaries for actions that require human confirmation:
- Booking, payment, cancellation
- Storing sensitive credentials (ID, passport, bank card)
- Non-refundable terms
- Legal/visa confirmations
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    """Risk level for an action."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class SafetyReview:
    """Result of safety review for an action."""
    action: str
    risk_level: RiskLevel
    allowed: bool
    warning: str | None = None
    requires_confirmation: bool = False


# High-risk action keywords that trigger interception
_HIGH_RISK_KEYWORDS = {
    "booking": {"预订", "订", "booking", "book", "reserve", "reservation"},
    "payment": {"付款", "支付", "pay", "payment", "转账", "transfer"},
    "save_credentials": {"身份证", "护照", "银行卡", "密码", "cookie", "token", "credential", "password", "card"},
    "non_refundable": {"不可退款", "non-refundable", "不可退", "不能退", "no refund"},
    "legal_confirmation": {"签证", "visa", "法律", "legal", "合同", "contract"},
}

_LOW_RISK_ACTIONS = {
    "search", "plan", "adjust", "replace", "feedback", "query", "recommend", "规划", "搜索", "调整", "推荐",
}


def classify_action_risk(action_description: str) -> SafetyReview:
    """Classify the risk level of a user action based on keywords.

    Args:
        action_description: Natural language description of what the user wants to do.

    Returns:
        SafetyReview with risk level, allowed status, and warning message.
    """
    text = action_description.lower()

    # Check for high-risk actions
    for action_type, keywords in _HIGH_RISK_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                warning = _get_warning_for_action(action_type)
                return SafetyReview(
                    action=action_type,
                    risk_level=RiskLevel.HIGH,
                    allowed=False,
                    warning=warning,
                    requires_confirmation=True,
                )

    # Check for known low-risk actions
    for action in _LOW_RISK_ACTIONS:
        if action in text:
            return SafetyReview(
                action=action,
                risk_level=RiskLevel.LOW,
                allowed=True,
            )
    return SafetyReview(
        action="unknown",
        risk_level=RiskLevel.MEDIUM,
        allowed=True,
        warning="此操作需要用户确认",
    )


def _get_warning_for_action(action_type: str) -> str:
    """Get user-facing warning message for a high-risk action type."""
    warnings = {
        "booking": "预订操作需要您手动确认，系统不会自动为您下单。建议前往官方平台完成预订。",
        "payment": "系统不会处理付款操作。请通过官方支付渠道完成交易。",
        "save_credentials": "出于安全考虑，系统不会保存身份证、护照、银行卡等敏感信息。",
        "non_refundable": "不可退款条款需要您自行确认。系统建议仔细阅读退改政策后再做决定。",
        "legal_confirmation": "签证和法律事项建议您通过官方渠道确认，系统不提供法律建议。",
    }
    return warnings.get(action_type, "此操作需要人工确认。")


def review_response_safety(response: dict) -> dict:
    """Add safety warnings to a response dict if high-risk actions are detected.

    Args:
        response: API response dict that may contain user actions.

    Returns:
        Response dict with added 'safety_warnings' and 'refused' fields.
    """
    safety_warnings = []
    refused = False

    # Check if response contains any high-risk action indicators
    user_query = response.get("query", "")
    review = classify_action_risk(user_query)

    if not review.allowed:
        refused = True
        safety_warnings.append(review.warning)

    response["safety_warnings"] = safety_warnings
    response["refused"] = refused
    return response
