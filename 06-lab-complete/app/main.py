"""
Production Legal Compliance Agent
Day 9 Stage 3 agent, productionized with Day 12 patterns.

Checklist:
  ✅ Config từ environment (12-factor)
  ✅ Vertex AI credentials via env var
  ✅ Structured JSON logging
  ✅ API Key authentication
  ✅ Rate limiting
  ✅ Cost guard
  ✅ Health check + Readiness probe
  ✅ Graceful shutdown
  ✅ Security headers
  ✅ CORS
"""
import os
import time
import signal
import logging
import json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Optional

import redis as redis_lib

from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.agent import setup_vertex_credentials, run_agent

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_request_count = 0
_error_count = 0
_daily_cost = 0.0
_cost_reset_day = time.strftime("%Y-%m-%d")
_redis: Optional[redis_lib.Redis] = None

# ─────────────────────────────────────────────────────────
# Rate Limiter (Redis sliding window per user; fallback in-memory)
# ─────────────────────────────────────────────────────────
_rate_windows: dict[str, deque] = defaultdict(deque)

def check_rate_limit(key: str):
    user = key[:16]
    now = time.time()
    if _redis:
        rkey = f"rl:{user}"
        pipe = _redis.pipeline()
        pipe.zremrangebyscore(rkey, 0, now - 60)
        pipe.zcard(rkey)
        pipe.zadd(rkey, {str(now): now})
        pipe.expire(rkey, 120)
        _, count, *_ = pipe.execute()
        if count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
                headers={"Retry-After": "60"},
            )
    else:
        window = _rate_windows[user]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: {settings.rate_limit_per_minute} req/min",
                headers={"Retry-After": "60"},
            )
        window.append(now)

# ─────────────────────────────────────────────────────────
# Cost Guard (Redis per-user monthly; fallback global daily)
# ─────────────────────────────────────────────────────────
def check_and_record_cost(input_tokens: int, output_tokens: int, user: str = "global"):
    cost = (input_tokens / 1000) * 0.000075 + (output_tokens / 1000) * 0.0003
    if _redis:
        month = time.strftime("%Y-%m")
        ckey = f"cost:{user}:{month}"
        current = float(_redis.get(ckey) or 0)
        if current >= settings.daily_budget_usd:
            raise HTTPException(402, "Monthly budget exhausted.")
        _redis.incrbyfloat(ckey, cost)
        _redis.expire(ckey, 86400 * 35)
    else:
        global _daily_cost, _cost_reset_day
        today = time.strftime("%Y-%m-%d")
        if today != _cost_reset_day:
            _daily_cost = 0.0
            _cost_reset_day = today
        if _daily_cost >= settings.daily_budget_usd:
            raise HTTPException(503, "Daily budget exhausted. Try tomorrow.")
        _daily_cost += cost

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _redis
    setup_vertex_credentials(settings.google_credentials_json)
    # Connect Redis
    if settings.redis_url:
        try:
            _redis = redis_lib.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)
            _redis.ping()
            logger.info(json.dumps({"event": "redis_connected", "url": settings.redis_url[:30]}))
        except Exception as e:
            logger.warning(json.dumps({"event": "redis_unavailable", "error": str(e)}))
            _redis = None
    logger.info(json.dumps({
        "event": "startup",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "vertex_project": settings.vertex_project,
        "vertex_model": settings.vertex_model,
        "redis": _redis is not None,
    }))
    _is_ready = True
    logger.info(json.dumps({"event": "ready"}))
    yield
    _is_ready = False
    if _redis:
        _redis.close()
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    global _request_count, _error_count
    start = time.time()
    _request_count += 1
    try:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if "server" in response.headers:
            del response.headers["server"]
        duration = round((time.time() - start) * 1000, 1)
        logger.info(json.dumps({
            "event": "request",
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration,
        }))
        return response
    except Exception:
        _error_count += 1
        raise

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Legal/compliance question for the agent")
    session_id: Optional[str] = Field(None, max_length=64,
                                      description="Session ID for conversation history (optional)")

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "description": "Legal compliance agent powered by Gemini via Vertex AI",
        "endpoints": {
            "ui": "GET /ui (chat interface)",
            "ask": "POST /ask (requires X-API-Key)",
            "health": "GET /health",
            "ready": "GET /ready",
        },
    }


@app.get("/ui", response_class=HTMLResponse, tags=["Info"], include_in_schema=False)
def ui():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Legal Compliance Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; height: 100vh; display: flex; flex-direction: column; }
  header { background: #1e293b; padding: 16px 24px; border-bottom: 1px solid #334155; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.1rem; font-weight: 600; }
  header span { font-size: 0.75rem; background: #0ea5e9; color: #fff; padding: 2px 8px; border-radius: 9999px; }
  .config { background: #1e293b; padding: 10px 24px; border-bottom: 1px solid #334155; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  .config label { font-size: 0.8rem; color: #94a3b8; }
  .config input { background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 6px 10px; border-radius: 6px; font-size: 0.85rem; width: 260px; }
  .config input:focus { outline: none; border-color: #0ea5e9; }
  #chat { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }
  .msg { max-width: 75%; display: flex; flex-direction: column; gap: 4px; }
  .msg.user { align-self: flex-end; }
  .msg.bot  { align-self: flex-start; }
  .bubble { padding: 10px 14px; border-radius: 12px; font-size: 0.9rem; line-height: 1.6; white-space: pre-wrap; }
  .user .bubble { background: #0ea5e9; color: #fff; border-bottom-right-radius: 2px; }
  .bot  .bubble { background: #1e293b; border: 1px solid #334155; border-bottom-left-radius: 2px; }
  .ts { font-size: 0.7rem; color: #475569; padding: 0 4px; }
  .user .ts { text-align: right; }
  .typing { display: none; align-self: flex-start; }
  .typing .bubble { background: #1e293b; border: 1px solid #334155; color: #64748b; font-style: italic; }
  footer { background: #1e293b; border-top: 1px solid #334155; padding: 14px 24px; display: flex; gap: 10px; }
  footer textarea { flex: 1; background: #0f172a; border: 1px solid #334155; color: #e2e8f0; padding: 10px 14px; border-radius: 8px; font-size: 0.9rem; resize: none; height: 44px; font-family: inherit; }
  footer textarea:focus { outline: none; border-color: #0ea5e9; }
  footer button { background: #0ea5e9; color: #fff; border: none; padding: 0 20px; border-radius: 8px; font-size: 0.9rem; cursor: pointer; font-weight: 600; }
  footer button:hover { background: #0284c7; }
  footer button:disabled { background: #334155; cursor: not-allowed; }
</style>
</head>
<body>
<header>
  <h1>⚖️ Legal Compliance Agent</h1>
  <span>Gemini 2.5 Flash</span>
</header>
<div class="config">
  <label>API Key:</label>
  <input id="apiKey" type="password" placeholder="X-API-Key" />
  <label>Session:</label>
  <input id="sessionId" type="text" placeholder="session-id (leave blank = no history)" style="width:180px" />
</div>
<div id="chat">
  <div class="msg bot">
    <div class="bubble">Xin chào! Tôi là Legal Compliance Agent. Hỏi tôi về NDA, tax evasion, data privacy, SOX compliance, hoặc bất kỳ vấn đề pháp lý nào.</div>
    <div class="ts">Legal Compliance Agent</div>
  </div>
</div>
<div class="typing" id="typing">
  <div class="bubble">Đang phân tích...</div>
</div>
<footer>
  <textarea id="input" placeholder="Nhập câu hỏi pháp lý..." rows="1"></textarea>
  <button id="sendBtn" onclick="send()">Gửi</button>
</footer>
<script>
  const chat = document.getElementById('chat');
  const typing = document.getElementById('typing');

  function addMsg(role, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + role;
    const ts = new Date().toLocaleTimeString('vi-VN', {hour:'2-digit', minute:'2-digit'});
    d.innerHTML = `<div class="bubble">${text.replace(/</g,'&lt;').replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/\n/g,'<br>')}</div><div class="ts">${role === 'user' ? 'Bạn' : 'Agent'} · ${ts}</div>`;
    chat.appendChild(d);
    chat.scrollTop = chat.scrollHeight;
  }

  async function send() {
    const input = document.getElementById('input');
    const apiKey = document.getElementById('apiKey').value.trim();
    const sessionId = document.getElementById('sessionId').value.trim();
    const q = input.value.trim();
    if (!q) return;
    if (!apiKey) { alert('Nhập API Key trước!'); return; }

    input.value = '';
    document.getElementById('sendBtn').disabled = true;
    addMsg('user', q);
    chat.appendChild(typing);
    typing.style.display = 'flex';
    chat.scrollTop = chat.scrollHeight;

    try {
      const body = { question: q };
      if (sessionId) body.session_id = sessionId;
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      typing.style.display = 'none';
      if (res.ok) {
        addMsg('bot', data.answer);
      } else {
        addMsg('bot', '❌ ' + (data.detail || 'Lỗi không xác định'));
      }
    } catch(e) {
      typing.style.display = 'none';
      addMsg('bot', '❌ Network error: ' + e.message);
    }
    document.getElementById('sendBtn').disabled = false;
    input.focus();
  }

  document.getElementById('input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  });
</script>
</body>
</html>""")


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Send a legal/compliance question to the agent."""
    user = _key[:16]
    check_rate_limit(user)

    input_tokens = len(body.question.split()) * 2
    check_and_record_cost(input_tokens, 0, user)

    # Load conversation history from Redis
    history = []
    if _redis and body.session_id:
        raw = _redis.get(f"history:{user}:{body.session_id}")
        if raw:
            history = json.loads(raw)

    logger.info(json.dumps({
        "event": "agent_call",
        "q_len": len(body.question),
        "history_len": len(history),
        "session": body.session_id,
        "client": str(request.client.host) if request.client else "unknown",
    }))

    answer = await run_agent(
        question=body.question,
        project=settings.vertex_project,
        location=settings.vertex_location,
        model=settings.vertex_model,
        history=history,
    )

    # Save updated history to Redis
    if _redis and body.session_id:
        history.append({"role": "user", "content": body.question})
        history.append({"role": "assistant", "content": answer})
        _redis.setex(f"history:{user}:{body.session_id}", 3600, json.dumps(history[-20:]))

    output_tokens = len(answer.split()) * 2
    check_and_record_cost(0, output_tokens, user)

    return AskResponse(
        question=body.question,
        answer=answer,
        model=f"vertex/{settings.vertex_model}",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/health", tags=["Operations"])
def health():
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.environment,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "llm": f"vertex/{settings.vertex_model}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if _redis:
        try:
            _redis.ping()
        except Exception:
            raise HTTPException(503, "Redis unavailable")
    return {"ready": True, "redis": _redis is not None}


@app.get("/metrics", tags=["Operations"])
def metrics(_key: str = Depends(verify_api_key)):
    return {
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _request_count,
        "error_count": _error_count,
        "daily_cost_usd": round(_daily_cost, 6),
        "daily_budget_usd": settings.daily_budget_usd,
    }


# ─────────────────────────────────────────────────────────
# Graceful Shutdown
# ─────────────────────────────────────────────────────────
def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
