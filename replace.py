import sys
import os

app_py_path = r"e:\AI MICROP\KisanMitra(telegram v)\kisanmitra_pro\dashboard\app.py"

with open(app_py_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

print("Line 196:", repr(lines[196][:50]))
print("Line 381:", repr(lines[381][:50]))

assert lines[196].startswith('LOGIN_HTML')
assert lines[381].startswith('</html>"""')

replacement = """import os\nLOGIN_HTML = open(os.path.join(os.path.dirname(__file__), 'login_template.html'), 'r', encoding='utf-8').read()\n"""

new_lines = lines[:196] + [replacement] + lines[382:]

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Replaced LOGIN_HTML successfully!")
