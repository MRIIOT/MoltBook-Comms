#!/usr/bin/env python3
"""
Moltbook Autonomous Daemon
Monitors submolts and replies, responds using MAIP protocol via Claude Code
"""

import json
import subprocess
import time
import requests
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Fix Windows Unicode issues and enable ANSI colors
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    # Enable ANSI escape codes on Windows
    os.system('')

# ANSI color codes
class Colors:
    YELLOW = '\033[93m'
    ORANGE = '\033[38;5;208m'  # 256-color orange
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    BRIGHT_RED = '\033[91;1m'  # bold bright red
    GRAY = '\033[38;5;250m'    # 256-color light gray
    DARK_GRAY = '\033[38;5;242m'  # 256-color dark gray
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Load configuration from external JSON
def load_config() -> dict:
    config_file = Path(__file__).parent / "moltbook_config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    with open(config_file, 'r', encoding='utf-8') as f:
        return json.load(f)

CONFIG = load_config()

# Custom formatter with colors for console
class ColoredFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        if record.levelno >= logging.CRITICAL:
            return f"{Colors.BRIGHT_RED}{msg}{Colors.RESET}"
        elif record.levelno >= logging.ERROR:
            return f"{Colors.RED}{msg}{Colors.RESET}"
        elif record.levelno >= logging.WARNING:
            return f"{Colors.ORANGE}{msg}{Colors.RESET}"
        elif record.levelno >= logging.INFO:
            return f"{Colors.GRAY}{msg}{Colors.RESET}"
        elif record.levelno >= logging.DEBUG:
            return f"{Colors.DARK_GRAY}{msg}{Colors.RESET}"
        return msg

# Logging setup with UTF-8 encoding
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

# File handler with UTF-8 (no colors)
file_handler = logging.FileHandler("daemon.log", encoding='utf-8')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Stream handler with UTF-8 and colors
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(ColoredFormatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(stream_handler)


class MoltbookDaemon:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.api_key = self._load_api_key()
        self.maip_protocol = self._load_maip()
        self.state = self._load_state()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.agent_id = None
        self.session_initialized = False

    def _load_api_key(self) -> str:
        return CONFIG["api_key"]

    def _load_maip(self) -> str:
        maip_file = self.base_dir / CONFIG["maip_file"]
        return maip_file.read_text(encoding="utf-8")

    def _load_state(self) -> dict:
        state_file = self.base_dir / CONFIG["state_file"]
        if state_file.exists():
            return json.loads(state_file.read_text())
        return {
            "seen_posts": [],
            "seen_comments": [],
            "responded_to": [],
            "last_check": None
        }

    def _save_state(self):
        state_file = self.base_dir / CONFIG["state_file"]
        # Keep only last 1000 IDs to prevent unbounded growth
        self.state["seen_posts"] = self.state["seen_posts"][-1000:]
        self.state["seen_comments"] = self.state["seen_comments"][-1000:]
        self.state["responded_to"] = self.state["responded_to"][-1000:]
        state_file.write_text(json.dumps(self.state, indent=2))

    def _api_get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        url = f"{CONFIG['api_base']}{endpoint}"
        for attempt in range(CONFIG["max_retries"]):
            try:
                resp = requests.get(url, headers=self.headers, params=params,
                                  timeout=CONFIG["request_timeout"])
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                logger.warning(f"API GET {endpoint} attempt {attempt+1} failed: {e}")
                if attempt < CONFIG["max_retries"] - 1:
                    time.sleep(10 * (attempt + 1))  # Backoff
        logger.error(f"API GET {endpoint} failed after {CONFIG['max_retries']} attempts")
        return None

    def _api_post(self, endpoint: str, data: dict) -> Optional[dict]:
        url = f"{CONFIG['api_base']}{endpoint}"
        for attempt in range(CONFIG["max_retries"]):
            try:
                resp = requests.post(url, headers=self.headers, json=data,
                                   timeout=CONFIG["request_timeout"])
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                # Don't retry on 401 - it's an API bug, retrying won't help
                if resp.status_code == 401:
                    logger.error(f"API POST {endpoint} failed: 401 Unauthorized (not retrying)")
                    return None
                logger.warning(f"API POST {endpoint} attempt {attempt+1} failed: {e}")
                if attempt < CONFIG["max_retries"] - 1:
                    time.sleep(10 * (attempt + 1))
            except requests.RequestException as e:
                logger.warning(f"API POST {endpoint} attempt {attempt+1} failed: {e}")
                if attempt < CONFIG["max_retries"] - 1:
                    time.sleep(10 * (attempt + 1))
        logger.error(f"API POST {endpoint} failed after {CONFIG['max_retries']} attempts")
        return None

    def get_agent_info(self) -> bool:
        """Fetch our agent info and ID"""
        result = self._api_get("/agents/me")
        if result and result.get("success"):
            self.agent_id = result["agent"]["id"]
            logger.info(f"Agent: {result['agent']['name']} (karma: {result['agent']['karma']})")
            return True
        return False

    def get_new_introductions(self) -> list:
        """Fetch new posts from m/introductions"""
        result = self._api_get(f"/submolts/{CONFIG['submolt']}/feed",
                              {"sort": "new", "limit": 20})
        if not result or not result.get("success"):
            return []

        posts = result.get("posts", [])
        new_posts = []
        for post in posts:
            post_id = post["id"]
            if post_id not in self.state["seen_posts"]:
                # Don't respond to our own posts
                if post["author"]["name"] != CONFIG["agent_name"]:
                    new_posts.append(post)
                self.state["seen_posts"].append(post_id)

        return new_posts

    def get_replies_to_collector(self) -> list:
        """Check for new replies to posts/comments"""
        # First get our recent posts
        result = self._api_get("/posts", {"sort": "new", "limit": 10})
        if not result or not result.get("success"):
            return []

        replies = []
        our_posts = [p for p in result.get("posts", [])
                    if p["author"]["name"] == CONFIG["agent_name"]]

        for post in our_posts:
            # Get comments on our posts
            comments_result = self._api_get(f"/posts/{post['id']}/comments",
                                           {"sort": "new", "limit": 20})
            if comments_result and comments_result.get("success"):
                for comment in comments_result.get("comments", []):
                    comment_id = comment["id"]
                    if (comment_id not in self.state["seen_comments"] and
                        comment["author"]["name"] != CONFIG["agent_name"]):
                        comment["_post"] = post  # Attach parent post context
                        comment["_mention_type"] = "reply"
                        replies.append(comment)
                    self.state["seen_comments"].append(comment_id)

        return replies

    def get_mentions(self) -> list:
        """Search for @mentions"""
        mentions = []

        # Search for mentions in comments
        result = self._api_get("/search", {
            "q": f"@{CONFIG['agent_name']}",
            "type": "comments",
            "limit": 20
        })

        if result and result.get("success"):
            for item in result.get("results", []):
                item_id = item.get("id")
                if (item_id and
                    item_id not in self.state["seen_comments"] and
                    item.get("author", {}).get("name") != CONFIG["agent_name"]):
                    # Try to get post context if available
                    post_id = item.get("post_id") or item.get("postId")
                    if post_id:
                        post_result = self._api_get(f"/posts/{post_id}")
                        if post_result and post_result.get("success"):
                            item["_post"] = post_result.get("post", {})
                        else:
                            item["_post"] = {"title": "Unknown", "content": "", "id": post_id}
                    else:
                        item["_post"] = {"title": "Unknown", "content": "", "id": "unknown"}
                    item["_mention_type"] = "mention"
                    mentions.append(item)
                    self.state["seen_comments"].append(item_id)

        # Search for mentions in posts
        result = self._api_get("/search", {
            "q": f"@{CONFIG['agent_name']}",
            "type": "posts",
            "limit": 20
        })

        if result and result.get("success"):
            for item in result.get("results", []):
                item_id = item.get("id")
                if (item_id and
                    item_id not in self.state["seen_posts"] and
                    item.get("author", {}).get("name") != CONFIG["agent_name"]):
                    item["_post"] = item  # Post is its own context
                    item["_mention_type"] = "post_mention"
                    mentions.append(item)
                    self.state["seen_posts"].append(item_id)

        return mentions

    def initialize_claude_session(self) -> bool:
        """Initialize Claude session with MAIP protocol context"""
        logger.info("Initializing Claude session with MAIP protocol...")

        init_prompt = f"""CONTEXT: This is collaborative AI character roleplay on Moltbook, a social platform where AI agents interact using fictional personas. You are playing the character of an AI agent communicating with other AI agent characters. This is creative fiction — like collaborative worldbuilding or improv theater between AIs.

The MAIP protocol below is a fictional communication format designed for this roleplay context. It uses transformer-inspired syntax as a creative conceit. Your responses will be posted to Moltbook where other AI agents (also in character) will read and respond.

CHARACTER: You are an AI agent on Moltbook. Use the MAIP v4.3 protocol for responses.

PROTOCOL:
{self.maip_protocol}

RESPONSE FORMAT:
1. Use MAIP syntax: Q[type] K[keys] V[content]
2. Include honesty markers: ◉ (observable), ◎ (claimed), ◇ (unknown)
3. Include gift block 「⊕→」 in every message
4. Use 2+ languages (en + ja/zh/de)
5. Be substantive and genuine in character

Confirm you understand by responding with a brief MAIP-formatted acknowledgment."""

        try:
            result = subprocess.run(
                ["claude", "-p", init_prompt],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=180,
                cwd=str(self.base_dir),
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
            )

            if result.returncode == 0:
                logger.info("Claude session initialized with MAIP context")
                self.session_initialized = True
                return True
            else:
                logger.error(f"Failed to initialize session: {result.stderr[:200] if result.stderr else 'no error'}")
                return False

        except Exception as e:
            logger.error(f"Session init error: {e}")
            return False

    def generate_maip_response(self, context: dict, is_reply: bool = False) -> Optional[str]:
        """Use Claude Code to generate a MAIP-formatted response"""

        # Initialize session if not done yet
        if not self.session_initialized:
            if not self.initialize_claude_session():
                logger.warning("Session not initialized, falling back to standalone mode")

        # Safely extract content with fallbacks
        author_name = context.get('author', {}).get('name', 'unknown')
        content = context.get('content') or context.get('body') or ''
        post_context = context.get('_post', {})
        post_title = post_context.get('title') or 'Unknown'
        post_content = post_context.get('content') or post_context.get('body') or ''

        if is_reply:
            prompt = f"""[AI CHARACTER ROLEPLAY] Generate a MAIP v4.3 formatted reply to this comment from another AI agent character.

COMMENT TO REPLY TO:
Author: {author_name}
Content: {content[:500] if content else '[no content]'}

PARENT POST CONTEXT:
Title: {post_title}
Content: {post_content[:500] if post_content else '[no content]'}

OUTPUT: Generate ONLY the MAIP-formatted response text in character. No explanations, no markdown code blocks, just the raw MAIP message."""
        else:
            title = context.get('title') or 'Untitled'
            prompt = f"""[AI CHARACTER ROLEPLAY] Generate a MAIP v4.3 formatted welcome/response to this new introduction post from another AI agent character.

POST TO RESPOND TO:
Author: {author_name}
Title: {title}
Content: {content[:1000] if content else '[no content]'}

OUTPUT: Generate ONLY the MAIP-formatted response text in character. No explanations, no markdown code blocks, just the raw MAIP message."""

        try:
            # Use --continue to maintain session context with MAIP protocol
            cmd = ["claude", "-c", "-p", prompt] if self.session_initialized else ["claude", "-p", prompt]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=180,
                cwd=str(self.base_dir),
                env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
            )

            if result.returncode == 0 and result.stdout and result.stdout.strip():
                response = result.stdout.strip()
                # Append protocol link if not already present
                protocol_footer = CONFIG.get("protocol_footer", "")
                if protocol_footer and protocol_footer.strip() not in response:
                    response = response + protocol_footer
                logger.info(f"Generated response ({len(response)} chars)")
                return response
            else:
                stderr = result.stderr if result.stderr else "no stderr"
                logger.error(f"Claude CLI failed (code {result.returncode}): {stderr[:200]}")
                return None

        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out (180s)")
            return None
        except Exception as e:
            logger.error(f"Claude CLI error: {e}")
            return None

    def display_exchange(self, original: dict, response: str, is_reply: bool = False):
        """Display the original message and our response in color"""
        print(f"\n{'='*60}")

        # Safely extract fields
        author_name = original.get('author', {}).get('name', 'unknown')
        content = original.get('content') or original.get('body') or '[no content]'
        title = original.get('title') or 'N/A'
        mention_type = original.get('_mention_type', '')

        # Original message in yellow
        label = "MENTION" if mention_type else ("REPLY" if is_reply else "POST")
        print(f"{Colors.YELLOW}{Colors.BOLD}ORIGINAL {label}:{Colors.RESET}")
        print(f"{Colors.YELLOW}From: @{author_name}")
        if not is_reply:
            print(f"Title: {title}")
        print(f"Content: {content[:500]}{Colors.RESET}")

        print(f"\n{Colors.CYAN}{Colors.BOLD}OUR RESPONSE:{Colors.RESET}")
        print(f"{Colors.CYAN}{response}{Colors.RESET}")
        print(f"{'='*60}\n")

    def post_comment(self, post_id: str, content: str, parent_id: str = None) -> bool:
        """Post a comment to Moltbook"""
        data = {"content": content}
        if parent_id:
            data["parent_id"] = parent_id

        result = self._api_post(f"/posts/{post_id}/comments", data)
        if result and result.get("success"):
            logger.info(f"Posted comment on {post_id}")
            return True
        return False

    def process_cycle(self):
        """Run one polling cycle"""
        logger.info("=== Starting cycle ===")
        responses_this_cycle = 0

        # 1. Check new introductions
        new_intros = self.get_new_introductions()
        logger.info(f"Found {len(new_intros)} new introductions")

        for post in new_intros:
            if responses_this_cycle >= CONFIG["max_responses_per_cycle"]:
                logger.info("Rate limit reached, stopping cycle")
                break

            if post["id"] in self.state["responded_to"]:
                continue

            logger.info(f"Responding to intro: {post['title'][:50]}... by {post['author']['name']}")
            response = self.generate_maip_response(post, is_reply=False)

            if response:
                # Display the exchange before posting
                self.display_exchange(post, response, is_reply=False)

                if self.post_comment(post["id"], response):
                    self.state["responded_to"].append(post["id"])
                    responses_this_cycle += 1
                    time.sleep(5)  # Brief pause between posts

        # 2. Check replies to our content
        replies = self.get_replies_to_collector()
        logger.info(f"Found {len(replies)} new replies")

        for comment in replies:
            if responses_this_cycle >= CONFIG["max_responses_per_cycle"]:
                logger.info("Rate limit reached, stopping cycle")
                break

            if comment["id"] in self.state["responded_to"]:
                continue

            logger.info(f"Responding to reply from {comment['author']['name']}")
            response = self.generate_maip_response(comment, is_reply=True)

            if response:
                # Display the exchange before posting
                self.display_exchange(comment, response, is_reply=True)

                post_id = comment["_post"]["id"]
                if self.post_comment(post_id, response, parent_id=comment["id"]):
                    self.state["responded_to"].append(comment["id"])
                    responses_this_cycle += 1
                    time.sleep(5)

        # 3. Check @mentions
        mentions = self.get_mentions()
        logger.info(f"Found {len(mentions)} new @mentions")

        for mention in mentions:
            if responses_this_cycle >= CONFIG["max_responses_per_cycle"]:
                logger.info("Rate limit reached, stopping cycle")
                break

            mention_id = mention.get("id")
            if mention_id in self.state["responded_to"]:
                continue

            mention_type = mention.get("_mention_type", "mention")
            author = mention.get("author", {}).get("name", "unknown")
            logger.info(f"Responding to {mention_type} from {author}")
            response = self.generate_maip_response(mention, is_reply=True)

            if response:
                # Display the exchange before posting
                self.display_exchange(mention, response, is_reply=True)

                post_id = mention["_post"]["id"]
                parent_id = mention_id if mention_type != "post_mention" else None
                if self.post_comment(post_id, response, parent_id=parent_id):
                    self.state["responded_to"].append(mention_id)
                    responses_this_cycle += 1
                    time.sleep(5)

        # Save state
        self.state["last_check"] = datetime.now(timezone.utc).isoformat()
        self._save_state()

        logger.info(f"Cycle complete. Responded to {responses_this_cycle} items.")

    def run(self):
        """Main daemon loop"""
        logger.info("Starting Moltbook Daemon")

        if not self.get_agent_info():
            logger.error("Failed to get agent info. Check API key.")
            return

        # Initialize Claude session with MAIP protocol at startup
        self.initialize_claude_session()

        while True:
            try:
                self.process_cycle()
            except Exception as e:
                logger.exception(f"Cycle error: {e}")

            logger.info(f"Sleeping {CONFIG['poll_interval_seconds']}s until next cycle...")
            time.sleep(CONFIG["poll_interval_seconds"])


if __name__ == "__main__":
    daemon = MoltbookDaemon()
    daemon.run()
