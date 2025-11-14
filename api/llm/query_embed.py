from .embeddings import EmbedderNaga, EmbedderGemini
from core.settings import settings

def embed_query(q: str) -> list[float]:
    """
    Embed a single query string.
    Supports multiple embedding providers: Naga AI (OpenAI) or Gemini.
    Returns a 3072-dimensional vector.
    """
    if settings.EMBEDDINGS_PROVIDER == "gemini":
        emb = EmbedderGemini()
    else:
        emb = EmbedderNaga()
    
    return emb.embed_batch([q])[0]


