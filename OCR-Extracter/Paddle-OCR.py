from pathlib import Path
from typing import Optional, Union
import numpy as np
import pandas as pd
import re
import os
import json

# coutomer struct data
QuestionData = list[Optional[Union[str, bool]]]

class PaddleOCR_Extracter:
    def __init__(self) -> None:
        self.BASE_PATH: Path = Path.cwd()
        self.TEMP_FILE_PATH = self.BASE_PATH.parent / 'tmpfile'
        return None
    
    def test_path(self):
        print(self.BASE_PATH, self.TEMP_FILE_PATH)
        if self.TEMP_FILE_PATH.is_dir():
            print('YES')
    
    def _extract_image_to_json(self, img_path: str, json_path: str) -> None:
        '''
        Using paddle to fetch image content and stored it to a json file.
        Args:
            img_path: Storage path of the photos to be extracted.
            json_path: The extracted content will be stored in `JSON` format.
        '''
        
        #Recommended to import necessary dependency packages in this function 
        # instead of at the beginning of the file 
        # to avoid frequent loading of data packages during instance creation. 
        # Also, avoid loading Paddle OCR when it is not needed, 
        # and avoiding wasting resources.
        import paddle
        from paddleocr import PaddleOCR
        
        # Check out your cuda compiled
        if paddle.device.is_compiled_with_cuda():
            print(f"Using GPU for acceleration... (Image: {img_path})")
        else:
            print(f"Using CPU... (Image: {img_path})")

        # Initialize OCR
        ocr = PaddleOCR(
            lang='ch',
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False 
        )

        # Run OCR identification
        result = ocr.predict(input=img_path)

        # --- REVERTED TO USER'S PREFERENCE ---
        # Save the result using the .save_to_json() method
        if result:
            # Ensure output directory exists before saving
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            for res in result:
                # This will save the result of the first page (or only page)
                # and overwrite if multiple pages are in the result.
                # Assuming one page per image.
                res.save_to_json(json_path)
        else:
            print(f"No OCR result for image: {img_path}")
    
    
    def extract_contents(self, json_file, deugger_model: bool = False) -> list[str]:
        '''Reads the OCR JSON output and returns a list of text lines that include all total content.'''
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            rec_texts_list: list[str] = data['rec_texts']
        
            # Optional: Save raw text for debugging
            if deugger_model == True:
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
        
    
    def _structure_questions(self, text_lines: list[str]) -> list[QuestionData]:
        """
        Parses raw OCR text lines into a structured list of questions.
        1. Combine multiple lines of questions into a single element of a list.
        2. Place options A, B, C, and D into separate list elements.
        
        Returns:
            list[QuestionData]
            QuestionData content is ['题目', 'A', 'B', 'C', 'D', '多选', '正确答案'].
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
            
if __name__ == '__main__':
    print("start running...")
    P = PaddleOCR_Extracter()
    output_excel = 'data.xlsx'
    excel_lines = P._structure_questions(P.extract_contents('../output/1_res.json'))
    df = pd.DataFrame(excel_lines)
    output_file = 'data.xlsx'
    # Create DataFrame (optional: add column names)
    df = pd.DataFrame(excel_lines, columns=['题目', 'A', 'B', 'C', 'D', '多选', '正确答案'])
    # Write to Excel
    df.to_excel(output_file, 
                sheet_name='Reshaped Data', 
                index=False) # Excludes the DataFrame's row index (0, 1, 2, 3)
    print(f"\nData successfully written to {output_file} in four columns.")