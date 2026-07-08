import sys
from numbers_parser import Document

doc = Document("/Users/surya/Downloads/50k doctors 7-Nov-25 (1).numbers")
sheets = doc.sheets
tables = sheets[0].tables
data = tables[0].rows()

bangalore_count = 0
hyderabad_count = 0

for row in data:
    row_values = [str(cell.value).lower() if cell and cell.value else "" for cell in row]
    row_str = " ".join(row_values)
    if "bangalore" in row_str or "bengaluru" in row_str:
        bangalore_count += 1
    if "hyderabad" in row_str or "hyd" in row_str:
        hyderabad_count += 1

print(f"Bangalore/Bengaluru: {bangalore_count}")
print(f"Hyderabad/Hyd: {hyderabad_count}")
