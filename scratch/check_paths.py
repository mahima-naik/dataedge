from pathlib import Path
import os

REPO_ROOT = Path("/Users/surya/Downloads/VernikaAI Max profit")
FRONTEND_DIR = REPO_ROOT / "frontend"
static_dir = FRONTEND_DIR / "static"

print(f"FRONTEND_DIR: {FRONTEND_DIR} (exists: {FRONTEND_DIR.exists()})")
print(f"static_dir: {static_dir} (exists: {static_dir.exists()})")

css_file = static_dir / "css" / "styles.css"
print(f"css_file: {css_file} (exists: {css_file.exists()})")

templates_dir = FRONTEND_DIR / "templates"
print(f"templates_dir: {templates_dir} (exists: {templates_dir.exists()})")

login_template = templates_dir / "login.html"
print(f"login_template: {login_template} (exists: {login_template.exists()})")
