# Streamlit Cloud / HuggingFace Spaces entry point
# Redirects to the actual demo app in review/demo_app.py
import runpy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
runpy.run_path(str(Path(__file__).parent / "review" / "demo_app.py"), run_name="__main__")
