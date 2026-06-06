from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import jinja2, json, random, string, asyncio, time

app = FastAPI()

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
    # Sattolo's algorithm: O(n), guaranteed single-cycle derangement
    a = list(range(len(lst)))
    for i in range(len(a) - 1, 0, -1):
        j = random.randint(0, i - 1)
        a[i], a[j] = a[j], a[i]
    return {lst[i]: lst[a[i]] for i in range(len(lst))}


def requiem_assignment(players: list, original_assignments: dict) -> dict:
    """Assign each player a stand to requiem.
    Strict: not own stand AND not the stand drawn for them.
    Fallback: just not own stand (Sattolo derangement).
    """
    reverse = {v: k for k, v in original_assignments.items()}
    for _ in range(500):
        perm = players[:]
        random.shuffle(perm)
        result = {players[i]: perm[i] for i in range(len(players))}
        if all(result[p] != p and result[p] != reverse.get(p) for p in players):
            return result
    return derangement(players)


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


async def timer_name(code: str, duration: int):
    await asyncio.sleep(duration + 3)
    room = rooms.get(code)
    if room and room["phase"] == "name":
        await _start_powers(code)


async def timer_powers(code: str, duration: int):
    await asyncio.sleep(duration + 3)
    room = rooms.get(code)
    if room and room["phase"] == "powers":
        await _start_draw(code)


async def timer_draw(code: str, duration: int):
    await asyncio.sleep(duration + 3)
    room = rooms.get(code)
    if room and room["phase"] == "draw":
        await _start_reveal(code)


async def timer_requiem_powers(code: str, duration: int):
    await asyncio.sleep(duration + 3)
    room = rooms.get(code)
    if room and room["phase"] == "requiem_powers":
        await _start_requiem_draw(code)


async def timer_requiem_draw(code: str, duration: int):
    await asyncio.sleep(duration + 3)
    room = rooms.get(code)
    if room and room["phase"] == "requiem_draw":
        await _start_requiem_reveal(code)


async def _start_powers(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "powers"
    pd = room.get("name_duration", 30)
    room["phase_started_at"] = time.time()
    room["phase_duration"] = pd
    for maker, pl in list(room["players"].items()):
        try:
            await pl["ws"].send_text(json.dumps({
                "type": "phase_change",
                "phase": "powers",
                "assigned_to": room["assignments"].get(maker),
                "stand_name": room["stand_names"].get(maker, "???"),
                "duration": pd,
            }))
        except Exception:
            pass
    asyncio.create_task(timer_powers(code, pd))


async def _start_draw(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "draw"
    dd = room.get("draw_duration", 120)
    room["phase_started_at"] = time.time()
    room["phase_duration"] = dd
    for maker, pl in list(room["players"].items()):
        try:
            await pl["ws"].send_text(json.dumps({
                "type": "phase_change",
                "phase": "draw",
                "assigned_to": room["assignments"].get(maker),
                "stand_name": room["stand_names"].get(maker, "???"),
                "stand_power": room["stand_powers"].get(maker, ""),
                "duration": dd,
            }))
        except Exception:
            pass
    asyncio.create_task(timer_draw(code, dd))


async def _start_reveal(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "reveal"
    room["reveal_index"] = 0
    room["reveal_next_votes"] = set()
    room["reveal_expected"] = set()
    room["reveal_next_event"] = None
    room["current_reveal_maker"] = None
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

        room["reveal_next_votes"] = set()
        room["reveal_expected"] = set(room["players"].keys())
        event = asyncio.Event()
        room["reveal_next_event"] = event
        room["reveal_index"] = idx
        room["current_reveal_maker"] = maker

        await broadcast(code, {
            "type": "reveal_stand",
            "maker": maker,
            "target": room["assignments"][maker],
            "stand_name": room["stand_names"].get(maker, "???"),
            "stand_power": room["stand_powers"].get(maker, ""),
            "drawing": room["drawings"].get(maker, ""),
            "index": idx,
            "total": len(order),
            "votes_needed": len(room["reveal_expected"]),
        })

        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass

    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "vote"
    stands = [
        {
            "maker": m,
            "target": room["assignments"][m],
            "stand_name": room["stand_names"].get(m, "???"),
            "stand_power": room["stand_powers"].get(m, ""),
            "drawing": room["drawings"].get(m, ""),
        }
        for m in order
    ]
    await broadcast(code, {"type": "phase_change", "phase": "vote", "stands": stands})


async def _start_requiem_powers(code: str):
    room = rooms.get(code)
    if not room:
        return
    players = room["all_players"]
    room["requiem_assignments"] = requiem_assignment(players, room["assignments"])
    room["phase"] = "requiem_powers"
    pd = room.get("name_duration", 30)
    room["phase_started_at"] = time.time()
    room["phase_duration"] = pd
    for player, pl in list(room["players"].items()):
        orig = room["requiem_assignments"][player]
        try:
            await pl["ws"].send_text(json.dumps({
                "type": "phase_change",
                "phase": "requiem_powers",
                "original_maker": orig,
                "stand_name": room["stand_names"].get(orig, "???"),
                "stand_power": room["stand_powers"].get(orig, ""),
                "drawing": room["drawings"].get(orig, ""),
                "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
                "duration": pd,
            }))
        except Exception:
            pass
    asyncio.create_task(timer_requiem_powers(code, pd))


async def _start_requiem_draw(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "requiem_draw"
    dd = room.get("draw_duration", 120)
    room["phase_started_at"] = time.time()
    room["phase_duration"] = dd
    for player, pl in list(room["players"].items()):
        orig = room["requiem_assignments"][player]
        try:
            await pl["ws"].send_text(json.dumps({
                "type": "phase_change",
                "phase": "requiem_draw",
                "original_maker": orig,
                "stand_name": room["stand_names"].get(orig, "???"),
                "stand_power": room["stand_powers"].get(orig, ""),
                "drawing": room["drawings"].get(orig, ""),
                "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
                "requiem_power": room["requiem_powers"].get(player, ""),
                "duration": dd,
            }))
        except Exception:
            pass
    asyncio.create_task(timer_requiem_draw(code, dd))


async def _start_requiem_reveal(code: str):
    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "requiem_reveal"
    order = room["all_players"][:]
    random.shuffle(order)
    room["requiem_reveal_order"] = order
    room["requiem_reveal_index"] = 0
    room["requiem_reveal_next_votes"] = set()
    room["requiem_reveal_expected"] = set()
    room["requiem_reveal_next_event"] = None
    room["current_requiem_reveal_maker"] = None
    await broadcast(code, {"type": "phase_change", "phase": "requiem_reveal"})
    asyncio.create_task(_do_requiem_reveals(code))


async def _do_requiem_reveals(code: str):
    await asyncio.sleep(2)
    room = rooms.get(code)
    if not room:
        return
    order = room["requiem_reveal_order"]

    for idx, player in enumerate(order):
        room = rooms.get(code)
        if not room or room["phase"] != "requiem_reveal":
            return

        room["requiem_reveal_next_votes"] = set()
        room["requiem_reveal_expected"] = set(room["players"].keys())
        event = asyncio.Event()
        room["requiem_reveal_next_event"] = event
        room["requiem_reveal_index"] = idx
        room["current_requiem_reveal_maker"] = player

        orig = room["requiem_assignments"][player]
        await broadcast(code, {
            "type": "requiem_reveal_stand",
            "requiem_maker": player,
            "original_maker": orig,
            "stand_name": room["stand_names"].get(orig, "???"),
            "stand_power": room["stand_powers"].get(orig, ""),
            "original_drawing": room["drawings"].get(orig, ""),
            "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
            "requiem_power": room["requiem_powers"].get(player, ""),
            "requiem_drawing": room["requiem_drawings"].get(player, ""),
            "index": idx,
            "total": len(order),
            "votes_needed": len(room["requiem_reveal_expected"]),
        })

        try:
            await asyncio.wait_for(event.wait(), timeout=300)
        except asyncio.TimeoutError:
            pass

    room = rooms.get(code)
    if not room:
        return
    room["phase"] = "requiem_vote"
    stands = []
    for p in order:
        orig = room["requiem_assignments"][p]
        stands.append({
            "requiem_maker": p,
            "original_maker": orig,
            "stand_name": room["stand_names"].get(orig, "???"),
            "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
            "requiem_power": room["requiem_powers"].get(p, ""),
            "requiem_drawing": room["requiem_drawings"].get(p, ""),
        })
    await broadcast(code, {"type": "phase_change", "phase": "requiem_vote", "stands": stands})


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
    valid_name = [30, 60, 120, 300]
    valid_draw = [60, 120, 300, 600]
    nd = data.get("name_duration", 30)
    dd = data.get("draw_duration", 120)
    rooms[code] = {
        "code": code,
        "party_name": pname,
        "host": uname,
        "players": {},
        "all_players": [],
        "phase": "lobby",
        "assignments": {},
        "stand_names": {},
        "stand_powers": {},
        "drawings": {},
        "votes": {},
        "reveal_order": [],
        "reveal_index": 0,
        "reveal_expected": set(),
        "reveal_next_votes": set(),
        "reveal_next_event": None,
        "current_reveal_maker": None,
        "name_duration": nd if nd in valid_name else 30,
        "draw_duration": dd if dd in valid_draw else 120,
        "phase_started_at": 0,
        "phase_duration": 0,
        # requiem fields
        "requiem_assignments": {},
        "requiem_powers": {},
        "requiem_drawings": {},
        "requiem_votes": {},
        "requiem_reveal_order": [],
        "requiem_reveal_index": 0,
        "requiem_reveal_expected": set(),
        "requiem_reveal_next_votes": set(),
        "requiem_reveal_next_event": None,
        "current_requiem_reveal_maker": None,
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

    phase = room["phase"]
    is_reconnect = username in room.get("all_players", []) and phase != "lobby"
    is_new_mid_game = not is_reconnect and phase != "lobby"

    if is_new_mid_game:
        await ws.send_text(json.dumps({"type": "error", "message": "Partita già iniziata"}))
        await ws.close()
        return

    room["players"][username] = {"ws": ws}

    if not is_reconnect:
        await ws.send_text(json.dumps({
            "type": "room_joined",
            "room_code": room_code,
            "party_name": room["party_name"],
            "players": list(room["players"].keys()),
            "is_host": username == room["host"],
            "phase": phase,
            "name_duration": room.get("name_duration", 30),
            "draw_duration": room.get("draw_duration", 120),
        }))
        await broadcast(room_code, {
            "type": "player_update",
            "players": list(room["players"].keys()),
            "host": room["host"],
        })
    else:
        elapsed = time.time() - room.get("phase_started_at", time.time())
        remaining = max(1, round(room.get("phase_duration", 30) - elapsed))

        if phase == "name":
            await ws.send_text(json.dumps({
                "type": "game_started",
                "phase": "name",
                "assigned_to": room["assignments"].get(username),
                "duration": remaining,
                "already_submitted": username in room["stand_names"],
            }))
        elif phase == "powers":
            await ws.send_text(json.dumps({
                "type": "phase_change",
                "phase": "powers",
                "assigned_to": room["assignments"].get(username),
                "stand_name": room["stand_names"].get(username, "???"),
                "duration": remaining,
                "already_submitted": username in room["stand_powers"],
            }))
        elif phase == "draw":
            await ws.send_text(json.dumps({
                "type": "phase_change",
                "phase": "draw",
                "assigned_to": room["assignments"].get(username),
                "stand_name": room["stand_names"].get(username, "???"),
                "stand_power": room["stand_powers"].get(username, ""),
                "duration": remaining,
                "already_submitted": username in room["drawings"],
            }))
        elif phase == "reveal":
            await ws.send_text(json.dumps({"type": "phase_change", "phase": "reveal"}))
            maker = room.get("current_reveal_maker")
            if maker and maker in room["assignments"]:
                idx = room.get("reveal_index", 0)
                votes = len(room.get("reveal_next_votes", set()))
                needed = len(room.get("reveal_expected", set()))
                await ws.send_text(json.dumps({
                    "type": "reveal_stand",
                    "maker": maker,
                    "target": room["assignments"][maker],
                    "stand_name": room["stand_names"].get(maker, "???"),
                    "stand_power": room["stand_powers"].get(maker, ""),
                    "drawing": room["drawings"].get(maker, ""),
                    "index": idx,
                    "total": len(room["reveal_order"]),
                    "votes_needed": needed,
                }))
                if votes > 0:
                    await ws.send_text(json.dumps({
                        "type": "reveal_next_update",
                        "votes": votes,
                        "total": needed,
                    }))
        elif phase == "vote":
            stands = [
                {
                    "maker": m,
                    "target": room["assignments"][m],
                    "stand_name": room["stand_names"].get(m, "???"),
                    "stand_power": room["stand_powers"].get(m, ""),
                    "drawing": room["drawings"].get(m, ""),
                }
                for m in room["reveal_order"]
            ]
            await ws.send_text(json.dumps({"type": "phase_change", "phase": "vote", "stands": stands}))
        elif phase == "requiem_powers":
            orig = room["requiem_assignments"].get(username)
            if orig:
                await ws.send_text(json.dumps({
                    "type": "phase_change",
                    "phase": "requiem_powers",
                    "original_maker": orig,
                    "stand_name": room["stand_names"].get(orig, "???"),
                    "stand_power": room["stand_powers"].get(orig, ""),
                    "drawing": room["drawings"].get(orig, ""),
                    "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
                    "duration": remaining,
                    "already_submitted": username in room["requiem_powers"],
                }))
        elif phase == "requiem_draw":
            orig = room["requiem_assignments"].get(username)
            if orig:
                await ws.send_text(json.dumps({
                    "type": "phase_change",
                    "phase": "requiem_draw",
                    "original_maker": orig,
                    "stand_name": room["stand_names"].get(orig, "???"),
                    "stand_power": room["stand_powers"].get(orig, ""),
                    "drawing": room["drawings"].get(orig, ""),
                    "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
                    "requiem_power": room["requiem_powers"].get(username, ""),
                    "duration": remaining,
                    "already_submitted": username in room["requiem_drawings"],
                }))
        elif phase == "requiem_reveal":
            await ws.send_text(json.dumps({"type": "phase_change", "phase": "requiem_reveal"}))
            maker = room.get("current_requiem_reveal_maker")
            if maker and maker in room["requiem_assignments"]:
                idx = room.get("requiem_reveal_index", 0)
                votes = len(room.get("requiem_reveal_next_votes", set()))
                needed = len(room.get("requiem_reveal_expected", set()))
                orig = room["requiem_assignments"][maker]
                await ws.send_text(json.dumps({
                    "type": "requiem_reveal_stand",
                    "requiem_maker": maker,
                    "original_maker": orig,
                    "stand_name": room["stand_names"].get(orig, "???"),
                    "stand_power": room["stand_powers"].get(orig, ""),
                    "original_drawing": room["drawings"].get(orig, ""),
                    "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
                    "requiem_power": room["requiem_powers"].get(maker, ""),
                    "requiem_drawing": room["requiem_drawings"].get(maker, ""),
                    "index": idx,
                    "total": len(room["requiem_reveal_order"]),
                    "votes_needed": needed,
                }))
                if votes > 0:
                    await ws.send_text(json.dumps({
                        "type": "requiem_reveal_next_update",
                        "votes": votes,
                        "total": needed,
                    }))
        elif phase == "requiem_vote":
            stands = []
            for p in room["requiem_reveal_order"]:
                orig = room["requiem_assignments"][p]
                stands.append({
                    "requiem_maker": p,
                    "original_maker": orig,
                    "stand_name": room["stand_names"].get(orig, "???"),
                    "requiem_name": room["stand_names"].get(orig, "???") + " Requiem",
                    "requiem_power": room["requiem_powers"].get(p, ""),
                    "requiem_drawing": room["requiem_drawings"].get(p, ""),
                })
            await ws.send_text(json.dumps({"type": "phase_change", "phase": "requiem_vote", "stands": stands}))
        elif phase == "results":
            order = room["reveal_order"]
            vc = {m: 0 for m in room["assignments"]}
            for vm in room["votes"].values():
                vc[vm] += 1
            normal_results = sorted([{
                "maker": m,
                "target": room["assignments"][m],
                "stand_name": room["stand_names"].get(m, "???"),
                "stand_power": room["stand_powers"].get(m, ""),
                "drawing": room["drawings"].get(m, ""),
                "votes": vc[m],
            } for m in order], key=lambda x: -x["votes"])

            vc_r = {p: 0 for p in room["all_players"]}
            for vm in room["requiem_votes"].values():
                vc_r[vm] += 1
            requiem_results = sorted([{
                "requiem_maker": p,
                "original_maker": room["requiem_assignments"].get(p, ""),
                "stand_name": room["stand_names"].get(room["requiem_assignments"].get(p, ""), "???"),
                "requiem_name": room["stand_names"].get(room["requiem_assignments"].get(p, ""), "???") + " Requiem",
                "requiem_power": room["requiem_powers"].get(p, ""),
                "requiem_drawing": room["requiem_drawings"].get(p, ""),
                "votes": vc_r[p],
            } for p in room.get("requiem_reveal_order", [])], key=lambda x: -x["votes"])

            await ws.send_text(json.dumps({
                "type": "results",
                "results": normal_results,
                "requiem_results": requiem_results,
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
                random.shuffle(players)
                room["assignments"] = derangement(players)
                room["reveal_order"] = players[:]
                random.shuffle(room["reveal_order"])
                room["all_players"] = players[:]
                nd = room.get("name_duration", 30)
                room["phase"] = "name"
                room["phase_started_at"] = time.time()
                room["phase_duration"] = nd
                for maker, pl in list(room["players"].items()):
                    try:
                        await pl["ws"].send_text(json.dumps({
                            "type": "game_started",
                            "phase": "name",
                            "assigned_to": room["assignments"][maker],
                            "duration": nd,
                        }))
                    except Exception:
                        pass
                asyncio.create_task(timer_name(room_code, nd))

            elif t == "submit_name":
                if room["phase"] != "name" or username in room["stand_names"]:
                    continue
                sname = (msg.get("stand_name") or "").strip() or "???"
                room["stand_names"][username] = sname
                if len(room["stand_names"]) >= len(room["all_players"]):
                    await _start_powers(room_code)

            elif t == "submit_powers":
                if room["phase"] != "powers" or username in room["stand_powers"]:
                    continue
                power = (msg.get("stand_power") or "").strip()
                room["stand_powers"][username] = power
                if len(room["stand_powers"]) >= len(room["all_players"]):
                    await _start_draw(room_code)

            elif t == "submit_drawing":
                if room["phase"] not in ("draw", "reveal") or username in room["drawings"]:
                    continue
                room["drawings"][username] = msg.get("drawing_data", "")
                if room["phase"] == "draw" and len(room["drawings"]) >= len(room["all_players"]):
                    await _start_reveal(room_code)

            elif t == "reveal_next":
                if room["phase"] != "reveal":
                    continue
                if username not in room.get("reveal_expected", set()):
                    continue
                room["reveal_next_votes"].add(username)
                votes = len(room["reveal_next_votes"])
                total = len(room["reveal_expected"])
                await broadcast(room_code, {
                    "type": "reveal_next_update",
                    "votes": votes,
                    "total": total,
                })
                if votes >= total:
                    event = room.get("reveal_next_event")
                    if event and not event.is_set():
                        event.set()

            elif t == "vote":
                if room["phase"] != "vote" or username in room["votes"]:
                    continue
                target = msg.get("target")
                if target and target in room["assignments"] and target != username:
                    room["votes"][username] = target
                    await broadcast(room_code, {
                        "type": "vote_update",
                        "vote_count": len(room["votes"]),
                        "total": len(room["all_players"]),
                    })
                    if len(room["votes"]) >= len(room["all_players"]):
                        await _start_requiem_powers(room_code)

            elif t == "submit_requiem_powers":
                if room["phase"] != "requiem_powers" or username in room["requiem_powers"]:
                    continue
                power = (msg.get("stand_power") or "").strip()
                room["requiem_powers"][username] = power
                if len(room["requiem_powers"]) >= len(room["all_players"]):
                    await _start_requiem_draw(room_code)

            elif t == "submit_requiem_drawing":
                if room["phase"] not in ("requiem_draw", "requiem_reveal") or username in room["requiem_drawings"]:
                    continue
                room["requiem_drawings"][username] = msg.get("drawing_data", "")
                if room["phase"] == "requiem_draw" and len(room["requiem_drawings"]) >= len(room["all_players"]):
                    await _start_requiem_reveal(room_code)

            elif t == "requiem_reveal_next":
                if room["phase"] != "requiem_reveal":
                    continue
                if username not in room.get("requiem_reveal_expected", set()):
                    continue
                room["requiem_reveal_next_votes"].add(username)
                votes = len(room["requiem_reveal_next_votes"])
                total = len(room["requiem_reveal_expected"])
                await broadcast(room_code, {
                    "type": "requiem_reveal_next_update",
                    "votes": votes,
                    "total": total,
                })
                if votes >= total:
                    event = room.get("requiem_reveal_next_event")
                    if event and not event.is_set():
                        event.set()

            elif t == "requiem_vote":
                if room["phase"] != "requiem_vote" or username in room["requiem_votes"]:
                    continue
                target = msg.get("target")
                if target and target in room["all_players"] and target != username:
                    room["requiem_votes"][username] = target
                    await broadcast(room_code, {
                        "type": "requiem_vote_update",
                        "vote_count": len(room["requiem_votes"]),
                        "total": len(room["all_players"]),
                    })
                    if len(room["requiem_votes"]) >= len(room["all_players"]):
                        vc = {m: 0 for m in room["assignments"]}
                        for vm in room["votes"].values():
                            vc[vm] += 1
                        normal_results = sorted([{
                            "maker": m,
                            "target": room["assignments"][m],
                            "stand_name": room["stand_names"].get(m, "???"),
                            "stand_power": room["stand_powers"].get(m, ""),
                            "drawing": room["drawings"].get(m, ""),
                            "votes": vc[m],
                        } for m in room["reveal_order"]], key=lambda x: -x["votes"])

                        vc_r = {p: 0 for p in room["all_players"]}
                        for vm in room["requiem_votes"].values():
                            vc_r[vm] += 1
                        requiem_results = sorted([{
                            "requiem_maker": p,
                            "original_maker": room["requiem_assignments"][p],
                            "stand_name": room["stand_names"].get(room["requiem_assignments"][p], "???"),
                            "requiem_name": room["stand_names"].get(room["requiem_assignments"][p], "???") + " Requiem",
                            "requiem_power": room["requiem_powers"].get(p, ""),
                            "requiem_drawing": room["requiem_drawings"].get(p, ""),
                            "votes": vc_r[p],
                        } for p in room["requiem_reveal_order"]], key=lambda x: -x["votes"])

                        room["phase"] = "results"
                        await broadcast(room_code, {
                            "type": "results",
                            "results": normal_results,
                            "requiem_results": requiem_results,
                        })

            elif t == "update_settings":
                if username != room["host"] or room["phase"] != "lobby":
                    continue
                valid_name = [30, 60, 120, 300]
                valid_draw = [60, 120, 300, 600]
                nd = msg.get("name_duration")
                dd = msg.get("draw_duration")
                if nd in valid_name:
                    room["name_duration"] = nd
                if dd in valid_draw:
                    room["draw_duration"] = dd
                await broadcast(room_code, {
                    "type": "settings_updated",
                    "name_duration": room["name_duration"],
                    "draw_duration": room["draw_duration"],
                })

            elif t == "reset_game":
                if room["phase"] != "results":
                    continue
                room["phase"] = "lobby"
                room["assignments"] = {}
                room["all_players"] = []
                room["stand_names"] = {}
                room["stand_powers"] = {}
                room["drawings"] = {}
                room["votes"] = {}
                room["reveal_order"] = []
                room["reveal_index"] = 0
                room["reveal_expected"] = set()
                room["reveal_next_votes"] = set()
                room["reveal_next_event"] = None
                room["current_reveal_maker"] = None
                room["requiem_assignments"] = {}
                room["requiem_powers"] = {}
                room["requiem_drawings"] = {}
                room["requiem_votes"] = {}
                room["requiem_reveal_order"] = []
                room["requiem_reveal_index"] = 0
                room["requiem_reveal_expected"] = set()
                room["requiem_reveal_next_votes"] = set()
                room["requiem_reveal_next_event"] = None
                room["current_requiem_reveal_maker"] = None
                await broadcast(room_code, {
                    "type": "game_reset",
                    "party_name": room["party_name"],
                    "players": list(room["players"].keys()),
                    "host": room["host"],
                    "name_duration": room["name_duration"],
                    "draw_duration": room["draw_duration"],
                })

    except WebSocketDisconnect:
        room["players"].pop(username, None)
        if room["players"]:
            if username == room["host"] and room["phase"] == "lobby":
                room["host"] = next(iter(room["players"]))
            await broadcast(room_code, {
                "type": "player_update",
                "players": list(room["players"].keys()),
                "host": room["host"],
            })
            if room.get("phase") == "reveal":
                exp = room.get("reveal_expected", set())
                if username in exp:
                    exp.discard(username)
                    room["reveal_next_votes"].discard(username)
                    if room["reveal_next_votes"] >= exp and exp:
                        event = room.get("reveal_next_event")
                        if event and not event.is_set():
                            event.set()
            elif room.get("phase") == "requiem_reveal":
                exp = room.get("requiem_reveal_expected", set())
                if username in exp:
                    exp.discard(username)
                    room["requiem_reveal_next_votes"].discard(username)
                    if room["requiem_reveal_next_votes"] >= exp and exp:
                        event = room.get("requiem_reveal_next_event")
                        if event and not event.is_set():
                            event.set()
        else:
            rooms.pop(room_code, None)
