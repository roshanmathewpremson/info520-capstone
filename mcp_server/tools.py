"""
Tool implementations + MCP tool catalog.
Both tools are async — fetch_jobs is in-memory (mock data), sync_pipeline hits Firestore.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Mock job catalog (data source for fetch_jobs).
# In a real system this would come from a job board API. For the capstone,
# a curated in-memory list demonstrates the protocol cleanly.
# ---------------------------------------------------------------------------
MOCK_JOBS = [
    {
        "id": "job_001", "company": "Google", "title": "Software Engineer Intern",
        "location": "Mountain View, CA", "role": "Software Engineer",
        "url": "https://careers.google.com/jobs/results/se-intern",
        "deadline": "2026-06-15", "tags": ["python", "distributed systems", "swe"],
    },
    {
        "id": "job_002", "company": "Microsoft", "title": "Data Analyst Intern",
        "location": "Redmond, WA", "role": "Data Analyst",
        "url": "https://careers.microsoft.com/us/en/job/da-intern",
        "deadline": "2026-06-01", "tags": ["sql", "powerbi", "data"],
    },
    {
        "id": "job_003", "company": "Capital One", "title": "ML Engineer Intern",
        "location": "Richmond, VA", "role": "ML Engineer",
        "url": "https://capitalonecareers.com/job/ml-intern",
        "deadline": "2026-05-30", "tags": ["python", "ml", "aws"],
    },
    {
        "id": "job_004", "company": "Anthropic", "title": "AI Research Intern",
        "location": "San Francisco, CA", "role": "AI Researcher",
        "url": "https://anthropic.com/careers/ai-research-intern",
        "deadline": "2026-06-30", "tags": ["llm", "research", "python"],
    },
    {
        "id": "job_005", "company": "Stripe", "title": "Backend Engineer Intern",
        "location": "Remote, US", "role": "Backend Engineer",
        "url": "https://stripe.com/jobs/listing/backend-intern",
        "deadline": "2026-06-10", "tags": ["go", "ruby", "payments"],
    },
    {
        "id": "job_006", "company": "Vanguard", "title": "Cloud Engineer Intern",
        "location": "Malvern, PA", "role": "Cloud Engineer",
        "url": "https://www.vanguardjobs.com/cloud-intern",
        "deadline": "2026-05-25", "tags": ["aws", "gcp", "terraform"],
    },
    {
        "id": "job_007", "company": "CarMax", "title": "Data Engineer Intern",
        "location": "Richmond, VA", "role": "Data Engineer",
        "url": "https://jobs.carmax.com/data-intern",
        "deadline": "2026-06-05", "tags": ["spark", "sql", "data"],
    },
    {
        "id": "job_008", "company": "Meta", "title": "Software Engineer Intern",
        "location": "Menlo Park, CA", "role": "Software Engineer",
        "url": "https://www.metacareers.com/swe-intern",
        "deadline": "2026-06-20", "tags": ["c++", "react", "swe"],
    },
]


# ---------------------------------------------------------------------------
# MCP tool catalog — published via tools/list
# Each entry follows MCP spec: name, description, inputSchema (JSON Schema)
# ---------------------------------------------------------------------------
TOOLS_CATALOG = [
    {
        "name": "fetch_jobs",
        "description": (
            "Search internship/job opportunities. Filters are optional; "
            "all are case-insensitive substring matches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "Role keyword, e.g. 'data analyst', 'ml engineer'",
                },
                "location": {
                    "type": "string",
                    "description": "Location keyword, e.g. 'remote', 'Richmond', 'CA'",
                },
                "keyword": {
                    "type": "string",
                    "description": "Free-form keyword matching company, title, or tags",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "sync_pipeline",
        "description": (
            "Manage the user's internship pipeline in Firestore. "
            "Supports create, list, update_status, and delete actions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "update_status", "delete"],
                    "description": "What to do",
                },
                "job_data": {
                    "type": "object",
                    "description": (
                        "For 'create': full job record (company, title, location, url, status, etc.). "
                        "For 'update_status': {id, status}. "
                        "For 'delete': {id}. "
                        "For 'list': empty or {status: <filter>}."
                    ),
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------------------
# fetch_jobs implementation
# ---------------------------------------------------------------------------
async def fetch_jobs_impl(
    role: Optional[str] = None,
    location: Optional[str] = None,
    keyword: Optional[str] = None,
) -> dict:
    results = []
    for job in MOCK_JOBS:
        if role and role.lower() not in job["role"].lower() and role.lower() not in job["title"].lower():
            continue
        if location and location.lower() not in job["location"].lower():
            continue
        if keyword:
            blob = " ".join([job["company"], job["title"], " ".join(job["tags"])]).lower()
            if keyword.lower() not in blob:
                continue
        results.append(job)
    return {"count": len(results), "jobs": results}


# ---------------------------------------------------------------------------
# sync_pipeline implementation — Firestore CRUD
# ---------------------------------------------------------------------------
COLLECTION = "internship_pipeline"
VALID_STATUSES = {"saved", "applied", "interviewing", "offer", "rejected"}


async def sync_pipeline_impl(action: str, job_data: Optional[dict] = None) -> dict:
    from firestore_client import get_firestore_client  # lazy import
    db = get_firestore_client()
    coll = db.collection(COLLECTION)
    job_data = job_data or {}
    now_iso = datetime.now(timezone.utc).isoformat()

    if action == "create":
        # Validate minimum required fields
        for field in ("company", "title"):
            if not job_data.get(field):
                raise ValueError(f"create requires '{field}' in job_data")

        doc_id = job_data.get("id") or f"pipe_{uuid.uuid4().hex[:8]}"
        doc = {
            "id": doc_id,
            "company": job_data.get("company"),
            "title": job_data.get("title"),
            "location": job_data.get("location", ""),
            "url": job_data.get("url", ""),
            "status": job_data.get("status", "saved"),
            "applied_at": job_data.get("applied_at"),
            "deadline": job_data.get("deadline"),
            "notes": job_data.get("notes", ""),
            "updated_at": now_iso,
        }
        if doc["status"] not in VALID_STATUSES:
            raise ValueError(f"Invalid status; must be one of {VALID_STATUSES}")
        coll.document(doc_id).set(doc)
        return {"action": "create", "ok": True, "doc": doc}

    if action == "list":
        status_filter = job_data.get("status") if job_data else None
        query = coll
        if status_filter:
            query = query.where("status", "==", status_filter)
        docs = [d.to_dict() for d in query.stream()]
        return {"action": "list", "count": len(docs), "items": docs}

    if action == "update_status":
        doc_id = job_data.get("id")
        new_status = job_data.get("status")
        if not doc_id or not new_status:
            raise ValueError("update_status requires {id, status} in job_data")
        if new_status not in VALID_STATUSES:
            raise ValueError(f"Invalid status; must be one of {VALID_STATUSES}")
        ref = coll.document(doc_id)
        if not ref.get().exists:
            raise ValueError(f"Document {doc_id} not found")
        ref.update({"status": new_status, "updated_at": now_iso})
        return {"action": "update_status", "ok": True, "id": doc_id, "status": new_status}

    if action == "delete":
        doc_id = job_data.get("id")
        if not doc_id:
            raise ValueError("delete requires {id} in job_data")
        coll.document(doc_id).delete()
        return {"action": "delete", "ok": True, "id": doc_id}

    raise ValueError(f"Unknown action: {action}")
