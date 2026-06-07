import os
import re

def main():
    with open('src/App.vue', 'r', encoding='utf-8') as f:
        content = f.read()

    template_match = re.search(r'<template>\n(.*)\n</template>', content, re.DOTALL)
    if not template_match:
        print("Template not found")
        return
        
    template = template_match.group(1)
    
    lines = template.split('\n')
    for i, line in enumerate(lines):
        if '<aside' in line or '</aside>' in line or '<main' in line or '</main>' in line or 'v-if="activeSection' in line:
            print(f'{i}: {line.strip()}')

if __name__ == '__main__':
    main()
