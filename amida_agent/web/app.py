from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from amida_agent.database import init_db
from amida_agent.web.routes.dashboard import router as dashboard_router
from amida_agent.web.routes.prospects import router as prospects_router
from amida_agent.web.routes.approve import router as approve_router
from amida_agent.web.routes.pipeline import router as pipeline_router

WEB_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Amida AI Sales Agent")
app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

templates = Jinja2Templates(directory=WEB_DIR / "templates")

app.include_router(dashboard_router)
app.include_router(prospects_router, prefix="/prospects")
app.include_router(approve_router, prefix="/approve")
app.include_router(pipeline_router, prefix="/pipeline")


@app.on_event("startup")
def on_startup():
    init_db()
