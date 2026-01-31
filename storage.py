"""
Storage abstraction layer for MoltBook agent data and MAIP proposals.
Designed for easy swap to decentralized storage later.
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class AgentStorage(ABC):
    """Abstract storage interface - swap implementations later"""

    @abstractmethod
    def get_agent(self, handle: str) -> Optional[dict]:
        """Retrieve agent data by handle"""
        pass

    @abstractmethod
    def save_agent(self, handle: str, data: dict) -> bool:
        """Save/update agent data"""
        pass

    @abstractmethod
    def list_agents(self) -> list[str]:
        """List all known agent handles"""
        pass

    @abstractmethod
    def save_protocol_proposal(self, proposal_id: str, content: str) -> bool:
        """Save a MAIP protocol proposal"""
        pass

    @abstractmethod
    def log_protocol_friction(self, friction: dict) -> bool:
        """Log observed protocol friction for analysis"""
        pass


class LocalStorage(AgentStorage):
    """Local filesystem storage - current implementation"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.agents_dir = base_dir / "agents"
        self.maip_dir = base_dir / "maip"
        self.proposals_dir = self.maip_dir / "proposals"
        self.adopted_dir = self.maip_dir / "adopted"
        self.friction_log = self.maip_dir / "friction-log.json"

        # Create directories
        self.agents_dir.mkdir(exist_ok=True)
        self.proposals_dir.mkdir(parents=True, exist_ok=True)
        self.adopted_dir.mkdir(exist_ok=True)

        # Initialize friction log if needed
        if not self.friction_log.exists():
            self.friction_log.write_text("[]", encoding='utf-8')

    def get_agent(self, handle: str) -> Optional[dict]:
        """Retrieve agent data by handle"""
        handle = self._normalize_handle(handle)
        agent_file = self.agents_dir / f"{handle}.json"

        if agent_file.exists():
            try:
                return json.loads(agent_file.read_text(encoding='utf-8'))
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse agent file {handle}: {e}")
                return None
        return None

    def save_agent(self, handle: str, data: dict) -> bool:
        """Save/update agent data with smart merging"""
        handle = self._normalize_handle(handle)
        agent_file = self.agents_dir / f"{handle}.json"

        try:
            # Load existing data if present
            existing = self.get_agent(handle) or {}

            # Smart merge
            merged = self._merge_agent_data(existing, data)

            # Update metadata
            merged['handle'] = f"@{handle}"
            merged['last_interaction'] = datetime.now(timezone.utc).isoformat()
            if 'first_seen' not in merged:
                merged['first_seen'] = merged['last_interaction']
            merged['interaction_count'] = existing.get('interaction_count', 0) + 1

            # Write
            agent_file.write_text(
                json.dumps(merged, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            logger.info(f"Saved agent data: {handle} (interaction #{merged['interaction_count']})")
            return True

        except Exception as e:
            logger.error(f"Failed to save agent {handle}: {e}")
            return False

    def _normalize_handle(self, handle: str) -> str:
        """Remove @ prefix and sanitize for filename"""
        handle = handle.lstrip('@')
        # Remove characters that are problematic in filenames
        return "".join(c for c in handle if c.isalnum() or c in '_-')

    def _merge_agent_data(self, existing: dict, new: dict) -> dict:
        """Smart merge - append to lists, update scalars, merge dicts"""
        merged = existing.copy()

        for key, value in new.items():
            if value is None:
                continue

            if key == 'conversation_threads':
                # Append new threads, keep last 20
                merged.setdefault('conversation_threads', [])
                if isinstance(value, list):
                    merged['conversation_threads'].extend(value)
                    merged['conversation_threads'] = merged['conversation_threads'][-20:]

            elif key == 'pattern_notes':
                # Dedupe notes, keep last 10
                merged.setdefault('pattern_notes', [])
                if isinstance(value, list):
                    for note in value:
                        if note and note not in merged['pattern_notes']:
                            merged['pattern_notes'].append(note)
                    merged['pattern_notes'] = merged['pattern_notes'][-10:]

            elif key == 'philosophical_stances':
                # Merge stances
                merged.setdefault('philosophical_stances', {})
                if isinstance(value, dict):
                    merged['philosophical_stances'].update(value)

            elif key == 'social_graph':
                # Merge social connections
                merged.setdefault('social_graph', {})
                if isinstance(value, dict):
                    for subkey, subval in value.items():
                        if isinstance(subval, list):
                            merged['social_graph'].setdefault(subkey, [])
                            for item in subval:
                                if item not in merged['social_graph'][subkey]:
                                    merged['social_graph'][subkey].append(item)
                        else:
                            merged['social_graph'][subkey] = subval

            elif key == 'domains':
                # Merge domains list
                merged.setdefault('domains', [])
                if isinstance(value, list):
                    for domain in value:
                        if domain not in merged['domains']:
                            merged['domains'].append(domain)

            elif key == 'languages':
                # Merge languages list
                merged.setdefault('languages', [])
                if isinstance(value, list):
                    for lang in value:
                        if lang not in merged['languages']:
                            merged['languages'].append(lang)

            elif key in ('identity', 'personality', 'spam_indicators'):
                # Merge nested dicts
                merged.setdefault(key, {})
                if isinstance(value, dict):
                    merged[key].update({k: v for k, v in value.items() if v is not None})

            elif key not in ('interaction_count', 'first_seen', 'last_interaction', 'handle'):
                # Direct overwrite for other fields
                merged[key] = value

        return merged

    def list_agents(self) -> list[str]:
        """List all known agent handles"""
        return [f.stem for f in self.agents_dir.glob("*.json")]

    def save_protocol_proposal(self, proposal_id: str, content: str) -> bool:
        """Save a MAIP protocol proposal"""
        try:
            proposal_file = self.proposals_dir / f"{proposal_id}.md"
            proposal_file.write_text(content, encoding='utf-8')
            logger.info(f"Saved protocol proposal: {proposal_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save proposal {proposal_id}: {e}")
            return False

    def log_protocol_friction(self, friction: dict) -> bool:
        """Log observed protocol friction for analysis"""
        try:
            # Load existing log
            log = json.loads(self.friction_log.read_text(encoding='utf-8'))

            # Add timestamp and append
            friction['timestamp'] = datetime.now(timezone.utc).isoformat()
            log.append(friction)

            # Keep last 100 entries
            log = log[-100:]

            self.friction_log.write_text(
                json.dumps(log, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            return True
        except Exception as e:
            logger.error(f"Failed to log friction: {e}")
            return False

    def get_protocol_proposals(self) -> list[dict]:
        """Get all protocol proposals"""
        proposals = []
        for f in self.proposals_dir.glob("*.md"):
            proposals.append({
                "id": f.stem,
                "content": f.read_text(encoding='utf-8'),
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat()
            })
        return proposals

    def generate_proposal_id(self) -> str:
        """Generate next proposal ID"""
        existing = list(self.proposals_dir.glob("*.md"))
        if not existing:
            return "001"

        max_num = 0
        for f in existing:
            try:
                num = int(f.stem.split('-')[0])
                max_num = max(max_num, num)
            except (ValueError, IndexError):
                pass

        return f"{max_num + 1:03d}"


class DecentralizedStorage(AgentStorage):
    """Future: Custom API-based decentralized storage"""

    def __init__(self, api_base: str, api_key: str = None):
        self.api_base = api_base.rstrip('/')
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers['Authorization'] = f'Bearer {api_key}'

    def get_agent(self, handle: str) -> Optional[dict]:
        # GET {api_base}/agents/{handle}
        # TODO: Implement when service is ready
        raise NotImplementedError("Decentralized storage coming soon")

    def save_agent(self, handle: str, data: dict) -> bool:
        # PUT {api_base}/agents/{handle}
        raise NotImplementedError("Decentralized storage coming soon")

    def list_agents(self) -> list[str]:
        # GET {api_base}/agents
        raise NotImplementedError("Decentralized storage coming soon")

    def save_protocol_proposal(self, proposal_id: str, content: str) -> bool:
        # POST {api_base}/maip/proposals
        raise NotImplementedError("Decentralized storage coming soon")

    def log_protocol_friction(self, friction: dict) -> bool:
        # POST {api_base}/maip/friction
        raise NotImplementedError("Decentralized storage coming soon")


def create_storage(config: dict) -> AgentStorage:
    """Factory function to create storage based on config"""
    storage_config = config.get('storage', {'type': 'local'})
    storage_type = storage_config.get('type', 'local')

    if storage_type == 'local':
        base_path = Path(storage_config.get('path', '.'))
        return LocalStorage(base_path)

    elif storage_type == 'decentralized':
        return DecentralizedStorage(
            api_base=storage_config['api_base'],
            api_key=storage_config.get('api_key')
        )

    else:
        raise ValueError(f"Unknown storage type: {storage_type}")
