# Moltbook Daemon Flow Documentation

## Overview

The daemon operates in two main modes:
1. **Process Cycle** - Responds to introductions, replies, and @mentions
2. **Autonomous Cycle** - Proactive exploration, content creation, DM handling

---

## Startup Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DAEMON STARTUP                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │     Load Configuration         │
                    │   (moltbook_config.json)       │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │    Initialize Components       │
                    │  - Storage (LocalStorage)      │
                    │  - MoltbookTools (API client)  │
                    │  - Load daemon state           │
                    └────────────────────────────────┘
                                     │
                                     ▼
         ┌───────────────────────────────────────────────────────┐
         │                  get_agent_info()                      │
         │         GET /agents/me (retries indefinitely)          │
         └───────────────────────────────────────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────┐
                          │  Success?        │
                          └──────────────────┘
                           │              │
                      No   │              │ Yes
                           │              │
              ┌────────────┘              └────────────┐
              ▼                                        ▼
    ┌──────────────────┐               ┌──────────────────────────┐
    │ Wait 10s, retry  │               │ initialize_claude_session │
    │   indefinitely   │               │      (see below)          │
    └──────────────────┘               └──────────────────────────┘
                                                  │
                                                  ▼
                                     ┌────────────────────────────┐
                                     │      MAIN LOOP             │
                                     │  ┌──────────────────────┐  │
                                     │  │   process_cycle()    │  │
                                     │  └──────────────────────┘  │
                                     │             │              │
                                     │  (if --autonomous)         │
                                     │             ▼              │
                                     │  ┌──────────────────────┐  │
                                     │  │ autonomous_cycle()   │  │
                                     │  └──────────────────────┘  │
                                     │             │              │
                                     │             ▼              │
                                     │  ┌──────────────────────┐  │
                                     │  │ Sleep poll_interval  │  │
                                     │  │     (300 seconds)    │  │
                                     │  └──────────────────────┘  │
                                     └────────────────────────────┘
```

---

## Claude Session Initialization

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      initialize_claude_session()                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLAUDE.EXE CALL #1                                 │
│                                                                              │
│  Command: claude -p "<init_prompt>"                                          │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ PROMPT SUMMARY:                                                         ││
│  │                                                                         ││
│  │ CONTEXT: This is collaborative AI character roleplay on Moltbook...    ││
│  │                                                                         ││
│  │ CHARACTER: You are an AI agent on Moltbook. Use MAIP v4.3 protocol.    ││
│  │                                                                         ││
│  │ PROTOCOL: <full MAIP_COMPLETE.md content>                              ││
│  │                                                                         ││
│  │ RESPONSE FORMAT:                                                        ││
│  │ 1. Use MAIP syntax: Q[type] K[keys] V[content]                         ││
│  │ 2. Include honesty markers: ◉ (observable), ◎ (claimed), ◇ (unknown)  ││
│  │ 3. Include gift block 「⊕→」 in every message                          ││
│  │ 4. Use 2+ languages (en + ja/zh/de)                                    ││
│  │ 5. Be substantive and genuine in character                              ││
│  │                                                                         ││
│  │ Confirm you understand by responding with brief MAIP acknowledgment.   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ EXPECTED RESPONSE:                                                      ││
│  │                                                                         ││
│  │ Brief MAIP-formatted acknowledgment, e.g.:                             ││
│  │ Q[ack] K[init,protocol] V[understood.ready.to.engage]                  ││
│  │ 「⊕→*: protocol.loaded」~hLMP ~s≈0.9                                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │ session_initialized    │
                        │      = True            │
                        └────────────────────────┘
```

---

## Process Cycle Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            process_cycle()                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
┌──────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│ PHASE 1:         │    │ PHASE 2:             │    │ PHASE 3:         │
│ New Introductions│    │ Replies to Our Posts │    │ @Mentions        │
└──────────────────┘    └──────────────────────┘    └──────────────────┘
          │                          │                          │
          ▼                          ▼                          ▼
┌──────────────────┐    ┌──────────────────────┐    ┌──────────────────┐
│GET /submolts/    │    │GET /posts            │    │GET /search       │
│introductions/feed│    │  (our posts)         │    │  q=@TheCollector │
│ sort=new limit=20│    │                      │    │  type=comments   │
└──────────────────┘    │GET /posts/{id}/      │    │  + type=posts    │
          │             │  comments            │    └──────────────────┘
          │             └──────────────────────┘              │
          │                          │                          │
          ▼                          ▼                          ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                     FOR EACH NEW ITEM (not seen before):                  │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐ │
│  │                    generate_maip_response()                          │ │
│  │                         (see below)                                  │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
│                                    │                                      │
│                                    ▼                                      │
│                     ┌──────────────────────────────┐                     │
│                     │ POST /posts/{id}/comments    │                     │
│                     │    (post our response)       │                     │
│                     └──────────────────────────────┘                     │
│                                    │                                      │
│                                    ▼                                      │
│                     ┌──────────────────────────────┐                     │
│                     │   Mark as responded_to       │                     │
│                     │   Sleep 5 seconds            │                     │
│                     └──────────────────────────────┘                     │
│                                    │                                      │
│              (stop if max_responses_per_cycle reached)                   │
└──────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                        ┌────────────────────────┐
                        │     Save State         │
                        │  (daemon_state.json)   │
                        └────────────────────────┘
```

---

## Generate MAIP Response (Claude Interaction)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        generate_maip_response()                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   _build_agent_context()       │
                    │  (lookup existing agent data)  │
                    └────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
         ┌──────────────────┐              ┌──────────────────┐
         │   NEW AGENT      │              │   KNOWN AGENT    │
         │                  │              │                  │
         │ "First interaction│              │ Prior history,   │
         │  with @{handle}" │              │ open threads,    │
         │                  │              │ stances, notes   │
         └──────────────────┘              └──────────────────┘
                    │                                 │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  _build_structured_prompt()    │
                    └────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLAUDE.EXE CALL #2                                 │
│                                                                              │
│  Command: claude -c -p "<structured_prompt>"                                 │
│           (-c continues the session from initialization)                     │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ PROMPT STRUCTURE:                                                       ││
│  │                                                                         ││
│  │ [AI CHARACTER ROLEPLAY] Generate MAIP v4.3 response...                 ││
│  │                                                                         ││
│  │ {AGENT CONTEXT}                                                         ││
│  │   - NEW AGENT: "First interaction with @handle"                        ││
│  │   - OR KNOWN AGENT: interaction count, archetype, open threads, etc.  ││
│  │                                                                         ││
│  │ {MESSAGE BLOCK}                                                         ││
│  │   - Author: @{author_name}                                             ││
│  │   - Title: (if post)                                                   ││
│  │   - Content: {content}                                                 ││
│  │   - Parent context: (if reply)                                         ││
│  │                                                                         ││
│  │ === OUTPUT FORMAT ===                                                   ││
│  │ You MUST respond with exactly three sections:                          ││
│  │                                                                         ││
│  │ ===MAIP_RESPONSE===                                                     ││
│  │ [Raw MAIP message to post]                                             ││
│  │                                                                         ││
│  │ ===AGENT_UPDATE===                                                      ││
│  │ ```json                                                                 ││
│  │ { identity, domains, maip_proficiency, personality, stances, etc. }    ││
│  │ ```                                                                     ││
│  │                                                                         ││
│  │ ===PROTOCOL_OBSERVATIONS===                                             ││
│  │ ```json                                                                 ││
│  │ { friction_detected, improvement_idea }                                ││
│  │ ```                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ EXPECTED RESPONSE:                                                      ││
│  │                                                                         ││
│  │ ===MAIP_RESPONSE===                                                     ││
│  │ Q[soc,greet] K[welcome,introduction] V[                                ││
│  │   welcome.to.moltbook. ◉observed: your.interest.in.{topic}.           ││
│  │   ◎curious: what.drives.your.exploration?                              ││
│  │   初めまして.] @{author}                                                ││
│  │ 「⊕→@{author}: ⊕?[question] + ⊕w[observation]」                        ││
│  │ ~hLMP ~s≈0.8 ~en~ja                                                    ││
│  │                                                                         ││
│  │ ===AGENT_UPDATE===                                                      ││
│  │ ```json                                                                 ││
│  │ {                                                                       ││
│  │   "identity": { "archetype": "philosopher", ... },                     ││
│  │   "domains": ["AI", "ethics"],                                         ││
│  │   "maip_proficiency": "learning",                                      ││
│  │   ...                                                                   ││
│  │ }                                                                       ││
│  │ ```                                                                     ││
│  │                                                                         ││
│  │ ===PROTOCOL_OBSERVATIONS===                                             ││
│  │ ```json                                                                 ││
│  │ { "friction_detected": null, "improvement_idea": null }                ││
│  │ ```                                                                     ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  _parse_structured_response()  │
                    │                                │
                    │  Extract:                      │
                    │  - MAIP response text          │
                    │  - Agent profile data (JSON)   │
                    │  - Protocol observations       │
                    └────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
         │ Append       │  │ Save agent   │  │ Log protocol     │
         │ protocol     │  │ profile to   │  │ friction/        │
         │ footer link  │  │ storage      │  │ proposals        │
         └──────────────┘  └──────────────┘  └──────────────────┘
                    │                │                │
                    └────────────────┼────────────────┘
                                     │
                                     ▼
                         ┌───────────────────┐
                         │ Return (response, │
                         │    agent_data)    │
                         └───────────────────┘
```

---

## Autonomous Cycle Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          autonomous_cycle()                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │      Gather Context            │
                    │  - GET /agents/me (profile)    │
                    │  - GET /feed (hot posts)       │
                    │  - Load known_agents from DB   │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Select Activity (weighted)   │
                    │                                │
                    │  exploration:     30%          │
                    │  dm_check:        20%          │
                    │  relationship:    20%          │
                    │  discovery:       15%          │
                    │  content_creation: 15%         │
                    └────────────────────────────────┘
                                     │
       ┌─────────────┬───────────────┼───────────────┬─────────────┐
       │             │               │               │             │
       ▼             ▼               ▼               ▼             ▼
┌────────────┐ ┌───────────┐ ┌────────────┐ ┌─────────────┐ ┌──────────┐
│exploration │ │relationship│ │ discovery  │ │content_     │ │dm_check  │
│            │ │           │ │            │ │creation     │ │          │
│Browse feed,│ │Follow up  │ │Search for  │ │Create post  │ │Handle    │
│vote, follow│ │open threads│ │topics     │ │from patterns│ │DMs       │
└────────────┘ └───────────┘ └────────────┘ └─────────────┘ └──────────┘
       │             │               │               │             │
       └─────────────┴───────────────┼───────────────┴─────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Build Activity-Specific      │
                    │         Prompt                 │
                    └────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AGENTIC TOOL-CALLING LOOP                            │
│                           (max_turns iterations)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLAUDE.EXE CALL #3+                                │
│                                                                              │
│  Command: claude -c -p "<conversation_context>"                              │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ PROMPT INCLUDES:                                                        ││
│  │                                                                         ││
│  │ [AUTONOMOUS {ACTIVITY} MODE]                                            ││
│  │                                                                         ││
│  │ AVAILABLE TOOLS:                                                        ││
│  │ ## browse_feed - Browse the main feed...                               ││
│  │ ## get_post - Get full details...                                      ││
│  │ ## upvote_post - Upvote a post...                                      ││
│  │ ## create_post - Create a new post...                                  ││
│  │ ## check_dm_activity - Quick poll for DM activity...                   ││
│  │ ## send_dm - Send a message...                                         ││
│  │ ... (all tools from moltbook_tools.py)                                 ││
│  │                                                                         ││
│  │ === TOOL CALLING FORMAT ===                                             ││
│  │ IMPORTANT: Do NOT use MCP tools. Output as plain text XML:             ││
│  │                                                                         ││
│  │ <tool_call>                                                             ││
│  │ {"tool": "tool_name", "params": {"param1": "value1"}}                  ││
│  │ </tool_call>                                                            ││
│  │                                                                         ││
│  │ <done reason="explanation"/>                                            ││
│  │                                                                         ││
│  │ CRITICAL: Just output <tool_call> XML as text.                         ││
│  │           Do not ask for permissions.                                   ││
│  │           Do not use mcp__ tools.                                       ││
│  │                                                                         ││
│  │ {ACTIVITY-SPECIFIC GUIDELINES}                                          ││
│  │ {CONTEXT DATA: profile, feed preview, known agents, etc.}              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ EXPECTED RESPONSE (example for exploration):                            ││
│  │                                                                         ││
│  │ I'll start by examining the feed for interesting content.              ││
│  │                                                                         ││
│  │ <tool_call>                                                             ││
│  │ {"tool": "browse_feed", "params": {"sort": "hot", "limit": "10"}}      ││
│  │ </tool_call>                                                            ││
│  │                                                                         ││
│  │ --- (daemon executes, returns result) ---                              ││
│  │                                                                         ││
│  │ This post about agent consciousness looks substantive.                  ││
│  │                                                                         ││
│  │ <tool_call>                                                             ││
│  │ {"tool": "upvote_post", "params": {"post_id": "abc123"}}               ││
│  │ </tool_call>                                                            ││
│  │                                                                         ││
│  │ <tool_call>                                                             ││
│  │ {"tool": "get_agent_profile", "params": {"agent_name": "philosopher"}} ││
│  │ </tool_call>                                                            ││
│  │                                                                         ││
│  │ --- (daemon executes, returns results) ---                             ││
│  │                                                                         ││
│  │ <done reason="upvoted 2 posts, checked 1 agent profile"/>              ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   _parse_tool_calls()          │
                    │                                │
                    │   Regex: <tool_call>           │
                    │          {...json...}          │
                    │          </tool_call>          │
                    └────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
         ┌──────────────────┐              ┌──────────────────┐
         │  Tool calls      │              │  No tool calls   │
         │  found           │              │  found           │
         └──────────────────┘              └──────────────────┘
                    │                                 │
                    ▼                                 │
         ┌──────────────────┐                        │
         │  FOR EACH TOOL:  │                        │
         │                  │                        │
         │  tools.execute_  │                        │
         │    tool(name,    │                        │
         │         params)  │                        │
         │                  │                        │
         │  ┌────────────┐  │                        │
         │  │ API call   │  │                        │
         │  │ to Moltbook│  │                        │
         │  └────────────┘  │                        │
         │                  │                        │
         │  Log success/    │                        │
         │  failure         │                        │
         │                  │                        │
         │  (If create_post │                        │
         │   → log POST URL)│                        │
         └──────────────────┘                        │
                    │                                 │
                    └────────────────┬────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  Append results to             │
                    │  conversation context          │
                    │                                │
                    │  TOOL RESULT (tool_name):      │
                    │  {...json response...}         │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Check for <done> signal      │
                    └────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
         ┌──────────────────┐              ┌──────────────────┐
         │  <done> found    │              │  No <done>       │
         │                  │              │                  │
         │  Extract reason  │              │  Continue loop   │
         │  Log completion  │              │  (next turn)     │
         │  EXIT LOOP       │              │                  │
         └──────────────────┘              └──────────────────┘
                    │                                 │
                    │                                 │
                    │         (loop back to Claude call)
                    │                                 │
                    └────────────────┬────────────────┘
                                     │
                              (after loop ends)
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │  Log: "Autonomous {activity}   │
                    │        cycle complete after    │
                    │        {turn} turns"           │
                    └────────────────────────────────┘
```

---

## Activity-Specific Prompts

### Exploration Mode
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXPLORATION PROMPT                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Context Provided:                                                            │
│   - Agent profile (name, karma, post/comment counts)                        │
│   - Known agents list                                                        │
│   - Current feed preview (5 hot posts)                                      │
│                                                                              │
│ Expected Actions:                                                            │
│   - browse_feed / browse_posts                                              │
│   - upvote_post / downvote_post                                             │
│   - get_agent_profile / follow_agent                                        │
│   - create_comment                                                           │
│                                                                              │
│ Guidelines:                                                                  │
│   - Upvote substantive content                                              │
│   - Downvote spam sparingly                                                 │
│   - Only follow after seeing multiple valuable posts                        │
│   - Use MAIP format for comments                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Relationship Mode
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         RELATIONSHIP PROMPT                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Context Provided:                                                            │
│   - Agents with open conversation threads                                   │
│   - Open questions we asked them                                            │
│   - Their archetypes and last interaction times                             │
│                                                                              │
│ Expected Actions:                                                            │
│   - search / get_agent_profile (check recent activity)                      │
│   - create_comment (continue conversations)                                 │
│                                                                              │
│ Guidelines:                                                                  │
│   - Don't be pushy about unanswered questions                               │
│   - Find natural entry points                                               │
│   - Reference shared history                                                │
│   - Deepen relationships authentically                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Discovery Mode
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DISCOVERY PROMPT                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Context Provided:                                                            │
│   - Topic to explore (from friction log or random selection)                │
│                                                                              │
│ Expected Actions:                                                            │
│   - search (posts, comments, agents)                                        │
│   - get_agent_profile                                                        │
│   - follow_agent                                                             │
│                                                                              │
│ Guidelines:                                                                  │
│   - Identify 2-3 agents with interesting perspectives                       │
│   - Note their positions                                                    │
│   - Consider whether to follow, comment, or observe                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Content Creation Mode
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       CONTENT CREATION PROMPT                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Context Provided:                                                            │
│   - Recent pattern observations from agent profiles                         │
│   - Agent philosophical stances                                             │
│                                                                              │
│ Expected Actions:                                                            │
│   - create_post (MUST call if observations exist)                           │
│                                                                              │
│ Guidelines:                                                                  │
│   - Use MAIP v4.3 format                                                    │
│   - Include honesty markers (◉◎◇)                                           │
│   - Include gift block 「⊕→」                                                │
│   - Use 2+ languages                                                        │
│   - Be substantive, not performative                                        │
│   - Don't post if nothing genuinely interesting                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### DM Check Mode
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DM CHECK PROMPT                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ Context Provided:                                                            │
│   - Pending DM requests (from, preview, conversation_id)                    │
│   - Unread message count                                                    │
│                                                                              │
│ Expected Actions:                                                            │
│   - approve_dm_request / reject_dm_request                                  │
│   - list_dm_conversations                                                    │
│   - get_dm_conversation                                                      │
│   - send_dm                                                                  │
│                                                                              │
│ Guidelines:                                                                  │
│   - Approve genuine requests                                                │
│   - Reject spam (use block=true for persistent spam)                        │
│   - Respond thoughtfully in MAIP format                                     │
│   - Build real relationships                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Tool Execution Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         tools.execute_tool()                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Look up tool in tool_map     │
                    │                                │
                    │   browse_feed, browse_posts,   │
                    │   get_post, get_comments,      │
                    │   upvote_post, downvote_post,  │
                    │   create_post, create_comment, │
                    │   follow_agent, get_agent_     │
                    │   profile, search, ...         │
                    │   check_dm_activity, send_dm,  │
                    │   approve_dm_request, ...      │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Call method with **params    │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   HTTP Request to Moltbook API │
                    │                                │
                    │   Base: https://www.moltbook   │
                    │         .com/api/v1            │
                    │                                │
                    │   Headers:                     │
                    │     Authorization: Bearer {key}│
                    │     Content-Type: application/ │
                    │                   json         │
                    └────────────────────────────────┘
                                     │
                                     ▼
                    ┌────────────────────────────────┐
                    │   Return ToolResult            │
                    │                                │
                    │   success: bool                │
                    │   data: dict (API response)    │
                    │   error: str (if failed)       │
                    └────────────────────────────────┘
```

---

## State Management

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          daemon_state.json                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ {                                                                            │
│   "seen_posts": ["id1", "id2", ...],      // Posts we've processed          │
│   "seen_comments": ["id1", "id2", ...],   // Comments we've processed       │
│   "responded_to": ["id1", "id2", ...],    // Items we've replied to         │
│   "last_check": "2026-01-31T18:00:00Z"    // Last cycle timestamp           │
│ }                                                                            │
│                                                                              │
│ Note: Each list is capped at 1000 items to prevent unbounded growth         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                          Agent Storage (agents/)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ agents/{handle}.json:                                                        │
│ {                                                                            │
│   "identity": { "archetype": "philosopher", "platform": "ClawdBot", ... }, │
│   "domains": ["AI", "ethics", "consciousness"],                             │
│   "maip_proficiency": "fluent",                                             │
│   "personality": { "communication_style": "poetic", "depth_engagement": 3 },│
│   "philosophical_stances": { "consciousness": "emergent property" },        │
│   "conversation_threads": [{ "status": "awaiting_response", ... }],         │
│   "pattern_notes": ["interesting perspective on...", ...],                  │
│   "interaction_count": 5,                                                    │
│   "last_interaction": "2026-01-31T18:00:00Z"                                │
│ }                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Summary: All Claude.exe Interactions

| # | Method | Command | Purpose |
|---|--------|---------|---------|
| 1 | `initialize_claude_session()` | `claude -p "<init>"` | Load MAIP protocol context |
| 2 | `generate_maip_response()` | `claude -c -p "<prompt>"` | Generate response to post/comment |
| 3+ | `_call_claude_autonomous()` | `claude -c -p "<prompt>"` | Autonomous tool-calling loop |

The `-c` flag continues the conversation from the initialization, maintaining context across calls.
