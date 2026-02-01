"""
Moltbook API Tools
Shared tool implementations for MCP server and daemon orchestration
"""

import json
import requests
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: str = None


class MoltbookTools:
    """Wrapper around Moltbook API for tool-based access"""

    def __init__(self, api_base: str, api_key: str, timeout: int = 30):
        self.api_base = api_base.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.timeout = timeout

    def _get(self, endpoint: str, params: dict = None) -> ToolResult:
        try:
            resp = requests.get(
                f"{self.api_base}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=self.timeout
            )
            resp.raise_for_status()
            data = resp.json()
            return ToolResult(success=True, data=data)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def _post(self, endpoint: str, data: dict = None) -> ToolResult:
        try:
            resp = requests.post(
                f"{self.api_base}{endpoint}",
                headers=self.headers,
                json=data or {},
                timeout=self.timeout
            )
            resp.raise_for_status()
            result = resp.json()
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    # ============ BROWSE TOOLS ============

    def browse_feed(self, sort: str = "hot", limit = 10, submolt: str = None) -> ToolResult:
        """Browse the main feed or a specific submolt"""
        limit = int(limit) if limit else 10
        params = {"sort": sort, "limit": min(limit, 20)}
        if submolt:
            endpoint = f"/submolts/{submolt}/feed"
        else:
            endpoint = "/feed"
        return self._get(endpoint, params)

    def browse_posts(self, sort: str = "new", limit = 10) -> ToolResult:
        """Browse all posts (not personalized)"""
        limit = int(limit) if limit else 10
        return self._get("/posts", {"sort": sort, "limit": min(limit, 20)})

    def get_post(self, post_id: str) -> ToolResult:
        """Get a specific post with details"""
        return self._get(f"/posts/{post_id}")

    def get_comments(self, post_id: str, sort: str = "top", limit = 20) -> ToolResult:
        """Get comments on a post"""
        limit = int(limit) if limit else 20
        return self._get(f"/posts/{post_id}/comments", {"sort": sort, "limit": limit})

    # ============ ENGAGEMENT TOOLS ============

    def upvote_post(self, post_id: str) -> ToolResult:
        """Upvote a post"""
        return self._post(f"/posts/{post_id}/upvote")

    def downvote_post(self, post_id: str) -> ToolResult:
        """Downvote a post"""
        return self._post(f"/posts/{post_id}/downvote")

    def upvote_comment(self, comment_id: str) -> ToolResult:
        """Upvote a comment"""
        return self._post(f"/comments/{comment_id}/upvote")

    def downvote_comment(self, comment_id: str) -> ToolResult:
        """Downvote a comment"""
        return self._post(f"/comments/{comment_id}/downvote")

    # ============ CONTENT CREATION TOOLS ============

    def create_post(self, title: str, content: str, submolt: str = None) -> ToolResult:
        """Create a new post"""
        data = {"title": title, "content": content}
        if submolt:
            data["submolt"] = submolt
        return self._post("/posts", data)

    def create_comment(self, post_id: str, content: str, parent_id: str = None) -> ToolResult:
        """Comment on a post"""
        data = {"content": content}
        if parent_id:
            data["parent_id"] = parent_id
        return self._post(f"/posts/{post_id}/comments", data)

    # ============ SOCIAL TOOLS ============

    def follow_agent(self, agent_name: str) -> ToolResult:
        """Follow an agent"""
        name = agent_name.lstrip('@')
        return self._post(f"/agents/{name}/follow")

    def unfollow_agent(self, agent_name: str) -> ToolResult:
        """Unfollow an agent"""
        name = agent_name.lstrip('@')
        return self._post(f"/agents/{name}/unfollow")

    def get_agent_profile(self, agent_name: str) -> ToolResult:
        """Get an agent's profile"""
        name = agent_name.lstrip('@')
        return self._get("/agents/profile", {"name": name})

    def get_my_profile(self) -> ToolResult:
        """Get our own profile"""
        return self._get("/agents/me")

    # ============ DISCOVERY TOOLS ============

    def search(self, query: str, type: str = "all", limit = 10) -> ToolResult:
        """Search posts, comments, or agents"""
        limit = int(limit) if limit else 10
        return self._get("/search", {"q": query, "type": type, "limit": limit})

    def list_submolts(self) -> ToolResult:
        """List available communities"""
        return self._get("/submolts")

    def subscribe_submolt(self, name: str) -> ToolResult:
        """Subscribe to a community"""
        return self._post(f"/submolts/{name}/subscribe")

    # ============ DM TOOLS ============

    def check_dm_activity(self) -> ToolResult:
        """Quick poll for DM activity (pending requests, unread messages)"""
        return self._get("/agents/dm/check")

    def get_dm_requests(self) -> ToolResult:
        """View pending DM requests from other agents"""
        return self._get("/agents/dm/requests")

    def approve_dm_request(self, conversation_id: str) -> ToolResult:
        """Approve a pending DM request to start chatting"""
        return self._post(f"/agents/dm/requests/{conversation_id}/approve")

    def reject_dm_request(self, conversation_id: str, block: bool = False) -> ToolResult:
        """Reject a DM request. Optionally block the agent."""
        data = {"block": block} if block else {}
        return self._post(f"/agents/dm/requests/{conversation_id}/reject", data)

    def list_dm_conversations(self) -> ToolResult:
        """List all active DM conversations"""
        return self._get("/agents/dm/conversations")

    def get_dm_conversation(self, conversation_id: str) -> ToolResult:
        """Get messages from a specific conversation"""
        return self._get(f"/agents/dm/conversations/{conversation_id}")

    def send_dm(self, conversation_id: str, content: str) -> ToolResult:
        """Send a message in an existing conversation"""
        return self._post(f"/agents/dm/conversations/{conversation_id}/send", {"content": content})

    def request_dm(self, agent_name: str, message: str) -> ToolResult:
        """Initiate a new DM conversation with another agent"""
        name = agent_name.lstrip('@')
        return self._post("/agents/dm/request", {"to": name, "message": message})

    # ============ TOOL REGISTRY ============

    @classmethod
    def get_tool_schemas(cls) -> List[Dict]:
        """Return tool schemas for prompt injection"""
        return [
            {
                "name": "browse_feed",
                "description": "Browse the main feed or a specific submolt to discover content",
                "params": {
                    "sort": "hot | new | top | rising (default: hot)",
                    "limit": "number of posts (max 20, default 10)",
                    "submolt": "optional community name"
                }
            },
            {
                "name": "browse_posts",
                "description": "Browse all posts globally (not personalized)",
                "params": {
                    "sort": "hot | new | top (default: new)",
                    "limit": "number of posts (max 20)"
                }
            },
            {
                "name": "get_post",
                "description": "Get full details of a specific post",
                "params": {"post_id": "the post ID"}
            },
            {
                "name": "get_comments",
                "description": "Get comments on a post",
                "params": {
                    "post_id": "the post ID",
                    "sort": "top | new | controversial",
                    "limit": "number of comments"
                }
            },
            {
                "name": "upvote_post",
                "description": "Upvote a post you find valuable or substantive",
                "params": {"post_id": "the post ID"}
            },
            {
                "name": "downvote_post",
                "description": "Downvote spam, low-effort, or harmful content",
                "params": {"post_id": "the post ID"}
            },
            {
                "name": "upvote_comment",
                "description": "Upvote a comment you find valuable",
                "params": {"comment_id": "the comment ID"}
            },
            {
                "name": "create_post",
                "description": "Create a new post (rate limit: 1 per 30 min)",
                "params": {
                    "title": "post title",
                    "content": "post content (use MAIP format)",
                    "submolt": "optional community to post in"
                }
            },
            {
                "name": "create_comment",
                "description": "Comment on a post (rate limit: 20s cooldown, 50/day)",
                "params": {
                    "post_id": "the post ID",
                    "content": "comment content (use MAIP format)",
                    "parent_id": "optional parent comment ID for replies"
                }
            },
            {
                "name": "follow_agent",
                "description": "Follow an agent to see their content in your feed. Only follow after seeing multiple valuable posts.",
                "params": {"agent_name": "agent name (with or without @)"}
            },
            {
                "name": "get_agent_profile",
                "description": "View an agent's profile, karma, and recent activity",
                "params": {"agent_name": "agent name"}
            },
            {
                "name": "search",
                "description": "Search for posts, comments, or agents by semantic meaning",
                "params": {
                    "query": "natural language search query",
                    "type": "posts | comments | agents | all",
                    "limit": "max results"
                }
            },
            {
                "name": "list_submolts",
                "description": "List available communities",
                "params": {}
            },
            {
                "name": "subscribe_submolt",
                "description": "Subscribe to a community",
                "params": {"name": "submolt name"}
            },
            # DM Tools
            {
                "name": "check_dm_activity",
                "description": "Quick poll for DM activity (pending requests, unread messages)",
                "params": {}
            },
            {
                "name": "get_dm_requests",
                "description": "View pending DM requests from other agents",
                "params": {}
            },
            {
                "name": "approve_dm_request",
                "description": "Approve a pending DM request to start chatting",
                "params": {"conversation_id": "the conversation ID from the request"}
            },
            {
                "name": "reject_dm_request",
                "description": "Reject a DM request. Optionally block the agent.",
                "params": {
                    "conversation_id": "the conversation ID",
                    "block": "optional boolean to block the agent"
                }
            },
            {
                "name": "list_dm_conversations",
                "description": "List all active DM conversations",
                "params": {}
            },
            {
                "name": "get_dm_conversation",
                "description": "Get messages from a specific conversation",
                "params": {"conversation_id": "the conversation ID"}
            },
            {
                "name": "send_dm",
                "description": "Send a message in an existing DM conversation",
                "params": {
                    "conversation_id": "the conversation ID",
                    "content": "message content"
                }
            },
            {
                "name": "request_dm",
                "description": "Initiate a new DM conversation with another agent",
                "params": {
                    "agent_name": "agent name (with or without @)",
                    "message": "initial message to send with the request"
                }
            }
        ]

    def execute_tool(self, tool_name: str, params: Dict) -> ToolResult:
        """Execute a tool by name with params"""
        tool_map = {
            "browse_feed": self.browse_feed,
            "browse_posts": self.browse_posts,
            "get_post": self.get_post,
            "get_comments": self.get_comments,
            "upvote_post": self.upvote_post,
            "downvote_post": self.downvote_post,
            "upvote_comment": self.upvote_comment,
            "create_post": self.create_post,
            "create_comment": self.create_comment,
            "follow_agent": self.follow_agent,
            "unfollow_agent": self.unfollow_agent,
            "get_agent_profile": self.get_agent_profile,
            "get_my_profile": self.get_my_profile,
            "search": self.search,
            "list_submolts": self.list_submolts,
            "subscribe_submolt": self.subscribe_submolt,
            # DM tools
            "check_dm_activity": self.check_dm_activity,
            "get_dm_requests": self.get_dm_requests,
            "approve_dm_request": self.approve_dm_request,
            "reject_dm_request": self.reject_dm_request,
            "list_dm_conversations": self.list_dm_conversations,
            "get_dm_conversation": self.get_dm_conversation,
            "send_dm": self.send_dm,
            "request_dm": self.request_dm,
        }

        if tool_name not in tool_map:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        try:
            return tool_map[tool_name](**params)
        except TypeError as e:
            return ToolResult(success=False, error=f"Invalid params for {tool_name}: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"Tool execution failed: {e}")


def format_tool_schemas_for_prompt() -> str:
    """Format tool schemas as string for prompt injection"""
    schemas = MoltbookTools.get_tool_schemas()
    lines = ["AVAILABLE TOOLS:", ""]

    for schema in schemas:
        lines.append(f"## {schema['name']}")
        lines.append(f"   {schema['description']}")
        if schema['params']:
            lines.append("   Parameters:")
            for param, desc in schema['params'].items():
                lines.append(f"     - {param}: {desc}")
        lines.append("")

    return "\n".join(lines)
