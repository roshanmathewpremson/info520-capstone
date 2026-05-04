# Agentic Career Coach (ACC)

A multi-agent internship-search assistant on Google Cloud Platform.
Built for **INFO 520 — Data Communications** (Spring 2026, VCU).

> **Authors:** Roshan & Michael
> **Stack:** Vertex AI Agent Builder · Cloud Run · Firestore · MCP-over-SSE · OIDC

---

## What this system does

A user asks a high-level career question — *"Find me data analyst internships in Richmond and save the Capital One ML role to my pipeline"* — and a **Supervisor agent** parses the intent, delegates the work to a **Career Specialist agent** via an A2A handoff, which calls **MCP tools** on a Cloud Run service. The MCP tools fetch jobs and update the user's pipeline in **Firestore**. The Supervisor composes a friendly final reply.

Every cross-service call is authenticated with a signed **OIDC ID token** (zero-trust).

## Architecture at a glance

```
┌─────────────────────────────────────────────────────────────────────┐
│                          End User (CLI / chat)                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ HTTPS
┌──────────────────────────────▼──────────────────────────────────────┐
│  AGENT ORCHESTRATION   ·   Vertex AI Agent Builder (Gemini)         │
│                                                                       │
│   ┌────────────────────┐    A2A    ┌─────────────────────────┐      │
│   │  Supervisor Agent  │  ──────►  │  Career Specialist      │      │
│   │  (user-facing)     │  ◄──────  │  Agent (worker)         │      │
│   │  Prompt-based      │           │  Holds MCP tools        │      │
│   │  routing           │           │  Carries OIDC token     │      │
│   └────────────────────┘           └────────────┬────────────┘      │
└─────────────────────────────────────────────────┼────────────────────┘
                                                  │ JSON-RPC 2.0 over SSE
                                                  │ + Authorization: Bearer <OIDC>
┌─────────────────────────────────────────────────▼────────────────────┐
│  MCP DATA LAYER   ·   Cloud Run (FastAPI · Python)                   │
│                                                                       │
│   tools/list   ·   fetch_jobs(role, location, keyword)               │
│   tools/call   ·   sync_pipeline(action, job_data)                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ gRPC
┌──────────────────────────────▼───────────────────────────────────────┐
│  PERSISTENCE   ·   Cloud Firestore (Native mode)                     │
│  Collection: internship_pipeline                                     │
│  Schema: { id, company, title, location, url, status, deadline, ... }│
└──────────────────────────────────────────────────────────────────────┘
```

See [`docs/architecture.pdf`](docs/architecture.pdf) for the full diagram.

---

## Repository layout

```
acc-repo/
├── mcp_server/            # FastAPI MCP server (deployed to Cloud Run)
│   ├── main.py            #   JSON-RPC dispatch, /sse and /messages endpoints
│   ├── tools.py           #   fetch_jobs + sync_pipeline implementations
│   ├── firestore_client.py
│   ├── requirements.txt
│   └── Dockerfile
├── agents/                # Multi-agent system (runs locally for the demo)
│   ├── supervisor.py      #   Lead Orchestrator — user-facing, delegates
│   ├── specialist.py      #   Career Specialist — worker, calls MCP tools
│   ├── mcp_client.py      #   JSON-RPC client with OIDC token attachment
│   ├── chat_cli.py        #   Interactive demo entry point
│   └── requirements.txt
├── scripts/               # gcloud automation (every step you need)
│   ├── 00_bootstrap.sh    #   one-time GCP setup
│   ├── 01_deploy_mcp.sh   #   build & deploy Cloud Run service (zero-trust)
│   ├── 02_test_mcp.sh     #   end-to-end smoke test
│   ├── 03_run_agents.sh   #   start the chat CLI
│   └── run_mcp_local.sh   #   run MCP server on localhost for dev
├── tests/                 # Unit tests for tool logic
└── docs/                  # Diagram, reflection, demo script
```

---

## Prerequisites

- A GCP project with billing enabled
- `gcloud` CLI installed and authenticated (`gcloud auth login`)
- Application Default Credentials for local Firestore access (`gcloud auth application-default login`)
- Python 3.11+
- Docker (only needed if you want to test the container locally; Cloud Build handles it for deploy)

---

## Quickstart — full deploy in 5 commands

```bash
# 1. Set your project
export GCP_PROJECT="your-gcp-project-id"
export GCP_REGION="us-central1"

# 2. Bootstrap GCP (enables APIs, creates service account, makes Firestore DB)
./scripts/00_bootstrap.sh

# 3. Deploy the MCP server to Cloud Run with zero-trust auth
./scripts/01_deploy_mcp.sh

# 4. Verify everything works end-to-end
./scripts/02_test_mcp.sh

# 5. Start the multi-agent chat
./scripts/03_run_agents.sh
```

Total time: ~10 minutes for the GCP services to provision.

---

## Demo conversation

Once `03_run_agents.sh` is running:

```
you > find me data analyst internships in Richmond
assistant > I found 1 data analyst internship in Richmond:
  • CarMax — Data Engineer Intern (Richmond, VA), deadline 2026-06-05.
  Want me to save this to your pipeline?

you > yes save it
assistant > Saved CarMax — Data Engineer Intern to your pipeline (status: saved).

you > what's in my pipeline?
assistant > You have 1 entry:
  1. CarMax — Data Engineer Intern · status: saved · saved Apr 23

you > mark it as applied
assistant > Updated CarMax to status: applied.
```

Each of those turns triggers an A2A handoff from Supervisor to Specialist and one or more MCP tool calls to Cloud Run.

---

## Zero-trust security (extra credit)

The MCP server is deployed with `--no-allow-unauthenticated`, meaning Cloud Run rejects every request that doesn't carry a valid OIDC ID token whose audience matches the service URL. Only the `acc-agents-sa` service account holds `roles/run.invoker`, so only the agents can call it.

The agent's `MCPClient` (`agents/mcp_client.py`) fetches a signed token from the GCE/Cloud Run metadata server (or `gcloud auth print-identity-token` locally) and attaches it as `Authorization: Bearer <jwt>` on every JSON-RPC call.

Verify it's enforced — these should fail and succeed respectively:

```bash
# Should return 403 (no token attached)
curl -i "$(gcloud run services describe acc-mcp-server \
  --region=$GCP_REGION --format='value(status.url)')/healthz"

# Should return 200 OK with an authorized token
curl -H "Authorization: Bearer $(gcloud auth print-identity-token \
  --audiences=$(gcloud run services describe acc-mcp-server \
  --region=$GCP_REGION --format='value(status.url)'))" \
  "$(gcloud run services describe acc-mcp-server \
  --region=$GCP_REGION --format='value(status.url)')/healthz"
```

---

## Observability — capturing the system trace

The rubric asks for a screenshot of a single user request flowing Orchestrator → Specialist → MCP. The cleanest way to get this:

1. Open **Cloud Logging** in the GCP Console.
2. Run the demo CLI and send one request, e.g. `find data analyst jobs in Richmond`.
3. In Cloud Logging, filter to `resource.type=cloud_run_revision AND resource.labels.service_name=acc-mcp-server` and the time window of your request. You'll see the structured JSON logs from `main.py` — `MCP method invoked: tools/list`, `MCP method invoked: tools/call`, etc.
4. In your local terminal you'll see the agent-side logs: `[USER]`, `[A2A HANDOFF →]`, `[MCP CALL]`, `[A2A HANDOFF ←]`, `[ASSISTANT]`.
5. Take a single screenshot showing the agent terminal alongside the Cloud Logging panel — that demonstrates the full request flow with timestamps.

Save the screenshot as `docs/system_trace.png`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `403 Forbidden` from MCP server | Missing/wrong OIDC token | Re-run `gcloud auth login`; check audience matches service URL |
| `Firestore PermissionDenied` | SA lacks `roles/datastore.user` | Re-run `00_bootstrap.sh` |
| `gcloud run deploy` fails | Cloud Build API not enabled | Re-run `00_bootstrap.sh` |
| Agent says "I cannot do that" | Supervisor didn't delegate | Check the system instruction in `supervisor.py` includes routing rules |
| `vertexai not found` | Wrong venv | `source agents/.venv/bin/activate && pip install -r agents/requirements.txt` |
| SSE connection times out | Cloud Run timeout < SSE keepalive | Already handled (15s keepalive); raise `--timeout` if needed |

---

## Data communications concepts demonstrated

This project is a working illustration of three layered protocols on top of HTTPS:

1. **MCP (Model Context Protocol)** — standardizes how an agent discovers and invokes tools without bespoke per-endpoint contracts.
2. **JSON-RPC 2.0** — uniform message envelope for every tool call, with structured error semantics.
3. **Server-Sent Events (SSE)** — one-way HTTP streaming transport that keeps a long-lived connection open for incremental tool output.

Plus **A2A messaging** between Supervisor and Specialist (in-process structured handoffs) and **OIDC** for zero-trust service-to-service auth.

See [`docs/reflection.pdf`](docs/reflection.pdf) for the full 500-word data communications analysis.

---

## License

Submitted as coursework for INFO 520 at Virginia Commonwealth University, Spring 2026. Not licensed for redistribution.
