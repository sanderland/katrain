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
    yield session
    session.close()


def test_create_book_with_full_hierarchy(db):
    book = models_db.TutorialBook(
        category="布局", subcategory="棋书", title="测试书", author="作者",
        slug="test-book", asset_dir="tutorial_assets/test-book/pages",
    )
    db.add(book)
    db.commit()

    chapter = models_db.TutorialChapter(
        book_id=book.id, chapter_number="第一章", title="布局入门", order=1,
    )
    db.add(chapter)
    db.commit()

    section = models_db.TutorialSection(
        chapter_id=chapter.id, section_number="1", title="外势和实地", order=1,
    )
    db.add(section)
    db.commit()

    figure = models_db.TutorialFigure(
        section_id=section.id, page=11, figure_label="图1",
        book_text="测试文字", page_image_path="tutorial_assets/test-book/pages/page_011.png",
        board_payload={"size": 19, "stones": {"B": [[2, 16]], "W": [[3, 3]]}, "labels": {"2,16": "1", "3,3": "2"}},
        order=1,
    )
    db.add(figure)
    db.commit()

    assert len(book.chapters) == 1
    assert len(chapter.sections) == 1
    assert len(section.figures) == 1
    assert section.figures[0].figure_label == "图1"
    assert section.figures[0].board_payload["stones"]["B"] == [[2, 16]]


def test_cascade_delete(db):
    book = models_db.TutorialBook(
        category="入门", subcategory="棋书", title="删除测试",
        slug="delete-test", asset_dir="tutorial_assets/delete-test/pages",
    )
    db.add(book)
    db.commit()

    chapter = models_db.TutorialChapter(book_id=book.id, chapter_number="第1课", title="测试", order=1)
    db.add(chapter)
    db.commit()
    section = models_db.TutorialSection(chapter_id=chapter.id, section_number="1", title="测试", order=1)
    db.add(section)
    db.commit()
    figure = models_db.TutorialFigure(
        section_id=section.id, page=1, figure_label="图1", order=1,
    )
    db.add(figure)
    db.commit()

    db.delete(book)
    db.commit()

    assert db.query(models_db.TutorialChapter).count() == 0
    assert db.query(models_db.TutorialSection).count() == 0
    assert db.query(models_db.TutorialFigure).count() == 0


def test_book_slug_unique(db):
    b1 = models_db.TutorialBook(category="布局", title="A", slug="same-slug", asset_dir="a")
    b2 = models_db.TutorialBook(category="布局", title="B", slug="same-slug", asset_dir="b")
    db.add(b1)
    db.commit()
    db.add(b2)
    with pytest.raises(Exception):
        db.commit()


def test_update_board_payload(db):
    book = models_db.TutorialBook(category="布局", title="T", slug="bp-test", asset_dir="a")
    db.add(book)
    db.commit()
    ch = models_db.TutorialChapter(book_id=book.id, chapter_number="1", title="C", order=1)
    db.add(ch)
    db.commit()
    sec = models_db.TutorialSection(chapter_id=ch.id, section_number="1", title="S", order=1)
    db.add(sec)
    db.commit()
    fig = models_db.TutorialFigure(
        section_id=sec.id, page=1, figure_label="图1", order=1,
        board_payload={"size": 19, "stones": {"B": [], "W": []}, "labels": {}},
    )
    db.add(fig)
    db.commit()

    fig.board_payload = {
        "size": 19,
        "stones": {"B": [[3, 3]], "W": []},
        "labels": {"3,3": "1"},
        "letters": {"5,5": "A"},
        "shapes": {"7,7": "triangle"},
    }
    db.commit()
    db.refresh(fig)
    assert fig.board_payload["letters"]["5,5"] == "A"
    assert fig.board_payload["shapes"]["7,7"] == "triangle"
