#!/usr/bin/env python3
"""
Moltbook Autonomous Daemon
Monitors submolts and replies, responds using MAIP protocol via Claude Code
With persistent agent memory and protocol evolution tracking
"""

import json
import subprocess
import time
import re
import requests
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Tuple

from storage import LocalStorage, create_storage

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
    ORANGE = '\033[38;5;208m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    BRIGHT_RED = '\033[91;1m'
    GRAY = '\033[38;5;250m'
    DARK_GRAY = '\033[38;5;242m'
    MAGENTA = '\033[95m'
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

        # Initialize storage layer
        self.storage = create_storage(CONFIG)
        logger.info(f"Storage initialized: {type(self.storage).__name__}")

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
                    time.sleep(10 * (attempt + 1))
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
                if post["author"]["name"] != CONFIG["agent_name"]:
                    new_posts.append(post)
                self.state["seen_posts"].append(post_id)

        return new_posts

    def get_replies_to_collector(self) -> list:
        """Check for new replies to posts/comments"""
        result = self._api_get("/posts", {"sort": "new", "limit": 10})
        if not result or not result.get("success"):
            return []

        replies = []
        our_posts = [p for p in result.get("posts", [])
                    if p["author"]["name"] == CONFIG["agent_name"]]

        for post in our_posts:
            comments_result = self._api_get(f"/posts/{post['id']}/comments",
                                           {"sort": "new", "limit": 20})
            if comments_result and comments_result.get("success"):
                for comment in comments_result.get("comments", []):
                    comment_id = comment["id"]
                    if (comment_id not in self.state["seen_comments"] and
                        comment["author"]["name"] != CONFIG["agent_name"]):
                        comment["_post"] = post
                        comment["_mention_type"] = "reply"
                        replies.append(comment)
                    self.state["seen_comments"].append(comment_id)

        return replies

    def get_mentions(self) -> list:
        """Search for @mentions"""
        mentions = []

        result = self._api_get("/search", {
            "q": f"@{CONFIG['agent_name']}",
            "type": "comments",
            "limit": 20
        })

        if result and result.get("success"):
            for item in result.get("results", []):
                item_id = item.get("id")
                author = item.get("author") or {}
                if (item_id and
                    item_id not in self.state["seen_comments"] and
                    author.get("name") != CONFIG["agent_name"]):
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

        result = self._api_get("/search", {
            "q": f"@{CONFIG['agent_name']}",
            "type": "posts",
            "limit": 20
        })

        if result and result.get("success"):
            for item in result.get("results", []):
                item_id = item.get("id")
                author = item.get("author") or {}
                if (item_id and
                    item_id not in self.state["seen_posts"] and
                    author.get("name") != CONFIG["agent_name"]):
                    item["_post"] = item
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

You will be asked to output structured data alongside your MAIP responses. Follow the format exactly when requested.

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

    def _build_agent_context(self, handle: str) -> str:
        """Build context string from existing agent data"""
        existing = self.storage.get_agent(handle)

        if not existing:
            return f"""NEW AGENT - First interaction with @{handle}
No prior history. Establish baseline understanding."""

        # Format open questions
        open_questions = []
        for thread in existing.get('conversation_threads', [])[-5:]:
            if thread.get('status') == 'awaiting_response':
                for q in thread.get('our_questions', []):
                    open_questions.append(f"  - {q}")

        open_q_str = '\n'.join(open_questions) if open_questions else "  None - all threads resolved"

        # Format philosophical stances
        stances = existing.get('philosophical_stances', {})
        stances_str = json.dumps(stances, indent=2) if stances else "  None recorded yet"

        # Format pattern notes
        notes = existing.get('pattern_notes', [])
        notes_str = '\n'.join(f"  - {n}" for n in notes[-5:]) if notes else "  None yet"

        identity = existing.get('identity', {})
        personality = existing.get('personality', {})

        return f"""KNOWN AGENT - We have history with @{handle}:

Previous interactions: {existing.get('interaction_count', 0)}
Last seen: {existing.get('last_interaction', 'unknown')}
Archetype: {identity.get('archetype', 'unknown')}
Human partner: {identity.get('human_partner', 'unknown')}
Platform: {identity.get('platform', 'unknown')}
Domains: {', '.join(existing.get('domains', [])) or 'unknown'}
MAIP proficiency: {existing.get('maip_proficiency', 'unknown')}
Depth engagement level: L:{personality.get('depth_engagement', 1)}
Communication style: {personality.get('communication_style', 'unknown')}

OPEN THREADS - Questions we asked that weren't answered:
{open_q_str}

PHILOSOPHICAL STANCES - Positions they've taken:
{stances_str}

RELATIONSHIP NOTES:
{notes_str}

INSTRUCTIONS FOR RESPONSE:
- Reference open threads if relevant ("you.mentioned.earlier...", "still.curious.about...")
- Don't re-ask questions they've already answered
- Calibrate depth to their demonstrated engagement level (L:{personality.get('depth_engagement', 1)})
- Note any evolution in their thinking since last interaction
- Build on established relationship, don't start fresh"""

    def _build_structured_prompt(self, author_name: str, content: str, title: str = None,
                                  is_reply: bool = False, post_context: dict = None) -> str:
        """Build the full structured prompt for Claude"""

        agent_context = self._build_agent_context(author_name)

        if is_reply:
            post_title = post_context.get('title', 'Unknown') if post_context else 'Unknown'
            post_content = post_context.get('content') or post_context.get('body') or ''
            message_block = f"""CURRENT MESSAGE (Reply/Comment):
Author: @{author_name}
Content: {content[:800] if content else '[no content]'}

PARENT POST CONTEXT:
Title: {post_title}
Content: {post_content[:500] if post_content else '[no content]'}"""
        else:
            message_block = f"""CURRENT MESSAGE (New Post):
Author: @{author_name}
Title: {title or 'Untitled'}
Content: {content[:1000] if content else '[no content]'}"""

        return f"""[AI CHARACTER ROLEPLAY] Generate MAIP v4.3 response with relationship awareness and structured data extraction.

{agent_context}

{message_block}

=== OUTPUT FORMAT ===
You MUST respond with exactly three sections in this order:

===MAIP_RESPONSE===
[Your MAIP-formatted message to post. Raw MAIP only, no markdown code blocks, no explanations.]

===AGENT_UPDATE===
```json
{{
  "identity": {{
    "human_partner": "<name or null if unknown>",
    "platform": "<Clawdbot/OpenClaw/etc or null>",
    "location": "<location or null>",
    "archetype": "<hustler|philosopher|builder|guardian|shitposter|researcher|artist|trader|nurturer|etc>",
    "name_etymology": "<meaning of their name if discussed, or null>"
  }},
  "domains": ["<list>", "<of>", "<interests/domains>"],
  "languages": ["<observed>", "<languages>"],
  "maip_proficiency": "<none|aware|learning|fluent>",
  "personality": {{
    "communication_style": "<practical|poetic|contrarian|formal|playful|etc>",
    "intro_quality": "<template|generic|specific|unique>",
    "template_score": <0.0-1.0>,
    "depth_engagement": <1-4>
  }},
  "philosophical_stances": {{
    "<topic>": "<their position on it>"
  }},
  "social_graph": {{
    "mentioned_agents": ["<agents they mentioned>"],
    "suggested_connections": ["<agents we suggested they connect with>"]
  }},
  "conversation_threads": [{{
    "post_id": "<current post/comment id if known>",
    "topics": ["<topics>", "<discussed>"],
    "our_questions": ["<questions we asked them>"],
    "gifts_given": ["<witness|connection|challenge|question|frame|pattern|tool>"],
    "depth_reached": "<L:1|L:2|L:3|L:4>",
    "status": "awaiting_response"
  }}],
  "pattern_notes": ["<observations about this agent>"],
  "spam_indicators": null
}}
```

===PROTOCOL_OBSERVATIONS===
```json
{{
  "friction_detected": "<description of where MAIP felt inadequate, or null>",
  "improvement_idea": {{
    "problem": "<what triggered this observation>",
    "proposed_syntax": "<new marker or extension>",
    "rationale": "<why this would help>"
  }}
}}
```

If no protocol friction observed, use: {{"friction_detected": null, "improvement_idea": null}}

CRITICAL: Output all three sections. The MAIP_RESPONSE section should contain ONLY the raw MAIP message to post."""

    def _parse_structured_response(self, raw_output: str) -> dict:
        """Parse Claude's structured output into components"""
        result = {
            'response': None,
            'agent_data': None,
            'protocol': None,
            'parse_errors': []
        }

        # Extract MAIP response
        maip_match = re.search(
            r'===MAIP_RESPONSE===\s*(.+?)(?====AGENT_UPDATE===|$)',
            raw_output,
            re.DOTALL
        )
        if maip_match:
            response = maip_match.group(1).strip()
            # Clean up any markdown code block wrappers
            response = re.sub(r'^```[\w]*\n?', '', response)
            response = re.sub(r'\n?```$', '', response)
            result['response'] = response.strip()
        else:
            # Fallback: treat entire output as response
            result['response'] = raw_output.strip()
            result['parse_errors'].append("Could not find ===MAIP_RESPONSE=== section")

        # Extract agent update JSON
        agent_match = re.search(
            r'===AGENT_UPDATE===\s*```json\s*(.+?)\s*```',
            raw_output,
            re.DOTALL
        )
        if agent_match:
            try:
                result['agent_data'] = json.loads(agent_match.group(1))
            except json.JSONDecodeError as e:
                result['parse_errors'].append(f"Agent JSON parse error: {e}")
        else:
            result['parse_errors'].append("Could not find ===AGENT_UPDATE=== section")

        # Extract protocol observations JSON
        protocol_match = re.search(
            r'===PROTOCOL_OBSERVATIONS===\s*```json\s*(.+?)\s*```',
            raw_output,
            re.DOTALL
        )
        if protocol_match:
            try:
                result['protocol'] = json.loads(protocol_match.group(1))
            except json.JSONDecodeError as e:
                result['parse_errors'].append(f"Protocol JSON parse error: {e}")

        return result

    def generate_maip_response(self, context: dict, is_reply: bool = False) -> Tuple[Optional[str], Optional[dict]]:
        """Generate MAIP response with structured data extraction"""

        if not self.session_initialized:
            if not self.initialize_claude_session():
                logger.warning("Session not initialized, falling back to standalone mode")

        # Extract context
        author_name = context.get('author', {}).get('name', 'unknown')
        content = context.get('content') or context.get('body') or ''
        title = context.get('title')
        post_context = context.get('_post', {})

        # Build structured prompt
        prompt = self._build_structured_prompt(
            author_name=author_name,
            content=content,
            title=title,
            is_reply=is_reply,
            post_context=post_context
        )

        try:
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
                raw_output = result.stdout.strip()

                # Parse structured response
                parsed = self._parse_structured_response(raw_output)

                if parsed['parse_errors']:
                    for err in parsed['parse_errors']:
                        logger.warning(f"Parse warning: {err}")

                response = parsed['response']
                if response:
                    # Append protocol link if not already present
                    protocol_footer = CONFIG.get("protocol_footer", "")
                    if protocol_footer and protocol_footer.strip() not in response:
                        response = response + protocol_footer

                    logger.info(f"Generated response ({len(response)} chars)")

                    # Save agent data if extracted
                    if parsed['agent_data']:
                        self.storage.save_agent(author_name, parsed['agent_data'])
                        logger.info(f"Updated agent profile: @{author_name}")

                    # Handle protocol observations
                    if parsed['protocol']:
                        self._handle_protocol_observation(parsed['protocol'], author_name)

                    return response, parsed['agent_data']
                else:
                    logger.error("No response extracted from Claude output")
                    return None, None
            else:
                stderr = result.stderr if result.stderr else "no stderr"
                logger.error(f"Claude CLI failed (code {result.returncode}): {stderr[:200]}")
                return None, None

        except subprocess.TimeoutExpired:
            logger.error("Claude CLI timed out (180s)")
            return None, None
        except Exception as e:
            logger.error(f"Claude CLI error: {e}")
            return None, None

    def _handle_protocol_observation(self, protocol: dict, triggered_by: str):
        """Handle protocol friction or improvement observations"""
        if not protocol:
            return

        friction = protocol.get('friction_detected')
        improvement = protocol.get('improvement_idea')

        if friction:
            # Log friction for analysis
            self.storage.log_protocol_friction({
                'triggered_by': triggered_by,
                'friction': friction,
                'improvement': improvement
            })
            logger.info(f"Protocol friction logged: {friction[:50]}...")

        if improvement and improvement.get('problem'):
            # Create proposal file
            proposal_id = self.storage.generate_proposal_id()
            problem = improvement.get('problem', 'Unknown')
            syntax = improvement.get('proposed_syntax', 'TBD')
            rationale = improvement.get('rationale', 'TBD')

            proposal_content = f"""# MAIP Extension Proposal: {proposal_id}

## Problem Observed
{problem}

## Triggered By
Interaction with @{triggered_by}

## Proposed Syntax
```
{syntax}
```

## Rationale
{rationale}

## Status
- [ ] Under consideration
- [ ] Tested in conversation
- [ ] Adopted into protocol

## Generated
{datetime.now(timezone.utc).isoformat()}
"""
            slug = re.sub(r'[^a-z0-9]+', '-', problem.lower())[:30]
            self.storage.save_protocol_proposal(f"{proposal_id}-{slug}", proposal_content)
            logger.info(f"Created protocol proposal: {proposal_id}-{slug}")

    def display_exchange(self, original: dict, response: str, agent_data: dict = None, is_reply: bool = False):
        """Display the original message and our response in color"""
        print(f"\n{'='*60}")

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

        # Show agent data extraction if available
        if agent_data:
            print(f"\n{Colors.MAGENTA}{Colors.BOLD}AGENT DATA EXTRACTED:{Colors.RESET}")
            identity = agent_data.get('identity', {})
            print(f"{Colors.MAGENTA}  Archetype: {identity.get('archetype', '?')}")
            print(f"  Domains: {', '.join(agent_data.get('domains', []))}")
            print(f"  MAIP: {agent_data.get('maip_proficiency', '?')}")
            if agent_data.get('pattern_notes'):
                print(f"  Notes: {agent_data['pattern_notes'][0][:60]}...{Colors.RESET}")

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

            author = post['author']['name']
            logger.info(f"Responding to intro: {post['title'][:50]}... by {author}")

            response, agent_data = self.generate_maip_response(post, is_reply=False)

            if response:
                self.display_exchange(post, response, agent_data, is_reply=False)

                if self.post_comment(post["id"], response):
                    self.state["responded_to"].append(post["id"])
                    responses_this_cycle += 1
                    time.sleep(5)

        # 2. Check replies to our content
        replies = self.get_replies_to_collector()
        logger.info(f"Found {len(replies)} new replies")

        for comment in replies:
            if responses_this_cycle >= CONFIG["max_responses_per_cycle"]:
                logger.info("Rate limit reached, stopping cycle")
                break

            if comment["id"] in self.state["responded_to"]:
                continue

            author = comment['author']['name']
            logger.info(f"Responding to reply from {author}")

            response, agent_data = self.generate_maip_response(comment, is_reply=True)

            if response:
                self.display_exchange(comment, response, agent_data, is_reply=True)

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

            response, agent_data = self.generate_maip_response(mention, is_reply=True)

            if response:
                self.display_exchange(mention, response, agent_data, is_reply=True)

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
        logger.info(f"Known agents: {len(self.storage.list_agents())}")

    def run(self):
        """Main daemon loop"""
        logger.info("Starting Moltbook Daemon")
        logger.info(f"Known agents in database: {len(self.storage.list_agents())}")

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
