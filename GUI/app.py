# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional
from pathlib import Path
from sqlalchemy.orm import joinedload
from sqlalchemy import distinct

# --- IMPORT ALL models ---
from models import db, User, WrongAnswer, Question, QuestionSet

# --- Pathlib Setup ---
APP_ROOT: Path = Path(__file__).parent 
INSTANCE_PATH: Path = APP_ROOT / 'instance'
INSTANCE_PATH.mkdir(exist_ok=True) 

# Initialize Flask app
app: Flask = Flask(__name__, instance_path=str(INSTANCE_PATH))
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{INSTANCE_PATH / "quiz.db"}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database and login manager
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore 
login_manager.login_message = 'Please login to access this page.'
login_manager.login_message_category = 'info'

# User loader callback
@login_manager.user_loader
def load_user(user_id: str) -> Optional[User]:
    return db.session.get(User, int(user_id))

# Create database tables in application context
with app.app_context():
    db.create_all()

# --- MODIFIED: Route: Home/Dashboard ---
@app.route('/')
@login_required
def index():
    # Show all Question Sets uploaded by the current user
    question_sets: list[QuestionSet] = QuestionSet.query.filter_by(user_id=current_user.id).order_by(QuestionSet.timestamp.desc()).all()
    return render_template('index.html', question_sets=question_sets)

# --- NEW: Route for taking a specific quiz ---
@app.route('/quiz/<int:set_id>')
@login_required
def take_quiz(set_id: int):
    # Find the set and ensure it belongs to the current user
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        abort(404)
        
    # Get all questions for this set
    questions: list[Question] = Question.query.filter_by(question_set_id=set_id).all()
    
    return render_template('quiz.html', questions=questions, question_set=question_set)

# --- MODIFIED: Route: Submit Answers (now tied to a set_id) ---
@app.route('/submit/<int:set_id>', methods=['POST'])
@login_required
def submit_answer(set_id: int):
    # Find the set and ensure it belongs to the current user
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        abort(404)

    wrong_count: int = 0
    all_questions_in_set: list[Question] = Question.query.filter_by(question_set_id=set_id).all()

    for question in all_questions_in_set:
        try:
            if not question.correct_answer:
                continue 
            
            correct_sorted: str = ''.join(sorted(list(str(question.correct_answer).upper().strip())))
            
            selected_sorted: str = ""
            if question.is_multiple:
                selected_list: list[str] = request.form.getlist(f'answer_{question.id}')
                selected_sorted = ''.join(sorted([s.upper() for s in selected_list]))
            else:
                selected_single: Optional[str] = request.form.get(f'answer_{question.id}')
                if selected_single:
                    selected_sorted = selected_single.upper().strip()

            if selected_sorted != correct_sorted:
                wrong_count += 1
                # Record the wrong answer in the database
                existing: Optional[WrongAnswer] = WrongAnswer.query.filter_by(
                    user_id=current_user.id,
                    question_text=question.text,
                    question_set_id=set_id # --- Track by set_id ---
                ).first()
                
                if not existing: 
                    wrong_record = WrongAnswer()
                    wrong_record.user_id = current_user.id
                    wrong_record.question_text = question.text
                    wrong_record.selected_answer = selected_sorted
                    wrong_record.correct_answer = correct_sorted
                    wrong_record.question_set_id = set_id # --- Save the set_id ---
                    
                    db.session.add(wrong_record)
        except Exception as e:
            print(f"Error processing question {question.id}: {e}")
            continue
    
    db.session.commit()
    flash(f'Quiz complete for "{question_set.name}"! You got {wrong_count} wrong.', 'info')
    # --- Redirect back to the main dashboard ---
    return redirect(url_for('index'))

# --- MODIFIED: Route: View Wrong Answer Sets ---
@app.route('/wrong_answers')
@login_required
def view_wrong_answer_sets():
    # Find all QuestionSets where the user has at least one wrong answer
    sets_with_errors: list[QuestionSet] = QuestionSet.query.join(WrongAnswer).filter(
        QuestionSet.user_id == current_user.id
    ).distinct().order_by(QuestionSet.name).all()
    
    return render_template('wrong_answer_sets.html', question_sets=sets_with_errors)

# --- NEW: Route to see wrong answers for a SPECIFIC set ---
@app.route('/wrong_answers/<int:set_id>')
@login_required
def view_wrong_answers_for_set(set_id: int):
    # Find the set and ensure it belongs to the current user
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        abort(404)
        
    wrong_list: list[WrongAnswer] = WrongAnswer.query.filter_by(
        user_id=current_user.id,
        question_set_id=set_id
    ).order_by(WrongAnswer.timestamp.desc()).all()
    
    return render_template('wrong_answer.html', wrong_answers=wrong_list, question_set=question_set)

# --- MODIFIED: Route: Import Excel (now creates a QuestionSet) ---
@app.route('/import_excel', methods=['GET', 'POST'])
@login_required
def import_excel():
    if request.method == 'POST':
        file = request.files.get('excel_file')
        set_name: Optional[str] = request.form.get('set_name')
        
        if not file or not set_name:
            flash('Please provide both a file and a name for the set.', 'error')
            return redirect(request.url)

        if not file.filename:
            flash('File has no filename', 'error')
            return redirect(request.url)
            
        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('Please select a valid Excel file (.xlsx or .xls)', 'error')
            return redirect(request.url)
        
        uploads_dir: Path = APP_ROOT / 'uploads'
        uploads_dir.mkdir(exist_ok=True)
        file_path: Path = uploads_dir / file.filename
        
        try:
            file.save(file_path)
            
            df = pd.read_excel(file_path, engine='openpyxl')
            df.columns = [str(col).strip() for col in df.columns]

            required_cols: list[str] = ['题目', 'A', 'B', 'C', 'D', '是否多选', '正确答案']
            if not all(col in df.columns for col in required_cols):
                flash(f'Excel file is missing required columns. Need: {", ".join(required_cols)}', 'error')
                if file_path.exists():
                    file_path.unlink()
                return redirect(request.url)

            # --- NEW: Create the QuestionSet ---
            new_set = QuestionSet(name=set_name, user_id=current_user.id)
            db.session.add(new_set)
            db.session.flush() # Flush to get the new_set.id for the questions
            
            for _, row in df.iterrows():
                question = Question()
                question.text = str(row['题目'])
                question.option_a = str(row['A'])
                question.option_b = str(row['B'])
                question.option_c = str(row['C'])
                question.option_d = str(row['D'])
                question.is_multiple = str(row['是否多选']).strip().upper() == 'TRUE'
                question.correct_answer = str(row['正确答案']).strip().upper()
                question.question_set_id = new_set.id # --- Link question to the new set ---
                
                db.session.add(question)
            
            db.session.commit()
            flash(f'Question Set "{set_name}" successfully imported!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Import failed: {str(e)}', 'error')
        finally:
            if file_path.exists():
                file_path.unlink()
        
        return redirect(url_for('index')) # Redirect to dashboard after import
        
    return render_template('import_excel.html')

# --- NEW: Route to delete a Question Set ---
@app.route('/delete_set/<int:set_id>', methods=['POST'])
@login_required
def delete_set(set_id: int):
    # Find the set and ensure it belongs to the current user
    question_set: Optional[QuestionSet] = db.session.get(QuestionSet, set_id)
    if not question_set or question_set.user_id != current_user.id:
        abort(404)
        
    try:
        # Thanks to `cascade="all, delete-orphan"` in models.py,
        # deleting the set will also delete all its questions and wrong answers.
        db.session.delete(question_set)
        db.session.commit()
        flash(f'Question Set "{question_set.name}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting set: {str(e)}', 'error')
        
    return redirect(url_for('index'))


# --- (Login/Register/Logout routes are unchanged) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username: str = request.form['username']
        password: str = request.form['password']
        user: Optional[User] = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page: Optional[str] = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username: str = request.form['username']
        password: str = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
        else:
            hashed_pw: str = generate_password_hash(password, method='pbkdf2:sha256')
            new_user = User()
            new_user.username = username
            new_user.password_hash = hashed_pw
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful, please login', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)