# Deployment

## Live URL

https://day12agent-production.up.railway.app

## Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/` | GET | None | App info |
| `/health` | GET | None | Health check |
| `/ready` | GET | None | Readiness probe |
| `/ask` | POST | X-API-Key | Legal compliance agent |
| `/metrics` | GET | X-API-Key | Runtime metrics |

## Test

```bash
# Health check
curl https://day12agent-production.up.railway.app/health

# Ask the agent
curl -X POST https://day12agent-production.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <AGENT_API_KEY>" \
  -d '{"question": "What are the penalties for NDA breach?"}'
```

## Stack

- **Runtime**: Python 3.11, FastAPI, Uvicorn
- **Agent**: LangGraph ReAct + Vertex AI Gemini 2.5 Flash
- **Platform**: Railway (Docker, single replica)
- **Auth**: API Key (`X-API-Key` header)
- **Rate limit**: 10 req/min per key
