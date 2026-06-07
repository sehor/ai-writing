import os
import re

def main():
    app_vue_path = 'src/App.vue'
    types_dir = 'src/types'
    types_file = 'src/types/index.ts'
    
    with open(app_vue_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    end_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('type ActiveSection = '):
            end_idx = i + 1
            break
            
    # lines[3:end_idx] contain the types
    types_lines = lines[3:end_idx]
    
    type_names = []
    for i, line in enumerate(types_lines):
        if line.startswith('type '):
            types_lines[i] = 'export ' + line
            name = line.split(' ')[1]
            type_names.append(name)
            
    os.makedirs(types_dir, exist_ok=True)
    with open(types_file, 'w', encoding='utf-8') as f:
        f.writelines(types_lines)
        
    import_stmt = 'import type {\n  ' + ',\n  '.join(type_names) + '\n} from "./types"\n'
    new_app_lines = lines[:3] + [import_stmt] + lines[end_idx:]
    
    with open(app_vue_path, 'w', encoding='utf-8') as f:
        f.writelines(new_app_lines)
        
    print(f"Extracted {len(type_names)} types to {types_file}")
    
if __name__ == '__main__':
    main()
