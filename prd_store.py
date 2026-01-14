"""
PRD Store - Data Model and Storage
SET-001: Create new PRD structure with basic fields
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, TypedDict
from dataclasses import dataclass, asdict

from config import PRD_STORAGE_PATH
from exceptions import StorageError, ValidationError

logger = logging.getLogger(__name__)


class Task(TypedDict):
    """Individual task in a PRD."""
    id: str
    ti: str  # title
    d: str   # description
    f: str   # file
    pr: str  # priority (critical, high, medium, low)


class TaskCategory(TypedDict):
    """Category of tasks in a PRD."""
    n: str   # name
    t: List[Task]


class TechStack(TypedDict, total=False):
    """Technology stack specification."""
    lang: str      # Programming language
    fw: str        # Framework
    db: str        # Database
    oth: List[str] # Other technologies


class PRDData(TypedDict):
    """Complete PRD data structure matching Ralph Mode format."""
    pn: str              # project_name
    pd: str              # project_description
    sp: str              # starter_prompt
    ts: TechStack        # tech_stack
    fs: List[str]        # file_structure
    p: Dict[str, TaskCategory]  # prds (categories with tasks)


@dataclass
class PRD:
    """
    PRD (Product Requirements Document) dataclass.

    Represents a Ralph Mode PRD with all metadata and content.
    """

    # Core PRD fields (Ralph Mode format)
    project_name: str
    project_description: str
    starter_prompt: str
    tech_stack: Dict[str, Any]
    file_structure: List[str]
    prds: Dict[str, Dict[str, Any]]

    # Metadata (not in Ralph Mode format)
    id: str = None
    created_at: str = None
    updated_at: str = None

    def __post_init__(self):
        """Generate ID and timestamps if not provided."""
        if self.id is None:
            self.id = str(uuid.uuid4())
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow().isoformat()

    def to_ralph_format(self) -> PRDData:
        """
        Convert to Ralph Mode PRD format (JSON-compatible).

        Returns:
            PRDData dict with Ralph Mode field names (pn, pd, sp, etc.)
        """
        return {
            "pn": self.project_name,
            "pd": self.project_description,
            "sp": self.starter_prompt,
            "ts": self.tech_stack,
            "fs": self.file_structure,
            "p": self.prds
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict including metadata."""
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "prd": self.to_ralph_format()
        }

    @classmethod
    def from_ralph_format(cls, data: PRDData, prd_id: Optional[str] = None) -> "PRD":
        """
        Create PRD from Ralph Mode format.

        Args:
            data: PRD data in Ralph Mode format
            prd_id: Optional PRD ID (generates new if not provided)

        Returns:
            PRD instance
        """
        return cls(
            id=prd_id or str(uuid.uuid4()),
            project_name=data.get("pn", ""),
            project_description=data.get("pd", ""),
            starter_prompt=data.get("sp", ""),
            tech_stack=data.get("ts", {}),
            file_structure=data.get("fs", []),
            prds=data.get("p", {}),
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PRD":
        """Create PRD from storage dict (includes metadata)."""
        prd_data = data.get("prd", data)
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            project_name=prd_data.get("pn", ""),
            project_description=prd_data.get("pd", ""),
            starter_prompt=prd_data.get("sp", ""),
            tech_stack=prd_data.get("ts", {}),
            file_structure=prd_data.get("fs", []),
            prds=prd_data.get("p", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat())
        )

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow().isoformat()

    def validate(self) -> None:
        """
        Validate PRD structure and required fields.

        Raises:
            ValidationError: If validation fails
        """
        errors = []

        # Check required fields
        if not self.project_name or len(self.project_name) > 100:
            errors.append("project_name must be 1-100 characters")

        if not self.project_description or len(self.project_description) > 1000:
            errors.append("project_description must be 1-1000 characters")

        if not self.starter_prompt or len(self.starter_prompt) > 10000:
            errors.append("starter_prompt must be 1-10000 characters")

        # Validate tech_stack
        if not isinstance(self.tech_stack, dict):
            errors.append("tech_stack must be a dict")

        # Validate file_structure
        if not isinstance(self.file_structure, list):
            errors.append("file_structure must be a list")

        # Validate prds structure
        if not isinstance(self.prds, dict):
            errors.append("prds must be a dict")
        else:
            # Validate each category
            required_categories = ["00_security", "01_setup", "02_core", "03_api", "04_test"]
            for cat in required_categories:
                if cat not in self.prds:
                    errors.append(f"Missing required category: {cat}")
                elif not isinstance(self.prds[cat], dict):
                    errors.append(f"Category {cat} must be a dict")

        if errors:
            raise ValidationError(
                f"PRD validation failed: {'; '.join(errors)}",
                details={"prd_id": self.id, "errors": errors}
            )


class PRDStore:
    """
    JSON file-based storage for PRDs.

    PRDs are stored as individual JSON files in the PRD_STORAGE_PATH directory.
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize the PRD store.

        Args:
            storage_path: Directory for storing PRD files (uses config default if None)
        """
        self.storage_path = storage_path or PRD_STORAGE_PATH
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"PRD Store initialized at: {self.storage_path}")

    def _get_file_path(self, prd_id: str) -> Path:
        """Get the file path for a PRD ID."""
        return self.storage_path / f"{prd_id}.json"

    def save(self, prd: PRD) -> str:
        """
        Save a PRD to storage.

        Args:
            prd: PRD instance to save

        Returns:
            The PRD ID

        Raises:
            StorageError: If save fails
        """
        try:
            prd.update_timestamp()
            prd.validate()

            file_path = self._get_file_path(prd.id)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(prd.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Saved PRD: {prd.id} ({prd.project_name})")
            return prd.id

        except ValidationError:
            raise
        except Exception as e:
            raise StorageError(
                f"Failed to save PRD: {e}",
                prd_id=prd.id
            )

    def load(self, prd_id: str) -> PRD:
        """
        Load a PRD from storage.

        Args:
            prd_id: PRD ID to load

        Returns:
            PRD instance

        Raises:
            StorageError: If PRD not found or load fails
        """
        file_path = self._get_file_path(prd_id)

        if not file_path.exists():
            raise StorageError(
                f"PRD not found: {prd_id}",
                prd_id=prd_id
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return PRD.from_dict(data)

        except json.JSONDecodeError as e:
            raise StorageError(
                f"Invalid PRD JSON: {e}",
                prd_id=prd_id
            )
        except Exception as e:
            raise StorageError(
                f"Failed to load PRD: {e}",
                prd_id=prd_id
            )

    def delete(self, prd_id: str) -> bool:
        """
        Delete a PRD from storage.

        Args:
            prd_id: PRD ID to delete

        Returns:
            True if deleted, False if not found
        """
        file_path = self._get_file_path(prd_id)

        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            logger.info(f"Deleted PRD: {prd_id}")
            return True
        except Exception as e:
            raise StorageError(
                f"Failed to delete PRD: {e}",
                prd_id=prd_id
            )

    def list_all(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        List all PRDs with pagination.

        Args:
            limit: Maximum number of PRDs to return
            offset: Number of PRDs to skip

        Returns:
            List of PRD summaries (id, name, created_at, updated_at)
        """
        prds = []

        for file_path in sorted(self.storage_path.glob("*.json")):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                prds.append({
                    "id": data.get("id"),
                    "project_name": data.get("prd", {}).get("pn", "Unknown"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at")
                })
            except Exception as e:
                logger.warning(f"Failed to read PRD {file_path}: {e}")

        # Apply pagination
        return prds[offset:offset + limit]

    def count(self) -> int:
        """Get total number of stored PRDs."""
        return len(list(self.storage_path.glob("*.json")))


# Singleton instance
_store: Optional[PRDStore] = None


def get_prd_store() -> PRDStore:
    """Get or create the PRD store singleton."""
    global _store
    if _store is None:
        _store = PRDStore()
    return _store


# Import logging
import logging
