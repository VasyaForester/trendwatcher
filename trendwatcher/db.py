import json
from datetime import datetime, timezone

from sqlalchemy import Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .config import DATA_DIR

DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "trendwatcher.db"
engine = create_engine(f"sqlite:///{DB_PATH}", future=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    source_name: Mapped[str] = mapped_column(String(128))
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    doc_type: Mapped[str] = mapped_column(String(32), index=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(index=True)
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    entities_json: Mapped[str] = mapped_column(Text, default="[]")
    trust: Mapped[float] = mapped_column(Float, default=0.5)
    severity: Mapped[float] = mapped_column(Float, default=0.0)

    @property
    def tags(self) -> list[str]:
        return json.loads(self.tags_json)

    @tags.setter
    def tags(self, value: list[str]) -> None:
        self.tags_json = json.dumps(value)

    @property
    def entities(self) -> list[str]:
        return json.loads(self.entities_json)

    @entities.setter
    def entities(self, value: list[str]) -> None:
        self.entities_json = json.dumps(value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "doc_type": self.doc_type,
            "url": self.url,
            "title": self.title,
            "summary": self.summary[:500],
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "tags": self.tags,
            "entities": self.entities,
            "trust": self.trust,
            "severity": self.severity,
        }


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return Session(engine)
