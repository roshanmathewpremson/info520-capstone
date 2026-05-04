"""
Firestore client singleton.
Uses Application Default Credentials — works locally with gcloud auth and
on Cloud Run via the runtime service account.
"""

import os
from functools import lru_cache
from google.cloud import firestore


@lru_cache(maxsize=1)
def get_firestore_client() -> firestore.Client:
    project = os.getenv("GCP_PROJECT")
    database = os.getenv("FIRESTORE_DATABASE", "(default)")
    if project:
        return firestore.Client(project=project, database=database)
    # Fall back to ADC project detection
    return firestore.Client(database=database)
