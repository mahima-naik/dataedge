import re

with open('backend/core/state.py', 'r') as f:
    content = f.read()

func = """
from pathlib import Path

def _get_role_path(role: str, subpath: str = None) -> Path:
    from config import settings
    # Assuming standard data directory layout
    base_dir = Path("data") / role
    if subpath:
        base_dir = base_dir / subpath
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir
"""

if "_get_role_path" not in content:
    with open('backend/core/state.py', 'a') as f:
        f.write(func)

