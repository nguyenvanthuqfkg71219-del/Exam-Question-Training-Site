import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from typing import List, Dict, Any, Optional

# Type alias for our structured question
Question = Dict[str, Any]

app = FastAPI()
DB_FILE = 'questions.db'

def fetch_questions_from_db() -> List[Question]:
    """Fetches all questions and formats them as dictionaries."""
    questions = []
    try:
        conn = sqlite3.connect(DB_FILE)
        # .row_factory makes the cursor return dictionaries instead of tuples
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, question_stem, option_a, option_b, option_c, option_d FROM questions")
        rows = cursor.fetchall()
        
        for row in rows:
            questions.append(dict(row))
            
        conn.close()
        return questions
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        # If the front-end gets an empty list, it will handle it
        return []

def check_answer_in_db(question_id: int) -> Optional[Dict[str, str]]:
    """Fetches the correct answer and explanation for a single question."""
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT correct_answer, explanation FROM questions WHERE id = ?", 
            (question_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        else:
            return None
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None

# API Endpoint 1: Get all questions
@app.get("/api/questions")
async def get_questions():
    questions = fetch_questions_from_db()
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found. Did you run main.py?")
    return questions

# API Endpoint 2: Check an answer
@app.get("/api/check_answer/{question_id}/{selected_option}")
async def check_answer(question_id: int, selected_option: str):
    result = check_answer_in_db(question_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Question ID not found.")
        
    is_correct = (selected_option.upper() == result["correct_answer"].upper())
    
    return {
        "is_correct": is_correct,
        "correct_answer": result["correct_answer"],
        "explanation": result["explanation"]
    }

# Main Endpoint: Serve the HTML front-end
@app.get("/")
async def get_index():
    return FileResponse('./Client/index.html')