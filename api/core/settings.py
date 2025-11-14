from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    OPENSEARCH_HOST: str = "http://localhost:9200"
    OPENSEARCH_INDEX: str = "chunks_v2"  # v2 uses knn_vector for faster searches
    OPENSEARCH_TABLE_INDEX: str = "table_rows_v2"
    POSTGRES_DSN: str
    EMBED_BASE_URL: str
    EMBED_MODEL: str = "text-embedding-3-large"
    NAGA_API_KEY: str
    LLM_BASE_URL: str = "https://api.naga.ac/v1"
    LLM_MODEL: str = "claude-haiku-4.5"  # Updated to match production config
    
    # Optional fields from .env (not used yet but present)
    LLM_PROVIDER: str = "naga"
    EMBEDDINGS_PROVIDER: str = "naga"  # "naga" or "gemini"
    RERANK_PROVIDER: str = "cohere"
    COHERE_API_KEY: str = ""
    GEMINI_API_KEY: str = ""  # For Gemini embeddings
    DATA_DIR: str = "./data"
    
    # Unstructured settings
    USE_UNSTRUCTURED: bool = True  # Updated to match production config
    UNSTRUCTURED_STRATEGY: str = "hi_res"  # "fast" or "hi_res" (hi_res recommended for scanned PDFs)
    UNSTRUCTURED_INFER_TABLES: bool = True
    UNSTRUCTURED_MIN_TEXT_THRESHOLD: int = 50  # Chars below this trigger unstructured
    
    # PyMuPDF table parser (for complex tables like Fire & Sound Resistance)
    # Note: Only works for PDFs with native text, not scanned images
    USE_PYMUPDF_TABLE_PARSER: bool = False  # Set to True to use bbox-based parsing for native-text PDFs
    
    # Vision LLM for visual content (drawings, scanned tables, diagrams)
    USE_VISION_LLM: bool = True  # Updated to match production config
    VISION_LLM_PROVIDER: str = "naga"  # "naga" or "openai"
    VISION_LLM_MODEL: str = "gpt-4o-mini"  # Fast and cost-effective for vision tasks
    VISION_MAX_PAGES_PER_DOC: int = 25  # Max visual pages to process per document
    VISION_MAX_TOKENS: int = 2000  # Max response tokens
    VISION_IMAGE_DPI: int = 300  # Image quality for rendering (higher = better quality, more cost)
    VISION_IMAGE_MAX_SIZE: int = 2048  # Max image width/height in pixels
    VISION_MIN_IMAGE_COVERAGE: float = 0.20  # Updated to match production config (triggers at 20%)
    
    model_config = ConfigDict(
        env_file="../infra/.env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra fields in .env
    )

settings = Settings()

