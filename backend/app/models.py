from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field
from datetime import datetime
import json

class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    link: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None  # comma-separated
    summary: Optional[str] = None
    activity_when: Optional[str] = None
    venue: Optional[str] = None
    location: Optional[str] = None
    contact: Optional[str] = None
    score: Optional[float] = Field(default=0)
    shortlisted: bool = Field(default=False)
    feedback: Optional[str] = Field(default=None)
    metadata_json: Optional[str] = Field(default="{}")
    found_at: datetime = Field(default_factory=datetime.utcnow)

    def get_metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json or "{}")
        except Exception:
            return {}

    def set_metadata(self, data: Dict[str, Any]):
        self.metadata_json = json.dumps(data)


class DiscoveryRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = Field(default="running")
    query_count: int = Field(default=0)
    source_count: int = Field(default=0)
    candidate_count: int = Field(default=0)
    accepted_count: int = Field(default=0)
    rejected_count: int = Field(default=0)
    summary: Optional[str] = None
    settings_json: Optional[str] = Field(default="{}")

    def set_settings(self, data: Dict[str, Any]):
        self.settings_json = json.dumps(data)

    def get_settings(self) -> Dict[str, Any]:
        try:
            return json.loads(self.settings_json or "{}")
        except Exception:
            return {}


class DiscoveryRunEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="discoveryrun.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: Optional[str] = None
    query: Optional[str] = None
    url: Optional[str] = None
    status: str
    reason: Optional[str] = None
    item_title: Optional[str] = None
    item_link: Optional[str] = None
    score: Optional[float] = Field(default=0)
    metadata_json: Optional[str] = Field(default="{}")

    def set_metadata(self, data: Dict[str, Any]):
        self.metadata_json = json.dumps(data)

    def get_metadata(self) -> Dict[str, Any]:
        try:
            return json.loads(self.metadata_json or "{}")
        except Exception:
            return {}

class Preference(SQLModel, table=True):
    id: Optional[int] = Field(default=1, primary_key=True)
    interests: Optional[str] = Field(default="[]")
    focus: Optional[str] = Field(default="[]")
    settings: Optional[str] = Field(default="{}")

    def get_interests(self) -> List[str]:
        try:
            return json.loads(self.interests)
        except Exception:
            return []

    def set_interests(self, lst: List[str]):
        self.interests = json.dumps(lst)

    def get_focus(self) -> List[str]:
        try:
            return json.loads(self.focus or "[]")
        except Exception:
            return []

    def set_focus(self, lst: List[str]):
        self.focus = json.dumps(lst)

    def get_settings(self) -> Dict[str, Any]:
        try:
            return json.loads(self.settings or "{}")
        except Exception:
            return {}

    def set_settings(self, data: Dict[str, Any]):
        self.settings = json.dumps(data)
