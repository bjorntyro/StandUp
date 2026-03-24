from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi.responses import HTMLResponse

app = FastAPI()

templates = Jinja2Templates(directory="frontend/templates")

app.mount("/frontend/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/create_party", response_class=HTMLResponse)
async def create_party_page(request: Request):
    return templates.TemplateResponse("", {"request": request})
