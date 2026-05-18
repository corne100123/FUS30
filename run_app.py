import streamlit.web.cli as stcli
import os, sys, webbrowser
from threading import Timer

def resolve_path(path):
    """Helper to find files relative to the executable or script."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, path)

def open_browser():
    """Opens the local browser once the server starts."""
    webbrowser.open_new("http://127.0.0.1:8501")

if __name__ == "__main__":
    # Automatically open the browser after 2 seconds
    Timer(2, open_browser).start()

    # Clear any existing arguments to prevent conflict with Streamlit CLI
    sys.argv = [
        "streamlit",
        "run",
        resolve_path(os.path.join("DFUS_30_Suite", "app.py")),
        "--global.developmentMode=false",
        "--server.port=8501",
        "--server.address=0.0.0.0",
        "--server.headless=true",
        "--server.enableCORS=false",
        "--server.enableXsrfProtection=false",
    ]
    sys.exit(stcli.main())