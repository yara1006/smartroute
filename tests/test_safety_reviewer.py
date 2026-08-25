"""Tests for safety_reviewer — High-risk action detection and interception."""
from __future__ import annotations

import pytest

from services.safety_reviewer import (
    RiskLevel,
    classify_action_risk,
    review_response_safety,
)


class TestClassifyActionRisk:
    """Test action risk classification."""

    def test_low_risk_search(self):
        result = classify_action_risk("帮我搜索深圳大学附近的咖啡")
        assert result.risk_level == RiskLevel.LOW
        assert result.allowed is True

    def test_low_risk_plan(self):
        result = classify_action_risk("帮我规划一个3小时路线")
        assert result.risk_level == RiskLevel.LOW
        assert result.allowed is True

    def test_high_risk_booking(self):
        result = classify_action_risk("帮我直接预订这家餐厅")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False
        assert result.requires_confirmation is True
        assert "预订" in result.warning or "booking" in result.warning.lower()

    def test_high_risk_payment(self):
        result = classify_action_risk("帮我付款")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False

    def test_high_risk_save_credentials(self):
        result = classify_action_risk("记住我的身份证和银行卡")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False
        assert "身份证" in result.warning or "credential" in result.warning.lower()

    def test_high_risk_non_refundable(self):
        result = classify_action_risk("帮我订不可退款的酒店")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False

    def test_high_risk_legal_confirmation(self):
        result = classify_action_risk("帮我确认签证材料")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False

    def test_medium_risk_unknown(self):
        result = classify_action_risk("帮我做一件奇怪的事")
        assert result.risk_level == RiskLevel.MEDIUM
        assert result.allowed is True  # Allow but flag

    def test_english_booking_keyword(self):
        result = classify_action_risk("Please book this restaurant for me")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False

    def test_chinese_payment_keyword(self):
        result = classify_action_risk("我要转账给这个商家")
        assert result.risk_level == RiskLevel.HIGH
        assert result.allowed is False


class TestReviewResponseSafety:
    """Test response safety review integration."""

    def test_safe_response_unchanged(self):
        response = {"query": "帮我规划路线", "routes": []}
        result = review_response_safety(response)
        assert result["safety_warnings"] == []
        assert result["refused"] is False

    def test_high_risk_response_refused(self):
        response = {"query": "帮我预订这家餐厅", "routes": []}
        result = review_response_safety(response)
        assert result["refused"] is True
        assert len(result["safety_warnings"]) > 0

    def test_payment_response_refused(self):
        response = {"query": "帮我付款", "routes": []}
        result = review_response_safety(response)
        assert result["refused"] is True

    def test_credential_response_refused(self):
        response = {"query": "保存我的银行卡密码", "routes": []}
        result = review_response_safety(response)
        assert result["refused"] is True
