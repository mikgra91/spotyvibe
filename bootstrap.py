import os
import traceback

def start(files_dir):
    try:
        os.environ["SPOTYVIBE_FILES_DIR"] = files_dir
        from app import app
        app.run(
            host="127.0.0.1",
            port=5000,
            debug=False,
            use_reloader=False,
        )
    except Exception:
        traceback.print_exc()
        raise
