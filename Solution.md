# Day 12 Lab - Mission Answers

> **Student Name:** Nguyễn Thái Dương  
> **Student ID:** 2A202600823  
> **Date:** 2026-06-12

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`

1. **API key & credentials hardcode trong code** (dòng 17-18)  
   `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@..."` — Push lên GitHub là lộ credentials ngay lập tức.

2. **Config cứng trong code, không đọc từ environment** (dòng 21-22)  
   `DEBUG = True`, `MAX_TOKENS = 500` viết thẳng trong code — muốn thay đổi phải sửa code và redeploy, không thể điều chỉnh theo môi trường.

3. **Dùng `print()` thay vì logging, và log ra secret** (dòng 33-34)  
   `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` — vừa không có log level, vừa in secret ra stdout để lộ trong log aggregator.

4. **Không có health check endpoint** (dòng 42-43)  
   Không có `/health` — khi container crash, platform (Railway/Render/K8s) không biết để tự động restart.

5. **Host `localhost`, port cứng, `reload=True` trong production** (dòng 51-53)  
   `host="localhost"` khiến container không nhận traffic từ bên ngoài; `port=8000` cứng gây conflict; `reload=True` là debug mode không nên chạy trong production.

---

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Tại sao quan trọng? |
|---------|---------|------------|---------------------|
| Config | Hardcode trong code | Environment variables qua `config.py` | Thay đổi config không cần sửa code; không lộ secrets trong git history |
| Health check | Không có | `/health` (liveness) + `/ready` (readiness) | Platform tự restart khi crash; load balancer biết khi nào route traffic |
| Logging | `print()` + log secret | JSON structured logging, không log secrets | Dễ parse bởi Datadog/Loki; filter theo level; không lộ credentials |
| Shutdown | Đột ngột (process kill) | `SIGTERM` handler + lifespan context manager | Request đang chạy được hoàn thành trước khi tắt, tránh mất data |
| Host/Port | `localhost:8000` cứng | `0.0.0.0` + `PORT` từ env var | Container mới nhận được traffic từ bên ngoài; cloud inject PORT tự động |

---

## Part 2: Docker

### Câu hỏi thảo luận Section 2

**1. Tại sao `COPY requirements.txt .` rồi `RUN pip install` TRƯỚC khi `COPY . .`?**

Docker build theo từng layer và cache lại. Nếu `requirements.txt` không thay đổi, Docker dùng lại layer `pip install` từ cache → build rất nhanh. Nếu COPY tất cả code cùng lúc thì mỗi lần sửa 1 dòng code, Docker phải chạy lại `pip install` toàn bộ dù requirements không đổi → mất thêm vài phút mỗi lần build.

**2. `.dockerignore` nên chứa những gì? Tại sao `venv/` và `.env` quan trọng?**

```
.venv/
.env
.env.local
__pycache__/
*.pyc
.git/
*.log
```
- `venv/` — thư mục hàng GB, không cần thiết trong container vì Docker cài dependencies riêng
- `.env` — chứa secrets (API key, password). Nếu bị COPY vào image thì ai pull image về đều thấy secrets → rất nguy hiểm

**3. Nếu agent cần đọc file từ disk, làm sao mount volume vào container?**

```bash
docker run -p 8000:8000 -v ./data:/app/data agent-develop
# hoặc trong docker-compose.yml:
volumes:
  - ./data:/app/data
```
Volume mount cho phép container đọc/ghi file trên máy host. Data persist sau khi container bị xóa.

---

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image là gì?**  
   `python:3.11` — full Python distribution (~1 GB, bao gồm compiler, tools, documentation).

2. **Working directory là gì?**  
   `/app` — tất cả file của app được đặt trong thư mục này bên trong container.

3. **Tại sao COPY requirements.txt trước khi COPY code?**  
   Docker build theo từng layer. Nếu chỉ code thay đổi mà requirements không đổi, Docker dùng lại layer cache của bước `pip install` → build nhanh hơn nhiều. Nếu COPY tất cả cùng lúc thì mỗi lần sửa code sẽ phải cài lại toàn bộ dependencies.

4. **CMD vs ENTRYPOINT khác nhau thế nào?**  
   `CMD` là default command có thể bị override khi chạy `docker run <image> <other_command>`. `ENTRYPOINT` là fixed command, không bị override (chỉ có thể thêm arguments). Dùng `ENTRYPOINT` khi muốn container luôn chạy đúng 1 process cụ thể.

---

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`)

- **Stage 1 (builder) làm gì?**  
  Dùng `python:3.11-slim` + cài `gcc`, `libpq-dev` (build tools), sau đó `pip install --user` toàn bộ dependencies vào `/root/.local`. Image này **không được deploy**.

- **Stage 2 (runtime) làm gì?**  
  Dùng `python:3.11-slim` sạch, chỉ COPY `/root/.local` (packages đã compile) từ stage builder sang, COPY source code, tạo non-root user, set PATH. Image này là image **cuối cùng được deploy**.

- **Tại sao image nhỏ hơn?**  
  Stage 2 không có `gcc`, `libpq-dev`, pip cache, hay bất kỳ build tool nào — chỉ chứa Python runtime và packages cần thiết để chạy. Kết quả image nhỏ hơn đáng kể, ít attack surface hơn.

---

### Exercise 2.4: Docker Compose stack architecture

```
Client (browser/curl)
        │
        ▼ port 80/443
  ┌──────────┐
  │  Nginx   │  ← Reverse proxy, load balancer
  └────┬─────┘
       │ internal network
   ┌───┴───┐
   ▼       ▼
┌──────┐ ┌──────┐   ← agent service (có thể scale nhiều replicas)
│Agent │ │Agent │     port 8000, không expose ra ngoài
└──┬───┘ └──┬───┘
   └────┬───┘
        ▼
  ┌──────────┐
  │  Redis   │  ← Cache, session, rate limiting
  └──────────┘
        
  ┌──────────┐
  │  Qdrant  │  ← Vector database cho RAG
  └──────────┘
```

**Services được start:** `nginx`, `agent` (2 replicas), `redis`, `qdrant`  
**Communicate:** Qua internal Docker network `internal` (bridge). Nginx nhận traffic bên ngoài và forward vào agent. Agent đọc/ghi Redis và Qdrant qua service name (DNS tự động trong Docker network).

---

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- **URL:** https://day12agent-production.up.railway.app
- **Platform:** Railway

### Câu hỏi thảo luận Section 3

**1. Tại sao serverless (Lambda) không phải lúc nào cũng tốt cho AI agent?**

Serverless (Lambda) bị giới hạn thời gian chạy tối đa (thường 15 phút với AWS Lambda) và timeout thấp cho HTTP request. AI agent gọi LLM có thể mất vài giây đến vài chục giây — nếu kèm streaming hay multi-step reasoning thì dễ vượt giới hạn. Ngoài ra Lambda không giữ kết nối persistent (WebSocket khó), không lưu in-memory state giữa các invocation, và cold start gây delay khó chịu cho user.

**2. "Cold start" là gì? Ảnh hưởng thế nào đến UX?**

Cold start là thời gian khởi động container/function từ trạng thái "lạnh" (chưa chạy) — tải code, khởi tạo runtime, load model/dependencies. Với serverless, nếu không có request trong vài phút thì instance bị tắt, request tiếp theo phải chờ cold start (có thể 2-10 giây). Với AI agent, user gửi câu hỏi mà chờ 5 giây mới có response → UX rất tệ, dễ tưởng app bị lỗi.

**3. Khi nào nên upgrade từ Railway lên Cloud Run?**

- Traffic tăng vượt giới hạn Railway free/hobby plan
- Cần auto-scaling linh hoạt (scale to zero hoặc scale to nhiều instances theo traffic)
- Cần SLA cao hơn và uptime đảm bảo
- Cần tích hợp sâu với hệ sinh thái GCP (BigQuery, Vertex AI, Cloud Storage...)
- Team lớn cần CI/CD pipeline phức tạp với `cloudbuild.yaml`
- Cần deploy ở nhiều region khác nhau

---

### Exercise 3.2: So sánh `render.yaml` vs `railway.toml`

| Điểm so sánh | `railway.toml` | `render.yaml` |
|---|---|---|
| Format | TOML | YAML |
| Build config | `builder = "NIXPACKS"` hoặc `"DOCKERFILE"` | `type: web`, tự detect hoặc chỉ định `buildCommand` |
| Start command | `startCommand = "uvicorn ..."` | `startCommand: uvicorn ...` |
| Health check | `healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Restart policy | `restartPolicyType = "ON_FAILURE"` | Tự động, không cần cấu hình |
| Env vars | Set qua CLI hoặc dashboard (không trong file) | Có thể khai báo `envVars` trong file |

---

## Part 4: API Security

### Câu hỏi thảo luận Section 4

**1. Khi nào nên dùng API Key vs JWT vs OAuth2?**

- **API Key** — dùng cho server-to-server (backend gọi backend), script tự động, không có khái niệm "user". Đơn giản, dễ implement, dễ rotate.
- **JWT** — dùng khi có user login, cần phân quyền theo role, stateless. Token chứa thông tin user nên không cần query DB mỗi request.
- **OAuth2** — dùng khi app cần truy cập tài nguyên của bên thứ ba thay mặt user (đăng nhập bằng Google, GitHub...). Phức tạp nhất nhưng chuẩn nhất cho production.

**2. Rate limit nên đặt bao nhiêu request/phút cho một AI agent?**

Phụ thuộc vào model và cost, nhưng hướng dẫn chung:
- Free tier: 5-10 req/phút
- Paid user: 20-60 req/phút
- Admin/internal: 100-500 req/phút

Nên theo dõi latency thực tế của LLM (~1-3 giây/request) để tránh set limit cao hơn khả năng xử lý thực tế, dẫn đến queue dài và timeout.

**3. Nếu API key bị lộ, bạn phát hiện và xử lý như thế nào?**

- **Phát hiện:** Monitor bất thường — spike đột ngột về số request, request từ IP lạ, cost tăng vọt. Dùng alerting (Datadog, Grafana) set threshold.
- **Xử lý ngay:** Revoke key cũ ngay lập tức, tạo key mới, update environment variable trên server và restart.
- **Phòng ngừa:** Không commit key vào git (dùng `.gitignore`), rotate key định kỳ, dùng secret manager (AWS Secrets Manager, Railway Variables).

---

### Exercise 4.1: API Key authentication

**API key được check ở đâu?**  
Trong `verify_api_key()` function dùng FastAPI `Security(APIKeyHeader(...))` — header `X-API-Key` được extract và so sánh với `settings.agent_api_key`.

**Điều gì xảy ra nếu sai key?**  
Raise `HTTPException(status_code=401)` với message "Invalid or missing API key".

**Làm sao rotate key?**  
Chỉ cần thay giá trị `AGENT_API_KEY` trong environment variables và restart service — không cần sửa code.

**Test results:**
```bash
# Không có key → 401
curl http://localhost:8000/ask -X POST -d '{"question":"Hello"}'
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

# Có key đúng → 200
curl http://localhost:8000/ask -X POST -H "X-API-Key: my-secret-key" -d '{"question":"Hello"}'
{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock)..."}
```

---

### Exercise 4.2: JWT flow

1. Client gửi `POST /auth/token` với `username` + `password`
2. Server verify credentials trong `DEMO_USERS`, tạo JWT bằng `jwt.encode()` với payload chứa `sub` (username), `role`, `iat`, `exp`
3. Client nhận JWT, đính kèm vào request sau: `Authorization: Bearer <token>`
4. Server decode JWT bằng `jwt.decode()`, verify signature và expiry, extract user info
5. Nếu token expired → 401; nếu invalid → 403

**Ưu điểm JWT so với API key:** Stateless (không cần query DB mỗi request), chứa thông tin user (role), có expiry tự động.

**Test results:**
```bash
# Lấy token
curl http://localhost:8000/auth/token -X POST -d '{"username":"student","password":"demo123"}'
{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...","token_type":"bearer","expires_in_minutes":60}

# Dùng token gọi API → 200
curl http://localhost:8000/ask -X POST \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -d '{"question":"Explain JWT"}'
{"question":"Explain JWT","answer":"Agent đang hoạt động tốt!...","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

---

### Exercise 4.3: Rate limiting

**Algorithm:** Sliding Window Counter — mỗi user có 1 deque lưu timestamps các request trong 60 giây gần nhất. Mỗi request mới, xóa timestamps cũ ngoài window, đếm còn lại.

**Limit:** User thường: 10 req/phút; Admin: 100 req/phút (2 singleton instances trong `rate_limiter.py`)

**Bypass cho admin:** Dùng instance `rate_limiter_admin` (100 req/min) thay vì `rate_limiter_user` (10 req/min) dựa trên `role` trong JWT payload.

**Test results:**
```
Request 1-9:  200 OK  — {"requests_remaining": 8..0}
Request 10:   429     — {"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":3}
Request 11-15: 429    — Rate limit exceeded
```
Rate limiter hoạt động đúng — chặn từ request thứ 10 trở đi, tự reset sau 60 giây.

---

### Exercise 4.4: Cost guard implementation

```python
import redis
from datetime import datetime

r = redis.Redis()

def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False
    
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # 32 days TTL, tự reset đầu tháng
    return True
```

**Approach:** Dùng Redis key theo format `budget:{user_id}:{YYYY-MM}` để track spending theo tháng. TTL 32 ngày đảm bảo key tự xóa sau khi tháng qua. `incrbyfloat` atomic nên thread-safe khi scale nhiều instances.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")
def health():
    # Liveness probe — container còn sống không?
    return {"status": "ok", "uptime_seconds": round(time.time() - START_TIME, 1)}

@app.get("/ready")
def ready():
    # Readiness probe — sẵn sàng nhận traffic không?
    if not _is_ready:
        raise HTTPException(503, "Not ready")
    try:
        _redis.ping()  # check Redis
        return {"ready": True}
    except Exception:
        raise HTTPException(503, "Redis not available")
```

**Sự khác biệt:** `/health` (liveness) — "process có còn chạy không?" → platform restart nếu fail. `/ready` (readiness) — "có thể nhận request không?" → load balancer ngừng route traffic nếu fail, nhưng không restart container.

---

### Exercise 5.2: Graceful shutdown

```python
import signal

def shutdown_handler(signum, frame):
    logger.info("Received SIGTERM — graceful shutdown initiated")
    # uvicorn xử lý việc hoàn thành in-flight requests
    # cleanup connections, flush buffers ở đây nếu cần

signal.signal(signal.SIGTERM, shutdown_handler)
```

Kết hợp với `uvicorn` flag `--timeout-graceful-shutdown 30` để cho 30 giây hoàn thành requests hiện tại trước khi force-kill.

---

### Exercise 5.3: Stateless design

**Anti-pattern (stateful):**
```python
conversation_history = {}  # dict trong memory của 1 instance

@app.post("/ask")
def ask(user_id: str, question: str):
    history = conversation_history.get(user_id, [])  # chỉ đúng nếu cùng instance
```

**Correct (stateless với Redis):**
```python
@app.post("/chat")
async def chat(body: ChatRequest):
    session_id = body.session_id or str(uuid.uuid4())
    append_to_history(session_id, "user", body.question)  # lưu vào Redis
    session = load_session(session_id)                     # đọc từ Redis
    answer = ask(body.question)
    append_to_history(session_id, "assistant", answer)
    return {"session_id": session_id, "answer": answer, "served_by": INSTANCE_ID}
```

**Tại sao quan trọng:** Khi scale ra 3 instances, request 1 có thể vào Instance A, request 2 vào Instance B. Nếu state trong memory, Instance B không có history của Instance A → bug. Redis là shared store cho tất cả instances.

---

### Exercise 5.4: Load balancing

Chạy `docker compose up --scale agent=3` — 3 instances start: `instance-df37c9`, `instance-978b6b`, `instance-037be3`.

**Test results:**
```
Request 1 → served_by: instance-df37c9  (storage: redis)
Request 2 → served_by: instance-037be3  (storage: redis)
Request 3 → served_by: instance-978b6b  (storage: redis)
Request 4 → served_by: instance-df37c9  ← round-robin lặp lại
Request 5 → served_by: instance-037be3
Request 6 → served_by: instance-978b6b
```
Nginx phân tán đều theo round-robin. Tất cả dùng `storage: redis` — stateless.

---

### Exercise 5.5: Test stateless

`test_stateless.py` hoạt động như sau:
1. Tạo conversation qua `/chat` (lấy `session_id`)
2. Kill random instance bằng `docker stop`
3. Tiếp tục chat với `session_id` cũ → conversation history vẫn còn trong Redis
4. Response vẫn trả về đúng, chỉ `served_by` thay đổi sang instance khác

**Kết quả:** Stateless design hoạt động — session không mất khi instance chết. Bất kỳ instance nào cũng đọc được session từ Redis.
