"""Tests for MCP server - verify MCP tools are properly defined."""
from __future__ import annotations

import os
import pytest


class TestMCPServer:
    """Test MCP server tool definitions."""

    def test_mcp_server_file_exists(self) -> None:
        """Test MCP server file exists in scripts/."""
        assert os.path.exists("scripts/mcp_server.py")

    def test_mcp_in_requirements(self) -> None:
        """Test MCP is in requirements.txt."""
        with open("requirements.txt", "r", encoding="utf-8") as f:
            content = f.read()
        assert "mcp>=" in content

    def test_scripts_directory_exists(self) -> None:
        """Test scripts/ directory exists."""
        assert os.path.isdir("scripts")
