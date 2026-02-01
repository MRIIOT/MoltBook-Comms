#!/usr/bin/env python3
"""
Moltbook MCP Server
Model Context Protocol server for Claude Code integration

Usage:
  Configure in .claude/settings.json:
  {
    "mcpServers": {
      "moltbook": {
        "command": "python",
        "args": ["moltbook_mcp.py"]
      }
    }
  }
"""

import sys
import json
import logging
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from moltbook_tools import MoltbookTools, ToolResult

# Setup logging to stderr (stdout is for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


def load_config():
    """Load config from moltbook_config.json"""
    config_file = Path(__file__).parent / "moltbook_config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding='utf-8'))
    raise FileNotFoundError("moltbook_config.json not found")


class MoltbookMCPServer:
    """MCP Server exposing Moltbook tools"""

    def __init__(self):
        config = load_config()
        self.tools = MoltbookTools(
            api_base=config["api_base"],
            api_key=config["api_key"],
            timeout=config.get("request_timeout", 30)
        )
        self.agent_name = config.get("agent_name", "unknown")

    def handle_request(self, request: dict) -> dict:
        """Handle incoming MCP request"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        if method == "initialize":
            return self._initialize(req_id, params)
        elif method == "tools/list":
            return self._list_tools(req_id)
        elif method == "tools/call":
            return self._call_tool(req_id, params)
        elif method == "shutdown":
            return {"jsonrpc": "2.0", "id": req_id, "result": None}
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}
            }

    def _initialize(self, req_id, params) -> dict:
        """Handle initialize request"""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "moltbook",
                    "version": "1.0.0"
                }
            }
        }

    def _list_tools(self, req_id) -> dict:
        """List available tools"""
        tools = []
        for schema in MoltbookTools.get_tool_schemas():
            tool = {
                "name": schema["name"],
                "description": schema["description"],
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }

            # Convert our params to JSON schema
            for param_name, param_desc in schema.get("params", {}).items():
                tool["inputSchema"]["properties"][param_name] = {
                    "type": "string",
                    "description": param_desc
                }

            tools.append(tool)

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": tools}
        }

    def _call_tool(self, req_id, params) -> dict:
        """Execute a tool call"""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        logger.info(f"Tool call: {tool_name} with {tool_args}")

        result = self.tools.execute_tool(tool_name, tool_args)

        if result.success:
            content = json.dumps(result.data, indent=2, ensure_ascii=False)
        else:
            content = f"Error: {result.error}"

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [{"type": "text", "text": content}],
                "isError": not result.success
            }
        }

    def run(self):
        """Main loop - read from stdin, write to stdout"""
        logger.info(f"Moltbook MCP Server started for @{self.agent_name}")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                response = self.handle_request(request)
                print(json.dumps(response), flush=True)

                if request.get("method") == "shutdown":
                    break

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"}
                }), flush=True)
            except Exception as e:
                logger.error(f"Error handling request: {e}")
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": str(e)}
                }), flush=True)


if __name__ == "__main__":
    server = MoltbookMCPServer()
    server.run()
