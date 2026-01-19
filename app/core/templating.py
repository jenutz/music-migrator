from fastapi.templating import Jinja2Templates

from app.core.config import APP_DIR

templates = Jinja2Templates(directory=APP_DIR / "templates")
