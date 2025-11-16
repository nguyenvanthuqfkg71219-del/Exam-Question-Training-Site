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
def index() -> str:
    question_sets: List[QuestionSet] = []
    if current_user.is_authenticated:
        question_sets = QuestionSet.query.filter_by(user_id=current_user.id).order_by(QuestionSet.name).all()
    return render_template('index.html', question_sets=question_sets)

@app.route('/register', methods=['GET', 'POST'])
def register() -> str:
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
def login() -> str:
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
def logout() -> str:
    logout_user()
    return redirect(url_for('index'))

@app.route('/import_excel', methods=['GET', 'POST'])
@login_required
def import_excel() -> str:
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
                file_name: str = file.filename
                new_question_set = QuestionSet(name=file_name, user_id=current_user.id)
                db.session.add(new_question_set)
                db.session.commit() 

                df: pd.DataFrame = pd.read_excel(file)
                required_cols: List[str] = ['题目', 'A', 'B', 'C', 'D', '正确答案', '是否多选']
                if not all(col in df.columns for col in required_cols):
                    flash(f'Excel 文件必须包含以下列: {", ".join(required_cols)}')
                    db.session.rollback() 
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
                        question_set_id=new_question_set.id 
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
def start_quiz() -> str:
    num_questions_str: Optional[str] = request.form.get('num_questions')
    question_set_id_str: Optional[str] = request.form.get('question_set_id')
    
    if not num_questions_str or not num_questions_str.isdigit():
        flash('请输入一个有效的题目数量。')
        return redirect(url_for('index'))

    num_questions: int = int(num_questions_str)
    
    query = Question.query.filter_by(user_id=current_user.id)
    selected_set_id: Optional[int] = None
    
    if question_set_id_str and question_set_id_str.isdigit():
        query = query.filter_by(question_set_id=int(question_set_id_str))
        selected_set_id = int(question_set_id_str)
    
    all_questions: List[Question] = query.all()
    
    if len(all_questions) == 0:
        flash('你所选的题集中没有题目。请先导入。')
        return redirect(url_for('index'))
    
    if len(all_questions) < num_questions:
        flash(f'该题集总共只有 {len(all_questions)} 道题。将开始一个 {len(all_questions)} 道题的测验。')
        num_questions = len(all_questions)
        
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
def quiz(question_id: int) -> str:
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
    
    options: List[dict] = [
        {'value': 'A', 'text': question.option_a},
        {'value': 'B', 'text': question.option_b},
        {'value': 'C', 'text': question.option_c},
        {'value': 'D', 'text': question.option_d}
    ]
    
    total_questions: int = len(session.get('question_ids', []))
    current_question_number: int = session.get('current_question_index', 0) + 1
    
    return render_template('quiz.html', 
                           question=question, 
                           options=options,
                           total_questions=total_questions,
                           current_question_number=current_question_number)


@app.route('/wrong_answer_sets')
@login_required
def wrong_answer_sets() -> str:
    question_sets: List[QuestionSet] = QuestionSet.query.filter_by(user_id=current_user.id).order_by(QuestionSet.timestamp.desc()).all()
    return render_template('wrong_answer_sets.html', question_sets=question_sets)


@app.route('/wrong_answer/<set_id>')
@login_required
def wrong_answer(set_id: str) -> str:
    title: str = ""
    query = db.session.query(Question).join(WrongAnswer).filter(
        WrongAnswer.user_id == current_user.id
    ).distinct()
    
    if set_id == 'all':
        title = "所有错题"
    else:
        try:
            set_id_int: int = int(set_id)
            query = query.filter(Question.question_set_id == set_id_int)
            set_data: Optional[QuestionSet] = db.session.get(QuestionSet, set_id_int)
            title = f'"{set_data.name}" 错题集' if set_data else "错题集"
        except ValueError:
            flash("无效的题集ID。")
            return redirect(url_for('wrong_answer_sets'))

    wrong_questions: List[Question] = query.all()
    
    return render_template('wrong_answer.html', 
                           questions=wrong_questions, 
                           title=title)


@app.route('/quiz_history')
@login_required
def quiz_history() -> str:
    attempts: List[WrongAnswerSet] = WrongAnswerSet.query.filter_by(
        user_id=current_user.id
    ).order_by(WrongAnswerSet.timestamp.desc()).all()
    
    valid_attempts: List[WrongAnswerSet] = [a for a in attempts if a.wrong_answers]
    return render_template('quiz_history.html', quiz_attempts=valid_attempts)

@app.route('/quiz_history/<int:attempt_id>')
@login_required
def quiz_history_detail(attempt_id: int) -> str:
    attempt: Optional[WrongAnswerSet] = WrongAnswerSet.query.options(
        joinedload(WrongAnswerSet.wrong_answers).joinedload(WrongAnswer.question)
    ).filter_by(id=attempt_id, user_id=current_user.id).first_or_404() # type: ignore
    
    wrong_answers: List[WrongAnswer] = attempt.wrong_answers
    
    return render_template('quiz_history_detail.html', 
                           wrong_answers=wrong_answers, 
                           set_timestamp=attempt.timestamp)


# --- MODIFIED: Goal 2 ---
# This page now shows a list of Question Sets
@app.route('/my_questions')
@login_required
def my_questions() -> str:
    question_sets: List[QuestionSet] = QuestionSet.query.filter_by(user_id=current_user.id).order_by(QuestionSet.timestamp.desc()).all()
    return render_template('my_questions.html', question_sets=question_sets)

# --- NEW: Goal 2 ---
# This new route shows the questions *inside* a specific set
@app.route('/my_questions/<int:set_id>')
@login_required
def my_questions_detail(set_id: int) -> str:
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        flash("未找到题集或无权访问。")
        return redirect(url_for('my_questions'))
        
    questions: List[Question] = question_set.questions
    return render_template('view_question_set_detail.html', questions=questions, set=question_set)


# --- NEW: Goal 1 (Delete Functionality) ---
# Step 1: Show a confirmation page
@app.route('/delete_confirm/<int:set_id>')
@login_required
def delete_question_set_confirm(set_id: int) -> str:
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        flash("未找到题集或无权访问。")
        return redirect(url_for('my_questions'))
    return render_template('delete_confirm.html', set=question_set)

# Step 2: Perform the actual deletion
@app.route('/delete_question_set/<int:set_id>', methods=['POST'])
@login_required
def delete_question_set(set_id: int) -> str:
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        flash("未找到题集或无权访问。")
        return redirect(url_for('my_questions'))
        
    set_name: str = question_set.name
    # The cascade rules in models.py will handle deleting all child Questions
    # and WrongAnswers, and setting history to NULL.
    db.session.delete(question_set)
    db.session.commit()
    
    flash(f'题集 "{set_name}" 已被永久删除。')
    return redirect(url_for('my_questions'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)