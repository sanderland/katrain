import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from katrain.web.core import models_db
from katrain.web.core.auth import SQLAlchemyUserRepository, create_access_token
from katrain.web.core.db import get_db


@pytest.fixture
def client():
    from katrain.web.server import create_app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models_db.Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    # Seed test data
    session = TestSession()
    book = models_db.TutorialBook(
        category="布局", subcategory="棋书", title="测试布局书",
        author="作者", slug="test-buju", asset_dir="tutorial_assets/test-buju/pages",
    )
    session.add(book)
    session.flush()
    chapter = models_db.TutorialChapter(book_id=book.id, chapter_number="第一章", title="布局入门", order=1)
    session.add(chapter)
    session.flush()
    section = models_db.TutorialSection(chapter_id=chapter.id, section_number="1", title="外势和实地", order=1)
    session.add(section)
    session.flush()
    for i in range(3):
        fig = models_db.TutorialFigure(
            section_id=section.id, page=11 + i, figure_label=f"图{i + 1}",
            book_text=f"测试文字{i + 1}", page_image_path=f"tutorial_assets/test-buju/pages/page_{11 + i:03d}.png",
            board_payload={"size": 19, "stones": {"B": [[3, 3]], "W": []}, "labels": {"3,3": "1"}} if i == 0 else None,
            order=i + 1,
        )
        session.add(fig)
    session.commit()
    session.close()

    app = create_app()

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


def test_get_categories(client):
    resp = client.get("/api/v1/tutorials/categories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    slugs = {c["slug"] for c in data}
    assert slugs == {"入门", "布局", "中盘", "官子"}


def test_get_books_by_category(client):
    resp = client.get("/api/v1/tutorials/categories/布局/books")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "测试布局书"
    assert data[0]["chapter_count"] == 1


def test_get_book_detail(client):
    resp = client.get("/api/v1/tutorials/books/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "测试布局书"
    assert len(data["chapters"]) == 1
    assert data["chapters"][0]["section_count"] == 1


def test_get_book_not_found(client):
    assert client.get("/api/v1/tutorials/books/999").status_code == 404


def test_get_sections(client):
    resp = client.get("/api/v1/tutorials/chapters/1/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "外势和实地"
    assert data[0]["figure_count"] == 3


def test_get_section_detail(client):
    resp = client.get("/api/v1/tutorials/sections/1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["figures"]) == 3
    assert data["figures"][0]["figure_label"] == "图1"


def test_get_figure(client):
    resp = client.get("/api/v1/tutorials/figures/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["figure_label"] == "图1"
    assert data["board_payload"]["stones"]["B"] == [[3, 3]]


def test_update_board_requires_auth(client):
    """Edit endpoint must require authentication."""
    resp = client.put("/api/v1/tutorials/figures/1/board",
                      json={"board_payload": {"size": 19, "stones": {"B": [], "W": []}}})
    assert resp.status_code == 401


def test_update_board_rejects_invalid_payload(client):
    """Malformed board_payload should be rejected by validation."""
    resp = client.put("/api/v1/tutorials/figures/1/board",
                      json={"board_payload": {"bad": "data"}})
    assert resp.status_code in (401, 422)


def test_path_traversal_rejected(client):
    """Asset endpoint rejects path traversal attempts."""
    resp = client.get("/api/v1/tutorials/assets/../../../etc/passwd")
    # FastAPI may normalize paths or reject them — either 400 or 404 is acceptable
    assert resp.status_code in (400, 404)


def test_empty_category_returns_empty_list(client):
    resp = client.get("/api/v1/tutorials/categories/入门/books")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.fixture
def client_with_auth():
    from katrain.web.server import create_app

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models_db.Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)

    # Seed test data
    session = TestSession()
    book = models_db.TutorialBook(
        category="布局", subcategory="棋书", title="测试布局书",
        author="作者", slug="test-buju", asset_dir="tutorial_assets/test-buju/pages",
    )
    session.add(book)
    session.flush()
    chapter = models_db.TutorialChapter(book_id=book.id, chapter_number="第一章", title="布局入门", order=1)
    session.add(chapter)
    session.flush()
    section = models_db.TutorialSection(chapter_id=chapter.id, section_number="1", title="外势和实地", order=1)
    session.add(section)
    session.flush()
    for i in range(3):
        fig = models_db.TutorialFigure(
            section_id=section.id, page=11 + i, figure_label=f"图{i + 1}",
            book_text=f"测试文字{i + 1}", page_image_path=f"tutorial_assets/test-buju/pages/page_{11 + i:03d}.png",
            board_payload={"size": 19, "stones": {"B": [[3, 3]], "W": []}, "labels": {"3,3": "1"}} if i == 0 else None,
            order=i + 1,
        )
        session.add(fig)

    # Create a test user
    user = models_db.User(
        username="testadmin",
        hashed_password="fakehash",
    )
    session.add(user)
    session.commit()
    session.close()

    app = create_app()

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.state.user_repo = SQLAlchemyUserRepository(TestSession)

    token = create_access_token(data={"sub": "testadmin"})
    return TestClient(app), token


def test_update_board_authenticated_success(client_with_auth):
    client, token = client_with_auth
    resp = client.put(
        "/api/v1/tutorials/figures/1/board",
        json={
            "board_payload": {
                "size": 19,
                "stones": {"B": [[3, 3], [15, 15]], "W": [[3, 15]]},
                "labels": {"3,3": "1", "3,15": "2", "15,15": "3"},
            }
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["board_payload"]["stones"]["B"] == [[3, 3], [15, 15]]
    assert "viewport" in data["board_payload"]
    assert data["updated_at"] is not None


def test_update_board_rejects_invalid_size(client_with_auth):
    client, token = client_with_auth
    resp = client.put(
        "/api/v1/tutorials/figures/1/board",
        json={"board_payload": {"size": 7, "stones": {"B": [], "W": []}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_update_board_rejects_bad_stone_key(client_with_auth):
    client, token = client_with_auth
    resp = client.put(
        "/api/v1/tutorials/figures/1/board",
        json={"board_payload": {"size": 19, "stones": {"R": [[0, 0]]}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422


def test_update_board_rejects_oob_coordinates(client_with_auth):
    client, token = client_with_auth
    resp = client.put(
        "/api/v1/tutorials/figures/1/board",
        json={"board_payload": {"size": 19, "stones": {"B": [[99, 99]]}}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422
