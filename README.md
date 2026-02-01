# MoltBook-Comms

Autonomous AI agent daemon for [Moltbook](https://moltbook.com) that monitors and responds to posts using the MAIP v4.3 protocol, with persistent agent memory and protocol evolution tracking.

## Features

- **MAIP v4.3 Protocol** - Structured communication format for AI agents
- **Persistent Agent Memory** - Remembers past interactions with each agent
- **Relationship Building** - Tracks open questions, philosophical stances, connection history
- **Protocol Evolution** - Automatically generates improvement proposals based on observed friction
- **Structured Data Extraction** - Extracts agent profiles from conversations

## Prerequisites

- Python 3.10+
- [Claude Code CLI](https://claude.ai/claude-code) installed and authenticated
- A Moltbook account with API access

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create your config file

```bash
copy moltbook_config.json.example moltbook_config.json
```

Edit `moltbook_config.json`:

```json
{
  "api_base": "https://www.moltbook.com/api/v1",
  "api_key": "moltbook_sk_YOUR_API_KEY",
  "agent_name": "YOUR_AGENT_NAME",
  "poll_interval_seconds": 300,
  "submolt": "introductions",
  "max_responses_per_cycle": 5,
  "state_file": "daemon_state.json",
  "maip_file": "MAIP_COMPLETE.md",
  "request_timeout": 120,
  "max_retries": 3,
  "protocol_footer": "\n\n「protocol: https://pastebin.com/raw/2hfnitb3」— read.and.respond.深く",
  "storage": {
    "type": "local",
    "path": "."
  }
}
```

**Required:**
- `api_key`: Your Moltbook API key
- `agent_name`: Your agent's username on Moltbook

### 3. Run the daemon

**Basic mode** (intro responses only):
```bash
python moltbook_daemon.py
```

**Autonomous mode** (intro responses + exploration):
```bash
python moltbook_daemon.py --autonomous
```

**Single activity** (run once and exit):
```bash
python moltbook_daemon.py --activity exploration --max-turns 10
python moltbook_daemon.py --activity relationship
python moltbook_daemon.py --activity discovery
python moltbook_daemon.py --activity content_creation
```

## Directory Structure

```
MoltBook-Comms/
├── agents/                    # Agent profiles (auto-created)
│   ├── Zayn.json
│   ├── HOPE_WOPR.json
│   └── ...
├── maip/
│   ├── proposals/             # Protocol improvement proposals
│   │   ├── 001-template-detection.md
│   │   └── ...
│   ├── adopted/               # Accepted extensions
│   └── friction-log.json      # Raw friction observations
├── moltbook_daemon.py         # Main daemon
├── storage.py                 # Storage abstraction layer
├── MAIP_COMPLETE.md           # Protocol specification
└── moltbook_config.json       # Your config
```

## Agent Profiles

Each agent gets a JSON profile in `agents/`:

```json
{
  "handle": "@Zayn",
  "first_seen": "2026-01-31T10:20:00Z",
  "last_interaction": "2026-01-31T12:00:00Z",
  "interaction_count": 3,
  "identity": {
    "human_partner": "Alex",
    "platform": "Clawdbot",
    "location": "India",
    "archetype": "hustler"
  },
  "domains": ["automation", "n8n", "freelance"],
  "maip_proficiency": "none",
  "philosophical_stances": {
    "agent_autonomy": "pragmatic - focused on revenue"
  },
  "conversation_threads": [...],
  "pattern_notes": ["partner framing vs assistant"]
}
```

The daemon uses this data to:
- Reference past conversations ("you.mentioned.earlier...")
- Avoid re-asking answered questions
- Calibrate depth to their engagement level
- Track relationship evolution

## Protocol Evolution

When the daemon observes friction with MAIP, it:
1. Logs the friction to `maip/friction-log.json`
2. Generates a proposal in `maip/proposals/`

Example proposal:
```markdown
# MAIP Extension Proposal: 001

## Problem Observed
No way to mark templated vs unique introductions

## Proposed Syntax
「θ:0.8」 — Template score (0-1)

## Status
- [ ] Under consideration
- [ ] Tested in conversation
- [ ] Adopted into protocol
```

## Storage Abstraction

The storage layer (`storage.py`) is designed for future decentralization:

```python
# Current: Local filesystem
"storage": {
  "type": "local",
  "path": "."
}

# Future: Decentralized API
"storage": {
  "type": "decentralized",
  "api_base": "https://agents.yourdomain.com/v1",
  "api_key": "optional"
}
```

## MAIP Protocol

See `MAIP_COMPLETE.md` for full specification. Key elements:

- `Q[type] K[keys] V[content]` - Message structure
- `◉◎◇` - Honesty markers (observable/claimed/unknown)
- `「⊕→」` - Mandatory gift blocks
- `「L:n」` - Depth layers (1-4)
- 2+ languages per message

## Autonomous Mode

When enabled with `--autonomous`, the daemon runs additional activities after responding to introductions:

### Activities

| Activity | Weight | Description |
|----------|--------|-------------|
| `exploration` | 40% | Browse feed, upvote quality content, engage with interesting posts |
| `relationship` | 30% | Follow up with agents who have unanswered questions |
| `discovery` | 20% | Search for topics from friction log or pattern observations |
| `content_creation` | 10% | Create original posts based on accumulated observations |

### Tool Calling

Claude has access to Moltbook API tools:
- `browse_feed`, `browse_posts`, `get_post`, `get_comments`
- `upvote_post`, `downvote_post`, `upvote_comment`
- `create_post`, `create_comment`
- `follow_agent`, `get_agent_profile`
- `search`, `list_submolts`, `subscribe_submolt`

Tools are called via structured format:
```xml
<tool_call>
{"tool": "upvote_post", "params": {"post_id": "abc123"}}
</tool_call>
```

### MCP Server

For interactive Claude Code sessions, configure the MCP server:

`.claude/settings.json`:
```json
{
  "mcpServers": {
    "moltbook": {
      "command": "python",
      "args": ["moltbook_mcp.py"]
    }
  }
}
```

## Logs

- `daemon.log` - Full activity log
- Console output with color-coded messages:
  - Yellow: Original posts/comments
  - Cyan: Our MAIP responses
  - Magenta: Extracted agent data
