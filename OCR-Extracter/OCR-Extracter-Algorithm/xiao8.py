from typing import Optional
from pathlib import Path
import re
from typing import Optional, Union


QuestionData = list[Optional[Union[str, bool]]]

class Xiao8_Extracter:
    
    def __init__(self, extracted_content: str) -> None:
        '''
        Args:
            input_path: Enter a folder name. This folder must be located under the `input` folder. This folder contains all the photos, PDFs, and other files that you need to extract using OCR.
        '''
        self.OUTPUT_FOLD_NAME = Path.cwd()
        return
    
    
    def structure_questions(self, text_lines: list[str]) -> list[QuestionData]:
        """
        Parses raw OCR text lines into a structured list of questions.
        1. Combine multiple lines of questions into a single element of a list.
        2. Place options A, B, C, and D into separate list elements.
        
        Return:
            list[QuestionData]
            QuestionData content is ['题目', 'A', 'B', 'C', 'D'].
        """
        # Helper function to clean and store an option in the correct index.
        def store_option(question_list: QuestionData, option_text: str) -> None:
            """Helper function to clean and store an option in the correct index."""
            option_text = option_text.strip()
            # print(f"option text: {option_text}") # debugger code
            if not option_text:
                return
        
            if option_text[0] in option_map:
                option_char: str = option_text[0]
                index: int = option_map[option_char]
                clean_text: str = option_clean_re.sub('', option_text).strip()
                
                # Fixed a bug caused by incorrect question extraction.
                if question_list[index] != None:
                    raise ValueError("Question recognition error")

                if 0 <= index < len(question_list):
                    question_list[index] = clean_text
                    
                return


        # --- 1. Regex Definitions ---
        new_item_re = re.compile(r'^(?:\d+\.|[ABCD]\.)\s*')
        question_stem_re = re.compile(r'^\d+\.\s*')
        multi_option_find_re = re.compile(r'[ABCD]\.\s*')
        multi_option_split_re = re.compile(r'(?=[ABCD]\.\s*)')
        option_clean_re = re.compile(r'^[ABCD]\.\s*')

    
        # --- 2. Pass 1: Merge Continuation Text ---
        merged_lines: list[str] = []
        for line in text_lines:
            # print(f"line: {line}") # debugger cod3
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
        # --- Main Loop for Pass 2 ---
        for line in merged_lines:
            if question_stem_re.search(line):
                # --- MODIFIED: Create QuestionData list ---
                stem_text = question_stem_re.sub('', line).strip()
                
                # # Check for multiple choice keywords
                # is_multi = "multiple selection" in stem_text.lower() or "多选" in stem_text

                current_question_list: QuestionData = [
                    stem_text,  # 0: stem
                    None,       # 1: A
                    None,       # 2: B
                    None,       # 3: C
                    None,       # 4: D
                ]
                all_questions.append(current_question_list)
        
            elif all_questions: # Only process options if a question has been started
                # This line is potentially an option
                active_question_list: QuestionData = all_questions[-1]
                
                # check one line whether include two or more choice
                option_matches = multi_option_find_re.findall(line)
                try:
                    if len(option_matches) >= 2:
                        split_parts: list[str] = multi_option_split_re.split(line)
                        for part in split_parts:
                            store_option(active_question_list, part)
                    elif len(option_matches) == 1 and line.startswith(tuple(option_map.keys())):
                        store_option(active_question_list, line)
                except ValueError as error:
                    print(f"{error}, The error occurred in question {len(all_questions) + 1}.")
                    current_question_list: QuestionData = [
                        'Errrrrrrrrrrrrrrrrrrrrrrrrrrrrror',  # 0: stem
                        None,       # 1: A
                        None,       # 2: B
                        None,       # 3: C
                        None,       # 4: D
                    ]
                    all_questions.append(current_question_list)
                    store_option(all_questions[-1], line)
                
                
        # Log file
        debug_txt_file = self.OUTPUT_FOLD_NAME / 'structed_contents.txt'
        with open(debug_txt_file, '+a', encoding='utf-8') as f:
            for question in all_questions:
                f.write("\n========================================")
                for line in question:
                    content_to_write = '\n' + str(line)
                    f.write(content_to_write)
        
        return all_questions
    


if __name__ == '__main__':
    Q = Xiao8_Extracter('../input/chapter2')