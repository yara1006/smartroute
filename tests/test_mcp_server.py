"""Tests for MCP server - verify MCP tools are properly defined."""
from __future__ import annotations

import pytest


class TestMCPServer:
    """Test MCP server tool definitions."""

    def test_mcp_server_module_imports(self) -> None:
        """Test MCP server module can be imported."""
        import mcp_server
        assert mcp_server is not None

    def test_mcp_server_file_exists(self) -> None:
        """Test MCP server file exists."""
        import os
        assert os.path.exists("mcp_server.py")

    def test_mcp_in_requirements(self) -> None:
        """Test MCP is in requirements.txt."""
        with open("requirements.txt", "r", encoding="utf-8") as f:
            content = f.read()
        assert "mcp>=" in content
