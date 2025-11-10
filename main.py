from paddleocr import PaddleOCR
import paddle
import re
import json

def ocr_extract(input_img: str, output_file: str):
    '''
    using paddle to fetch image inforamtion
    Args:
        input_img: Storage path of the photos to be extracted
        output_file: The extracted content will be stored in `JSON` format.
    '''
    if paddle.device.is_compiled_with_cuda():
        print("使用GPU加速运行...")
    else:
        print("使用CPU运行...")

    ocr = PaddleOCR(
        lang='ch',          # simple china
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False  # avoid GPU/CPU model conflact
    )

    # 3. running OCR identifaction（keeping predict call）
    result = ocr.predict(input=input_img)

    for res in result:
        res.save_to_json(output_file)
        

def fetch_image_text(json_file: str) -> list[str]:
    import json
    # Use encoding='utf-8' to correctly read the Chinese characters
    with open(json_file, 'r', encoding='utf-8') as f:
        # Use json.load() to parse the file object into a dictionary
        data = json.load(f)
    rec_texts_list = data['rec_texts']
    with open('1.text', '+a', encoding='utf-8') as f:
        content_to_write = '\n'.join(rec_texts_list)
        f.writelines(content_to_write)
    # test code
    # for line in rec_texts_list:
    #     print(line)
    return rec_texts_list


def structure_questions(text_lines):
    """
    Parses raw OCR text lines into a structured list of questions.
    
    1. Merges continuation text.
    2. Structures into [stem, A, B, C, D] lists.
    """
    
    # --- 1. Regex Definitions ---
    
    # For Pass 1: Detects if a line is a NEW item (question or option)
    # Used to know if a line is continuation text or not.
    new_item_re = re.compile(r'^(?:\d+\.|[ABCD]\.)\s*')
    # For Pass 2: Detects a question stem (e.g., "81.")
    question_stem_re = re.compile(r'^\d+\.\s*')
    # For Pass 2: Detects multiple options in one line
    multi_option_find_re = re.compile(r'[ABCD]\.\s*')
    # For Pass 2: Splits a line *before* an option, keeping the option
    multi_option_split_re = re.compile(r'(?=[ABCD]\.\s*)')
    # For Pass 2: Cleans the "A. " prefix from an option
    option_clean_re = re.compile(r'^[ABCD]\.\s*')
    
    # --- 2. Pass 1: Merge Continuation Text ---
    
    merged_lines = []
    for line in text_lines:
        line = line.strip()
        if not line:
            continue
        
        # If the line starts with a number or option, it's a new item.
        # OR, if it's the very first line, it's also a "new" item.
        if new_item_re.search(line) or not merged_lines:
            merged_lines.append(line)
        else:
            # This is continuation text. Append it to the *previous* line.
            merged_lines[-1] += "" + line

    # --- 3. Pass 2: Structure into Question Lists ---
    
    all_questions = []
    current_question_list:list[None | str] = [None] * 5
    
    # Helper map to know where to store options
    # A -> index 1, B -> index 2, etc.
    option_map = {'A': 1, 'B': 2, 'C': 3, 'D': 4}

    def store_option(question_list, option_text):
        """Helper function to clean and store an option in the correct index."""
        option_text = option_text.strip()
        if not option_text:
            return
        
        # Get the option character (e.g., 'A')
        option_char = option_text[0]
        
        if option_char in option_map:
            index = option_map[option_char]
            # Clean the "A. " part from the text
            clean_text = option_clean_re.sub('', option_text).strip()
            question_list[index] = clean_text

    # --- Main Loop for Pass 2 ---
    for line in merged_lines:
        
        # Check if this line is a new question stem
        if question_stem_re.search(line):
            # Create a new list for this question, pre-filled with None
            current_question_list:list[None | str] = [None] * 5  # [stem, A, B, C, D]
            
            # Store the stem (at index 0) after removing the "81. "
            current_question_list[0] = question_stem_re.sub('', line).strip()
            
            # Add our new question list to the final list
            all_questions.append(current_question_list)
        
        # If it's not a new question, check if it's an option.
        # We MUST have a question active (current_question_list is not None)
        elif current_question_list is not None:
            
            option_matches = multi_option_find_re.findall(line)
            
            if len(option_matches) >= 2:
                # Rule 3: Line has multiple options (e.g., "A. ... B. ...")
                # Split *before* each option (using the lookahead)
                split_parts = multi_option_split_re.split(line)
                for part in split_parts:
                    store_option(current_question_list, part)
            elif len(option_matches) == 1:
                # Rule 2: Line is a single option (e.g., "A. ...")
                store_option(current_question_list, line)
                
            # If it's not a stem and not an option, it's an 
            # orphaned line we ignore (since it should have been merged in Pass 1).
            # This also safely ignores the "C." and "D." lines at the very
            # beginning of your example, as they appear before a question stem.
            
    return all_questions


if __name__ == '__main__':
    # 1. get text inforamtion from image, and
    ocr_extract('1.jpg', 'output/2_res.json')
    
    # # 2. Load the Json data
    rec_texts_list = fetch_image_text('output/1_res.json')

    # # 3. structre questions
    structured_data = structure_questions(rec_texts_list)

    # # 3. Print the results for verification
    print(f"--- Found {len(structured_data)} questions ---")
    for i, question in enumerate(structured_data):
        print(f"\n--- Question {i+1} ---")
        print(f"{question[0]}")
        print(f"A: {question[1]}")
        print(f"B: {question[2]}")
        print(f"C: {question[3]}")
        print(f"D: {question[4]}")