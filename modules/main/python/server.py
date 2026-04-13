"""Compatibility entrypoint for running the web server as a module.

Run with:
    python -m modules.main.python.server
"""

from modules.main.python.app import app, socketio, db_init, init_auth, check_ollama_models, settings


def main() -> None:
    db_init()
    init_auth()
    print("=" * 60)
    print("TISH SEARCH v4: http://localhost:5000")
    print("=" * 60)
    print(f"Ollama URL: {settings['ollama_url']}")
    print(f"Vision model: {settings['vision_model']}")
    print()

    if check_ollama_models():
        print("Application is ready")
    else:
        print("WARNING: vision model is unavailable")
        print("Command: ollama list")

    print("=" * 60)
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)


if __name__ == "__main__":
    main()

