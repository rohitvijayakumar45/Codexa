import ast
import os
import json

def extract_from_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None
    
    try:
        tree = ast.parse(content)
    except Exception:
        return None

    results = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            class_info = {
                'type': 'class',
                'name': node.name,
                'docstring': ast.get_docstring(node),
                'methods': []
            }
            for child in node.body:
                if isinstance(child, ast.FunctionDef):
                    class_info['methods'].append({
                        'name': child.name,
                        'docstring': ast.get_docstring(child)
                    })
            results.append(class_info)
        elif isinstance(node, ast.FunctionDef):
            results.append({
                'type': 'function',
                'name': node.name,
                'docstring': ast.get_docstring(node)
            })
    return results

def main():
    root = r"C:\Users\rohit\OneDrive\Documents\Codexa\backend"
    architecture = {}
    for dirpath, dirnames, filenames in os.walk(root):
        if "__pycache__" in dirpath: continue
        rel_path = os.path.relpath(dirpath, root)
        for f in filenames:
            if f.endswith('.py'):
                filepath = os.path.join(dirpath, f)
                info = extract_from_file(filepath)
                if info:
                    key = os.path.join(rel_path, f)
                    architecture[key] = info
                    
    with open('arch_extract.json', 'w', encoding='utf-8') as f:
        json.dump(architecture, f, indent=2)

if __name__ == "__main__":
    main()
