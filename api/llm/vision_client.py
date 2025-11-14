"""
Vision LLM client for analyzing construction document images.

Supports:
- Naga AI (OpenAI-compatible)
- OpenAI GPT-4o-mini

Extracts structured data from:
- Tables (simple and complex/nested)
- Architectural drawings
- Engineering diagrams
- Forms
- Mixed content pages
"""

import base64
import json
import logging
import requests
from typing import Dict, Any, Optional
from core.settings import settings

logger = logging.getLogger(__name__)

# ============================================================================
# OLD PROMPT (COMMENTED OUT - Simple structure, but searchability issues)
# ============================================================================
# VISION_SYSTEM_PROMPT_OLD = """You are a construction document analysis expert.
# Extract ALL visible information from this construction document page image.
#
# Identify the content type and structure your response accordingly:
# - Tables: Extract title, headers, and all row data (handle nested headers and merged cells)
# - Drawings: Extract title, scale, room labels, dimensions, notes, annotations, symbols
# - Forms: Extract all fields, labels, and their values
# - Specifications: Extract section titles and detailed content
# - Mixed content: Group by logical sections
#
# Return a JSON object with this structure:
# {
#   "content_type": "table|drawing|form|specification|mixed",
#   "data": { ... your structured extraction based on content type ... }
# }
#
# CRITICAL RULES:
# 1. Be comprehensive - extract EVERYTHING visible and legible
# 2. Preserve exact values, units, and measurements
# 3. Structure data logically based on what you see
# 4. Include spatial relationships where relevant (e.g., "north side", "adjacent to")
# 5. If multiple content types exist, include all sections
# 6. For tables: preserve column structure even with merged cells
# 7. For drawings: capture all labels, dimensions, notes, and symbols
# 8. Never invent or assume information - only extract what's clearly visible
#
# Return ONLY the JSON object, no additional text."""
#
# VISION_USER_PROMPT_OLD = """Analyze this construction document page and extract all information according to the system instructions.
#
# Focus on accuracy and completeness. This data will be used for:
# - Answering technical questions about the project
# - Code compliance verification
# - Construction planning and coordination
#
# Return your extraction as a structured JSON object."""

# ============================================================================
# NEW PROMPT (HYBRID FORMAT - Structured data + Searchable text)
# ============================================================================
# Solves BM25/keyword search issues by providing natural language text
# alongside structured JSON data
VISION_SYSTEM_PROMPT = """You are a construction document analysis expert.
Extract ALL visible information from this construction document page image.

Return a JSON object with THREE sections:

1. "content_type": Identify the type of content (table|drawing|form|specification|mixed)

2. "structured_data": Organized JSON for programmatic access
   - Use logical structure appropriate to content type
   - Preserve exact values, units, and measurements
   - Use clear, readable field names
   - Handle nested headers and merged cells in tables
   - Capture all dimensions, labels, and annotations in drawings

3. "searchable_text": Natural language summary for search (CRITICAL!)
   - Write complete, natural sentences
   - Use the EXACT terminology from the document
   - Include ALL key information (don't omit details)
   - Make it sound human-readable
   - Include all numbers, measurements, and values
   - For tables: describe each row's key information
   - For drawings: describe all labels, dimensions, and notes
   - For forms: include all field names and their values

CRITICAL RULES:
1. Be comprehensive - extract EVERYTHING visible and legible
2. Preserve exact values in BOTH structured_data AND searchable_text
3. Never invent or assume information - only extract what's clearly visible
4. The searchable_text should be complete enough to answer questions without the structured_data

Example Output:
{
  "content_type": "table",
  "structured_data": {
    "title": "Project Design Conditions",
    "window_to_wall_ratio": "7.40%",
    "climate_zone": "5"
  },
  "searchable_text": "This page shows the project design conditions. The window to wall ratio is 7.40 percent. The climate zone is 5. This information is used for energy efficiency compliance."
}

Return ONLY the JSON object, no additional text."""

VISION_USER_PROMPT = """Analyze this construction document page and extract all information according to the system instructions.

Focus on creating HIGH-QUALITY searchable text that captures every important detail in natural language.

This data will be used for:
- Semantic search (users asking natural language questions)
- Code compliance verification
- Construction planning and coordination

Return your extraction as a JSON object with content_type, structured_data, and searchable_text."""


def encode_image_to_base64(image_bytes: bytes) -> str:
    """Encode image bytes to base64 string for API transmission."""
    return base64.b64encode(image_bytes).decode('utf-8')


def call_vision_llm(image_base64: str, page_number: int) -> Dict[str, Any]:
    """
    Call Vision LLM API to analyze a construction document page image.
    
    Args:
        image_base64: Base64-encoded PNG image
        page_number: Page number (for logging)
        
    Returns:
        Dict with extracted data or error information
        
    Raises:
        Exception: If API call fails
    """
    provider = settings.VISION_LLM_PROVIDER
    model = settings.VISION_LLM_MODEL
    
    logger.info(f"[Vision LLM] Analyzing page {page_number} with {provider}/{model}")
    
    # Prepare API request based on provider
    if provider == "naga":
        api_url = f"{settings.LLM_BASE_URL}/chat/completions"
        api_key = settings.NAGA_API_KEY
    elif provider == "openai":
        api_url = "https://api.openai.com/v1/chat/completions"
        api_key = settings.NAGA_API_KEY  # Assuming same key or separate OPENAI_API_KEY
    else:
        raise ValueError(f"Unsupported Vision LLM provider: {provider}")
    
    # Build request payload
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": VISION_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": VISION_USER_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                            "detail": "high"  # High detail for construction documents
                        }
                    }
                ]
            }
        ],
        "max_tokens": settings.VISION_MAX_TOKENS,
        "temperature": 0.1,  # Low temperature for factual extraction
        "response_format": {"type": "json_object"}  # Force JSON response
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            json=payload,
            headers=headers,
            timeout=60  # 60 second timeout for vision processing
        )
        response.raise_for_status()
        
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        
        # Parse JSON response
        try:
            parsed_data = json.loads(content)
            logger.info(f"[Vision LLM] Successfully extracted {parsed_data.get('content_type', 'unknown')} from page {page_number}")
            return {
                "success": True,
                "data": parsed_data,
                "raw_response": content,
                "tokens_used": result.get("usage", {})
            }
        except json.JSONDecodeError as e:
            logger.error(f"[Vision LLM] Failed to parse JSON response: {e}")
            return {
                "success": False,
                "error": f"Invalid JSON response: {str(e)}",
                "raw_response": content
            }
    
    except requests.exceptions.Timeout:
        logger.error(f"[Vision LLM] Request timeout for page {page_number}")
        return {
            "success": False,
            "error": "Vision LLM request timeout (60s)"
        }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"[Vision LLM] API request failed: {e}")
        return {
            "success": False,
            "error": f"Vision LLM API error: {str(e)}"
        }
    
    except Exception as e:
        logger.error(f"[Vision LLM] Unexpected error: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


def flatten_vision_data_to_text(vision_data: Dict[str, Any]) -> str:
    """
    Convert Vision LLM structured JSON to searchable text.
    
    NEW (Hybrid Format): Prefers natural language 'searchable_text' field
    OLD (Fallback): Recursively flattens structured JSON
    
    This text will be used for:
    - BM25 keyword search
    - Vector embeddings
    
    Args:
        vision_data: Parsed JSON from Vision LLM
        
    Returns:
        Searchable text (natural language or flattened JSON)
    """
    # NEW APPROACH: Use searchable_text if available (Hybrid Format)
    searchable_text = vision_data.get("searchable_text", "").strip()
    if searchable_text:
        logger.info("[Vision Indexer] Using natural language searchable_text (Hybrid Format)")
        return searchable_text
    
    # FALLBACK: Use old flattening approach for backward compatibility
    logger.info("[Vision Indexer] No searchable_text found, falling back to JSON flattening")
    
    content_type = vision_data.get("content_type", "unknown")
    
    # Try to get data from either 'structured_data' (new) or 'data' (old)
    data = vision_data.get("structured_data") or vision_data.get("data", {})
    
    parts = [f"Content Type: {content_type}"]
    
    def extract_recursive(obj, prefix=""):
        """Recursively extract text from nested structures."""
        result = []
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    result.extend(extract_recursive(value, f"{prefix}{key}: "))
                else:
                    result.append(f"{prefix}{key}: {value}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    result.extend(extract_recursive(item, prefix))
                else:
                    result.append(f"{prefix}{item}")
        else:
            result.append(f"{prefix}{obj}")
        return result
    
    parts.extend(extract_recursive(data))
    
    return "\n".join(parts)

