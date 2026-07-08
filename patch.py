import re

auth_file = "backend/core/auth.py"
with open(auth_file, "r") as f:
    auth_content = f.read()
auth_content = auth_content.replace('_CONSOLE_SWITCHABLE_ROLES = frozenset({"buyers", "sellers", "rfqs"})', '_CONSOLE_SWITCHABLE_ROLES = frozenset({"buyers", "sellers", "rfqs", "real_estate", "factory"})')
auth_content = auth_content.replace('_CONSOLE_LOCKED_ROLES = frozenset({"data_edge", "real_estate", "vernikaai", "admin", "factory"})', '_CONSOLE_LOCKED_ROLES = frozenset({"data_edge", "vernikaai", "admin"})')
with open(auth_file, "w") as f:
    f.write(auth_content)

api_utils_file = "frontend/static/js/api_utils.js"
with open(api_utils_file, "r") as f:
    api_utils_content = f.read()
api_utils_content = api_utils_content.replace("const CONSOLE_SWITCHABLE_ROLES = ['buyers', 'sellers', 'rfqs'];", "const CONSOLE_SWITCHABLE_ROLES = ['buyers', 'sellers', 'rfqs', 'real_estate', 'factory'];")
api_utils_content = api_utils_content.replace("const LOCKED_CONSOLE_ROLES = ['data_edge', 'real_estate', 'vernikaai', 'admin', 'factory'];", "const LOCKED_CONSOLE_ROLES = ['data_edge', 'vernikaai', 'admin'];")
with open(api_utils_file, "w") as f:
    f.write(api_utils_content)

app_file = "frontend/static/js/app.js"
with open(app_file, "r") as f:
    app_content = f.read()
app_content = app_content.replace("rfqs: 'RFQ',", "rfqs: 'RFQ',\n            real_estate: 'Real Estate',\n            factory: 'Factory',")
with open(app_file, "w") as f:
    f.write(app_content)

console_file = "frontend/templates/console.html"
with open(console_file, "r") as f:
    console_content = f.read()
console_content = console_content.replace("grid-template-columns: 1fr 1fr 1fr;", "grid-template-columns: repeat(5, 1fr);")
console_content = console_content.replace("""<button type="button" class="role-switch-btn" data-role="rfqs" onclick="switchRole('rfqs')">RFQ</button>""", """<button type="button" class="role-switch-btn" data-role="rfqs" onclick="switchRole('rfqs')">RFQ</button>\n                    <button type="button" class="role-switch-btn" data-role="real_estate" onclick="switchRole('real_estate')">Real Est</button>\n                    <button type="button" class="role-switch-btn" data-role="factory" onclick="switchRole('factory')">Factory</button>""")
with open(console_file, "w") as f:
    f.write(console_content)

print("Patch applied successfully.")
