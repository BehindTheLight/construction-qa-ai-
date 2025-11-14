import time
import requests
from typing import List
from core.settings import settings

EMBED_DIM = 3072  # for text-embedding-3-large or text-embedding-004

class EmbedderNaga:
    def __init__(self, base_url: str = None, model: str = None, api_key: str = None):
        self.base_url = (base_url or settings.EMBED_BASE_URL).rstrip("/")
        self.model = model or settings.EMBED_MODEL
        self.api_key = api_key or settings.NAGA_API_KEY

    def embed_batch(self, texts: List[str], retry: int = 2, sleep: float = 1.0) -> List[List[float]]:
        """
        Embed texts using Naga AI with shorter timeout and better error handling.
        
        Args:
            texts: List of texts to embed
            retry: Number of retries (reduced to 2 for faster failure)
            sleep: Base sleep duration between retries
            
        Returns:
            List of embedding vectors
            
        Raises:
            RuntimeError: If embedding fails after all retries
        """
        url = f"{self.base_url}/embeddings"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "input": texts}
        
        last_error = None
        for attempt in range(retry + 1):
            try:
                # Shorter timeout: fail faster when API is down (15s instead of 60s)
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    return [d["embedding"] for d in data["data"]]
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.exceptions.Timeout:
                last_error = "Request timed out (API not responding)"
            except requests.exceptions.ConnectionError:
                last_error = "Connection failed (API unreachable)"
            except Exception as e:
                last_error = str(e)
            
            if attempt < retry:
                time.sleep(sleep * (attempt + 1))
        
        raise RuntimeError(f"Embedding failed after {retry + 1} attempts: {last_error}")


class EmbedderGemini:
    """
    Gemini embeddings from Google AI Studio.
    
    Features:
    - Better quality (MTEB 68.32 vs OpenAI 64.6)
    - Flexible dimensions (768, 1536, 3072)
    - Multimodal support
    """
    def __init__(self, api_key: str = None, model: str = "gemini-embedding-001", dimension: int = 3072):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model
        self.dimension = dimension
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    
    def embed_batch(self, texts: List[str], retry: int = 2, sleep: float = 1.0) -> List[List[float]]:
        """
        Embed texts using Google Gemini.
        
        Args:
            texts: List of texts to embed (max 100 per batch)
            retry: Number of retries
            sleep: Base sleep duration between retries
            
        Returns:
            List of embedding vectors
            
        Raises:
            RuntimeError: If embedding fails after all retries
        """
        # Gemini supports max 100 texts per batch
        if len(texts) > 100:
            # Split into batches
            all_embeddings = []
            for i in range(0, len(texts), 100):
                batch = texts[i:i+100]
                embeddings = self._embed_single_batch(batch, retry, sleep)
                all_embeddings.extend(embeddings)
            return all_embeddings
        else:
            return self._embed_single_batch(texts, retry, sleep)
    
    def _embed_single_batch(self, texts: List[str], retry: int, sleep: float) -> List[List[float]]:
        url = f"{self.base_url}/{self.model}:batchEmbedContents?key={self.api_key}"
        
        # Build requests for each text
        requests_data = []
        for text in texts:
            requests_data.append({
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
                "output_dimensionality": self.dimension  # Fixed: snake_case not camelCase
            })
        
        payload = {"requests": requests_data}
        
        last_error = None
        for attempt in range(retry + 1):
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    embeddings = [item["values"] for item in data["embeddings"]]
                    return embeddings
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.exceptions.Timeout:
                last_error = "Request timed out"
            except requests.exceptions.ConnectionError:
                last_error = "Connection failed"
            except Exception as e:
                last_error = str(e)
            
            if attempt < retry:
                time.sleep(sleep * (attempt + 1))
        
        raise RuntimeError(f"Gemini embedding failed after {retry + 1} attempts: {last_error}")


