"""
Create OpenSearch index for table rows extracted by Unstructured.

This index enables full-text search across structured table data with:
- Hybrid search (BM25 + k-NN vectors)
- Filtering by doc_id, page, project
- Coordinate storage for PDF highlighting
"""

from search.opensearch_client import get_os_client
from core.settings import settings

TABLE_INDEX_NAME = settings.OPENSEARCH_TABLE_INDEX


def create_table_index():
    """
    Create OpenSearch index for table rows with hybrid search support.
    
    Schema:
    - row_id: unique identifier
    - doc_id: document reference
    - page_number: page location
    - project_id: project filter
    - table_label: optional table caption/title
    - table_text: full concatenated text from all columns (searchable)
    - columns_text: JSON stringified columns for full-text search
    - labels: extracted construction labels (e.g., W2a, R-10)
    - vector: embedding for semantic search
    - bbox: bounding box for highlighting
    """
    client = get_os_client()
    
    # Check if index exists
    if client.indices.exists(TABLE_INDEX_NAME):
        print(f"Table index {TABLE_INDEX_NAME} already exists")
        return
    
    # Index configuration
    body = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "knn": True,  # Enable k-NN for vector search
            }
        },
        "mappings": {
            "properties": {
                "row_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "page_number": {"type": "integer"},
                "project_id": {"type": "keyword"},
                "doc_type": {"type": "keyword"},
                "discipline": {"type": "keyword"},
                
                # Table metadata
                "table_label": {"type": "text"},
                
                # Searchable text fields
                "table_text": {
                    "type": "text",
                    "analyzer": "standard"
                },
                "columns_text": {
                    "type": "text",
                    "analyzer": "standard"
                },
                
                # Labels for exact matching (W2a, A-2, etc.)
                "labels": {"type": "keyword"},
                
                # Vector for semantic search
                "vector": {
                    "type": "knn_vector",
                    "dimension": 3072,  # text-embedding-3-large
                    "method": {
                        "name": "hnsw",
                        "engine": "nmslib",
                        "parameters": {
                            "ef_construction": 128,
                            "m": 16
                        }
                    }
                },
                
                # Bounding box and metadata
                "bbox": {
                    "type": "float",
                    "index": False
                },
                "source": {"type": "keyword"},
                "created_at": {"type": "date"}
            }
        }
    }
    
    # Create index
    client.indices.create(TABLE_INDEX_NAME, body=body)
    print(f"Created table index: {TABLE_INDEX_NAME}")


def delete_table_index():
    """Delete the table rows index (for testing/reset)"""
    client = get_os_client()
    if client.indices.exists(TABLE_INDEX_NAME):
        client.indices.delete(TABLE_INDEX_NAME)
        print(f"Deleted table index: {TABLE_INDEX_NAME}")
    else:
        print(f"Table index {TABLE_INDEX_NAME} does not exist")


if __name__ == "__main__":
    create_table_index()

