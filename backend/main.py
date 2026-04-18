from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from fastapi.responses import HTMLResponse

from fastapi import Form

app = FastAPI()

templates = Jinja2Templates(directory="frontend/templates")

app.mount("/frontend/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/create_party", response_class=HTMLResponse)
async def create_party_page(request: Request):
    return templates.TemplateResponse("create_party.html", {"request": request})

@app.post("/create_party")
async def create_party(
    request: Request,
    party_name: str = Form(...),
    username: str = Form(...)
):
    # Debug print (always do this in early stage)
    print(f"Party: {party_name}")
    print(f"User: {username}")

    return templates.TemplateResponse(
        "create_party.html",
        {
            "request": request,
            "party_name": party_name,
            "username": username
        }
    )
