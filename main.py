import paddle
import re
import json
import sqlite3
import os  # Added for file/directory operations
from paddleocr import PaddleOCR
from typing import Optional, Union

# --- NEW TYPE ALIAS ---
# This list will hold:
# [0] stem (str)
# [1] option_a (Optional[str])
# [2] option_b (Optional[str])
# [3] option_c (Optional[str])
# [4] option_d (Optional[str])
# [5] is_multiple_choice (bool)
# [6] correct_answer (Optional[str])
# [7] explanation (Optional[str])
QuestionData = list[Optional[Union[str, bool]]]


def ocr_extract(input_img: str, output_file: str) -> None:
    '''
    Using paddle to fetch image information.
    Args:
        input_img: Storage path of the photos to be extracted.
        output_file: The extracted content will be stored in `JSON` format.
    '''
    if paddle.device.is_compiled_with_cuda():
        print(f"Using GPU for acceleration... (Image: {input_img})")
    else:
        print(f"Using CPU... (Image: {input_img})")

    # Initialize OCR
    ocr = PaddleOCR(
        lang='ch',
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False 
    )

    # Run OCR identification
    result = ocr.predict(input=input_img)

    # --- REVERTED TO USER'S PREFERENCE ---
    # Save the result using the .save_to_json() method
    if result:
        # Ensure output directory exists before saving
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        for res in result:
            # This will save the result of the first page (or only page)
            # and overwrite if multiple pages are in the result.
            # Assuming one page per image.
            res.save_to_json(output_file)
    else:
        print(f"No OCR result for image: {input_img}")


def fetch_image_text(json_file: str) -> list[str]:
    '''Reads the OCR JSON output and returns a list of text lines.'''
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # This assumes the .save_to_json() format is the same as the
        # raw predict() dictionary structure we've seen.
        rec_texts_list: list[str] = data['rec_texts']
        
        # Optional: Save raw text for debugging
        debug_txt_file = os.path.join(os.path.dirname(json_file), f"{os.path.basename(json_file)}.txt")
        with open(debug_txt_file, 'w', encoding='utf-8') as f:
            content_to_write = '\n'.join(rec_texts_list)
            f.write(content_to_write)
            
        return rec_texts_list
        
    except FileNotFoundError:
        print(f"Error: JSON file not found at {json_file}")
        return []
    except KeyError:
        print(f"Error: 'rec_texts' key not found in {json_file}. The JSON structure might be different.")
        return []


def structure_questions(text_lines: list[str]) -> list[QuestionData]:
    """
    Parses raw OCR text lines into a structured list of questions.
    1. Merges continuation text.
    2. Structures into an 8-item list per your new format.
    
    Returns:
        list[QuestionData]
    """
    
    # --- 1. Regex Definitions ---
    new_item_re = re.compile(r'^(?:\d+\.|[ABCD]\.)\s*')
    question_stem_re = re.compile(r'^\d+\.\s*')
    multi_option_find_re = re.compile(r'[ABCD]\.\s*')
    multi_option_split_re = re.compile(r'(?=[ABCD]\.\s*)')
    option_clean_re = re.compile(r'^[ABCD]\.\s*')
    
    # --- 2. Pass 1: Merge Continuation Text ---
    merged_lines: list[str] = []
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        
        if new_item_re.search(line) or not merged_lines:
            merged_lines.append(line)
        else:
            merged_lines[-1] += "" + line

    # --- 3. Pass 2: Structure into Question lists ---
    all_questions: list[QuestionData] = []
    
    option_map: dict[str, int] = {'A': 1, 'B': 2, 'C': 3, 'D': 4}

    def store_option(question_list: QuestionData, option_text: str) -> None:
        """Helper function to clean and store an option in the correct index."""
        option_text = option_text.strip()
        if not option_text:
            return
        
        if option_text[0] in option_map:
            option_char: str = option_text[0]
            index: int = option_map[option_char]
            clean_text: str = option_clean_re.sub('', option_text).strip()
            
            if 0 <= index < len(question_list):
                question_list[index] = clean_text

    # --- Main Loop for Pass 2 ---
    for line in merged_lines:
        if question_stem_re.search(line):
            # --- MODIFIED: Create 8-item list ---
            stem_text = question_stem_re.sub('', line).strip()
            # Check for multiple choice keywords
            is_multi = "multiple selection" in stem_text.lower() or "多选" in stem_text

            current_question_list: QuestionData = [
                stem_text,  # 0: stem
                None,       # 1: A
                None,       # 2: B
                None,       # 3: C
                None,       # 4: D
                is_multi,   # 5: is_multiple_choice
                'A',        # 6: correct_answer (placeholder)
                'This is a placeholder explanation.' # 7: explanation (placeholder)
            ]
            all_questions.append(current_question_list)
        
        elif all_questions: # Only process options if a question has been started
            # This line is potentially an option
            active_question_list: QuestionData = all_questions[-1] # Get the 8-item list
            
            option_matches = multi_option_find_re.findall(line)
            
            if len(option_matches) >= 2:
                split_parts: list[str] = multi_option_split_re.split(line)
                for part in split_parts:
                    store_option(active_question_list, part)
            elif len(option_matches) == 1 and line.startswith(tuple(option_map.keys())):
                store_option(active_question_list, line)
            
    return all_questions


def create_database(db_file: str) -> None:
    """
    Creates an empty SQLite database with the 'questions' table.
    The schema matches the 8-item QuestionData list.
    """
    try:
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS questions")
        
        # This schema maps directly to the 8-item list
        cursor.execute('''
        CREATE TABLE questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_stem TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            is_multiple_choice BOOLEAN NOT NULL DEFAULT 0,
            correct_answer TEXT,
            explanation TEXT
        )
        ''')
        
        conn.commit()
        conn.close()
        print(f"Successfully created/reset database: '{db_file}'")
    except sqlite3.Error as e:
        print(f"Database error: {e}")


def save_questions_to_db(db_file: str, questions: list[QuestionData]) -> None:
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


if __name__ == '__main__':
    
    # --- Configuration ---
    CHAPTER_FOLDERS: list[str] = ['chapter1', 'chapter2']
    IMAGE_BASE_FOLDER: str = 'input_images'
    JSON_OUTPUT_FOLDER: str = 'output'
    DB_OUTPUT_FOLDER: str = 'database'
    
    os.makedirs(JSON_OUTPUT_FOLDER, exist_ok=True)
    os.makedirs(DB_OUTPUT_FOLDER, exist_ok=True)

    # --- Main Processing Loop ---
    for chapter in CHAPTER_FOLDERS:
        print(f"\n--- Processing Chapter: {chapter} ---")
        
        image_folder: str = os.path.join(IMAGE_BASE_FOLDER, chapter)
        db_file: str = os.path.join(DB_OUTPUT_FOLDER, f"{chapter}.db")
        
        if not os.path.isdir(image_folder):
            print(f"Warning: Folder not found, skipping: {image_folder}")
            continue
            
        all_structured_data_for_chapter: list[QuestionData] = []
        
        image_files: list[str] = [
            f for f in os.listdir(image_folder) 
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ]
        
        print(f"Found {len(image_files)} images in {image_folder}")
        
        for image_name in image_files:
            image_path: str = os.path.join(image_folder, image_name)
            json_file_name: str = f"{chapter}_{os.path.splitext(image_name)[0]}.json"
            json_output_file: str = os.path.join(JSON_OUTPUT_FOLDER, json_file_name)
            
            # 1. Run OCR
            ocr_extract(image_path, json_output_file)
            
            # 2. Load the JSON data
            rec_texts_list = fetch_image_text(json_output_file)
            
            if not rec_texts_list:
                print(f"  -> No text found in {json_output_file}. Skipping.")
                continue
            
            # 3. Structure questions
            structured_data = structure_questions(rec_texts_list)
            
            print(f"  -> Extracted {len(structured_data)} questions from {image_name}")
            all_structured_data_for_chapter.extend(structured_data)

        if not all_structured_data_for_chapter:
            print(f"No questions extracted for chapter {chapter}. Skipping database creation.")
            continue
            
        # 4. Create the database (this will reset it)
        print(f"\nCreating database for {chapter}...")
        create_database(db_file)
        
        # 5. Save all extracted questions to the DB
        print(f"Saving {len(all_structured_data_for_chapter)} total questions to {db_file}...")
        save_questions_to_db(db_file, all_structured_data_for_chapter)

    print(f"\n--- Batch Process Complete ---")
    print(f"Databases are located in the '{DB_OUTPUT_FOLDER}' folder.")