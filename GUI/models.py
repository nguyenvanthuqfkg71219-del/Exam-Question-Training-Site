from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from typing import List
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    questions = db.relationship('Question', backref='author', lazy=True)
    wrong_answers = db.relationship('WrongAnswer', backref='user', lazy=True)
    wrong_answer_sets = db.relationship('WrongAnswerSet', backref='user', lazy=True)

    # ADDED: Constructor to fix Pylance error
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.String(1000), nullable=False)
    option_a = db.Column(db.String(500), nullable=False)
    option_b = db.Column(db.String(500), nullable=False)
    option_c = db.Column(db.String(500), nullable=False)
    option_d = db.Column(db.String(500), nullable=False)
    correct_answer = db.Column(db.String(10), nullable=False)
    is_multiple_choice = db.Column(db.Boolean, default=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wrong_answers = db.relationship('WrongAnswer', backref='question', lazy=True)

    # ADDED: Constructor to fix Pylance error
    def __init__(self, question_text: str, option_a: str, option_b: str, option_c: str, option_d: str, correct_answer: str, is_multiple_choice: bool, user_id: int):
        self.question_text = question_text
        self.option_a = option_a
        self.option_b = option_b
        self.option_c = option_c
        self.option_d = option_d
        self.correct_answer = correct_answer
        self.is_multiple_choice = is_multiple_choice
        self.user_id = user_id


class WrongAnswerSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wrong_answers = db.relationship('WrongAnswer', backref='wrong_answer_set', lazy=True)

    # ADDED: Constructor to fix Pylance error
    def __init__(self, user_id: int):
        self.user_id = user_id


class WrongAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    selected_answer = db.Column(db.String(10), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    wrong_answer_set_id = db.Column(db.Integer, db.ForeignKey('wrong_answer_set.id'), nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
    
    # ADDED: Constructor to fix Pylance error
    def __init__(self, question_id: int, selected_answer: str, user_id: int, wrong_answer_set_id: int):
        self.question_id = question_id
        self.selected_answer = selected_answer
        self.user_id = user_id
        self.wrong_answer_set_id = wrong_answer_set_id