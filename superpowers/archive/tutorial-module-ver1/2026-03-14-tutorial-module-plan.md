# Tutorial Module — Web App Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Tutorial module to KaTrain Galaxy Web that serves structured voice-guided Go lessons from a pre-published file-based content package, with DB-backed user progress tracking.

**Architecture:** Three-layer: (1) a pre-published file package (`data/tutorials_published/`) acting as a read-only content store, (2) a FastAPI backend that loads the package at startup and exposes lesson content + progress APIs, (3) a React frontend integrated into Galaxy with four pages (category landing, topic list, topic detail, example playback with audio).

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / Pydantic v2 (backend); React 19 / TypeScript / MUI (frontend); pytest (backend tests); Playwright (frontend e2e tests).

---

## File Structure

**New files:**
```
data/tutorials_published/
  active.json
  versions/v001/
    manifest.json
    categories/opening.json
    topics/opening/board-center-value.json
    examples/ex_opening_001.json
    assets/
      images/ex_opening_001_step_01.png
              ex_opening_001_step_02.png
      audio/ex_opening_001_step_01.mp3
             ex_opening_001_step_02.mp3

katrain/web/tutorials/__init__.py
katrain/web/tutorials/loader.py         # reads active.json → loads version into memory
katrain/web/tutorials/models.py         # Pydantic: Category, Topic, Example, Step, TutorialProgress
katrain/web/tutorials/progress.py       # SQLAlchemy UserTutorialProgress CRUD

katrain/web/api/v1/endpoints/tutorials.py   # REST endpoints

katrain/web/ui/src/galaxy/types/tutorial.ts
katrain/web/ui/src/galaxy/api/tutorialApi.ts
katrain/web/ui/src/galaxy/pages/tutorials/TutorialLandingPage.tsx
katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicsPage.tsx
katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicDetailPage.tsx
katrain/web/ui/src/galaxy/pages/tutorials/TutorialExamplePage.tsx
katrain/web/ui/src/galaxy/components/tutorials/StepDisplay.tsx
katrain/web/ui/src/galaxy/components/tutorials/AudioPlayer.tsx

tests/test_tutorial_progress_model.py
tests/test_tutorial_loader.py
tests/test_tutorial_api.py
katrain/web/ui/tests/tutorial.spec.ts
```

**Modified files:**
```
katrain/web/core/models_db.py                                  + UserTutorialProgress (appended at end of file)
katrain/web/api/v1/api.py                                      + include tutorials router
katrain/web/server.py                                          + tutorial_loader init at end of _lifespan_server
katrain/web/ui/src/GalaxyApp.tsx                               + tutorial routes
katrain/web/ui/src/galaxy/components/layout/GalaxySidebar.tsx  + Tutorial menu item (with t())
```

---

## Chunk 1: Foundation

### Task 1: Create Published Package Fixture

**Files:**
- Create: `data/tutorials_published/active.json`
- Create: `data/tutorials_published/versions/v001/manifest.json`
- Create: `data/tutorials_published/versions/v001/categories/opening.json`
- Create: `data/tutorials_published/versions/v001/topics/opening/board-center-value.json`
- Create: `data/tutorials_published/versions/v001/examples/ex_opening_001.json`
- Create: placeholder PNG images (2) and MP3 audio stubs (2) in `assets/`

- [ ] **Step 1.1: Create directory structure**

```bash
mkdir -p data/tutorials_published/versions/v001/categories
mkdir -p data/tutorials_published/versions/v001/topics/opening
mkdir -p data/tutorials_published/versions/v001/examples
mkdir -p data/tutorials_published/versions/v001/assets/images
mkdir -p data/tutorials_published/versions/v001/assets/audio
```

- [ ] **Step 1.2: Write `data/tutorials_published/active.json`**

```json
{"version": "v001", "path": "versions/v001"}
```

- [ ] **Step 1.3: Write `data/tutorials_published/versions/v001/manifest.json`**

```json
{
  "version": "v001",
  "published_at": "2026-03-14T00:00:00Z",
  "categories": ["opening"],
  "stats": {"categories": 1, "topics": 1, "examples": 1, "steps": 2}
}
```

- [ ] **Step 1.4: Write `data/tutorials_published/versions/v001/categories/opening.json`**

```json
{
  "id": "cat_opening",
  "slug": "opening",
  "title": "布局",
  "summary": "围棋布局的基本原则，学习如何在开局阶段高效占据关键位置。",
  "order": 1,
  "topic_count": 1,
  "cover_asset": null
}
```

- [ ] **Step 1.5: Write `data/tutorials_published/versions/v001/topics/opening/board-center-value.json`**

```json
{
  "id": "topic_opening_001",
  "category_id": "cat_opening",
  "slug": "board-center-value",
  "title": "角、边与中央的价值",
  "summary": "理解棋盘不同区域的效率差异，掌握布局时优先占据角部的基本原则。",
  "tags": null,
  "difficulty": null,
  "estimated_minutes": null,
  "example_ids": ["ex_opening_001"]
}
```

- [ ] **Step 1.6: Write `data/tutorials_published/versions/v001/examples/ex_opening_001.json`**

```json
{
  "id": "ex_opening_001",
  "topic_id": "topic_opening_001",
  "title": "星位与小目的选择",
  "summary": "对比星位与小目，理解不同布局思路各自的侧重点。",
  "order": 1,
  "total_duration_sec": null,
  "step_count": 2,
  "steps": [
    {
      "id": "step_ex001_001",
      "example_id": "ex_opening_001",
      "order": 1,
      "narration": "围棋开局时，角部是最重要的落子区域。角部比边和中央效率更高，用更少的棋子便能围出更多实地。",
      "image_asset": "assets/images/ex_opening_001_step_01.png",
      "audio_asset": "assets/audio/ex_opening_001_step_01.mp3",
      "audio_duration_ms": null,
      "board_mode": "image",
      "board_payload": null
    },
    {
      "id": "step_ex001_002",
      "example_id": "ex_opening_001",
      "order": 2,
      "narration": "星位强调外势与速度，适合喜欢影响力的棋手。小目兼顾实地与灵活性，是平衡型的布局选择。",
      "image_asset": "assets/images/ex_opening_001_step_02.png",
      "audio_asset": "assets/audio/ex_opening_001_step_02.mp3",
      "audio_duration_ms": null,
      "board_mode": "image",
      "board_payload": null
    }
  ]
}
```

- [ ] **Step 1.7: Create placeholder PNG images**

```bash
python3 -c "
import struct, zlib

def make_png(w, h, color=(200, 200, 200)):
    def u32(n): return struct.pack('>I', n)
    def chunk(t, d): c = t+d; return u32(len(d)) + t + d + u32(zlib.crc32(c) & 0xffffffff)
    sig = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', u32(w)+u32(h)+bytes([8,2,0,0,0]))
    row = b'\x00' + bytes(color)*w
    idat = chunk(b'IDAT', zlib.compress(row*h))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend

base = 'data/tutorials_published/versions/v001/assets/images/'
with open(base+'ex_opening_001_step_01.png','wb') as f: f.write(make_png(400,400,(180,160,120)))
with open(base+'ex_opening_001_step_02.png','wb') as f: f.write(make_png(400,400,(120,160,180)))
print('PNG OK')
"
```

Expected output: `PNG OK`

- [ ] **Step 1.8: Create placeholder MP3 audio stubs**

Note: these are minimal MPEG frame bytes — browsers accept them as audio/mpeg but they produce silence. They serve only to verify the asset-serving pipeline; real narration audio will be generated offline via CosyVoice before content is published.

```bash
python3 -c "
mp3 = bytes([0xFF,0xFB,0x10,0x00] + [0x00]*28) * 50
base = 'data/tutorials_published/versions/v001/assets/audio/'
for name in ['ex_opening_001_step_01.mp3','ex_opening_001_step_02.mp3']:
    open(base+name,'wb').write(mp3)
print('MP3 OK')
"
```

Expected output: `MP3 OK`

- [ ] **Step 1.9: Verify complete fixture structure**

```bash
find data/tutorials_published -type f | sort
```

Expected (9 files):
```
data/tutorials_published/active.json
data/tutorials_published/versions/v001/assets/audio/ex_opening_001_step_01.mp3
data/tutorials_published/versions/v001/assets/audio/ex_opening_001_step_02.mp3
data/tutorials_published/versions/v001/assets/images/ex_opening_001_step_01.png
data/tutorials_published/versions/v001/assets/images/ex_opening_001_step_02.png
data/tutorials_published/versions/v001/categories/opening.json
data/tutorials_published/versions/v001/examples/ex_opening_001.json
data/tutorials_published/versions/v001/manifest.json
data/tutorials_published/versions/v001/topics/opening/board-center-value.json
```

- [ ] **Step 1.10: Commit fixture**

```bash
git add data/tutorials_published/
git commit -m "feat(tutorials): add published package fixture v001 with sample opening lesson"
```

---

### Task 2: Add UserTutorialProgress DB Model (TDD)

**Files:**
- Modify: `katrain/web/core/models_db.py` (append at end of file — after the last existing model class)
- Create: `tests/test_tutorial_progress_model.py`

- [ ] **Step 2.1: Write failing test**

Create `tests/test_tutorial_progress_model.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from katrain.web.core import models_db


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    models_db.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    user = models_db.User(username="testuser", hashed_password="fakehash")
    session.add(user)
    session.commit()
    session.refresh(user)
    yield session, user.id
    session.close()


def test_create_tutorial_progress(db):
    session, user_id = db
    progress = models_db.UserTutorialProgress(
        user_id=user_id,
        topic_id="topic_opening_001",
        example_id="ex_opening_001",
        last_step_id="step_ex001_001",
        completed=False,
    )
    session.add(progress)
    session.commit()
    session.refresh(progress)  # flush server_default values

    fetched = session.query(models_db.UserTutorialProgress).filter_by(
        user_id=user_id, example_id="ex_opening_001"
    ).first()
    assert fetched is not None
    assert fetched.last_step_id == "step_ex001_001"
    assert fetched.completed is False
    assert fetched.last_played_at is not None


def test_update_tutorial_progress(db):
    session, user_id = db
    progress = models_db.UserTutorialProgress(
        user_id=user_id,
        topic_id="topic_opening_001",
        example_id="ex_opening_001",
        last_step_id="step_ex001_001",
        completed=False,
    )
    session.add(progress)
    session.commit()

    progress.last_step_id = "step_ex001_002"
    progress.completed = True
    session.commit()
    session.refresh(progress)

    assert progress.last_step_id == "step_ex001_002"
    assert progress.completed is True
```

- [ ] **Step 2.2: Run test — verify it fails**

```bash
CI=true uv run pytest tests/test_tutorial_progress_model.py -v 2>&1 | head -20
```

Expected: `AttributeError` or `ImportError` — `UserTutorialProgress` does not exist yet.

- [ ] **Step 2.3: Append `UserTutorialProgress` to the end of `katrain/web/core/models_db.py`**

Open the file, scroll to the very last line, and append:

```python
class UserTutorialProgress(Base):
    __tablename__ = "user_tutorial_progress"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    example_id = Column(String(64), primary_key=True)
    topic_id = Column(String(64), nullable=False, index=True)
    last_step_id = Column(String(64), nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
    last_played_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User")

    __table_args__ = (
        Index("ix_user_tutorial_topic", "user_id", "topic_id"),
    )
```

Note: `user = relationship("User")` has no `back_populates` intentionally — we do not add a `tutorial_progress` attribute to the `User` model in this phase.

- [ ] **Step 2.4: Run test — verify it passes**

```bash
CI=true uv run pytest tests/test_tutorial_progress_model.py -v
```

Expected: 2 tests `PASSED`

- [ ] **Step 2.5: Commit**

```bash
git add katrain/web/core/models_db.py tests/test_tutorial_progress_model.py
git commit -m "feat(tutorials): add UserTutorialProgress DB model with tests"
```

---

## Chunk 2: Backend Loader + API

**Prerequisite:** Chunk 1 (Task 1) must be committed and `data/tutorials_published/` must exist before running loader tests.

### Task 3: Tutorial Loader (TDD)

**Files:**
- Create: `katrain/web/tutorials/__init__.py`
- Create: `katrain/web/tutorials/loader.py`
- Create: `tests/test_tutorial_loader.py`

- [ ] **Step 3.1: Write failing loader tests**

Create `tests/test_tutorial_loader.py`:

```python
import pytest
from pathlib import Path
from katrain.web.tutorials.loader import TutorialLoader

FIXTURE_PATH = Path("data/tutorials_published")


@pytest.fixture
def loader():
    ldr = TutorialLoader(base_dir=FIXTURE_PATH)
    ldr.load()
    return ldr


def test_loader_loads_categories(loader):
    cats = loader.get_categories()
    assert len(cats) == 1
    assert cats[0]["id"] == "cat_opening"
    assert cats[0]["slug"] == "opening"


def test_loader_loads_topics_for_category(loader):
    topics = loader.get_topics_by_category("opening")
    assert len(topics) == 1
    assert topics[0]["id"] == "topic_opening_001"


def test_loader_get_topic_by_id(loader):
    topic = loader.get_topic("topic_opening_001")
    assert topic is not None
    assert topic["title"] == "角、边与中央的价值"


def test_loader_get_unknown_topic_returns_none(loader):
    assert loader.get_topic("does_not_exist") is None


def test_loader_get_example(loader):
    example = loader.get_example("ex_opening_001")
    assert example is not None
    assert example["step_count"] == 2
    assert len(example["steps"]) == 2


def test_loader_get_examples_for_topic(loader):
    examples = loader.get_examples_for_topic("topic_opening_001")
    assert len(examples) == 1
    assert examples[0]["id"] == "ex_opening_001"


def test_loader_get_examples_for_unknown_topic(loader):
    assert loader.get_examples_for_topic("does_not_exist") == []


def test_loader_example_steps_have_no_source_fields(loader):
    example = loader.get_example("ex_opening_001")
    forbidden = {"source_path", "raw_text", "source_id", "book_title", "author"}
    for step in example["steps"]:
        assert not forbidden.intersection(step.keys())


def test_loader_example_steps_board_mode_image(loader):
    example = loader.get_example("ex_opening_001")
    step = example["steps"][0]
    assert step["board_mode"] == "image"
    assert step["board_payload"] is None


def test_loader_asset_exists(loader):
    asset_path = loader.get_asset_path("assets/images/ex_opening_001_step_01.png")
    assert asset_path.exists()


def test_loader_reload_is_idempotent(loader):
    loader.load()
    cats = loader.get_categories()
    assert len(cats) == 1
```

- [ ] **Step 3.2: Run test — verify it fails**

```bash
CI=true uv run pytest tests/test_tutorial_loader.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'katrain.web.tutorials'`

- [ ] **Step 3.3: Create `katrain/web/tutorials/__init__.py`** (empty file)

- [ ] **Step 3.4: Create `katrain/web/tutorials/loader.py`**

```python
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TutorialLoader:
    """Loads the published tutorial package from disk into memory at startup.

    Reads active.json to find the current version directory, then loads all
    categories, topics, and examples into in-memory dicts. Thread-safe for
    read operations after load() completes. load() itself is not thread-safe
    and should only be called at startup or under an external lock.
    """

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir
        self._version_dir: Optional[Path] = None
        self._categories: List[Dict] = []
        self._topics_by_category: Dict[str, List[Dict]] = {}
        self._topics_by_id: Dict[str, Dict] = {}
        self._examples: Dict[str, Dict] = {}

    def load(self) -> None:
        """Load (or reload) the active published package from disk."""
        active_path = self._base_dir / "active.json"
        if not active_path.exists():
            raise FileNotFoundError(f"Tutorial active.json not found at {active_path}")

        active = json.loads(active_path.read_text())
        version_path = self._base_dir / active["path"]
        if not version_path.is_dir():
            raise FileNotFoundError(f"Tutorial version dir not found: {version_path}")

        self._version_dir = version_path
        self._categories = []
        self._topics_by_category = {}
        self._topics_by_id = {}
        self._examples = {}

        self._load_categories()
        logger.info(
            "Tutorial package loaded: version=%s, categories=%d, topics=%d, examples=%d",
            active["version"],
            len(self._categories),
            len(self._topics_by_id),
            len(self._examples),
        )

    def _load_categories(self) -> None:
        categories_dir = self._version_dir / "categories"
        if not categories_dir.is_dir():
            return
        cats = []
        for f in sorted(categories_dir.glob("*.json")):
            cat = json.loads(f.read_text())
            cats.append(cat)
            self._load_topics_for_category(cat["slug"])
        self._categories = sorted(cats, key=lambda c: c.get("order", 999))

    def _load_topics_for_category(self, slug: str) -> None:
        topic_dir = self._version_dir / "topics" / slug
        if not topic_dir.is_dir():
            self._topics_by_category[slug] = []
            return
        topics = []
        for f in sorted(topic_dir.glob("*.json")):
            topic = json.loads(f.read_text())
            topics.append(topic)
            self._topics_by_id[topic["id"]] = topic
            for example_id in topic.get("example_ids", []):
                self._load_example(example_id)
        self._topics_by_category[slug] = topics

    def _load_example(self, example_id: str) -> None:
        path = self._version_dir / "examples" / f"{example_id}.json"
        if not path.exists():
            logger.warning("Example file not found: %s", path)
            return
        self._examples[example_id] = json.loads(path.read_text())

    # ── Public read API ───────────────────────────────────────────────────────

    def get_categories(self) -> List[Dict]:
        return list(self._categories)

    def get_topics_by_category(self, slug: str) -> List[Dict]:
        return list(self._topics_by_category.get(slug, []))

    def get_topic(self, topic_id: str) -> Optional[Dict]:
        return self._topics_by_id.get(topic_id)

    def get_example(self, example_id: str) -> Optional[Dict]:
        return self._examples.get(example_id)

    def get_examples_for_topic(self, topic_id: str) -> List[Dict]:
        """Return all published examples belonging to a topic, in order."""
        topic = self._topics_by_id.get(topic_id)
        if topic is None:
            return []
        return [
            self._examples[eid]
            for eid in topic.get("example_ids", [])
            if eid in self._examples
        ]

    def get_asset_path(self, asset_ref: str) -> Path:
        """Return the absolute path to an asset within the active version directory.

        Note: asset_ref must be a relative path within the version directory
        (e.g. 'assets/images/foo.png'). No path traversal sanitization is
        performed here — callers are responsible for validating inputs before
        serving to external users.
        """
        return self._version_dir / asset_ref
```

- [ ] **Step 3.5: Run tests — verify all pass**

```bash
CI=true uv run pytest tests/test_tutorial_loader.py -v
```

Expected: 11 tests `PASSED`

- [ ] **Step 3.6: Commit**

```bash
git add katrain/web/tutorials/ tests/test_tutorial_loader.py
git commit -m "feat(tutorials): add TutorialLoader — reads published package from disk"
```

---

### Task 4: Pydantic Models + Progress CRUD + API Endpoints

**Files:**
- Create: `katrain/web/tutorials/models.py`
- Create: `katrain/web/tutorials/progress.py`
- Create: `katrain/web/api/v1/endpoints/tutorials.py`

- [ ] **Step 4.1: Create `katrain/web/tutorials/models.py`**

```python
from typing import Any, List, Literal, Optional
from pydantic import BaseModel


class Category(BaseModel):
    id: str
    slug: str
    title: str
    summary: str
    order: int
    topic_count: int
    cover_asset: Optional[str] = None


class Topic(BaseModel):
    id: str
    category_id: str
    slug: str
    title: str
    summary: str
    tags: Optional[List[str]] = None
    difficulty: Optional[str] = None
    estimated_minutes: Optional[int] = None


class Step(BaseModel):
    id: str
    example_id: str
    order: int
    narration: str
    image_asset: Optional[str] = None
    audio_asset: Optional[str] = None
    audio_duration_ms: Optional[int] = None
    board_mode: Literal["image", "sgf"]  # enforces rendering contract at API boundary
    board_payload: Optional[Any] = None


class Example(BaseModel):
    id: str
    topic_id: str
    title: str
    summary: str
    order: int
    total_duration_sec: Optional[float] = None
    step_count: int
    steps: List[Step]


class TutorialProgress(BaseModel):
    example_id: str
    topic_id: str
    last_step_id: Optional[str] = None
    completed: bool
    last_played_at: Optional[str] = None


class ProgressUpdate(BaseModel):
    topic_id: str
    last_step_id: str
    completed: bool
```

- [ ] **Step 4.2: Create `katrain/web/tutorials/progress.py`**

```python
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy.orm import Session

from katrain.web.core.models_db import UserTutorialProgress


def get_user_progress(db: Session, user_id: int) -> List[Dict]:
    rows = db.query(UserTutorialProgress).filter_by(user_id=user_id).all()
    return [
        {
            "example_id": r.example_id,
            "topic_id": r.topic_id,
            "last_step_id": r.last_step_id,
            "completed": r.completed,
            "last_played_at": r.last_played_at.isoformat() if r.last_played_at else None,
        }
        for r in rows
    ]


def upsert_progress(
    db: Session,
    user_id: int,
    example_id: str,
    topic_id: str,
    last_step_id: str,
    completed: bool,
) -> Dict:
    row = db.query(UserTutorialProgress).filter_by(
        user_id=user_id, example_id=example_id
    ).first()
    if row is None:
        row = UserTutorialProgress(
            user_id=user_id,
            example_id=example_id,
            topic_id=topic_id,
        )
        db.add(row)
    row.last_step_id = last_step_id
    row.completed = completed
    # Explicit Python-side timestamp; DB onupdate=func.now() is a fallback for
    # direct SQL updates that bypass SQLAlchemy.
    row.last_played_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return {
        "example_id": row.example_id,
        "topic_id": row.topic_id,
        "last_step_id": row.last_step_id,
        "completed": row.completed,
        "last_played_at": row.last_played_at.isoformat() if row.last_played_at else None,
    }
```

- [ ] **Step 4.3: Create `katrain/web/api/v1/endpoints/tutorials.py`**

```python
import logging
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from katrain.web.api.v1.endpoints.auth import get_current_user
from katrain.web.core.db import get_db
from katrain.web.core.models_db import User
from katrain.web.tutorials.models import (
    Category,
    Example,
    ProgressUpdate,
    Topic,
    TutorialProgress,
)
from katrain.web.tutorials import progress as progress_repo

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Version directory base path used to validate asset refs stay in-bounds ──
_PARDIR = ".."


def _loader(request: Request):
    loader = getattr(request.app.state, "tutorial_loader", None)
    if loader is None:
        raise HTTPException(status_code=503, detail="Tutorial module not initialized")
    return loader


def _safe_asset_path(loader, asset_path: str) -> Path:
    """Resolve asset path and reject any path traversal attempts."""
    resolved = (loader.get_asset_path(f"assets/{asset_path}")).resolve()
    base = loader.get_asset_path("assets").resolve()
    if not str(resolved).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Invalid asset path")
    return resolved


@router.get("/categories", response_model=List[Category])
async def get_categories(request: Request):
    return _loader(request).get_categories()


@router.get("/categories/{slug}/topics", response_model=List[Topic])
async def get_topics(slug: str, request: Request):
    return _loader(request).get_topics_by_category(slug)


@router.get("/topics/{topic_id}", response_model=Topic)
async def get_topic(topic_id: str, request: Request):
    topic = _loader(request).get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


@router.get("/topics/{topic_id}/examples", response_model=List[Example])
async def get_topic_examples(topic_id: str, request: Request):
    loader = _loader(request)
    if loader.get_topic(topic_id) is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return loader.get_examples_for_topic(topic_id)


@router.get("/examples/{example_id}", response_model=Example)
async def get_example(example_id: str, request: Request):
    example = _loader(request).get_example(example_id)
    if example is None:
        raise HTTPException(status_code=404, detail="Example not found")
    return example


@router.get("/assets/{asset_path:path}")
async def get_asset(asset_path: str, request: Request):
    """Serve a published asset. Path traversal outside the assets directory is rejected."""
    file_path = _safe_asset_path(_loader(request), asset_path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(file_path)


@router.get("/progress", response_model=List[TutorialProgress])
async def get_progress(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return progress_repo.get_user_progress(db, current_user.id)


@router.post("/progress/{example_id}", response_model=TutorialProgress)
async def update_progress(
    example_id: str,
    update: ProgressUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if _loader(request).get_example(example_id) is None:
        raise HTTPException(status_code=404, detail="Example not found")
    return progress_repo.upsert_progress(
        db, current_user.id, example_id, update.topic_id, update.last_step_id, update.completed
    )
```

- [ ] **Step 4.4: Commit**

```bash
git add katrain/web/tutorials/models.py \
        katrain/web/tutorials/progress.py \
        katrain/web/api/v1/endpoints/tutorials.py
git commit -m "feat(tutorials): add Pydantic models, progress CRUD, and API endpoints"
```

---

### Task 5: Register Router + Server Init + API Tests

**Files:**
- Modify: `katrain/web/api/v1/api.py`
- Modify: `katrain/web/server.py`
- Create: `tests/test_tutorial_api.py`

- [ ] **Step 5.1: Register tutorials router in `katrain/web/api/v1/api.py`**

Open `katrain/web/api/v1/api.py`. After the last existing `api_router.include_router(...)` call, add:

```python
from katrain.web.api.v1.endpoints import tutorials
api_router.include_router(tutorials.router, prefix="/tutorials", tags=["tutorials"])
```

- [ ] **Step 5.2: Initialize tutorial_loader in `katrain/web/server.py`**

Open `katrain/web/server.py`. Find the `_lifespan_server` async function. At the very end of that function's body (after the live service initialization block and before the function returns), add:

```python
    # ── Tutorial Loader ──────────────────────────────────────────────────────
    import pathlib
    from katrain.web.tutorials.loader import TutorialLoader

    tutorial_base = pathlib.Path("data/tutorials_published")
    if tutorial_base.exists():
        tutorial_loader = TutorialLoader(tutorial_base)
        try:
            tutorial_loader.load()
            app.state.tutorial_loader = tutorial_loader
            log.info("Tutorial package loaded successfully")
        except Exception as e:
            log.warning(f"Failed to load tutorial package: {e}")
    else:
        log.info("No tutorial package found at data/tutorials_published — tutorial module disabled")
```

- [ ] **Step 5.3: Write API tests**

Create `tests/test_tutorial_api.py`:

```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from katrain.web.core import models_db
from katrain.web.core.db import get_db
from katrain.web.tutorials.loader import TutorialLoader

FIXTURE_PATH = Path("data/tutorials_published")


@pytest.fixture
def client():
    from katrain.web.server import create_app

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models_db.Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    app = create_app()

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    loader = TutorialLoader(FIXTURE_PATH)
    loader.load()
    app.state.tutorial_loader = loader

    return TestClient(app)


def test_get_categories(client):
    resp = client.get("/api/v1/tutorials/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["slug"] == "opening"


def test_get_topics(client):
    resp = client.get("/api/v1/tutorials/categories/opening/topics")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == "topic_opening_001"


def test_get_topic(client):
    resp = client.get("/api/v1/tutorials/topics/topic_opening_001")
    assert resp.status_code == 200
    assert resp.json()["title"] == "角、边与中央的价值"


def test_get_topic_not_found(client):
    assert client.get("/api/v1/tutorials/topics/does_not_exist").status_code == 404


def test_get_topic_examples(client):
    resp = client.get("/api/v1/tutorials/topics/topic_opening_001/examples")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "ex_opening_001"


def test_get_topic_examples_not_found(client):
    assert client.get("/api/v1/tutorials/topics/does_not_exist/examples").status_code == 404


def test_get_example(client):
    resp = client.get("/api/v1/tutorials/examples/ex_opening_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_count"] == 2
    assert len(data["steps"]) == 2


def test_example_not_found(client):
    assert client.get("/api/v1/tutorials/examples/does_not_exist").status_code == 404


def test_example_board_mode_image(client):
    data = client.get("/api/v1/tutorials/examples/ex_opening_001").json()
    for step in data["steps"]:
        assert step["board_mode"] == "image"
        assert step["board_payload"] is None


def test_example_no_forbidden_fields(client):
    data = client.get("/api/v1/tutorials/examples/ex_opening_001").json()
    forbidden = {"source_path", "raw_text", "source_id", "book_title", "author", "translator"}
    for step in data["steps"]:
        assert not forbidden.intersection(step.keys()), \
            f"Forbidden fields in step: {forbidden.intersection(step.keys())}"


def test_get_asset_image(client):
    resp = client.get("/api/v1/tutorials/assets/images/ex_opening_001_step_01.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")


def test_get_asset_not_found(client):
    assert client.get("/api/v1/tutorials/assets/images/missing.png").status_code == 404


def test_progress_requires_auth(client):
    # get_current_user raises HTTP 401 when no bearer token is present
    assert client.get("/api/v1/tutorials/progress").status_code == 401


def test_category_no_forbidden_fields(client):
    data = client.get("/api/v1/tutorials/categories").json()
    forbidden = {"source_path", "book_title", "author", "translator", "raw_text"}
    for cat in data:
        assert not forbidden.intersection(cat.keys())
```

- [ ] **Step 5.4: Run API tests — verify all pass**

```bash
CI=true uv run pytest tests/test_tutorial_api.py -v
```

Expected: 14 tests `PASSED`

- [ ] **Step 5.5: Run full test suite — no regressions**

```bash
CI=true uv run pytest tests/ -v --tb=short 2>&1 | tail -15
```

Expected: all previously passing tests still pass.

- [ ] **Step 5.6: Commit**

```bash
git add katrain/web/api/v1/api.py katrain/web/server.py tests/test_tutorial_api.py
git commit -m "feat(tutorials): register router, init loader in server lifespan, add API tests"
```

---

## Chunk 3: Frontend

### Task 6: TypeScript Types + API Client

**Files:**
- Create: `katrain/web/ui/src/galaxy/types/tutorial.ts`
- Create: `katrain/web/ui/src/galaxy/api/tutorialApi.ts`

- [ ] **Step 6.1: Create `katrain/web/ui/src/galaxy/types/tutorial.ts`**

```typescript
export interface TutorialCategory {
  id: string;
  slug: string;
  title: string;
  summary: string;
  order: number;
  topic_count: number;
  cover_asset: string | null;
}

export interface TutorialTopic {
  id: string;
  category_id: string;
  slug: string;
  title: string;
  summary: string;
  tags: string[] | null;
  difficulty: string | null;
  estimated_minutes: number | null;
}

export type BoardMode = 'image' | 'sgf';

export interface TutorialStep {
  id: string;
  example_id: string;
  order: number;
  narration: string;
  image_asset: string | null;
  audio_asset: string | null;
  audio_duration_ms: number | null;
  board_mode: BoardMode;
  board_payload: unknown | null;
}

export interface TutorialExample {
  id: string;
  topic_id: string;
  title: string;
  summary: string;
  order: number;
  total_duration_sec: number | null;
  step_count: number;
  steps: TutorialStep[];
}

export interface TutorialProgress {
  example_id: string;
  topic_id: string;
  last_step_id: string | null;
  completed: boolean;
  last_played_at: string | null;
}

export interface ProgressUpdate {
  topic_id: string;
  last_step_id: string;
  completed: boolean;
}
```

- [ ] **Step 6.2: Create `katrain/web/ui/src/galaxy/api/tutorialApi.ts`**

```typescript
import type {
  TutorialCategory,
  TutorialExample,
  TutorialProgress,
  TutorialTopic,
  ProgressUpdate,
} from '../types/tutorial';

const BASE = '/api/v1/tutorials';

async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`Tutorial API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Tutorial API ${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export const TutorialAPI = {
  getCategories: (): Promise<TutorialCategory[]> => apiGet('/categories'),

  getTopics: (categorySlug: string): Promise<TutorialTopic[]> =>
    apiGet(`/categories/${categorySlug}/topics`),

  getTopic: (topicId: string): Promise<TutorialTopic> => apiGet(`/topics/${topicId}`),

  getTopicExamples: (topicId: string): Promise<TutorialExample[]> =>
    apiGet(`/topics/${topicId}/examples`),

  getExample: (exampleId: string): Promise<TutorialExample> =>
    apiGet(`/examples/${exampleId}`),

  /** Build the URL for a published asset (image or audio). */
  assetUrl: (assetRef: string): string =>
    `${BASE}/assets/${assetRef.replace(/^assets\//, '')}`,

  getProgress: (): Promise<TutorialProgress[]> => apiGet('/progress'),

  updateProgress: (exampleId: string, update: ProgressUpdate): Promise<TutorialProgress> =>
    apiPost(`/progress/${exampleId}`, update),
};
```

- [ ] **Step 6.3: TypeScript check**

```bash
cd katrain/web/ui && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors.

- [ ] **Step 6.4: Commit**

```bash
cd katrain/web/ui && cd ../../..
git add katrain/web/ui/src/galaxy/types/tutorial.ts \
        katrain/web/ui/src/galaxy/api/tutorialApi.ts
git commit -m "feat(tutorials): add TypeScript types and API client"
```

---

### Task 7: Components + Pages

**Files:**
- Create: `katrain/web/ui/src/galaxy/components/tutorials/AudioPlayer.tsx`
- Create: `katrain/web/ui/src/galaxy/components/tutorials/StepDisplay.tsx`
- Create: `katrain/web/ui/src/galaxy/pages/tutorials/TutorialLandingPage.tsx`
- Create: `katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicsPage.tsx`
- Create: `katrain/web/ui/src/galaxy/pages/tutorials/TutorialTopicDetailPage.tsx`
- Create: `katrain/web/ui/src/galaxy/pages/tutorials/TutorialExamplePage.tsx`

- [ ] **Step 7.1: Create `AudioPlayer.tsx`**

```tsx
import React, { useEffect, useRef, useState } from 'react';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';

interface AudioPlayerProps {
  src: string | null;
  autoPlay?: boolean;
  onEnded?: () => void;
}

export default function AudioPlayer({ src, autoPlay = false, onEnded }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.load();
    setPlaying(false);
    if (autoPlay && src) {
      audio.play().then(() => setPlaying(true)).catch(() => {});
    }
  }, [src, autoPlay]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      audio.play().then(() => setPlaying(true)).catch(() => {});
    }
  };

  if (!src) return null;

  return (
    <Box display="flex" alignItems="center" gap={1}>
      <audio
        ref={audioRef}
        src={src}
        onEnded={() => { setPlaying(false); onEnded?.(); }}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
      />
      <IconButton onClick={toggle} size="small" color="primary" aria-label={playing ? 'Pause' : 'Play'}>
        {playing ? <PauseIcon /> : <PlayArrowIcon />}
      </IconButton>
    </Box>
  );
}
```

- [ ] **Step 7.2: Create `StepDisplay.tsx`**

```tsx
import React from 'react';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import type { TutorialStep } from '../../types/tutorial';
import { TutorialAPI } from '../../api/tutorialApi';
import AudioPlayer from './AudioPlayer';

interface StepDisplayProps {
  step: TutorialStep;
  onAudioEnded?: () => void;
}

export default function StepDisplay({ step, onAudioEnded }: StepDisplayProps) {
  const imageUrl = step.image_asset ? TutorialAPI.assetUrl(step.image_asset) : null;
  const audioUrl = step.audio_asset ? TutorialAPI.assetUrl(step.audio_asset) : null;

  return (
    <Box>
      {step.board_mode === 'image' && imageUrl && (
        <Box
          component="img"
          src={imageUrl}
          alt={`Step ${step.order}`}
          sx={{ width: '100%', maxWidth: 480, display: 'block', mx: 'auto', mb: 2, borderRadius: 1 }}
        />
      )}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="body1">{step.narration}</Typography>
      </Paper>
      <AudioPlayer src={audioUrl} autoPlay={false} onEnded={onAudioEnded} />
    </Box>
  );
}
```

- [ ] **Step 7.3: Create `TutorialLandingPage.tsx`**

```tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActionArea from '@mui/material/CardActionArea';
import Grid from '@mui/material/Grid';
import CircularProgress from '@mui/material/CircularProgress';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialCategory } from '../../types/tutorial';

export default function TutorialLandingPage() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<TutorialCategory[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    TutorialAPI.getCategories()
      .then(setCategories)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;

  return (
    <Box p={3}>
      <Typography variant="h5" gutterBottom>教程</Typography>
      <Typography variant="body2" color="text.secondary" gutterBottom>选择一个学习阶段开始学习</Typography>
      <Grid container spacing={2} mt={1}>
        {categories.map(cat => (
          <Grid item xs={12} sm={6} md={4} key={cat.id}>
            <Card>
              <CardActionArea onClick={() => navigate(`/galaxy/tutorials/${cat.slug}`)}>
                <CardContent>
                  <Typography variant="h6">{cat.title}</Typography>
                  <Typography variant="body2" color="text.secondary">{cat.summary}</Typography>
                  <Typography variant="caption" color="text.secondary" mt={1} display="block">
                    {cat.topic_count} 个主题
                  </Typography>
                </CardContent>
              </CardActionArea>
            </Card>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}
```

- [ ] **Step 7.4: Create `TutorialTopicsPage.tsx`**

```tsx
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';
import CircularProgress from '@mui/material/CircularProgress';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialTopic } from '../../types/tutorial';

export default function TutorialTopicsPage() {
  const { categorySlug } = useParams<{ categorySlug: string }>();
  const navigate = useNavigate();
  const [topics, setTopics] = useState<TutorialTopic[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!categorySlug) return;
    TutorialAPI.getTopics(categorySlug)
      .then(setTopics)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [categorySlug]);

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;

  return (
    <Box p={3}>
      <Typography variant="h6" gutterBottom>选择主题</Typography>
      <List>
        {topics.map((topic, i) => (
          <React.Fragment key={topic.id}>
            {i > 0 && <Divider />}
            <ListItem disablePadding>
              <ListItemButton onClick={() => navigate(`/galaxy/tutorials/topic/${topic.id}`)}>
                <ListItemText primary={topic.title} secondary={topic.summary} />
              </ListItemButton>
            </ListItem>
          </React.Fragment>
        ))}
        {topics.length === 0 && <Typography color="text.secondary">该分类下暂无主题</Typography>}
      </List>
    </Box>
  );
}
```

- [ ] **Step 7.5: Create `TutorialTopicDetailPage.tsx`**

```tsx
import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CardActionArea from '@mui/material/CardActionArea';
import CircularProgress from '@mui/material/CircularProgress';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialExample, TutorialTopic } from '../../types/tutorial';

export default function TutorialTopicDetailPage() {
  const { topicId } = useParams<{ topicId: string }>();
  const navigate = useNavigate();
  const [topic, setTopic] = useState<TutorialTopic | null>(null);
  const [examples, setExamples] = useState<TutorialExample[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!topicId) return;
    Promise.all([
      TutorialAPI.getTopic(topicId),
      TutorialAPI.getTopicExamples(topicId),
    ])
      .then(([t, exs]) => { setTopic(t); setExamples(exs); })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [topicId]);

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;
  if (!topic) return <Typography p={3} color="error">主题未找到</Typography>;

  return (
    <Box p={3}>
      <Typography variant="h6" gutterBottom>{topic.title}</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>{topic.summary}</Typography>
      <Typography variant="subtitle2" gutterBottom>例题</Typography>
      {examples.map(ex => (
        <Card key={ex.id} sx={{ mb: 2 }}>
          <CardActionArea onClick={() => navigate(`/galaxy/tutorials/example/${ex.id}`)}>
            <CardContent>
              <Typography variant="body1">{ex.title}</Typography>
              <Typography variant="body2" color="text.secondary">{ex.summary}</Typography>
              <Typography variant="caption" color="text.secondary" mt={1} display="block">
                {ex.step_count} 步
              </Typography>
            </CardContent>
          </CardActionArea>
        </Card>
      ))}
      {examples.length === 0 && <Typography color="text.secondary">该主题下暂无例题</Typography>}
    </Box>
  );
}
```

- [ ] **Step 7.6: Create `TutorialExamplePage.tsx`**

```tsx
import React, { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import LinearProgress from '@mui/material/LinearProgress';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { TutorialAPI } from '../../api/tutorialApi';
import type { TutorialExample } from '../../types/tutorial';
import StepDisplay from '../../components/tutorials/StepDisplay';

export default function TutorialExamplePage() {
  const { exampleId } = useParams<{ exampleId: string }>();
  const [example, setExample] = useState<TutorialExample | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!exampleId) return;
    TutorialAPI.getExample(exampleId)
      .then(setExample)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [exampleId]);

  const currentStep = example?.steps[currentStepIndex] ?? null;
  const isLast = example ? currentStepIndex === example.steps.length - 1 : false;

  const saveProgress = useCallback((stepIdx: number, done: boolean) => {
    if (!example) return;
    TutorialAPI.updateProgress(example.id, {
      topic_id: example.topic_id,
      last_step_id: example.steps[stepIdx].id,
      completed: done,
    }).catch(console.error);
  }, [example]);

  const goNext = () => {
    if (!example) return;
    if (isLast) {
      setCompleted(true);
      saveProgress(currentStepIndex, true);
    } else {
      const next = currentStepIndex + 1;
      setCurrentStepIndex(next);
      saveProgress(next, false);
    }
  };

  const goPrev = () => {
    if (currentStepIndex > 0) setCurrentStepIndex(i => i - 1);
  };

  if (loading) return <Box display="flex" justifyContent="center" p={4}><CircularProgress /></Box>;
  if (!example) return <Typography p={3} color="error">例子未找到</Typography>;

  const progressPct = ((currentStepIndex + 1) / example.steps.length) * 100;

  return (
    <Box p={3} maxWidth={640} mx="auto">
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="h6">{example.title}</Typography>
        {completed && <Chip icon={<CheckCircleIcon />} label="已完成" color="success" size="small" />}
      </Box>
      <LinearProgress variant="determinate" value={progressPct} sx={{ mb: 2 }} />
      <Typography variant="caption" color="text.secondary" mb={2} display="block">
        第 {currentStepIndex + 1} / {example.steps.length} 步
      </Typography>
      {currentStep && <StepDisplay step={currentStep} onAudioEnded={isLast ? undefined : goNext} />}
      <Box display="flex" gap={2} mt={3}>
        <Button startIcon={<ArrowBackIcon />} onClick={goPrev} disabled={currentStepIndex === 0} variant="outlined">
          上一步
        </Button>
        <Button
          endIcon={isLast ? <CheckCircleIcon /> : <ArrowForwardIcon />}
          onClick={goNext}
          variant="contained"
          color={isLast ? 'success' : 'primary'}
        >
          {isLast ? '完成' : '下一步'}
        </Button>
      </Box>
    </Box>
  );
}
```

- [ ] **Step 7.7: TypeScript check**

```bash
cd katrain/web/ui && npx tsc --noEmit 2>&1 | head -30
```

Expected: no new errors.

- [ ] **Step 7.8: Commit**

```bash
cd katrain/web/ui && cd ../../..
git add katrain/web/ui/src/galaxy/components/tutorials/ \
        katrain/web/ui/src/galaxy/pages/tutorials/
git commit -m "feat(tutorials): add components and four Tutorial pages (landing/topics/topic-detail/example)"
```

---

### Task 8: Sidebar + Routing Integration

**Files:**
- Modify: `katrain/web/ui/src/GalaxyApp.tsx`
- Modify: `katrain/web/ui/src/galaxy/components/layout/GalaxySidebar.tsx`

- [ ] **Step 8.1: Add imports to `GalaxyApp.tsx`**

Add to the import block:

```typescript
import TutorialLandingPage from './galaxy/pages/tutorials/TutorialLandingPage';
import TutorialTopicsPage from './galaxy/pages/tutorials/TutorialTopicsPage';
import TutorialTopicDetailPage from './galaxy/pages/tutorials/TutorialTopicDetailPage';
import TutorialExamplePage from './galaxy/pages/tutorials/TutorialExamplePage';
```

- [ ] **Step 8.2: Add routes to `GalaxyApp.tsx`**

Inside `<Routes>` → `<Route element={<MainLayout />}>`, before the `<Route path="*" ...>` catch-all:

```tsx
<Route path="tutorials" element={<TutorialLandingPage />} />
<Route path="tutorials/:categorySlug" element={<TutorialTopicsPage />} />
<Route path="tutorials/topic/:topicId" element={<TutorialTopicDetailPage />} />
<Route path="tutorials/example/:exampleId" element={<TutorialExamplePage />} />
```

- [ ] **Step 8.3: Add Tutorial to `GalaxySidebar.tsx`**

Add `MenuBookIcon` import at the top:

```typescript
import MenuBookIcon from '@mui/icons-material/MenuBook';
```

Add Tutorial entry to the `menuItems` array (after the Tsumego entry), using the existing i18n pattern:

```typescript
{ text: t('Tutorials', '教程'), icon: <MenuBookIcon />, path: '/galaxy/tutorials', disabled: false },
```

- [ ] **Step 8.4: Build frontend — verify no errors**

```bash
cd katrain/web/ui && npm run build 2>&1 | tail -10
```

Expected: build succeeds (exit 0).

- [ ] **Step 8.5: Commit**

```bash
cd katrain/web/ui && cd ../../..
git add katrain/web/ui/src/GalaxyApp.tsx \
        katrain/web/ui/src/galaxy/components/layout/GalaxySidebar.tsx
git commit -m "feat(tutorials): add Tutorial module to Galaxy sidebar and routing"
```

---

## Chunk 4: End-to-End Tests

### Task 9: Playwright E2E Tests

**Files:**
- Create: `katrain/web/ui/tests/tutorial.spec.ts`

Prerequisite: server running on `http://localhost:8001` with `data/tutorials_published/` present.

- [ ] **Step 9.1: Create `katrain/web/ui/tests/tutorial.spec.ts`**

```typescript
import { test, expect } from '@playwright/test';

async function login(page: Parameters<typeof test>[1]['page']) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  const loginVisible = await page.getByText('Login').isVisible().catch(() => false);
  if (loginVisible) {
    await page.getByLabel('Username').fill('admin');
    await page.getByLabel('Password').fill('admin');
    await page.getByRole('button', { name: 'Login' }).click();
    await page.waitForLoadState('networkidle');
  }
}

test.describe('Tutorial Module', () => {
  test.beforeEach(async ({ page }) => { await login(page); });

  test('Tutorial link appears in sidebar', async ({ page }) => {
    await page.goto('/galaxy');
    await expect(page.getByText('教程')).toBeVisible({ timeout: 10000 });
  });

  test('Tutorial landing page shows category cards', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await expect(page.getByText('布局')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/围棋布局的基本原则/)).toBeVisible();
  });

  test('Clicking category navigates to topic list', async ({ page }) => {
    await page.goto('/galaxy/tutorials');
    await page.getByText('布局').click();
    await expect(page.getByText('角、边与中央的价值')).toBeVisible({ timeout: 10000 });
  });

  test('Clicking topic navigates to topic detail with example list', async ({ page }) => {
    await page.goto('/galaxy/tutorials/opening');
    await page.getByText('角、边与中央的价值').click();
    await expect(page.getByText('星位与小目的选择')).toBeVisible({ timeout: 10000 });
  });

  test('Clicking example from topic detail opens playback page', async ({ page }) => {
    await page.goto('/galaxy/tutorials/topic/topic_opening_001');
    await page.getByText('星位与小目的选择').click();
    await expect(page.getByText('第 1 / 2 步')).toBeVisible({ timeout: 10000 });
  });

  test('Example page shows step narration text', async ({ page }) => {
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    await expect(page.getByText(/围棋开局时/)).toBeVisible({ timeout: 10000 });
  });

  test('Example page shows step image (board_mode=image renders image_asset)', async ({ page }) => {
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    const img = page.locator('img[alt^="Step"]');
    await expect(img).toBeVisible({ timeout: 10000 });
    const loaded = await img.evaluate((el: HTMLImageElement) => el.naturalWidth > 0);
    expect(loaded).toBe(true);
    // Verify the image src points to the asset API (board_mode=image uses image_asset)
    const src = await img.getAttribute('src');
    expect(src).toContain('/api/v1/tutorials/assets/images');
  });

  test('Example page has audio element pointing to asset API', async ({ page }) => {
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    await page.waitForSelector('audio', { timeout: 10000 });
    const src = await page.locator('audio').getAttribute('src');
    expect(src).toContain('/api/v1/tutorials/assets/audio');
  });

  test('Next button advances to step 2', async ({ page }) => {
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    await expect(page.getByText('第 1 / 2 步')).toBeVisible({ timeout: 10000 });
    await page.getByRole('button', { name: '下一步' }).click();
    await expect(page.getByText('第 2 / 2 步')).toBeVisible({ timeout: 5000 });
    await expect(page.getByText(/星位强调外势/)).toBeVisible();
  });

  test('Back button is disabled on step 1', async ({ page }) => {
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    await expect(page.getByRole('button', { name: '上一步' })).toBeDisabled({ timeout: 10000 });
  });

  test('Finish button marks example as completed', async ({ page }) => {
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    await page.getByRole('button', { name: '下一步' }).click();
    await expect(page.getByRole('button', { name: '完成' })).toBeVisible({ timeout: 5000 });
    await page.getByRole('button', { name: '完成' }).click();
    await expect(page.getByText('已完成')).toBeVisible({ timeout: 5000 });
  });

  test('Re-entering a completed example starts from step 1', async ({ page }) => {
    // Complete the example
    await page.goto('/galaxy/tutorials/example/ex_opening_001');
    await page.getByRole('button', { name: '下一步' }).click();
    await page.getByRole('button', { name: '完成' }).click();
    await expect(page.getByText('已完成')).toBeVisible({ timeout: 5000 });

    // Navigate away then back
    await page.goto('/galaxy/tutorials');
    await page.goto('/galaxy/tutorials/example/ex_opening_001');

    // Should start at step 1 (completed badge may or may not show — progress not restored in phase 1)
    await expect(page.getByText('第 1 / 2 步')).toBeVisible({ timeout: 10000 });
  });
});
```

- [ ] **Step 9.2: Start the server**

In a separate terminal:

```bash
python -m katrain --ui web --port 8001
```

Wait for: `Uvicorn running on http://127.0.0.1:8001`

- [ ] **Step 9.3: Run Playwright tests**

```bash
cd katrain/web/ui && npm test -- --grep "Tutorial" 2>&1 | tail -30
```

Expected: all 12 Tutorial tests pass.

- [ ] **Step 9.4: Commit**

```bash
git add katrain/web/ui/tests/tutorial.spec.ts
git commit -m "test(tutorials): add Playwright e2e tests for tutorial module navigation and playback"
```

---

## Acceptance Check

After all tasks complete, verify against the design doc acceptance criteria:

- [ ] **AC1:** One category (`opening`), one topic (`board-center-value`), one multi-step example (`ex_opening_001`) browsable end to end — confirmed by Playwright tests
- [ ] **AC2:** Galaxy sidebar shows "教程" entry linking to `/galaxy/tutorials` — "Tutorial link appears in sidebar" test
- [ ] **AC3:** Example playback page: picture + narrated audio + step navigation — image, audio, next/prev tests
- [ ] **AC4:** `test_example_no_forbidden_fields` passes — public API does not expose `source_path`, `book_title`, `author`, etc.
- [ ] **AC5:** Publish process requires explicit human approval — the fixture in `data/tutorials_published/` represents manually reviewed content; `active.json` is only updated by a human running the publish step. No automated publish path exists in the online app.
- [ ] **AC6:** `board_mode` field is explicit (`Literal["image","sgf"]`) on every Step — compatible with future SGF renderer without schema migration
- [ ] **AC7:** IDs are stable human-readable strings (`ex_opening_001`, `step_ex001_001`) — not auto-increment — stored `UserProgress` remains valid across republishes
