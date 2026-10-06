"""Voice/video call signaling. This relays WebRTC handshake messages (invite, offer,
answer, ICE candidates, hangup) between two logged-in users over a WebSocket - it
never sees or touches the actual audio/video media, only the small JSON messages
needed to set up the peer-to-peer connection.

State lives in this process's memory only. That's fine for a single backend
instance (which is what this app runs today); a multi-instance deployment would
need this moved to something shared like Redis pub/sub.

Getting audio/video to actually connect also needs a STUN server (free, public
ones work fine - e.g. Google's) and, for networks with strict NATs/firewalls, a
TURN relay. STUN alone is usually enough for two people on the same Wi-Fi, which
covers local testing; add a TURN provider (e.g. Metered, Twilio, or a self-hosted
coturn) before relying on this across arbitrary networks.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.common.services.message_service import MessageService
from app.core.database import SessionLocal
from app.core.dependencies import _user_from_access_token

logger = logging.getLogger("calls")

router = APIRouter(prefix="/calls", tags=["Calls"])

RING_TIMEOUT_SECONDS = 45


@dataclass
class CallUser:
    """Plain snapshot of the logged-in user, taken while the DB session is still
    open. The ORM `User` can't be used after `db.close()`: reading `avatar_url`
    lazy-loads the profile and raises DetachedInstanceError, which is what broke
    the "incoming call" card."""

    user_id: int
    username: str
    full_name: str
    avatar_url: Optional[str] = None



_MAX_AVATAR_CHARS = 200_000


def _snapshot_user(user) -> CallUser:
    avatar = user.avatar_url
    if avatar and len(avatar) > _MAX_AVATAR_CHARS:
        avatar = None
    return CallUser(
        user_id=user.user_id,
        username=user.username,
        full_name=user.full_name,
        avatar_url=avatar,
    )


def _is_blocked_pair(a_id: int, b_id: int) -> bool:
    db = SessionLocal()
    try:
        return MessageService.is_blocked_between(db, a_id, b_id)
    finally:
        db.close()


def _user_card(user: CallUser) -> dict:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "full_name": user.full_name,
        "avatar_url": user.avatar_url,
    }


@dataclass
class CallSession:
    call_id: str
    caller_id: int
    callee_id: int
    media: str 
    caller_ws: WebSocket
    callee_ws: Optional[WebSocket] = None
    created_at: float = field(default_factory=time.monotonic)
    answered_at: Optional[float] = None
    ended: bool = False
    timeout_task: Optional["asyncio.Task[None]"] = None


class CallManager:
    """One active call per user at a time. Everything here runs on the single
    asyncio event loop FastAPI already uses for WebSockets, so plain dict access
    is safe - there's no multithreading to race against."""

    def __init__(self) -> None:
        self.connections: Dict[int, WebSocket] = {}
        self.calls: Dict[str, CallSession] = {}
        self.user_call: Dict[int, str] = {}
        self._next_id = 0
      
        self._background: Set["asyncio.Task[None]"] = set()

    def _new_call_id(self) -> str:
        self._next_id += 1
        return f"call-{int(time.time())}-{self._next_id}"

    async def _send(self, ws: Optional[WebSocket], payload: dict) -> None:
        if ws is None:
            return
        try:
            await ws.send_json(payload)
        except Exception:
            pass  

    async def _send_user(self, user_id: int, payload: dict) -> None:
        await self._send(self.connections.get(user_id), payload)


    async def register(self, user_id: int, ws: WebSocket) -> None:
        """Only one live socket per user - a second tab/device takes over."""
        old = self.connections.get(user_id)
        if old is not None and old is not ws:
            try:
                await old.close()
            except Exception:
                pass
        self.connections[user_id] = ws

    def unregister(self, user_id: int, ws: WebSocket) -> None:
        if self.connections.get(user_id) is ws:
            self.connections.pop(user_id, None)

    async def drop_user(self, user_id: int) -> None:
        """Socket closed (tab closed, refresh, network loss) - end any call they're in."""
        call_id = self.user_call.get(user_id)
        if not call_id:
            return
        session = self.calls.get(call_id)
        if session:
            await self._end(session, reason="disconnected")


    async def handle_message(self, me: CallUser, ws: WebSocket, message: dict) -> None:
        mtype = message.get("type")
        if mtype == "invite":
            await self._handle_invite(me, ws, message)
        elif mtype in ("offer", "answer", "ice"):
            await self._relay(me, message)
        elif mtype == "accept":
            await self._handle_accept(me, ws, message)
        elif mtype == "decline":
            await self._handle_end(me, message, reason="declined")
        elif mtype == "hangup":
            await self._handle_end(me, message, reason="hangup")
        elif mtype == "ping":
            await self._send(ws, {"type": "pong"})

    async def _handle_invite(self, me: CallUser, ws: WebSocket, message: dict) -> None:
        try:
            to_id = int(message.get("to"))
        except (TypeError, ValueError):
            return
        if to_id == me.user_id:
            return
        media = message.get("media") if message.get("media") in ("audio", "video") else "audio"


        if await run_in_threadpool(_is_blocked_pair, me.user_id, to_id):
            await self._send(ws, {"type": "unavailable", "call_id": None})
            return

        if me.user_id in self.user_call:
            await self._send(ws, {"type": "error", "reason": "already_in_call"})
            return
        if to_id in self.user_call:
            await self._send(ws, {"type": "busy", "call_id": None})
            await self._log_call_async(me.user_id, to_id, media, "busy", 0)
            return

        callee_ws = self.connections.get(to_id)
        if callee_ws is None:
            await self._send(ws, {"type": "unavailable", "call_id": None})
            await self._log_call_async(me.user_id, to_id, media, "missed", 0)
            return

        call_id = self._new_call_id()
        session = CallSession(
            call_id=call_id, caller_id=me.user_id, callee_id=to_id, media=media, caller_ws=ws
        )
        self.calls[call_id] = session
        self.user_call[me.user_id] = call_id
        self.user_call[to_id] = call_id
        session.timeout_task = asyncio.get_running_loop().create_task(self._ring_timeout(call_id))

        await self._send(ws, {"type": "ringing", "call_id": call_id})
        await self._send(
            callee_ws,
            {"type": "incoming", "call_id": call_id, "media": media, "from": _user_card(me)},
        )

    async def _ring_timeout(self, call_id: str) -> None:
        try:
            await asyncio.sleep(RING_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            return
        session = self.calls.get(call_id)
        if session and not session.ended and session.answered_at is None:
            await self._end(session, reason="no_answer")

    async def _handle_accept(self, me: CallUser, ws: WebSocket, message: dict) -> None:
        session = self.calls.get(message.get("call_id"))
        if session is None or session.callee_id != me.user_id or session.ended:
            return
        session.callee_ws = ws
        session.answered_at = time.monotonic()
        if session.timeout_task is not None:
            session.timeout_task.cancel()
            session.timeout_task = None
        await self._send(session.caller_ws, {"type": "accepted", "call_id": session.call_id})

    async def _relay(self, me: CallUser, message: dict) -> None:
        """Passes an SDP offer/answer or an ICE candidate straight through to the
        other side of the call - we never inspect the contents."""
        session = self.calls.get(message.get("call_id"))
        if session is None or session.ended or me.user_id not in (session.caller_id, session.callee_id):
            return
        if me.user_id == session.caller_id:
            target = session.callee_ws or self.connections.get(session.callee_id)
        else:
            target = session.caller_ws
        await self._send(target, message)

    async def _handle_end(self, me: CallUser, message: dict, reason: str) -> None:
        session = self.calls.get(message.get("call_id"))
        if session is None or me.user_id not in (session.caller_id, session.callee_id):
            return
        await self._end(session, reason=reason)


    async def _end(self, session: CallSession, reason: str) -> None:
        if session.ended:
            return
        session.ended = True
        if session.timeout_task is not None:
            session.timeout_task.cancel()
            session.timeout_task = None

        self.calls.pop(session.call_id, None)
        for uid in (session.caller_id, session.callee_id):
            if self.user_call.get(uid) == session.call_id:
                self.user_call.pop(uid, None)

        if session.answered_at is not None:
            outcome, seconds = "completed", int(time.monotonic() - session.answered_at)
        elif reason == "declined":
            outcome, seconds = "declined", 0
        else:
            outcome, seconds = "missed", 0

        payload = {
            "type": "ended",
            "call_id": session.call_id,
            "reason": reason,
            "outcome": outcome,
            "seconds": seconds,
        }
        await self._send(session.caller_ws, payload)
        await self._send_user(session.callee_id, payload)
        await self._log_call_async(session.caller_id, session.callee_id, session.media, outcome, seconds)

   
    async def _log_call_async(
        self, caller_id: int, callee_id: int, media: str, outcome: str, seconds: int
    ) -> None:
        task = asyncio.get_running_loop().create_task(
            run_in_threadpool(self._log_call_sync, caller_id, callee_id, media, outcome, seconds)
        )
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    @staticmethod
    def _log_call_sync(caller_id: int, callee_id: int, media: str, outcome: str, seconds: int) -> None:
        db = SessionLocal()
        try:
            MessageService.log_call(db, caller_id, callee_id, media, outcome, seconds)
        except Exception:
            logger.exception("Could not log call %s -> %s", caller_id, callee_id)
        finally:
            db.close()


manager = CallManager()


@router.websocket("/ws")
async def calls_ws(websocket: WebSocket, token: str = Query(...)) -> None:
    """Browsers can't set an Authorization header on a WebSocket handshake, so the
    access token travels as a query parameter instead: wss://.../calls/ws?token=..."""
    db = SessionLocal()
    try:
        orm_user = _user_from_access_token(db, token)

        user = _snapshot_user(orm_user) if orm_user is not None else None
    finally:
        db.close()

    if user is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await manager.register(user.user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except ValueError:
                continue
            if isinstance(message, dict):
                await manager.handle_message(user, websocket, message)
    except WebSocketDisconnect:
        pass
    finally:
        manager.unregister(user.user_id, websocket)
        await manager.drop_user(user.user_id)