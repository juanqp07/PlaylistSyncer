import unicodedata
import re
from pathlib import Path

import os

# Constants
# Determine path based on location to avoid CWD ambiguity
_utils_dir = Path(__file__).resolve().parent

# Logic:
# Check if we are in Docker environment (standard path /app exists)
# Check if we are in Docker environment
# We check for .dockerenv OR common app paths
if Path("/app/.dockerenv").exists() or Path("/app/app.py").exists() or Path("/app/backend/app.py").exists():
    DEFAULT_OUTPUT_DIR = Path("/app/downloads")
else:
    # Use relative for local dev
    # Determine path based on location to avoid CWD ambiguity
    _utils_dir = Path(__file__).resolve().parent
    if _utils_dir.name == "app": 
        ROOT_DIR = _utils_dir
    elif _utils_dir.name == "backend": 
        ROOT_DIR = _utils_dir.parent
    else:
        ROOT_DIR = Path(os.getcwd())
        
    DEFAULT_OUTPUT_DIR = ROOT_DIR / "downloads"

def get_safe_filename(input_str: str) -> str:
    """
    Sanitizes a string to be used as a filename.
    1. Normalizes Unicode (NFD)
    2. Removes accents
    3. Manually replaces special chars (Ø->O, ß->ss, etc.)
    4. Allows only Alphanumeric + ' ', '-', '_'
    5. Strips whitespace
    """
    if not input_str:
        return "Unknown"

    # Normalize unicode characters to their base form (NFD)
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    # Filter out non-spacing mark characters (accents)
    ascii_str = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    
    # Manual replacements for edge cases NFD doesn't cover
    replacements = {
        'Ø': 'O', 'ø': 'o',
        'Æ': 'AE', 'æ': 'ae',
        'Œ': 'OE', 'œ': 'oe',
        'ß': 'ss',
        'Ð': 'D', 'ð': 'd',
        'Þ': 'TH', 'þ': 'th',
        'Ł': 'L', 'ł': 'l'
    }
    for char, repl in replacements.items():
        ascii_str = ascii_str.replace(char, repl)
        
    # Filter: Allow Alphanumeric + safe chars (space, dash, underscore)
    # Note: 'core.py' sanitize had different rules for *files* vs *folders*. 
    # For Folders (playlists), we want strict ASCII.
    # For Files (songs), generally same.
    safe_str = "".join(c for c in ascii_str if c.isalnum() or c in (' ', '-', '_')).strip()
    
    # Clean up double spaces
    safe_str = re.sub(r'\s+', ' ', safe_str).strip()
    
    if not safe_str:
        return "Unknown_Name"
        
    return safe_str
