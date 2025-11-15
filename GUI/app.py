from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Question, WrongAnswer, WrongAnswerSet
import pandas as pd
import random
from sqlalchemy.orm import joinedload
from typing import List, Optional
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
    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username: str = request.form['username']
        password: str = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('用户名已存在') # Username already exists
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
            flash('登录失败。请检查用户名和密码。') # Login failed. Check username and password.
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
            flash('请求中没有文件部分。') # No file part in the request.
            return redirect(request.url)
        
        file = request.files['file']

        if file.filename == '':
            flash('未选择要上传的文件。') # No file selected for uploading.
            return redirect(request.url)
        
        # --- FIX 1 (Line 85) ---
        # Added 'and file.filename' to ensure filename is not None before calling .endswith()
        if file and file.filename and file.filename.endswith('.xlsx'):
            try:
                df: pd.DataFrame = pd.read_excel(file)
                required_cols: List[str] = ['题目', 'A', 'B', 'C', 'D', '正确答案', '是否多选']
                if not all(col in df.columns for col in required_cols):
                    flash(f'Excel 文件必须包含以下列: {", ".join(required_cols)}') # Excel file must contain columns...
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
                        user_id=current_user.id
                    )
                    new_questions.append(question)
                
                db.session.add_all(new_questions)
                db.session.commit()
                
                flash(f'成功导入 {len(new_questions)} 道题目!') # {len(new_questions)} questions imported successfully!

                if new_questions:
                    flash('已开始使用新题目进行测验...') # Starting quiz with your new questions...
                    
                    new_wrong_answer_set = WrongAnswerSet(user_id=current_user.id)
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
                flash(f'发生错误: {e}') # An error occurred
            
            return redirect(url_for('import_excel'))
        
        else:
            flash('请上传一个有效的 .xlsx 文件') # Please upload a valid .xlsx file
            return redirect(url_for('import_excel'))
            
    return render_template('import_excel.html')


@app.route('/start_quiz', methods=['GET', 'POST'])
@login_required
def start_quiz():
    num_questions_str: Optional[str] = request.form.get('num_questions')
    if not num_questions_str or not num_questions_str.isdigit():
        flash('请输入一个有效的题目数量。') # Please enter a valid number of questions.
        return redirect(url_for('index'))

    num_questions: int = int(num_questions_str)
    all_questions: List[Question] = Question.query.filter_by(user_id=current_user.id).all()
    
    if len(all_questions) == 0:
        flash('你还没有上传任何题目。请先导入一个 Excel 文件。') # You have no questions uploaded. Please import an Excel file first.
        return redirect(url_for('index'))
    
    if len(all_questions) < num_questions:
        flash(f'你总共只有 {len(all_questions)} 道题。将开始一个 {len(all_questions)} 道题的测验。') # You only have {len(all_questions)} questions. Starting quiz with...
        num_questions = len(all_questions)
        
    new_wrong_answer_set = WrongAnswerSet(user_id=current_user.id)
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
        flash('没有正在进行的测验。请开始一个新的测验。') # No quiz in progress. Please start a new quiz.
        return redirect(url_for('index'))

    question: Optional[Question] = db.session.get(Question, question_id)
    if not question:
        flash('未找到题目。') # Question not found.
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

            # --- FIX 2 (Line 222) ---
            # Add an assert to prove to Pylance that this can't be None
            assert current_wrong_answer_set_id is not None, "Set ID should be valid"
            
            wrong_answer = WrongAnswer(
                question_id=question.id,
                selected_answer=user_answer_to_store,
                user_id=current_user.id,
                wrong_answer_set_id=current_wrong_answer_set_id # Pylance is now happy
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
                    flash('测验完成！快去看看你的错题吧。') # Quiz finished! Check your wrong answers.
                    return redirect(url_for('wrong_answer_sets'))
                else:
                    empty_set: Optional[WrongAnswerSet] = db.session.get(WrongAnswerSet, wrong_set_id)
                    if empty_set:
                        db.session.delete(empty_set)
                        db.session.commit()
                    flash('测验完成！你太棒了，全部正确！') # Quiz finished! You got all questions correct!
                    return redirect(url_for('index'))
            
            flash('测验完成！') # Quiz finished!
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
def wrong_answer_sets():
    sets: List[WrongAnswerSet] = WrongAnswerSet.query.filter_by(user_id=current_user.id).order_by(WrongAnswerSet.timestamp.desc()).all()
    valid_sets: List[WrongAnswerSet] = [s for s in sets if s.wrong_answers]
    return render_template('wrong_answer_sets.html', wrong_answer_sets=valid_sets)


@app.route('/wrong_answer/<int:set_id>')
@login_required
def wrong_answer(set_id: int):
    # --- FIX 3 (Lines 280-285) ---
    # 1. Change type hint from Optional[WrongAnswerSet] to just WrongAnswerSet
    #    because .first_or_404() *guarantees* it's not None.
    # 2. Add # type: ignore to silence the linter's confusion about joinedload.
    wrong_answer_set: WrongAnswerSet = WrongAnswerSet.query.options(
        joinedload(WrongAnswerSet.wrong_answers).joinedload(WrongAnswer.question) # type: ignore
    ).filter_by(id=set_id, user_id=current_user.id).first_or_404() # type: ignore
    
    # Pylance is now happy, as wrong_answer_set cannot be None
    wrong_answers: List[WrongAnswer] = wrong_answer_set.wrong_answers # type: ignore
    
    return render_template('wrong_answer.html', 
                           wrong_answers=wrong_answers, 
                           set_timestamp=wrong_answer_set.timestamp)


@app.route('/my_questions')
@login_required
def my_questions():
    questions: List[Question] = Question.query.filter_by(user_id=current_user.id).order_by(Question.id.desc()).all()
    return render_template('view_questions.html', questions=questions)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)