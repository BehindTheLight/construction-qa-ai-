import os, uuid
from .opensearch_client import get_os_client, INDEX_NAME

def seed_one():
    client = get_os_client()
    doc = {
        "chunk_id": str(uuid.uuid4()),
        "doc_id": "demo_doc",
        "project_id": "demo_project",
        "doc_type": "permit",
        "discipline": "GENERAL",
        "page_number": 3,
        "section": "Required Inspections",
        "text": "Foundation wall inspection prior to backfill. Call 519-255-6453 to schedule with 24 hours notice.",
        "vector": [0.0] * 3072  # placeholder until real embeddings
    }
    resp = client.index(index=INDEX_NAME, id=doc["chunk_id"], body=doc, refresh=True)
    print("Indexed:", resp["result"])

if __name__ == "__main__":
    seed_one()

