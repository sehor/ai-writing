import os
import re

def main():
    with open('src/App.vue', 'r', encoding='utf-8') as f:
        content = f.read()

    template = re.search(r'<template>\n(.*)\n</template>', content, re.DOTALL).group(1)

    blocks = {}
    
    # Extract sidebar
    blocks['Sidebar'] = re.search(r'(<aside class="sidebar">.*?</aside>)', template, re.DOTALL).group(1)
    
    # Split by section v-if
    parts = re.split(r'<section v-if="activeSection === \'([a-z]+)\'"', template)
    
    # parts[0] is everything before the first section v-if (sidebar, workspace, topbar)
    # parts[1] is 'snowflake'
    # parts[2] is the content of 'snowflake' (which includes class="create-project" ...)
    # Wait, there are TWO snowflake sections!
    
    # Let's just use string split to find the exact boundaries
    canon_start = template.find('<section v-if="activeSection === \'canon\'"')
    memory_start = template.find('<section v-if="activeSection === \'memory\'"')
    graph_start = template.find('<section v-if="activeSection === \'graph\'"')
    manuscript_start = template.find('<section v-if="activeSection === \'manuscript\'"')
    
    # snowflake is from the first <section v-if="activeSection === 'snowflake'" to canon_start
    snowflake_start = template.find('<section\n        v-if="activeSection === \'snowflake\'"')
    if snowflake_start == -1:
        snowflake_start = template.find('<section v-if="activeSection === \'snowflake\'"')
        
    blocks['SnowflakeWorkspace'] = template[snowflake_start:canon_start].strip()
    blocks['CanonWorkspace'] = template[canon_start:memory_start].strip()
    blocks['MemoryWorkspace'] = template[memory_start:graph_start].strip()
    blocks['GraphWorkspace'] = template[graph_start:manuscript_start].strip()
    
    manuscript_code = template[manuscript_start:]
    blocks['ManuscriptWorkspace'] = manuscript_code.rsplit('</main>', 1)[0].strip()

    with open('src/stores/workspace.ts', 'r', encoding='utf-8') as f:
        store_content = f.read()
        
    return_idx = store_content.rfind('return {\n')
    returns_block = store_content[return_idx:]
    returns_match = re.search(r'return \{\n(.*)\n  \}', returns_block, re.DOTALL)
    exports = [x.strip().strip(',') for x in returns_match.group(1).split('\n')]
    
    refs = [e for e in exports if e and f'const {e} ' in store_content]
    funcs = [e for e in exports if e and e not in refs]

    os.makedirs('src/components', exist_ok=True)
    for name, block_content in blocks.items():
        used_refs = [r for r in refs if re.search(r'\b' + r + r'\b', block_content)]
        used_funcs = [f for f in funcs if re.search(r'\b' + f + r'\b', block_content)]
        
        script = '<script setup lang="ts">\n'
        if used_refs:
            script += 'import { storeToRefs } from \'pinia\'\n'
        script += 'import { useWorkspaceStore } from \'../stores/workspace\'\n\n'
        script += 'const store = useWorkspaceStore()\n'
        if used_refs:
            script += 'const {\n  ' + ',\n  '.join(used_refs) + '\n} = storeToRefs(store)\n'
        if used_funcs:
            script += 'const {\n  ' + ',\n  '.join(used_funcs) + '\n} = store\n'
        script += '</script>\n\n<template>\n'
        
        # Remove v-if activeSection from the root elements
        clean_content = re.sub(r'\s*v-if="activeSection === \'[a-z]+\'"', '', block_content)
        script += clean_content + '\n</template>\n'
        
        with open(f'src/components/{name}.vue', 'w', encoding='utf-8') as f:
            f.write(script)
            
    print('Generated components:', list(blocks.keys()))

if __name__ == '__main__':
    main()
