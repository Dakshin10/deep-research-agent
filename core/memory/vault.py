"""
Obsidian-compatible Markdown Vault Manager (L3 Memory).

Manages plain markdown notes in ./vault organized by entity category
with YAML frontmatter, [[wikilinks]], and bidirectional synchronization.
"""

from datetime import datetime, timezone
import os
import re
from typing import Any, Dict, List, Optional
import yaml

from core.memory.schemas import Entity, EntityType, Fact, Relation

DEFAULT_VAULT_ROOT = "vault"
VAULT_FOLDERS = [
    "People",
    "Projects",
    "Ideas",
    "Research",
    "Sources",
    "Preferences",
    "Daily",
]


class VaultManager:
    """Manages markdown files in the local Obsidian vault."""

    def __init__(self, vault_root: str = DEFAULT_VAULT_ROOT):
        self.vault_root = vault_root
        self._ensure_folders()

    def _ensure_folders(self):
        """Creates vault directories if not already existing."""
        for folder in VAULT_FOLDERS:
            os.makedirs(os.path.join(self.vault_root, folder), exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """Convert entity name to a safe filename."""
        clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
        return clean or "Unnamed_Note"

    def get_note_path(self, entity_name: str, entity_type: str = "Projects") -> str:
        """Return the absolute path to an entity note."""
        folder = entity_type if entity_type in VAULT_FOLDERS else "Projects"
        filename = f"{self._sanitize_filename(entity_name)}.md"
        return os.path.join(self.vault_root, folder, filename)

    def write_entity_note(
        self,
        entity: Entity,
        facts: List[Fact],
        relations: List[Dict[str, str]],  # [{"relation": "USES_TOOL", "target": "Cloudflare Code Mode"}]
    ) -> str:
        """Writes or updates an entity note in standard Obsidian format."""
        self._ensure_folders()
        folder = entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type)
        if folder not in VAULT_FOLDERS:
            folder = "Projects"

        note_path = os.path.join(self.vault_root, folder, f"{self._sanitize_filename(entity.name)}.md")

        frontmatter = {
            "id": entity.id,
            "name": entity.name,
            "type": folder,
            "aliases": entity.aliases,
            "tags": entity.tags,
            "salience": entity.salience,
            "created": entity.created_at.isoformat(),
            "updated": datetime.now(timezone.utc).isoformat(),
        }

        # Build Markdown document
        lines = ["---", yaml.dump(frontmatter, sort_keys=False).strip(), "---", ""]
        lines.append(f"# {entity.name}\n")

        if entity.summary:
            lines.append(f"{entity.summary}\n")

        if relations:
            lines.append("## Connected Relations")
            for r in relations:
                rel_name = r.get("relation", "RELATED_TO").replace("_", " ").lower()
                target_name = r.get("target", "Target")
                lines.append(f"- **{rel_name}**: [[{target_name}]]")
            lines.append("")

        if facts:
            lines.append("## Verified Temporal Facts")
            for f in facts:
                status_icon = "🟢" if f.is_active else "⚪"
                valid_from_str = f.valid_from.strftime("%Y-%m-%d") if f.valid_from else "Unknown"
                valid_to_str = f.valid_to.strftime("%Y-%m-%d") if f.valid_to else "Present"
                lines.append(
                    f"- {status_icon} `[{valid_from_str} -> {valid_to_str}]` {f.statement}"
                )
                if f.provenance_url:
                    lines.append(f"  - *Source:* [{f.provenance_location or 'verified location'}]({f.provenance_url})")
            lines.append("")

        with open(note_path, "w", encoding="utf-8") as file:
            file.write("\n".join(lines))

        return note_path

    def delete_entity_note(self, entity_name: str, entity_type: str = "Projects") -> bool:
        """Deletes the entity note from the vault for hard-forget operations."""
        note_path = self.get_note_path(entity_name, entity_type)
        if os.path.exists(note_path):
            os.remove(note_path)
            return True
        return False

    def parse_note(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Parses an Obsidian markdown note into structured frontmatter and content."""
        if not os.path.exists(filepath):
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        match = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
        if not match:
            return {"raw_content": content}

        try:
            fm_text = match.group(1)
            body = match.group(2).strip()
            frontmatter = yaml.safe_load(fm_text) or {}
            # Extract [[wikilinks]]
            wikilinks = re.findall(r"\[\[(.*?)\]\]", body)
            return {
                "frontmatter": frontmatter,
                "body": body,
                "wikilinks": wikilinks,
            }
        except Exception:
            return {"raw_content": content}
