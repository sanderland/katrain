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
