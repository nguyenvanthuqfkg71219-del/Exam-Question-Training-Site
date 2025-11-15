import numpy as np
import pandas as pd
from typing import Optional, Union
from pathlib import Path

QuestionData = list[Optional[Union[str, bool]]]
class Excel_Exector:
    
    
    def __init__(self):
        self.BASE_PATH: Path = Path.cwd()
        return
    
    
    def store_excel(self, question_lists: list[QuestionData]):
        output_file = self.BASE_PATH / 'data.xlsx'

        # Create DataFrame (optional: add column names)
        df = pd.DataFrame(question_lists, columns=['题目', 'A', 'B', 'C', 'D', '多选', '正确答案'])

        # Write to Excel
        df.to_excel(output_file, 
                    sheet_name='Reshaped Data', 
                    index=False) # Excludes the DataFrame's row index (0, 1, 2, 3)

        print(f"\nData successfully written to {output_file} in four columns.")

if __name__ == '__main__':
    TEST_CONTENTS: list[QuestionData] = [
        ['题目1', 'A 1', 'B 2', 'C 3', 'D 4', 'True', 'A'],
        ['题目2', 'A 1', 'B 2', 'C 3', 'D 4', 'True', 'A'],
        ['题目3', 'A 1', 'B 2', 'C 3', 'D 4', 'True', 'A']
    ]
    
    E = Excel_Exector()
    E.store_excel(TEST_CONTENTS)