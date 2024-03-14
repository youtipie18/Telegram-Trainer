from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from db import Base


class User(Base):
    __tablename__ = "user"
    user_id = Column("user_id", Integer, primary_key=True)
    admin_status = Column("is_admin", Boolean, nullable=False, default=False)
    videos = relationship("Video", backref="user")

    def __init__(self, user_id):
        self.user_id = user_id

    def __repr__(self):
        return f"User №{self.user_id}"


class Category(Base):
    __tablename__ = "category"
    category_id = Column("category_id", Integer, primary_key=True)
    videos = relationship("Video", backref="category")
    name = Column("name", String, nullable=False)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


class Video(Base):
    __tablename__ = "video"
    id = Column("id", Integer, primary_key=True)
    video_id = Column("video_id", Integer, nullable=False)
    description_id = Column("description_id", Integer, nullable=False)
    category_id = Column("category_id", Integer, ForeignKey("category.category_id"), nullable=False)
    difficulty = Column("difficulty", String, nullable=False)
    chat_id = Column("chat_id", Integer, ForeignKey("user.user_id"), nullable=False)

    def __init__(self, video_id, description_id, category, difficulty, user):
        self.video_id = video_id
        self.description_id = description_id
        self.category = category
        self.difficulty = difficulty
        self.user = user
