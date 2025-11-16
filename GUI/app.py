from flask import Flask, render_template, request, redirect, url_for, flash, session, Request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
# Updated model imports
from models import db, User, Question, WrongAnswer, WrongAnswerSet, QuestionSet
import pandas as pd
import random
from sqlalchemy.orm import joinedload
from typing import List, Optional, cast
import os

basedir: str = os.path.abspath(os.path.dirname(__file__))

app: Flask = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

db.init_app(app)

login_manager: LoginManager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # type: ignore

@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return db.session.get(User, int(user_id))

@app.route('/')
def index():
    # Fetch question sets for the dropdown
    question_sets: List[QuestionSet] = []
    if current_user.is_authenticated:
        question_sets = QuestionSet.query.filter_by(user_id=current_user.id).order_by(QuestionSet.name).all()
    return render_template('index.html', question_sets=question_sets)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username: str = request.form['username']
        password: str = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('用户名已存在')
            return redirect(url_for('register'))
            
        hashed_password: str = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username: str = request.form['username']
        password: str = request.form['password']
        user: Optional[User] = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('登录失败。请检查用户名和密码。')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/import_excel', methods=['GET', 'POST'])
@login_required
def import_excel():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('请求中没有文件部分。')
            return redirect(request.url)
        
        file = request.files['file']
        if not file or not file.filename:
            flash('未选择要上传的文件。')
            return redirect(request.url)
        
        if file.filename.endswith('.xlsx'):
            try:
                # --- Point 1: Create a new QuestionSet for this file ---
                file_name: str = file.filename
                new_question_set = QuestionSet(name=file_name, user_id=current_user.id)
                db.session.add(new_question_set)
                db.session.commit() # Commit to get the new_question_set.id

                df: pd.DataFrame = pd.read_excel(file)
                required_cols: List[str] = ['题目', 'A', 'B', 'C', 'D', '正确答案', '是否多选']
                if not all(col in df.columns for col in required_cols):
                    flash(f'Excel 文件必须包含以下列: {", ".join(required_cols)}')
                    db.session.rollback() # Rollback the new_question_set
                    return redirect(url_for('import_excel'))
                
                new_questions: List[Question] = []
                for _, row in df.iterrows():
                    is_multi_val: bool = row.get('是否多选', False)
                    if pd.isna(is_multi_val):
                        is_multi_val = False

                    question = Question(
                        question_text=str(row['题目']),
                        option_a=str(row['A']),
                        option_b=str(row['B']),
                        option_c=str(row['C']),
                        option_d=str(row['D']),
                        correct_answer=str(row['正确答案']).strip(),
                        is_multiple_choice=bool(is_multi_val),
                        user_id=current_user.id,
                        question_set_id=new_question_set.id # Link to the new set
                    )
                    new_questions.append(question)
                
                if not new_questions:
                    flash('Excel 文件为空或无法读取题目。')
                    db.session.rollback()
                    return redirect(url_for('import_excel'))

                db.session.add_all(new_questions)
                db.session.commit()
                
                flash(f'成功导入 {len(new_questions)} 道题目到 "{file_name}" 题集!')

                if new_questions:
                    flash('已开始使用新题目进行测验...')
                    
                    # Create a new wrong answer set, linking to this question set
                    new_wrong_answer_set = WrongAnswerSet(user_id=current_user.id, question_set_id=new_question_set.id)
                    db.session.add(new_wrong_answer_set)
                    db.session.commit()
                    session['wrong_answer_set_id'] = new_wrong_answer_set.id
                    
                    new_question_ids: List[int] = [q.id for q in new_questions]
                    random.shuffle(new_question_ids)
                    
                    session['question_ids'] = new_question_ids
                    session['current_question_index'] = 0
                    
                    first_question_id: int = session['question_ids'][0]
                    return redirect(url_for('quiz', question_id=first_question_id))
                else:
                    return redirect(url_for('index'))

            except Exception as e:
                db.session.rollback()
                flash(f'发生错误: {e}')
            
            return redirect(url_for('import_excel'))
        
        else:
            flash('请上传一个有效的 .xlsx 文件')
            return redirect(url_for('import_excel'))
            
    return render_template('import_excel.html')

@app.route('/start_quiz', methods=['POST'])
@login_required
def start_quiz():
    num_questions_str: Optional[str] = request.form.get('num_questions')
    # --- Get the selected question set ID ---
    question_set_id_str: Optional[str] = request.form.get('question_set_id')
    
    if not num_questions_str or not num_questions_str.isdigit():
        flash('请输入一个有效的题目数量。')
        return redirect(url_for('index'))

    num_questions: int = int(num_questions_str)
    
    # --- Build query based on selected set ---
    query = Question.query.filter_by(user_id=current_user.id)
    selected_set_id: Optional[int] = None
    
    if question_set_id_str and question_set_id_str.isdigit():
        query = query.filter_by(question_set_id=int(question_set_id_str))
        selected_set_id = int(question_set_id_str)
    # 'all' is the default, so no 'else' needed
    
    all_questions: List[Question] = query.all()
    
    if len(all_questions) == 0:
        flash('你所选的题集中没有题目。请先导入。')
        return redirect(url_for('index'))
    
    if len(all_questions) < num_questions:
        flash(f'该题集总共只有 {len(all_questions)} 道题。将开始一个 {len(all_questions)} 道题的测验。')
        num_questions = len(all_questions)
        
    # Create new quiz attempt, linking to the set ID (None if 'all')
    new_wrong_answer_set = WrongAnswerSet(user_id=current_user.id, question_set_id=selected_set_id)
    db.session.add(new_wrong_answer_set)
    db.session.commit()
    session['wrong_answer_set_id'] = new_wrong_answer_set.id
        
    sampled_questions: List[Question] = random.sample(all_questions, num_questions)
    session['question_ids'] = [q.id for q in sampled_questions]
    session['current_question_index'] = 0
    
    first_question_id: int = session['question_ids'][0]
    return redirect(url_for('quiz', question_id=first_question_id))

@app.route('/quiz/<int:question_id>', methods=['GET', 'POST'])
@login_required
def quiz(question_id: int):
    if 'question_ids' not in session or not session['question_ids']:
        flash('没有正在进行的测验。请开始一个新的测验。')
        return redirect(url_for('index'))

    question: Optional[Question] = db.session.get(Question, question_id)
    if not question:
        flash('未找到题目。')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        correct_answer: str = str(question.correct_answer)
        user_answer_to_store: str = ""
        is_correct: bool = False
        
        if question.is_multiple_choice:
            selected_answers: List[str] = request.form.getlist('answer')
            user_answer_to_store = "".join(sorted(selected_answers))
            correct_answer_sorted: str = "".join(sorted(correct_answer))
            is_correct = (user_answer_to_store == correct_answer_sorted)
        else:
            selected_answer_raw: Optional[str] = request.form.get('answer')
            if selected_answer_raw:
                user_answer_to_store = selected_answer_raw
                is_correct = (user_answer_to_store == correct_answer)
            else:
                user_answer_to_store = ""
                is_correct = False

        if not is_correct:
            current_wrong_answer_set_id: Optional[int] = session.get('wrong_answer_set_id')
            if not current_wrong_answer_set_id:
                # Fallback, though this shouldn't happen
                new_set = WrongAnswerSet(user_id=current_user.id) 
                db.session.add(new_set)
                db.session.commit()
                current_wrong_answer_set_id = new_set.id
                session['wrong_answer_set_id'] = current_wrong_answer_set_id

            wrong_answer = WrongAnswer(
                question_id=question.id,
                selected_answer=user_answer_to_store,
                user_id=current_user.id,
                wrong_answer_set_id=current_wrong_answer_set_id
            )
            db.session.add(wrong_answer)
            db.session.commit()

        session['current_question_index'] += 1
        current_index: int = session['current_question_index']
        
        if current_index < len(session['question_ids']):
            next_question_id: int = session['question_ids'][current_index]
            return redirect(url_for('quiz', question_id=next_question_id))
        else:
            session.pop('question_ids', None)
            session.pop('current_question_index', None)
            wrong_set_id: Optional[int] = session.pop('wrong_answer_set_id', None)
            
            if wrong_set_id:
                count: int = WrongAnswer.query.filter_by(wrong_answer_set_id=wrong_set_id).count()
                if count > 0:
                    flash('测验完成！快去看看你的错题吧。')
                    # Redirect to the new "Quiz History" page
                    return redirect(url_for('quiz_history'))
                else:
                    empty_set: Optional[WrongAnswerSet] = db.session.get(WrongAnswerSet, wrong_set_id)
                    if empty_set:
                        db.session.delete(empty_set)
                        db.session.commit()
                    flash('测验完成！你太棒了，全部正确！')
                    return redirect(url_for('index'))
            
            flash('测验完成！')
            return redirect(url_for('index'))
    
    # --- THIS IS THE FIX ---
    options: List[dict] = [
        {'value': 'A', 'text': question.option_a},
        {'value': 'B', 'text': question.option_b},
        {'value': 'C', 'text': question.option_c},
        {'value': 'D', 'text': question.option_d} # Changed .d to _d
    ]
    # --- END OF FIX ---
    
    total_questions: int = len(session.get('question_ids', []))
    current_question_number: int = session.get('current_question_index', 0) + 1
    
    return render_template('quiz.html', 
                           question=question, 
                           options=options,
                           total_questions=total_questions,
                           current_question_number=current_question_number)

# --- NEW/MODIFIED "WRONG ANSWER" ROUTES ---

# Point 2: Show overview of wrong answers by SET
@app.route('/wrong_answer_sets')
@login_required
def wrong_answer_sets():
    # Fetch all QuestionSets for the user
    question_sets: List[QuestionSet] = QuestionSet.query.filter_by(user_id=current_user.id).order_by(QuestionSet.timestamp.desc()).all()
    return render_template('wrong_answer_sets.html', question_sets=question_sets)

# Point 3: Show detailed list of wrong questions for a SET (or 'all')
@app.route('/wrong_answer/<set_id>')
@login_required
def wrong_answer(set_id: str):
    title: str = ""
    # Base query for all unique wrong questions for this user
    query = db.session.query(Question).join(WrongAnswer).filter(
        WrongAnswer.user_id == current_user.id
    ).distinct()
    
    if set_id == 'all':
        title = "所有错题"
        # Query already filters by user, so just get all
    else:
        # Filter by the specific question set
        query = query.filter(Question.question_set_id == int(set_id))
        set_data: Optional[QuestionSet] = db.session.get(QuestionSet, int(set_id))
        title = f'"{set_data.name}" 错题集' if set_data else "错题集"

    wrong_questions: List[Question] = query.all()
    
    return render_template('wrong_answer.html', 
                           questions=wrong_questions, 
                           title=title)

# --- END OF "WRONG ANSWER" ROUTES ---


# --- NEW "QUIZ HISTORY" ROUTES (Old "Wrong Answer" logic) ---
@app.route('/quiz_history')
@login_required
def quiz_history():
    # This shows all past QUIZ ATTEMPTS
    attempts: List[WrongAnswerSet] = WrongAnswerSet.query.filter_by(
        user_id=current_user.id
    ).order_by(WrongAnswerSet.timestamp.desc()).all()
    
    # Filter out attempts where the user got 0 wrong
    valid_attempts: List[WrongAnswerSet] = [a for a in attempts if a.wrong_answers]
    return render_template('quiz_history.html', quiz_attempts=valid_attempts)

@app.route('/quiz_history/<int:attempt_id>')
@login_required
def quiz_history_detail(attempt_id: int):
    # This shows the specific wrong answers from ONE quiz attempt
    attempt: Optional[WrongAnswerSet] = WrongAnswerSet.query.options(
        joinedload(WrongAnswerSet.wrong_answers).joinedload(WrongAnswer.question)
    ).filter_by(id=attempt_id, user_id=current_user.id).first_or_404() # type: ignore
    
    wrong_answers: List[WrongAnswer] = attempt.wrong_answers
    
    return render_template('quiz_history_detail.html', 
                           wrong_answers=wrong_answers, 
                           set_timestamp=attempt.timestamp)
# --- END OF "QUIZ HISTORY" ROUTES ---


@app.route('/my_questions')
@login_required
def my_questions():
    questions: List[Question] = Question.query.filter_by(user_id=current_user.id).order_by(Question.id.desc()).all()
    return render_template('view_questions.html', questions=questions)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)