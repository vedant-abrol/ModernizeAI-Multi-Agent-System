# ModernizeAI - Multi-Agent System

ModernizeAI is a multi-agent legacy application modernization assistant. A user uploads a Java/Spring Boot or Node.js repository zip, or enters a public GitHub repository URL, and the system produces an evidence-backed modernization report.

The MVP performs static analysis only. It does not execute uploaded code, install dependencies, deploy applications, delete files, or perform migrations. All recommendations require human review.

## Architecture

```text
User
 |
 v
Streamlit UI
 |
 v
FastAPI Backend
 |
 v
Safe ZIP / GitHub Ingestion
 |
 v
Repo Scanner Agent -> ChromaDB repo chunk index
 |
 v
Architecture Agent
 |
 v
Dependency Risk Agent
 |
 v
Security Agent
 |
 v
Test Strategy Agent
 |
 v
Modernization Planner Agent
 |
 v
Critic Agent
 |
 v
Report Agent -> Markdown report
```

## Agents

- Repo Scanner Agent: deterministic repository facts, framework detection, file classification, API inventory, and vector indexing.
- Architecture Agent: summarizes layers, API entry points, data access, and integrations from evidence.
- Dependency Risk Agent: parses Maven, Gradle, and npm dependency files and reports modernization risk without inventing CVEs.
- Security Agent: performs deterministic pattern scans for hardcoded secrets, exposed actuator settings, plaintext HTTP integrations, wildcard CORS, disabled CSRF, debug mode, and SQL concatenation patterns.
- Test Strategy Agent: identifies likely missing controller and service tests without claiming coverage percentages.
- Modernization Planner Agent: creates a phased AWS/cloud modernization roadmap and candidate service boundaries backed by files.
- Critic Agent: blocks unsupported claims and verifies that security findings and service candidates include evidence.
- Report Agent: renders the final Markdown report with an evidence appendix.

## Guardrails

- Uploaded repositories are treated as untrusted input.
- ZIP extraction prevents path traversal and skips suspicious binary/script extensions.
- Repository code is never executed.
- Secrets are redacted before indexing and report generation.
- Dependency findings are modernization risks unless a real vulnerability scanner is integrated.
- Microservice boundaries are candidates, not automatic refactoring instructions.
- Bedrock agent output is expected to be strict JSON when enabled.
- GitHub URL ingestion uses the GitHub API to find the default branch and download a zipball. Public repositories work without a token; private repositories require `GITHUB_TOKEN` or `GH_TOKEN` with repository read access.

## Tech Stack

- Frontend: Streamlit
- Backend: FastAPI
- Orchestration: LangGraph with a sequential fallback runner
- LLM provider: Amazon Bedrock
- Embeddings: Amazon Titan Text Embeddings V2 with deterministic local fallback for tests and pre-AWS demos
- Vector store: ChromaDB with in-memory fallback
- Deployment: Docker Compose on EC2
- Tests: Pytest

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
mkdir -p data/uploads data/repos data/reports data/chroma sample_repos
python3 scripts/create_sample_repo.py
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Start the UI in another terminal:

```bash
streamlit run frontend/streamlit_app.py --server.port 8501
```

Open `http://localhost:8501` and upload one of the generated sample repos:

- `sample_repos/legacy-order-management-system.zip` for a compact walkthrough.
- `sample_repos/legacy-claims-processing-platform.zip` for a richer demo with multiple domains, CI/CD files, security findings, and stronger modernization candidates.

## Bedrock Configuration

For local demos, `.env.example` keeps `MODERNIZEAI_USE_BEDROCK_AGENTS=false` so the app can produce deterministic reports before AWS credentials are connected. For the final AWS demo, set:

```env
MODERNIZEAI_USE_BEDROCK_AGENTS=true
MODERNIZEAI_USE_BEDROCK_EMBEDDINGS=true
AWS_REGION=us-east-1
BEDROCK_CHAT_MODEL_ID=us.anthropic.claude-opus-4-6-v1
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0
MODERNIZEAI_REQUIRE_BEDROCK_AGENTS=true
```

Attach an IAM role to EC2 with Bedrock runtime permissions instead of storing access keys in `.env`.

Claude Opus 4.6 should be called through a Bedrock inference profile. For `us-east-1`, use the US geo inference profile ID. Verify the real Bedrock call path before the final demo:

```bash
MODERNIZEAI_USE_BEDROCK_AGENTS=true \
BEDROCK_CHAT_MODEL_ID=us.anthropic.claude-opus-4-6-v1 \
python3 scripts/check_bedrock_nova.py
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8501`.

The FastAPI backend runs inside the same container as Streamlit and does not need to be exposed publicly for the demo.

## EC2 Deployment

Use an Ubuntu `t3.small` or `t3.medium` instance in `us-east-1`.

1. Enable Bedrock access for Amazon Titan Text Embeddings V2 and Anthropic Claude Opus 4.6.
2. Attach an IAM role with `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`.
3. Open inbound port `8501` for your IP or for a limited demo window.
4. Install Docker and clone this repo.
5. Copy `.env.example` to `.env`, set `MODERNIZEAI_USE_BEDROCK_AGENTS=true`, set `MODERNIZEAI_REQUIRE_BEDROCK_AGENTS=true`, and confirm the model IDs.
6. Run `docker compose up --build -d`.

## API

- `POST /analyze/upload`: upload repository zip.
- `POST /analyze/github`: analyze a `https://github.com/{owner}/{repo}` URL using the GitHub API. Public repositories work without a token; private repositories require `GITHUB_TOKEN` or `GH_TOKEN`.
- `GET /analysis/{analysis_id}/status`: return agent progress.
- `GET /analysis/{analysis_id}/report`: return Markdown report.
- `GET /analysis/{analysis_id}/evidence`: return scanner and agent evidence.

## Demo Script

1. Open Streamlit.
2. Upload `sample_repos/legacy-claims-processing-platform.zip` for the full demo, or `sample_repos/legacy-order-management-system.zip` for a shorter walkthrough.
3. Click Analyze Repository.
4. Show detected framework, controllers, services, repositories, security findings, missing tests, and service candidates.
5. Open the final report and evidence expander.
6. Download the Markdown report.

## Tests

```bash
pytest
```

The tests cover ZIP safety, secret redaction, scanner detection, and report generation.

## Known Limitations

- The MVP performs static analysis only.
- It does not execute tests or build the uploaded project.
- Dependency risks are not confirmed vulnerabilities without OSV or another scanner.
- Local ChromaDB storage is suitable for a demo; production should use a managed or server-backed vector store.
- Authentication and multi-user isolation are not implemented.
- Large repositories need better job queueing, chunking, and status streaming.

## Reference Links

- Amazon EC2 documentation: https://docs.aws.amazon.com/ec2/
- Amazon Bedrock documentation: https://docs.aws.amazon.com/bedrock/
- Amazon Bedrock Converse API: https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html
- Amazon Titan Text Embeddings: https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html
- Amazon Bedrock pricing: https://aws.amazon.com/bedrock/pricing/
- ChromaDB Python client: https://docs.trychroma.com/reference/python/client
- LangGraph overview: https://docs.langchain.com/oss/python/langgraph/overview
