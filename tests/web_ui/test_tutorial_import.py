import pytest
import json
import sys
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from katrain.web.core import models_db

# Import from scripts directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
from import_book import import_book, slugify, make_page_image_path


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models_db.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _write_book_json(tmp_path, data):
    """Helper: write book.json and create a dummy page image."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "book.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "page_011.png").write_bytes(b"\x89")
    (pages_dir / "page_009.png").write_bytes(b"\x89")


TYPE_B_DATA = {
    "title": "测试布局书",
    "author": "作者",
    "chapters": [
        {
            "chapter": "第一章",
            "title": "布局入门",
            "sections": [
                {
                    "section": "1",
                    "title": "外势和实地",
                    "pages": [
                        {
                            "page": 11,
                            "elements": [
                                {"type": "description", "text": "描述文字"},
                                {
                                    "type": "figure_ref",
                                    "label": "图1",
                                    "text": "黑先",
                                    "bbox": {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1},
                                },
                                {"type": "figure_ref", "label": "图2", "text": "白先"},
                            ],
                        }
                    ],
                }
            ],
        }
    ],
}

TYPE_A_DATA = {
    "title": "入门测试",
    "author": "作者",
    "chapters": [
        {
            "chapter": "第1课",
            "title": "打劫",
            "intro": [
                {
                    "page": 9,
                    "elements": [
                        {"type": "figure_ref", "label": "图", "text": "基本劫"},
                    ],
                }
            ],
            "sections": [],
        }
    ],
}


@patch("import_book.copy_page_assets", return_value=1)
def test_type_b_import(mock_copy, db, tmp_path):
    """Book WITH sections: 1 book, 1 chapter, 1 section, 2 figures with correct fields."""
    _write_book_json(tmp_path, TYPE_B_DATA)

    book = import_book(db, tmp_path, "布局")

    # Counts
    assert db.query(models_db.TutorialBook).count() == 1
    assert db.query(models_db.TutorialChapter).count() == 1
    assert db.query(models_db.TutorialSection).count() == 1
    assert db.query(models_db.TutorialFigure).count() == 2

    # Book fields
    assert book.title == "测试布局书"
    assert book.category == "布局"

    # Figures
    figures = db.query(models_db.TutorialFigure).order_by(models_db.TutorialFigure.order).all()
    slug = book.slug

    # Both figures come from page 11 → same page_image_path
    expected_path = f"tutorial_assets/{slug}/pages/page_011.png"
    assert figures[0].page_image_path == expected_path
    assert figures[1].page_image_path == expected_path

    # book_text
    assert figures[0].book_text == "黑先"
    assert figures[1].book_text == "白先"

    # page_context_text (from description element)
    assert figures[0].page_context_text == "描述文字"
    assert figures[1].page_context_text == "描述文字"

    # bbox present only on first figure
    assert figures[0].bbox == {"x_min": 0, "y_min": 0, "x_max": 1, "y_max": 1}
    assert figures[1].bbox is None


@patch("import_book.copy_page_assets", return_value=1)
def test_type_a_import(mock_copy, db, tmp_path):
    """Book WITHOUT sections: synthetic section created with chapter title."""
    _write_book_json(tmp_path, TYPE_A_DATA)

    book = import_book(db, tmp_path, "入门")

    assert db.query(models_db.TutorialBook).count() == 1
    assert db.query(models_db.TutorialChapter).count() == 1
    assert db.query(models_db.TutorialSection).count() == 1
    assert db.query(models_db.TutorialFigure).count() == 1

    # Synthetic section inherits chapter title
    section = db.query(models_db.TutorialSection).first()
    assert section.title == "打劫"

    # Figure
    figure = db.query(models_db.TutorialFigure).first()
    assert figure.book_text == "基本劫"
    assert figure.figure_label == "图"


@patch("import_book.copy_page_assets", return_value=1)
def test_same_page_multi_figure(mock_copy, db, tmp_path):
    """Two figure_ref elements on the same page should have the same page_image_path."""
    _write_book_json(tmp_path, TYPE_B_DATA)

    book = import_book(db, tmp_path, "布局")
    figures = db.query(models_db.TutorialFigure).order_by(models_db.TutorialFigure.order).all()

    assert len(figures) == 2
    assert figures[0].page == 11
    assert figures[1].page == 11
    assert figures[0].page_image_path == figures[1].page_image_path


@patch("import_book.copy_page_assets", return_value=1)
def test_force_reimport(mock_copy, db, tmp_path):
    """Import once, then import again with force=True: no duplicates, data is fresh."""
    _write_book_json(tmp_path, TYPE_B_DATA)

    book1 = import_book(db, tmp_path, "布局")
    assert db.query(models_db.TutorialBook).count() == 1

    book2 = import_book(db, tmp_path, "布局", force=True)
    assert db.query(models_db.TutorialBook).count() == 1

    # Should be a new record (different id after delete + recreate)
    assert book2.id is not None
    assert book2.title == "测试布局书"
    assert db.query(models_db.TutorialFigure).count() == 2


@patch("import_book.copy_page_assets", return_value=1)
def test_duplicate_without_force(mock_copy, db, tmp_path):
    """Import once, import again without force: returns existing book, count unchanged."""
    _write_book_json(tmp_path, TYPE_B_DATA)

    book1 = import_book(db, tmp_path, "布局")
    book1_id = book1.id

    book2 = import_book(db, tmp_path, "布局")

    assert db.query(models_db.TutorialBook).count() == 1
    assert book2.id == book1_id


@patch("import_book.copy_page_assets", return_value=1)
def test_empty_elements(mock_copy, db, tmp_path):
    """Page with empty elements list: no crash, zero figures created."""
    data = {
        "title": "空元素测试",
        "author": "作者",
        "chapters": [
            {
                "chapter": "第一章",
                "title": "测试",
                "sections": [
                    {
                        "section": "1",
                        "title": "空页",
                        "pages": [
                            {"page": 11, "elements": []},
                        ],
                    }
                ],
            }
        ],
    }
    _write_book_json(tmp_path, data)

    book = import_book(db, tmp_path, "布局")

    assert db.query(models_db.TutorialBook).count() == 1
    assert db.query(models_db.TutorialFigure).count() == 0


def test_slugify():
    assert slugify("test-book") == "test-book"
    assert slugify("Hello World") == "hello-world"
    assert slugify("") == "book"


def test_make_page_image_path():
    assert make_page_image_path("my-book", 11) == "tutorial_assets/my-book/pages/page_011.png"
