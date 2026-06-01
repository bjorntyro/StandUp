from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import jinja2, json, random, string, asyncio

app = FastAPI()

# cache_size=0 → self.cache=None in Jinja2, skips the LRU key lookup entirely.
# Needed because Jinja2 3.x on Python 3.13 tries to use env.globals (a dict)
# as part of the cache key, which raises TypeError: unhashable type: 'dict'.
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("frontend/templates"),
    autoescape=True,
    cache_size=0,
)
templates = Jinja2Templates(env=_env)
app.mount("/frontend/static", StaticFiles(directory="frontend/static"), name="static")

rooms: dict = {}


def gen_code() -> str:
    while True:
        c = "".join(random.choices(string.ascii_uppercase, k=4))
        if c not in rooms:
            return c


def derangement(lst: list) -> dict:
    indices = list(range(len(lst)))
    while True:
        p = indices[:]
        random.shuffle(p)
        if all(p[i] != i for i in range(len(lst))):
            return {lst[i]: lst[p[i]] for i in range(len(lst))}


async def broadcast(code: str, msg: dict):
    room = rooms.get(code)
    if not room:
        return
    dead = []
    for u, pl in list(room["players"].items()):
        try:
            await pl["ws"].send_text(json.dumps(msg))
        except Exception:
            dead.append(u)
    for u in dead:
        room["players"].pop(u, None)


async def timer_name(code: str):
    await asyncio.sleep(30)
    room = rooms.get(code)
    if room and room["phase"] == "name":
        await _start_draw(code)


async def timer_draw(code: str):
    await asyncio.sleep(120)
    room = rooms.get(code)
    if room and room["phase"] == "draw":
        await _start_reveal(code)


async def _start_draw(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "draw"
    for maker, pl in list(room["players"].items()):
        try:
            await pl["ws"].send_text(json.dumps({
                "type": "phase_change",
                "phase": "draw",
                "assigned_to": room["assignments"].get(maker),
                "stand_name": room["stand_names"].get(maker, "???"),
                "duration": 120,
            }))
        except Exception:
            pass
    asyncio.create_task(timer_draw(code))


async def _start_reveal(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "reveal"
    room["reveal_index"] = 0
    await broadcast(code, {"type": "phase_change", "phase": "reveal"})
    asyncio.create_task(_do_reveals(code))


async def _do_reveals(code: str):
    await asyncio.sleep(2)
    room = rooms.get(code)
    if not room:
        return
    order = room["reveal_order"]
    for idx, maker in enumerate(order):
        room = rooms.get(code)
        if not room or room["phase"] != "reveal":
            return
        await broadcast(code, {
            "type": "reveal_stand",
            "maker": maker,
            "target": room["assignments"][maker],
            "stand_name": room["stand_names"].get(maker, "???"),
            "drawing": room["drawings"].get(maker, ""),
            "index": idx,
            "total": len(order),
        })
        await asyncio.sleep(9)
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "vote"
    stands = [
        {
            "maker": m,
            "target": room["assignments"][m],
            "stand_name": room["stand_names"].get(m, "???"),
            "drawing": room["drawings"].get(m, ""),
        }
        for m in order
    ]
    await broadcast(code, {"type": "phase_change", "phase": "vote", "stands": stands})


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html")


@app.get("/lobby/{room_code}")
def lobby_page(request: Request, room_code: str):
    return templates.TemplateResponse(request, "lobby.html", {"room_code": room_code})


@app.post("/api/create_room")
async def create_room(request: Request):
    data = await request.json()
    pname = (data.get("party_name") or "").strip()
    uname = (data.get("username") or "").strip()
    if not pname or not uname:
        return {"error": "Campi mancanti"}
    code = gen_code()
    rooms[code] = {
        "code": code,
        "party_name": pname,
        "host": uname,
        "players": {},
        "phase": "lobby",
        "assignments": {},
        "stand_names": {},
        "drawings": {},
        "votes": {},
        "reveal_order": [],
        "reveal_index": 0,
    }
    return {"room_code": code}


@app.post("/api/check_room")
async def check_room(request: Request):
    data = await request.json()
    code = (data.get("room_code") or "").strip().upper()
    if code not in rooms:
        return {"error": "Stanza non trovata"}
    if rooms[code]["phase"] != "lobby":
        return {"error": "Partita già iniziata"}
    return {"ok": True, "party_name": rooms[code]["party_name"]}


@app.websocket("/ws/{room_code}/{username}")
async def ws_endpoint(ws: WebSocket, room_code: str, username: str):
    await ws.accept()
    room = rooms.get(room_code)
    if not room:
        await ws.send_text(json.dumps({"type": "error", "message": "Stanza non trovata"}))
        await ws.close()
        return
    if username in room["players"]:
        await ws.send_text(json.dumps({"type": "error", "message": "Username già in uso in questa stanza"}))
        await ws.close()
        return

    room["players"][username] = {"ws": ws}
    await ws.send_text(json.dumps({
        "type": "room_joined",
        "room_code": room_code,
        "party_name": room["party_name"],
        "players": list(room["players"].keys()),
        "is_host": username == room["host"],
        "phase": room["phase"],
    }))
    await broadcast(room_code, {
        "type": "player_update",
        "players": list(room["players"].keys()),
        "host": room["host"],
    })

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            t = msg.get("type")

            if t == "start_game":
                if username != room["host"]:
                    continue
                if len(room["players"]) < 2:
                    await ws.send_text(json.dumps({"type": "error", "message": "Servono almeno 2 giocatori!"}))
                    continue
                players = list(room["players"].keys())
                room["assignments"] = derangement(players)
                room["reveal_order"] = players[:]
                random.shuffle(room["reveal_order"])
                room["phase"] = "name"
                for maker, pl in list(room["players"].items()):
                    try:
                        await pl["ws"].send_text(json.dumps({
                            "type": "game_started",
                            "phase": "name",
                            "assigned_to": room["assignments"][maker],
                            "duration": 30,
                        }))
                    except Exception:
                        pass
                asyncio.create_task(timer_name(room_code))

            elif t == "submit_name":
                if room["phase"] != "name" or username in room["stand_names"]:
                    continue
                sname = (msg.get("stand_name") or "").strip() or "???"
                room["stand_names"][username] = sname
                if len(room["stand_names"]) >= len(room["players"]):
                    await _start_draw(room_code)

            elif t == "submit_drawing":
                if room["phase"] != "draw" or username in room["drawings"]:
                    continue
                room["drawings"][username] = msg.get("drawing_data", "")
                if len(room["drawings"]) >= len(room["players"]):
                    await _start_reveal(room_code)

            elif t == "vote":
                if room["phase"] != "vote" or username in room["votes"]:
                    continue
                target = msg.get("target")
                if target and target in room["assignments"] and target != username:
                    room["votes"][username] = target
                    await broadcast(room_code, {
                        "type": "vote_update",
                        "vote_count": len(room["votes"]),
                        "total": len(room["players"]),
                    })
                    if len(room["votes"]) >= len(room["players"]):
                        room["phase"] = "results"
                        vc = {m: 0 for m in room["assignments"]}
                        for vm in room["votes"].values():
                            vc[vm] += 1
                        results = sorted([{
                            "maker": m,
                            "target": room["assignments"][m],
                            "stand_name": room["stand_names"].get(m, "???"),
                            "drawing": room["drawings"].get(m, ""),
                            "votes": vc[m],
                        } for m in room["reveal_order"]], key=lambda x: -x["votes"])
                        await broadcast(room_code, {"type": "results", "results": results})

    except WebSocketDisconnect:
        room["players"].pop(username, None)
        if room["players"]:
            if username == room["host"]:
                room["host"] = next(iter(room["players"]))
            await broadcast(room_code, {
                "type": "player_update",
                "players": list(room["players"].keys()),
                "host": room["host"],
            })
        else:
            rooms.pop(room_code, None)
