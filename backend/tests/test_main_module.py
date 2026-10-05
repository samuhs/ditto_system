"""pyflakes should not flag the `app` name as redefined in the API entry point.

`app.main` imports the registry packages (`app.core.chunking`, etc.) for their
side effects and also exposes the FastAPI instance as module-level `app` (what
uvicorn loads as `app.main:app`). Importing the packages with `import app.core.x`
binds the local name `app` to the top-level package, which pyflakes then flags
as redefined once `app = create_app()` runs. `from app.core import x` avoids the
ambiguity without renaming the FastAPI instance.
"""
import io
from pathlib import Path

from pyflakes.api import check
from pyflakes.reporter import Reporter


def test_main_module_does_not_redefine_app():
    path = Path(__file__).resolve().parents[1] / "app" / "main.py"
    out, err = io.StringIO(), io.StringIO()
    check(path.read_text(), str(path), Reporter(out, err))
    messages = out.getvalue()
    assert "redefinition" not in messages, messages
