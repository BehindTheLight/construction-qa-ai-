import json, os
from .opensearch_client import get_os_client, INDEX_NAME

def create_index():
    client = get_os_client()

    # 1) Put a synonyms set (can be edited later)
    synonyms = [
        "adu, coach house, accessory dwelling unit",
        "esa, electrical safety authority",
        "hrv, heat recovery ventilator",
        "obc, ontario building code",
        "rfi, request for information",
        "bwv, backwater valve",
        "hvac, heating ventilation air conditioning",
    ]
    client.indices.close(INDEX_NAME, ignore_unavailable=True)
    try:
        client.indices.put_settings(
            index=INDEX_NAME,
            body={
                "analysis": {
                    "analyzer": {
                        "insani_standard": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "insani_syns"]
                        }
                    },
                    "filter": {
                        "insani_syns": {
                            "type": "synonym",
                            "synonyms": synonyms
                        }
                    }
                }
            }
        )
    except Exception:
        pass
    finally:
        try:
            client.indices.open(INDEX_NAME, ignore_unavailable=True)
        except Exception:
            pass

    # 2) Delete and recreate index (for dev - allows analyzer/synonym changes)
    if client.indices.exists(INDEX_NAME):
        print(f"Deleting existing index {INDEX_NAME}")
        client.indices.delete(INDEX_NAME)
    
    # Create index with mappings
    if True:
        body = {
          "settings": {
            "index": {
              "number_of_shards": 1,
              "number_of_replicas": 0,
              "knn": True,
              "analysis": {
                "analyzer": {
                  "insani_standard": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "insani_syns"]
                  }
                },
                "filter": {
                  "insani_syns": {
                    "type": "synonym",
                    "synonyms": synonyms
                  }
                }
              }
            }
          },
          "mappings": {
            "properties": {
              "chunk_id":     {"type": "keyword"},
              "doc_id":       {"type": "keyword"},
              "project_id":   {"type": "keyword"},
              "doc_type":     {"type": "keyword"},
              "discipline":   {"type": "keyword"},
              "page_number":  {"type": "integer"},
              "section":      {"type": "text", "analyzer": "insani_standard"},
              "text":         {"type": "text", "analyzer": "insani_standard"},
              "vector":       {"type": "knn_vector", "dimension": 3072, "method": {"name":"hnsw","engine":"nmslib","parameters":{"ef_construction":128,"m":16}}},
              "revision_date":{"type": "date"},
              "bbox":         {"type": "object", "enabled": False},  # stored but not indexed
              "source":       {"type": "keyword"},                   # "text"|"ocr"|"drawing_ocr"
              "confidence":   {"type": "float"}                       # average OCR confidence if applicable
            }
          }
        }
        client.indices.create(INDEX_NAME, body=body)
        print(f"Created index {INDEX_NAME}")

if __name__ == "__main__":
    create_index()

