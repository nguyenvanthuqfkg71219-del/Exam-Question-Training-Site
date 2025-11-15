# models.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

# --- NEW: QuestionSet Model ---
# This table will store the name of each uploaded quiz file (e.g., "Chapter 1")
class QuestionSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # --- Link to the User who uploaded it ---
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('question_sets', lazy=True, cascade="all, delete-orphan"))
    
    # --- Link to all questions and wrong answers in this set ---
    questions = db.relationship('Question', backref='question_set', lazy=True, cascade="all, delete-orphan")
    wrong_answers = db.relationship('WrongAnswer', backref='question_set', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<QuestionSet {self.name}>'

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    is_multiple = db.Column(db.Boolean, default=False)
    correct_answer = db.Column(db.String(10), nullable=True) # e.g., "A", "AB", "C"
    
    # --- ADD THIS: Foreign key to link to the QuestionSet ---
    question_set_id = db.Column(db.Integer, db.ForeignKey('question_set.id'), nullable=False)
    
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)  # Stored as hash
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    def __repr__(self):
        return f'<User {self.username}>'

class WrongAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    selected_answer = db.Column(db.String(10))  # e.g. "A", "AB" (multi)
    correct_answer = db.Column(db.String(10))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('wrong_answers', lazy=True, cascade="all, delete-orphan"))

    # --- ADD THIS: Foreign key to link to the QuestionSet ---
    question_set_id = db.Column(db.Integer, db.ForeignKey('question_set.id'), nullable=False)

    def __repr__(self):
        return f'<WrongAnswer for User {self.user_id}: {self.question_text[:50]}...>'