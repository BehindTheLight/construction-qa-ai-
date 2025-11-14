from opensearchpy import OpenSearch
from core.settings import settings

def get_os_client():
    return OpenSearch(hosts=[settings.OPENSEARCH_HOST])

INDEX_NAME = settings.OPENSEARCH_INDEX

