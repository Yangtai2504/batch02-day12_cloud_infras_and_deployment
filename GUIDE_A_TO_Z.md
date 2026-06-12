# Hướng dẫn A-Z — Day 12: Cloud Infrastructure & Deployment

## Mục tiêu

Nộp 2 thứ trước deadline:
1. `Solution.md` — đáp án Parts 1-5
2. `06-lab-complete/` — personal agent từ buổi trước, productionized + deployed

---

## PHẦN 1: Solution.md (Parts 1-5)

### Part 1 — Localhost vs Production

Chạy app develop:
```bash
cd 01-localhost-vs-production
pip install -r requirements.txt
python develop/app.py        # chạy trên port 5000
python production/app.py     # chạy trên port 8000
```

**Câu hỏi thảo luận cần trả lời:**
- Sự khác biệt giữa develop vs production config?
- Tại sao production dùng `0.0.0.0` thay vì `127.0.0.1`?
- Vai trò của environment variables?

**Trả lời mẫu:**
- Develop: debug=True, hot reload, log verbose. Production: debug=False, log JSON, bind 0.0.0.0
- `0.0.0.0` = lắng nghe mọi network interface, cần thiết trong container/cloud
- Env vars: tách config khỏi code (12-factor app), không hardcode secrets

### Part 2 — Docker

```bash
cd 02-docker
docker build -t myapp .
docker run -p 8000:8000 myapp
curl http://localhost:8000/health
```

**Câu hỏi thảo luận:**
- Multi-stage build giảm image size như thế nào?
- Tại sao không chạy container với root user?
- `.dockerignore` có tác dụng gì?

**Trả lời mẫu:**
- Stage builder: cài dependencies nặng. Stage runtime: chỉ copy output → image nhỏ hơn 60-70%
- Non-root: nếu container bị compromise, attacker không có root access trên host
- `.dockerignore`: loại trừ `.env`, `__pycache__`, `.git` → build nhanh hơn, không leak secrets

### Part 3 — Cloud Deployment

```bash
cd 03-cloud-deployment
# Xem railway.toml / render.yaml để hiểu cấu hình
```

**Câu hỏi thảo luận:**
- Sự khác biệt giữa PaaS (Railway/Render) và IaaS (EC2)?
- Environment variables trên cloud được set ở đâu?
- Zero-downtime deployment là gì?

**Trả lời mẫu:**
- PaaS: managed infra, tự scale, CI/CD built-in. IaaS: tự quản lý OS, more control
- Cloud env vars: Railway Dashboard → Variables, không bao giờ commit lên git
- Zero-downtime: deploy version mới song song → health check pass → swap traffic → terminate old

### Part 4 — API Gateway

```bash
cd 04-api-gateway
docker compose up
# Test API key auth
curl -H "X-API-Key: valid-key" http://localhost/ask
curl -H "X-API-Key: wrong-key" http://localhost/ask  # → 401
# Test rate limiting
for i in $(seq 1 12); do curl -s -H "X-API-Key: valid-key" http://localhost/ask -X POST -d '{}'; done
# Request 11+ → 429
```

**Câu hỏi thảo luận:**
- API Key vs JWT: khi nào dùng cái nào?
- Sliding window rate limiting hoạt động thế nào?
- Cost guard giúp gì?

**Trả lời mẫu:**
- API Key: service-to-service, stateless, đơn giản. JWT: user auth, có expiry, carry claims
- Sliding window: đếm requests trong 60s gần nhất, reject nếu vượt limit
- Cost guard: cap chi phí LLM theo ngày/tháng, tránh bill sốc

### Part 5 — Scaling & Reliability

```bash
cd 05-scaling-reliability
cp .env.example .env.local   # tạo file .env.local rỗng nếu chưa có
docker compose up --scale agent=3
# Test load balancing
for i in $(seq 1 9); do curl -s http://localhost/health | python -m json.tool; done
# Xem container_id khác nhau → đang load balance
```

**Câu hỏi thảo luận:**
- Horizontal vs Vertical scaling?
- Stateless design quan trọng thế nào khi scale?
- Health check và readiness probe khác nhau thế nào?

**Trả lời mẫu:**
- Horizontal: thêm nhiều instance. Vertical: tăng CPU/RAM instance hiện tại
- Stateless: mỗi request tự chứa đủ thông tin → bất kỳ instance nào cũng serve được
- Health: "app còn sống không?" Readiness: "app sẵn sàng nhận traffic chưa?" (e.g., DB connected?)

### Viết Solution.md

Tạo file `Solution.md` ở root repo với đáp án tất cả câu hỏi trên.

---

## PHẦN 2: Productionize Personal Agent

### Bước 1: Chọn agent từ buổi trước

Chọn một agent đã build (Day 9, 10, 11...) có LLM thực (không dùng mock). Ví dụ: LangGraph agent dùng Vertex AI, OpenAI, hoặc Groq.

### Bước 2: Cấu trúc thư mục

Xóa nội dung cũ trong `06-lab-complete/app/` và tạo lại:

```
06-lab-complete/
├── app/
│   ├── __init__.py
│   ├── main.py       ← FastAPI app (production patterns)
│   ├── agent.py      ← Logic agent từ buổi trước
│   └── config.py     ← Config từ env vars
├── Dockerfile
├── docker-compose.yml
├── railway.toml
├── requirements.txt
├── .env.example
├── .dockerignore
└── check_production_ready.py
```

### Bước 3: app/config.py

```python
import os
from dataclasses import dataclass, field

@dataclass
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "My Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    # LLM credentials — thay đổi tùy agent bạn dùng
    # Nếu dùng Vertex AI:
    vertex_project: str = field(default_factory=lambda: os.getenv("VERTEX_PROJECT", ""))
    vertex_location: str = field(default_factory=lambda: os.getenv("VERTEX_LOCATION", "us-central1"))
    vertex_model: str = field(default_factory=lambda: os.getenv("VERTEX_MODEL", "gemini-2.5-flash"))
    google_credentials_json: str = field(default_factory=lambda: os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON", ""))
    # Nếu dùng OpenAI: openai_api_key = os.getenv("OPENAI_API_KEY", "")
    # Nếu dùng Groq:   groq_api_key = os.getenv("GROQ_API_KEY", "")

    # Redis (cho conversation history)
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))

    # Security
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    allowed_origins: list = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*").split(","))

    # Rate & Budget
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))
    daily_budget_usd: float = field(default_factory=lambda: float(os.getenv("DAILY_BUDGET_USD", "5.0")))

    def validate(self):
        if self.environment == "production" and self.agent_api_key == "dev-key-change-me":
            raise ValueError("AGENT_API_KEY must be set in production!")
        return self

settings = Settings().validate()
```

### Bước 4: app/agent.py

Copy logic agent từ buổi trước vào đây. Đảm bảo:
- Credentials được load từ env var (không hardcode path file)
- Có hàm `run_agent(question, ..., history=None) -> str` async

**Ví dụ cho Vertex AI:**
```python
import os, tempfile, logging
from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

def setup_vertex_credentials(credentials_json: str):
    """Ghi JSON credentials từ env var ra file tạm, set GOOGLE_APPLICATION_CREDENTIALS."""
    if not credentials_json:
        return
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    tmp.write(credentials_json)
    tmp.flush()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

# --- Định nghĩa tools của agent ---
@tool
def my_tool(query: str) -> str:
    """Tool description."""
    return f"Result for {query}"

TOOLS = [my_tool]
SYSTEM_PROMPT = "You are a helpful agent."

async def run_agent(question: str, project: str, location: str, model: str, history=None) -> str:
    llm = ChatVertexAI(model=model, project=project, location=location, temperature=0.3,
                       model_kwargs={"thinking_config": {"thinking_budget": 0}})
    graph = create_react_agent(model=llm, tools=TOOLS, prompt=SYSTEM_PROMPT)
    messages = list(history or []) + [{"role": "user", "content": question}]

    final = ""
    async for chunk in graph.astream({"messages": messages}, stream_mode="updates"):
        for _, update in chunk.items():
            for msg in update.get("messages", []):
                if msg.type == "ai" and msg.content:
                    text = msg.content if isinstance(msg.content, str) else \
                           "".join(b.get("text","") for b in msg.content if isinstance(b,dict))
                    if text:
                        final = text
    return final or "No answer."
```

**Nếu dùng OpenAI thay Vertex AI:**
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.openai_api_key)
```

### Bước 5: app/main.py

```python
import os, time, signal, logging, json
from datetime import datetime, timezone
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Optional

import redis as redis_lib
from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from app.config import settings
from app.agent import setup_vertex_credentials, run_agent  # điều chỉnh import theo agent của bạn

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
_rate_windows: dict = defaultdict(deque)

# ── Rate Limiter ──────────────────────────────────────────
def check_rate_limit(user: str):
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
            raise HTTPException(429, f"Rate limit: {settings.rate_limit_per_minute} req/min",
                                headers={"Retry-After": "60"})
    else:
        window = _rate_windows[user]
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= settings.rate_limit_per_minute:
            raise HTTPException(429, f"Rate limit: {settings.rate_limit_per_minute} req/min",
                                headers={"Retry-After": "60"})
        window.append(now)

# ── Cost Guard ───────────────────────────────────────────
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
            raise HTTPException(503, "Daily budget exhausted.")
        _daily_cost += cost

# ── Auth ─────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(401, "Invalid or missing API key. Include header: X-API-Key: <key>")
    return api_key

# ── Lifespan ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _redis
    # Setup LLM credentials
    setup_vertex_credentials(settings.google_credentials_json)
    # Connect Redis
    if settings.redis_url:
        try:
            _redis = redis_lib.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)
            _redis.ping()
            logger.info(json.dumps({"event": "redis_connected"}))
        except Exception as e:
            logger.warning(json.dumps({"event": "redis_unavailable", "error": str(e)}))
            _redis = None
    logger.info(json.dumps({"event": "startup", "app": settings.app_name, "redis": _redis is not None}))
    _is_ready = True
    yield
    _is_ready = False
    if _redis:
        _redis.close()
    logger.info(json.dumps({"event": "shutdown"}))

# ── App ──────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins,
                   allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-API-Key"])

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
        logger.info(json.dumps({"event": "request", "method": request.method,
                                "path": request.url.path, "status": response.status_code,
                                "ms": round((time.time() - start) * 1000, 1)}))
        return response
    except Exception:
        _error_count += 1
        raise

# ── Models ───────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(None, max_length=64)

class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    timestamp: str

# ── Endpoints ────────────────────────────────────────────
@app.get("/")
def root():
    return {"app": settings.app_name, "version": settings.app_version,
            "environment": settings.environment}

@app.post("/ask", response_model=AskResponse)
async def ask_agent(body: AskRequest, request: Request, _key: str = Depends(verify_api_key)):
    user = _key[:16]
    check_rate_limit(user)
    check_and_record_cost(len(body.question.split()) * 2, 0, user)

    # Load conversation history
    history = []
    if _redis and body.session_id:
        raw = _redis.get(f"history:{user}:{body.session_id}")
        if raw:
            history = json.loads(raw)

    logger.info(json.dumps({"event": "agent_call", "q_len": len(body.question),
                            "history_len": len(history), "session": body.session_id}))

    # Gọi agent — điều chỉnh params tùy agent của bạn
    answer = await run_agent(
        question=body.question,
        project=settings.vertex_project,
        location=settings.vertex_location,
        model=settings.vertex_model,
        history=history,
    )

    # Save history
    if _redis and body.session_id:
        history.append({"role": "user", "content": body.question})
        history.append({"role": "assistant", "content": answer})
        _redis.setex(f"history:{user}:{body.session_id}", 3600, json.dumps(history[-20:]))

    check_and_record_cost(0, len(answer.split()) * 2, user)
    return AskResponse(question=body.question, answer=answer,
                       model=f"vertex/{settings.vertex_model}",
                       timestamp=datetime.now(timezone.utc).isoformat())

@app.get("/health")
def health():
    return {"status": "ok", "version": settings.app_version, "environment": settings.environment,
            "uptime_seconds": round(time.time() - START_TIME, 1),
            "total_requests": _request_count}

@app.get("/ready")
def ready():
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    if _redis:
        try:
            _redis.ping()
        except Exception:
            raise HTTPException(503, "Redis unavailable")
    return {"ready": True, "redis": _redis is not None}

@app.get("/metrics")
def metrics(_key: str = Depends(verify_api_key)):
    return {"uptime_seconds": round(time.time() - START_TIME, 1),
            "total_requests": _request_count, "error_count": _error_count,
            "daily_cost_usd": round(_daily_cost, 6)}

def _handle_signal(signum, _frame):
    logger.info(json.dumps({"event": "signal", "signum": signum}))

signal.signal(signal.SIGTERM, _handle_signal)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port,
                reload=settings.debug, timeout_graceful_shutdown=30)
```

### Bước 6: Dockerfile

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim AS runtime
RUN groupadd -r agent && useradd -r -g agent agent
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app/ ./app/
RUN chown -R agent:agent /app
USER agent
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8000')+'/health')" || exit 1
CMD ["python", "app/main.py"]
```

### Bước 7: railway.toml

```toml
[build]
builder = "DOCKERFILE"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

**Quan trọng: KHÔNG đặt `startCommand`** — để Dockerfile CMD tự xử lý PORT.

### Bước 8: requirements.txt

```
fastapi>=0.115.0
uvicorn[standard]>=0.34.0
pydantic>=2.11.0
python-dotenv>=1.1.0
redis>=5.0.0
# Thêm dependencies của agent:
langgraph>=0.4.1
langchain-core>=0.3.0
langchain-google-vertexai>=2.0.0   # nếu dùng Vertex AI
# langchain-openai>=0.2.0           # nếu dùng OpenAI
```

### Bước 9: .env.example

```
HOST=0.0.0.0
PORT=8000
ENVIRONMENT=development

APP_NAME=My Agent
APP_VERSION=1.0.0

VERTEX_PROJECT=your-gcp-project
VERTEX_LOCATION=us-central1
VERTEX_MODEL=gemini-2.5-flash
GOOGLE_APPLICATION_CREDENTIALS_JSON=   # paste nội dung file .json (1 dòng)

REDIS_URL=

AGENT_API_KEY=dev-key-change-me-in-production
RATE_LIMIT_PER_MINUTE=10
DAILY_BUDGET_USD=5.0
ALLOWED_ORIGINS=*
```

### Bước 10: Kiểm tra local

```bash
cd 06-lab-complete
python check_production_ready.py
# Phải đạt 20/20
```

---

## PHẦN 3: Deploy lên Railway

### 1. Tạo tài khoản Railway
Vào railway.com → Sign up với GitHub.

### 2. Push code lên GitHub
```bash
git add .
git commit -m "Add productionized agent"
git push
```

Đảm bảo repo **public** để instructor xem được.

### 3. Tạo project trên Railway
- Railway Dashboard → **New Project** → **Deploy from GitHub repo**
- Chọn repo → chọn branch `main`

### 4. Set Root Directory
Service → **Settings** → **Source** → **Add Root Directory** → nhập `06-lab-complete`

### 5. Set Environment Variables
Service → **Variables** → thêm từng biến:

| Key | Value |
|-----|-------|
| `AGENT_API_KEY` | key bí mật của bạn |
| `ENVIRONMENT` | `production` |
| `VERTEX_PROJECT` | GCP project ID |
| `VERTEX_LOCATION` | `us-central1` |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | nội dung file vertex-key.json (paste nguyên JSON) |

### 6. Thêm Redis
Railway Dashboard → project → **+ Add** → **Database** → **Redis**

Sau khi Redis tạo xong:
- Vào service **day12_agent** → **Variables** → **+ New Variable**
- Tên: `REDIS_URL`, giá trị: click biểu tượng ⚡ → chọn **Redis → REDIS_URL**
- **Add** → **Deploy**

### 7. Kiểm tra deploy
Sau khi build xong, vào tab **Deploy Logs** → thấy:
```
Healthcheck succeeded!
```

---

## PHẦN 4: Test

```bash
# Health check
curl https://YOUR-APP.up.railway.app/health

# Ask agent (không history)
curl -X POST https://YOUR-APP.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"question": "Your question here"}'

# Ask với conversation history (cùng session_id)
curl -X POST https://YOUR-APP.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"question": "First question", "session_id": "session-1"}'

curl -X POST https://YOUR-APP.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"question": "Follow-up question about it", "session_id": "session-1"}'
```

---

## Các lỗi thường gặp

| Lỗi | Nguyên nhân | Fix |
|-----|------------|-----|
| `$PORT is not a valid integer` | `startCommand` trong railway.toml dùng `$PORT` | Xóa `startCommand`, dùng Dockerfile CMD |
| `ModuleNotFoundError: uvicorn` | `pip install --user` + non-root user conflict | Dùng `pip install --prefix=/install` trong builder |
| `MutableHeaders has no pop()` | FastAPI headers không có `.pop()` | Dùng `del response.headers["server"]` |
| `Railpack could not determine how to build` | Railway build từ root thay vì subfolder | Set Root Directory = `06-lab-complete` |
| Healthcheck failed (startup crash) | App crash khi start | Xem Deploy Logs để tìm traceback |

---

## Checklist cuối

- [ ] `Solution.md` có đáp án Parts 1-5 ở root repo
- [ ] `06-lab-complete/` có agent thực (không mock)
- [ ] `python check_production_ready.py` → 20/20
- [ ] Railway deploy thành công, `/health` trả 200
- [ ] `/ask` trả lời đúng
- [ ] Conversation history hoạt động (test với session_id)
- [ ] Repo public trên GitHub
