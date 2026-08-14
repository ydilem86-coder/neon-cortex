"""Run the Discord Bot Web Control Panel.

Usage:
    python run_web.py            # http://localhost:8000
    python run_web.py 8080       # custom port
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8000))
    print("=" * 60)
    print("  Discord Bot Web Control Panel")
    print(f"  Open:  http://localhost:{port}")
    print("=" * 60)
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()