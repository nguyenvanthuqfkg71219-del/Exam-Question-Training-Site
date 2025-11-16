from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from typing import List, Optional
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id: db.Mapped[int] = db.Column(db.Integer, primary_key=True)
    username: db.Mapped[str] = db.Column(db.String(150), unique=True, nullable=False)
    password: db.Mapped[str] = db.Column(db.String(150), nullable=False)
    
    # Relationships
    question_sets: db.Mapped[List["QuestionSet"]] = db.relationship('QuestionSet', back_populates='user', lazy=True, cascade="all, delete-orphan")
    wrong_answers: db.Mapped[List["WrongAnswer"]] = db.relationship('WrongAnswer', backref='user', lazy=True)
    wrong_answer_sets: db.Mapped[List["WrongAnswerSet"]] = db.relationship('WrongAnswerSet', backref='user', lazy=True)

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

class QuestionSet(db.Model):
    id: db.Mapped[int] = db.Column(db.Integer, primary_key=True)
    name: db.Mapped[str] = db.Column(db.String(255), nullable=False)
    timestamp: db.Mapped[datetime] = db.Column(db.DateTime, server_default=db.func.now())
    
    user_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    user: db.Mapped["User"] = db.relationship('User', back_populates='question_sets')
    # ADDED: Cascade delete for questions when a set is deleted
    questions: db.Mapped[List["Question"]] = db.relationship('Question', back_populates='question_set', lazy=True, cascade="all, delete-orphan")
    # Relationship for quiz history (WrongAnswerSet)
    quiz_attempts: db.Mapped[List["WrongAnswerSet"]] = db.relationship('WrongAnswerSet', back_populates='question_set')


    def __init__(self, name: str, user_id: int):
        self.name = name
        self.user_id = user_id

class Question(db.Model):
    id: db.Mapped[int] = db.Column(db.Integer, primary_key=True)
    question_text: db.Mapped[str] = db.Column(db.String(1000), nullable=False)
    option_a: db.Mapped[str] = db.Column(db.String(500), nullable=False)
    option_b: db.Mapped[str] = db.Column(db.String(500), nullable=False)
    option_c: db.Mapped[str] = db.Column(db.String(500), nullable=False)
    option_d: db.Mapped[str] = db.Column(db.String(500), nullable=False)
    correct_answer: db.Mapped[str] = db.Column(db.String(10), nullable=False)
    is_multiple_choice: db.Mapped[bool] = db.Column(db.Boolean, default=False, nullable=False)
    
    user_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    question_set_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('question_set.id'), nullable=False)
    question_set: db.Mapped["QuestionSet"] = db.relationship('QuestionSet', back_populates='questions')

    # ADDED: Cascade delete for wrong answers when a question is deleted
    wrong_answers: db.Mapped[List["WrongAnswer"]] = db.relationship('WrongAnswer', backref='question', lazy=True, cascade="all, delete-orphan")

    def __init__(self, question_text: str, option_a: str, option_b: str, option_c: str, option_d: str, correct_answer: str, is_multiple_choice: bool, user_id: int, question_set_id: int):
        self.question_text = question_text
        self.option_a = option_a
        self.option_b = option_b
        self.option_c = option_c
        self.option_d = option_d
        self.correct_answer = correct_answer
        self.is_multiple_choice = is_multiple_choice
        self.user_id = user_id
        self.question_set_id = question_set_id

class WrongAnswerSet(db.Model):
    id: db.Mapped[int] = db.Column(db.Integer, primary_key=True)
    timestamp: db.Mapped[datetime] = db.Column(db.DateTime, server_default=db.func.now())
    user_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # MODIFIED: Added ondelete='SET NULL'
    # If a QuestionSet is deleted, this ID becomes NULL instead of deleting the history
    question_set_id: db.Mapped[Optional[int]] = db.Column(db.Integer, db.ForeignKey('question_set.id', ondelete='SET NULL'), nullable=True)
    question_set: db.Mapped[Optional["QuestionSet"]] = db.relationship('QuestionSet', back_populates='quiz_attempts')
    
    wrong_answers: db.Mapped[List["WrongAnswer"]] = db.relationship('WrongAnswer', backref='wrong_answer_set', lazy=True, cascade="all, delete-orphan")

    def __init__(self, user_id: int, question_set_id: Optional[int] = None):
        self.user_id = user_id
        self.question_set_id = question_set_id

class WrongAnswer(db.Model):
    id: db.Mapped[int] = db.Column(db.Integer, primary_key=True)
    question_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    selected_answer: db.Mapped[str] = db.Column(db.String(10), nullable=False)
    user_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wrong_answer_set_id: db.Mapped[int] = db.Column(db.Integer, db.ForeignKey('wrong_answer_set.id'), nullable=False)
    timestamp: db.Mapped[datetime] = db.Column(db.DateTime, server_default=db.func.now())
    
    def __init__(self, question_id: int, selected_answer: str, user_id: int, wrong_answer_set_id: int):
        self.question_id = question_id
        self.selected_answer = selected_answer
        self.user_id = user_id
        self.wrong_answer_set_id = wrong_answer_set_id