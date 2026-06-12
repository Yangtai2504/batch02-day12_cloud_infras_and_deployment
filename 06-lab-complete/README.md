# Legal Compliance Agent — Production

Day 9 Stage 3 Legal Compliance Agent, productionized với Day 12 patterns.

**Live URL:** https://day12agent-production.up.railway.app

## Agent

Phân tích câu hỏi pháp lý (NDA breach, tax evasion, data privacy, SOX compliance) sử dụng LangGraph ReAct loop + Vertex AI Gemini 2.5 Flash. Có conversation history qua Redis.

## Production Checklist

- [x] Dockerfile (multi-stage, non-root user, < 200 MB)
- [x] Config từ environment variables (12-factor)
- [x] API Key authentication (`X-API-Key` header)
- [x] Rate limiting — 10 req/min per user (Redis sliding window)
- [x] Cost guard — monthly budget per user (Redis)
- [x] Conversation history (Redis, TTL 1h, session_id)
- [x] Health check (`GET /health`)
- [x] Readiness probe (`GET /ready`) — kiểm tra Redis
- [x] Graceful shutdown (SIGTERM)
- [x] Structured JSON logging
- [x] Stateless design (state trong Redis)
- [x] Deploy Railway với public URL

## Cấu Trúc

```
06-lab-complete/
├── app/
│   ├── main.py      # FastAPI app — auth, rate limit, cost guard, endpoints
│   ├── agent.py     # LangGraph ReAct agent + Vertex AI tools
│   └── config.py    # 12-factor config từ env vars
├── Dockerfile       # Multi-stage build
├── docker-compose.yml
├── railway.toml
├── requirements.txt
├── .env.example
└── check_production_ready.py
```

## Endpoints

| Endpoint | Method | Auth | Mô tả |
|----------|--------|------|-------|
| `/` | GET | — | App info |
| `/health` | GET | — | Health status |
| `/ready` | GET | — | Readiness + Redis check |
| `/ask` | POST | X-API-Key | Legal compliance question |
| `/metrics` | GET | X-API-Key | Runtime metrics |

## Chạy Local

```bash
cp .env.example .env
# Điền AGENT_API_KEY và GOOGLE_APPLICATION_CREDENTIALS_JSON vào .env

docker compose up
curl http://localhost:8000/health
```

## Test Live

```bash
# Health check
curl https://day12agent-production.up.railway.app/health

# Ask agent (không có history)
curl -X POST https://day12agent-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -d '{"question": "What are the penalties for NDA breach?"}'

# Ask với conversation history
curl -X POST https://day12agent-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -d '{"question": "What is NDA?", "session_id": "my-session"}'

curl -X POST https://day12agent-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -d '{"question": "What are the penalties for breaching it?", "session_id": "my-session"}'
```

## Production Readiness

```bash
python check_production_ready.py
# Result: 20/20 checks passed (100%)
```
