import os
import re

def main():
    with open('src/App.vue', 'r', encoding='utf-8') as f:
        content = f.read()

    import_type = re.search(r'import type \{[\s\S]*?\} from "\./types"', content)
    script_end = content.find('</script>')
    start_logic = import_type.end()
    
    logic_code = content[start_logic:script_end].strip()

    os.makedirs('src/stores', exist_ok=True)
    with open('src/stores/workspace.ts', 'w', encoding='utf-8') as f:
        f.write("import { defineStore } from 'pinia'\n")
        f.write("import { computed, ref, watch } from 'vue'\n")
        f.write(import_type.group(0) + '\n\n')
        f.write("export const useWorkspaceStore = defineStore('workspace', () => {\n")
        
        indented = '\n'.join('  ' + line for line in logic_code.split('\n'))
        
        var_names = re.findall(r'^  const (\w+) =', indented, re.MULTILINE)
        func_names = re.findall(r'^  async function (\w+)\(|^  function (\w+)\(', indented, re.MULTILINE)
        func_names = [f[0] or f[1] for f in func_names]
        
        returns = var_names + func_names + ['loadInitialData']
        
        # carefully replace onMounted block
        # onMounted(async () => {
        #   ...
        # })
        # We will use regex to find the onMounted block and replace it
        pattern = re.compile(r'^  onMounted\(async \(\) => \{\n(.*?)\n  \}\)', re.MULTILINE | re.DOTALL)
        
        def replacer(match):
            return "  async function loadInitialData() {\n" + match.group(1) + "\n  }"
            
        indented = pattern.sub(replacer, indented)
        
        f.write(indented)
        f.write('\n\n  return {\n    ' + ',\n    '.join(returns) + '\n  }\n')
        f.write('})\n')
        
    print("Generated workspace.ts")

if __name__ == '__main__':
    main()
