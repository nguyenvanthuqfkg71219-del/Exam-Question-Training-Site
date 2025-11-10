import sqlite3
import os  # Import os to securely build file paths
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from typing import List, Dict, Any, Optional

# Type alias for our structured question
Question = Dict[str, Any]

app = FastAPI()

def fetch_questions_from_db(db_file: str) -> List[Question]:
    """Fetches all questions and formats them as dictionaries."""
    questions = []
    try:
        conn = sqlite3.connect(db_file)
        # .row_factory makes the cursor return dictionaries instead of tuples
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()
        
        # Select the new 'is_multiple_choice' column
        cursor.execute("SELECT id, question_stem, option_a, option_b, option_c, option_d, is_multiple_choice FROM questions")
        rows = cursor.fetchall()
        
        for row in rows:
            questions.append(dict(row))
            
        conn.close()
        return questions
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

def check_answer_in_db(db_file: str, question_id: int) -> Optional[Dict[str, str]]:
    """Fetches the correct answer and explanation for a single question."""
    try:
        conn = sqlite3.connect(db_file)
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
@app.get("/api/questions/{chapter}")
async def get_questions(chapter: str):
    # This path is correct relative to where server.py is run
    db_file = os.path.join('database', f"{chapter}.db")
    
    if not os.path.exists(db_file):
        raise HTTPException(status_code=404, detail="Database file not found for this chapter.")
        
    questions = fetch_questions_from_db(db_file)
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found. Did you run main.py?")
    return questions

# API Endpoint 2: Check an answer
@app.get("/api/check_answer/{chapter}/{question_id}/{selected_option}")
async def check_answer(chapter: str, question_id: int, selected_option: str):
    db_file = os.path.join('database', f"{chapter}.db")

    if not os.path.exists(db_file):
        raise HTTPException(status_code=404, detail="Database file not found for this chapter.")

    result = check_answer_in_db(db_file, question_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Question ID not found.")
    
    # Handle single and multiple-choice answers
    user_parts = sorted(selected_option.upper().split(','))
    correct_parts = sorted(result["correct_answer"].upper().split(','))

    is_correct = (user_parts == correct_parts)
    
    return {
        "is_correct": is_correct,
        "correct_answer": result["correct_answer"],
        "explanation": result["explanation"]
    }

# --- THIS IS THE ONLY CHANGE ---
# Main Endpoint: Serve the HTML front-end from the 'Client' folder
@app.get("/")
async def get_index():
    html_file_path = os.path.join('Client', 'index.html')
    if not os.path.exists(html_file_path):
        raise HTTPException(status_code=404, detail="index.html not found in Client folder.")
    return FileResponse(html_file_path)