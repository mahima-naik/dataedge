import re

with open('frontend/console.html', 'r') as f:
    html = f.read()

# Extract the script section
script_match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
if not script_match:
    print("Could not find script block")
    exit(1)

js_content = script_match.group(1)

missing_functions = [
    'executeWipe', 'downloadFilteredCSV', 'reanalyzeCall', 'saveTuning',
    'submitCaseModal', 'stopLiveTest', 'recordGreeting', 'confirmRecordGreeting',
    'addSchedule', 'clearScheduleStop', 'loadTuning'
]

output_js = "// --- Restored Missing Functions ---\n\n"

for func in missing_functions:
    # Find the function definition
    # Need to match standard, async, and exported functions. 
    # Example: async function executeWipe() { ... }
    
    # We will search for 'function <func>'
    # We will track braces to extract the full body.
    
    match = re.search(rf'(async\s+)?function\s+{func}\s*\(.*?\)\s*{{', js_content)
    if not match:
        print(f"Could not find function {func}")
        continue
        
    start_idx = match.start()
    
    # Track braces to find the end
    brace_count = 0
    in_string = False
    string_char = ''
    in_escape = False
    end_idx = -1
    
    # Start looking from the opening brace
    brace_start = match.end() - 1
    
    for i in range(brace_start, len(js_content)):
        char = js_content[i]
        
        if in_escape:
            in_escape = False
            continue
            
        if char == '\\':
            in_escape = True
            continue
            
        if in_string:
            if char == string_char:
                in_string = False
            continue
            
        if char in ('"', "'", '`'):
            in_string = True
            string_char = char
            continue
            
        if char == '{':
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = i + 1
                break
                
    if end_idx != -1:
        extracted = js_content[start_idx:end_idx]
        output_js += extracted + "\n\n"
        print(f"Extracted {func}")
    else:
        print(f"Could not parse braces for {func}")

with open('frontend/static/js/restored.js', 'w') as f:
    f.write(output_js)

print("restored.js created.")
