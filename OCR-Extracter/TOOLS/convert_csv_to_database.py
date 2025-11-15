import sqlite3
import os
from typing import Optional, Union
from pathlib import Path

QuestionData = list[Optional[Union[str, bool]]]

def create_database(db_file: str | Path) -> None:
    """
    Creates an empty SQLite database with the 'questions' table.
    The schema matches the QuestionData list.
    """
    try:
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS questions")
        
        # This schema maps directly to the a list
        cursor.execute('''
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_stem TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            is_multiple_choice BOOLEAN NOT NULL DEFAULT 0,
        )
        ''')
        
        conn.commit()
        conn.close()
        print(f"Successfully created/reset database: '{db_file}'")
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        
        
def save_questions_to_db(db_file: str | Path, questions: list[QuestionData]) -> None:
    """
    Saves the list of structured (8-item) questions to the SQLite database.
    """
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        for q_list in questions:
            # --- MODIFIED: q_list is now the 8-item list ---
            if len(q_list) != 8:
                print(f"Warning: Skipping malformed question data: {q_list}")
                continue
            
            data_to_insert = tuple(q_list)
            
            # The 8 '?' placeholders match the 8 items in QuestionData
            cursor.execute('''
            INSERT INTO questions (
                question_stem, option_a, option_b, option_c, option_d,
                is_multiple_choice, correct_answer, explanation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', data_to_insert)
        
        conn.commit()
        conn.close()
        print(f"Successfully saved {len(questions)} questions to '{db_file}'")
    except sqlite3.Error as e:
        print(f"Database error while inserting: {e}")


if __name__ == "__main__":
    CHAPTER_FOLDERS: list[str] = ['chapter2']
    
    for chapter in CHAPTER_FOLDERS:
        DB_OUTPUT_FOLDER: Path = Path.cwd().parent.parent / 'database'
        all_structured_data_for_chapter: list[QuestionData] = []
        db_file: Path = DB_OUTPUT_FOLDER / f'{chapter}.db'