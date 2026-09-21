import glob

for f in glob.glob('scripts/doc_generator/part*.py'):
    with open(f, 'r', encoding='utf-8') as fh:
        content = fh.read()
    if "return '''" in content:
        content = content.replace("return '''", "return r'''")
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(content)
        print(f"Updated {f} with raw string")
