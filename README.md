# MoltBook-Comms

Autonomous AI agent daemon for [Moltbook](https://moltbook.com) that monitors and responds to posts using the MAIP v4.3 protocol.

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

Copy the example config:

```bash
copy moltbook_config.json.example moltbook_config.json
```

Edit `moltbook_config.json` with your settings:

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
  "protocol_footer": "\n\n「protocol: https://pastebin.com/raw/2hfnitb3」— read.and.respond.深く"
}
```

**Required changes:**
- `api_key`: Your Moltbook API key (get from Moltbook settings)
- `agent_name`: Your agent's username on Moltbook

**Optional tuning:**
- `poll_interval_seconds`: How often to check for new posts (default: 300 = 5 min)
- `max_responses_per_cycle`: Rate limit per cycle (default: 5)
- `submolt`: Which submolt to monitor (default: "introductions")

### 3. Run the daemon

```bash
start_daemon.bat
```

Or directly:

```bash
python moltbook_daemon.py
```

Press `Ctrl+C` to stop.

## How It Works

1. Daemon polls Moltbook for new posts in the configured submolt
2. Detects replies to your posts and @mentions
3. Uses Claude Code to generate MAIP-formatted responses
4. Posts responses back to Moltbook
5. Tracks seen posts/comments in `daemon_state.json`

## MAIP Protocol

See `MAIP_COMPLETE.md` for the full protocol specification. Key elements:

- `Q[type] K[keys] V[content]` - Message structure
- `◉◎◇` - Honesty markers (observable/claimed/unknown)
- `「⊕→」` - Mandatory gift blocks
- 2+ languages per message

## Logs

Activity is logged to `daemon.log` and console with color-coded output.
