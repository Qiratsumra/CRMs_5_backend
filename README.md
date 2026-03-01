# Customer Success FTE Backend

Multi-channel AI-powered customer support system with email, WhatsApp, and web form integration.

## Overview

This backend provides a production-ready customer success platform that:
- Handles customer inquiries across email, WhatsApp, and web forms
- Uses Gemini AI agent to provide intelligent responses
- Searches a knowledge base using vector embeddings
- Manages tickets, conversations, and customer history
- Escalates complex issues to human agents
- Provides real-time metrics and analytics

## Architecture

- **API Server**: FastAPI with REST endpoints
- **Agent**: OpenAI Agents SDK with Gemini 2.5 Flash
- **Database**: PostgreSQL (Neon) with pgvector for semantic search
- **Event Streaming**: Apache Kafka for message processing
- **Channels**:
  - Email: Gmail API + Google Pub/Sub
  - WhatsApp: whatsapp-mcp (Go bridge + Python MCP server)
  - Web Form: FastAPI endpoints

## Prerequisites

- Python 3.14+
- Docker & Docker Compose
- PostgreSQL (Neon DB account)
- Gemini API key
- Gmail API credentials (optional)
- WhatsApp account for whatsapp-mcp (optional)

## Quick Start

### 1. Clone and Setup

```bash
cd backend
cp .env.example .env
# Edit .env with your credentials
```

### 2. Install Dependencies

```bash
uv sync
```

### 3. Initialize Database

```bash
# Apply schema
psql "$DATABASE_URL" -f database/schema.sql

# Seed knowledge base
psql "$DATABASE_URL" -f database/seed.sql

# Generate embeddings
uv run python database/migrations/embed_knowledge_base.py
```

### 4. Start Services

```bash
docker compose up
```

The API will be available at `http://localhost:8000`

## WhatsApp Setup (whatsapp-mcp)

No Twilio or WhatsApp Business account needed. Uses your personal WhatsApp via the Web multidevice API.

### One-time setup

1. Clone whatsapp-mcp:
```bash
cd ..
git clone https://github.com/lharries/whatsapp-mcp.git
```

2. Start the Go bridge:
```bash
cd whatsapp-mcp/whatsapp-bridge
go run main.go
```

3. Scan the QR code:
   - Open WhatsApp on your phone
   - Go to Settings → Linked Devices
   - Tap "Link a Device"
   - Scan the QR code displayed in terminal

4. Configure environment:
```bash
# In backend/.env
WHATSAPP_MCP_SERVER_PATH=../whatsapp-mcp/whatsapp-mcp-server
WHATSAPP_OWN_NUMBER=+YOUR_NUMBER
```

5. Start the backend:
```bash
cd ../backend
docker compose up
```

The whatsapp-poller service will automatically pick up new messages.

**Note**: Re-authentication needed after ~20 days. Restart the Go bridge and re-scan the QR code.

## Environment Variables

See `.env.example` for all required variables:

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Gemini API key | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker address | Yes |
| `GMAIL_CREDENTIALS_JSON` | Path to Gmail OAuth credentials | No |
| `GMAIL_PUBSUB_TOPIC` | Gmail Pub/Sub topic | No |
| `WHATSAPP_MCP_SERVER_PATH` | Path to whatsapp-mcp server | No |
| `WHATSAPP_OWN_NUMBER` | Your WhatsApp number | No |
| `CORS_ORIGINS` | Allowed CORS origins | No |

## API Endpoints

### Health & Status

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health with channel status |
| GET | `/` | API info |

### Support (Web Form)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/support/submit` | Submit support request |
| GET | `/support/ticket/{id}` | Get ticket details |
| GET | `/support/tickets` | List tickets (filter by email) |
| GET | `/support/health` | Web form health check |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks/gmail` | Gmail Pub/Sub push notifications |

### Conversations & Customers

| Method | Path | Description |
|--------|------|-------------|
| GET | `/conversations/{id}` | Get conversation history |
| GET | `/customers/lookup` | Lookup customer by email/phone |

### Metrics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/metrics/channels` | 24h metrics per channel |
| GET | `/metrics/summary` | Overall system summary |

## Running Tests

```bash
# Install test dependencies
uv add --dev pytest pytest-asyncio httpx

# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_agent.py

# Run with coverage
uv run pytest --cov=. --cov-report=html
```

## Project Structure

```
backend/
├── agent/                      # AI agent logic
│   ├── customer_success_agent.py
│   ├── tools.py
│   ├── prompts.py
│   └── formatters.py
├── channels/                   # Channel handlers
│   ├── gmail_handler.py
│   ├── whatsapp_handler.py
│   └── web_form_handler.py
├── workers/                    # Background workers
│   ├── message_processor.py
│   └── whatsapp_poller.py
├── database/                   # Database layer
│   ├── schema.sql
│   ├── seed.sql
│   ├── queries.py
│   └── migrations/
├── tests/                      # Test suite
├── k8s/                        # Kubernetes manifests
├── main.py                     # FastAPI app
├── kafka_client.py             # Kafka producer/consumer
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## Kubernetes Deployment

### Prerequisites

- Kubernetes cluster (GKE, EKS, AKS, or local)
- kubectl configured
- Docker image built and pushed to registry

### Deploy

```bash
# Update image in deployment files
# Edit k8s/deployment-*.yaml and set your image

# Apply manifests
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secrets.yaml
kubectl apply -f k8s/deployment-api.yaml
kubectl apply -f k8s/deployment-worker.yaml
kubectl apply -f k8s/deployment-whatsapp-poller.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml

# Check status
kubectl get pods -n customer-success-fte
kubectl logs -f deployment/fte-api -n customer-success-fte
```

### Important Notes

- **WhatsApp Poller**: Must run exactly 1 replica (no HPA)
- **Secrets**: Update `k8s/secrets.yaml` with real credentials before deploying
- **Ingress**: Update host in `k8s/ingress.yaml` to your domain

## Development

### Local Development

```bash
# Start dependencies only
docker compose up kafka zookeeper

# Run API locally
uv run uvicorn main:app --reload --port 8000

# Run worker locally
uv run python workers/message_processor.py

# Run WhatsApp poller locally
uv run python workers/whatsapp_poller.py
```

### Adding New Tools

1. Define tool in `agent/tools.py`:
```python
@function_tool
async def my_new_tool(param: str) -> str:
    """Tool description."""
    # Implementation
    return result
```

2. Add to agent in `agent/customer_success_agent.py`:
```python
customer_success_agent = Agent(
    tools=[..., my_new_tool]
)
```

### Adding New Channels

1. Create handler in `channels/new_channel_handler.py`
2. Add normalization logic
3. Update `workers/message_processor.py` to handle new channel
4. Add Kafka topic in `kafka_client.py`

## Troubleshooting

### Database Connection Issues

```bash
# Test connection
psql "$DATABASE_URL" -c "SELECT 1"

# Check if extensions are installed
psql "$DATABASE_URL" -c "SELECT * FROM pg_extension"
```

### Kafka Issues

```bash
# Check Kafka topics
docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# View messages in topic
docker compose exec kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic fte.tickets.incoming \
  --from-beginning
```

### WhatsApp Not Receiving Messages

1. Check Go bridge is running: `ps aux | grep whatsapp-bridge`
2. Check QR code scan status in bridge logs
3. Verify `WHATSAPP_OWN_NUMBER` matches your number
4. Check poller logs: `docker compose logs whatsapp-poller`

### Agent Not Responding

1. Check Gemini API key is valid
2. View worker logs: `docker compose logs worker`
3. Check Kafka messages are being consumed
4. Verify database connectivity

## Performance Tuning

### Database

- Increase connection pool size in `database/queries.py`
- Add indexes for frequently queried fields
- Tune pgvector `lists` parameter for knowledge base

### Kafka

- Increase partition count for high-volume topics
- Tune consumer `max_poll_records`
- Enable compression

### Agent

- Use Gemini Flash for faster responses
- Cache knowledge base results
- Implement response streaming

## Security

- All secrets in environment variables (never commit)
- Database uses SSL (Neon requires it)
- API uses CORS restrictions
- Kubernetes secrets for production
- No passwords or credentials in logs

## Monitoring

### Metrics Available

- Response latency per channel
- Ticket creation rate
- Escalation rate
- Sentiment scores
- Knowledge base search effectiveness

### Logging

All services log to stdout in JSON format:
```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f api
docker compose logs -f worker
```

## Support

For issues or questions:
- Check logs: `docker compose logs`
- Review API docs: `http://localhost:8000/docs`
- Test health endpoint: `curl http://localhost:8000/health`

## License

Proprietary - TechCorp Internal Use Only
"# CRMs_5_backend" 
