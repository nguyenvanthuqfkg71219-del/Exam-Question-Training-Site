# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import pandas as pd
import os

from models import db, User, WrongAnswer

# 初始化Flask应用
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'  # 重要！
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库和登录管理器
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # 未登录时重定向到登录页

# 加载用户回调函数
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# 在应用上下文中创建数据库表
with app.app_context():
    db.create_all()

# 从Excel加载题目数据
QUESTIONS = []
def load_questions():
    global QUESTIONS
    try:
        # 假设你的数据在第一个sheet，且第一行是标题
        df = pd.read_excel('dataSet/data.xlsx')
        # 清理列名，去除可能的空格或特殊字符
        df.columns = [col.strip() for col in df.columns]
        QUESTIONS = df.to_dict('records') # 转换为字典列表
        print(f"成功加载 {len(QUESTIONS)} 道题目")
    except Exception as e:
        print(f"加载题目失败: {e}")
        QUESTIONS = []

# 应用启动时加载题目
load_questions()

# 路由：首页/题目列表
@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    return render_template('index.html', questions=QUESTIONS)

# 路由：登录
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'] # 注意：生产环境必须加密
        
        # 简单验证（实际应查数据库并验证密码哈希）
        user = User.query.filter_by(username=username).first()
        if user and user.password_hash == password: # 不安全！仅作演示
            login_user(user)
            flash('登录成功！', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'error')
    return render_template('login.html')

# 路由：注册（可选，简化版可省略，手动创建用户）
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'error')
        else:
            # 创建新用户（生产环境密码需哈希）
            new_user = User(username=username, password_hash=password)
            db.session.add(new_user)
            db.session.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

# 路由：登出
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已成功登出', 'info')
    return redirect(url_for('login'))

# 路由：答题提交
@app.route('/submit', methods=['POST'])
@login_required
def submit_answer():
    # 获取表单数据
    answers = {}
    for key, value in request.form.items():
        if key.startswith('answer_'):
            qid = key.split('_')[1] # 提取问题ID（假设是索引）
            answers[qid] = value
    
    wrong_count = 0
    # 遍历所有回答
    for qid_str, selected in answers.items():
        try:
            qid = int(qid_str)
            if qid >= len(QUESTIONS): 
                continue # 防止越界
            question = QUESTIONS[qid]
            # 从文本中解析正确答案，例如： "|A||"
            # 这里假设正确答案在最后一个"| |"之间
            answer_parts = str(question['是否多选']).split('|')
            # 找到最后一个非空部分
            correct_ans = None
            for part in reversed(answer_parts):
                if part.strip():
                    correct_ans = part.strip()
                    break
            
            # 如果没有找到，跳过
            if not correct_ans:
                continue
                
            # 比较答案（忽略大小写和顺序，对于多选）
            if isinstance(selected, list): # 多选框返回list
                selected_sorted = ''.join(sorted([s.upper() for s in selected]))
            else:
                selected_sorted = selected.upper().strip()
                
            correct_sorted = ''.join(sorted([c.upper() for c in correct_ans if c in 'ABCD']))
            
            if selected_sorted != correct_sorted:
                wrong_count += 1
                # 记录错题到数据库
                existing = WrongAnswer.query.filter_by(
                    user_id=current_user.id,
                    question_text=question['题目']
                ).first()
                if not existing: # 避免重复记录同一道错题
                    wrong_record = WrongAnswer(
                        user_id=current_user.id,
                        question_text=question['题目'],
                        selected_answer=selected_sorted,
                        correct_answer=correct_sorted
                    )
                    db.session.add(wrong_record)
        except Exception as e:
            print(f"处理第{qid}题时出错: {e}")
            continue
    
    db.session.commit()
    flash(f'答题完成！共答错 {wrong_count} 题。', 'info')
    return redirect(url_for('index'))

# 路由：查看错题集
@app.route('/wrong_answers')
@login_required
def view_wrong_answers():
    wrong_list = WrongAnswer.query.filter_by(user_id=current_user.id).all()
    return render_template('wrong_answers.html', wrong_answers=wrong_list)

@app.route('/import_excel', methods=['GET', 'POST'])
@login_required  # 仅登录用户可访问
def import_excel():
    if request.method == 'POST':
        # 获取上传的文件
        file = request.files.get('excel_file')
        if not file:
            flash('请选择一个Excel文件', 'error')
            return redirect(request.url)
        
        # 保存文件到临时路径
        file_path = os.path.join('uploads', file.filename)
        os.makedirs('uploads', exist_ok=True)  # 创建上传目录
        file.save(file_path)
        
        try:
            # 读取Excel文件
            df = pd.read_excel(file_path, engine='openpyxl')
            # 清理列名（去除空格）
            df.columns = [col.strip() for col in df.columns]
            
            # 将数据写入数据库
            for _, row in df.iterrows():
                question = Question(
                    text=row['题目'],
                    option_a=row['A'],
                    option_b=row['B'],
                    option_c=row['C'],
                    option_d=row['D'],
                    is_multiple=row['是否多选'] == 'TRUE'
                )
                db.session.add(question)
            db.session.commit()
            flash('Excel 数据已成功导入数据库！', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'导入失败: {str(e)}', 'error')
        finally:
            os.remove(file_path)  # 删除临时文件
        
    return render_template('import_excel.html')

if __name__ == '__main__':
    app.run(debug=True)