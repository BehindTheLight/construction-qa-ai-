import requests
import time
import json
from typing import List, Dict, Any
from core.settings import settings

class CohereChat:
    """
    Direct Cohere API client for Command models.
    
    Uses Cohere's native /v1/chat endpoint instead of OpenAI-compatible format.
    Supports Command A, Command R, and other Cohere models.
    """
    def __init__(self, model: str = None, api_key: str = None):
        self.model = model or settings.LLM_MODEL
        self.api_key = api_key or settings.COHERE_API_KEY
        self.base_url = "https://api.cohere.com/v1"
        assert self.api_key, "COHERE_API_KEY not set"
    
    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.0, 
        max_tokens: int = 500, 
        retry: int = 2, 
        sleep: float = 1.0
    ) -> str:
        """
        Call Cohere chat endpoint with native API format.
        
        Converts OpenAI-style messages to Cohere's format:
        - Last user message → message parameter
        - Previous messages → chat_history parameter
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: 0.0 for deterministic, higher for creative
            max_tokens: Max tokens to generate
            retry: Number of retries on failure
            sleep: Base sleep duration between retries
        
        Returns:
            The assistant's response text
            
        Raises:
            RuntimeError: If LLM call fails after all retries
        """
        url = f"{self.base_url}/chat"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Convert OpenAI format to Cohere format
        # Last message is the current message, previous are history
        chat_history = []
        current_message = ""
        
        for msg in messages:
            role = msg.get("role", "").upper()
            content = msg.get("content", "")
            
            if role == "SYSTEM":
                # Add system message to preamble (will be separate parameter)
                chat_history.append({"role": "SYSTEM", "message": content})
            elif role == "USER":
                current_message = content  # Last user message
            elif role == "ASSISTANT":
                chat_history.append({"role": "CHATBOT", "message": content})
        
        payload = {
            "model": self.model,
            "message": current_message,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Add chat history if exists
        if chat_history:
            payload["chat_history"] = chat_history
        
        # Log which model we're using (for debugging)
        print(f"[LLM Call] Using model: {self.model} (Cohere Direct)")
        
        last_error = None
        for attempt in range(retry + 1):
            try:
                resp = requests.post(url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    # Cohere returns text in 'text' field, not 'choices'
                    response_text = data.get("text", "")
                    
                    # For JSON responses, try to extract just the JSON
                    # (Cohere doesn't have native JSON mode like OpenAI)
                    if response_text.strip().startswith("{"):
                        return response_text
                    else:
                        # Try to find JSON in the response
                        start = response_text.find("{")
                        end = response_text.rfind("}") + 1
                        if start >= 0 and end > start:
                            return response_text[start:end]
                        # If no JSON found, return as-is (will be handled by caller)
                        return response_text
                        
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.exceptions.Timeout:
                last_error = "Request timed out (API not responding)"
            except requests.exceptions.ConnectionError:
                last_error = "Connection failed (API unreachable)"
            except Exception as e:
                last_error = str(e)
            
            if attempt < retry:
                time.sleep(sleep * (attempt + 1))
        
        raise RuntimeError(f"LLM call failed after {retry + 1} attempts: {last_error}")


def get_chat_client():
    """
    Factory function to get the appropriate chat client based on settings.
    
    Returns:
        CohereChat or NagaChat instance based on LLM_PROVIDER setting
    """
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "cohere":
        return CohereChat()
    elif provider == "naga":
        return NagaChat()
    else:
        # Default to Naga for backward compatibility
        print(f"[Warning] Unknown LLM_PROVIDER '{provider}', defaulting to Naga")
        return NagaChat()


class NagaChat:
    def __init__(self, base_url: str = None, model: str = None, api_key: str = None):
        self.base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.api_key = api_key or settings.NAGA_API_KEY
        assert self.api_key, "NAGA_API_KEY not set"

    def stream(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.0, 
        max_tokens: int = 500
    ):
        """
        Stream chat completion responses (Server-Sent Events).
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: 0.0 for deterministic, higher for creative
            max_tokens: Max tokens to generate
        
        Yields:
            String chunks as they're generated by the LLM
            
        Raises:
            RuntimeError: If LLM call fails
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}", 
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model, 
            "messages": messages, 
            "temperature": temperature, 
            "max_tokens": max_tokens,
            "stream": True  # Enable streaming
        }
        
        print(f"[LLM Stream] Using model: {self.model}")
        
        try:
            resp = requests.post(url, json=payload, headers=headers, stream=True, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            
            # Parse SSE stream
            for line in resp.iter_lines():
                if not line:
                    continue
                
                line = line.decode('utf-8')
                
                # SSE format: "data: {...}"
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    
                    # Check for end of stream
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        # Extract content delta
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue  # Skip malformed chunks
                        
        except requests.exceptions.Timeout:
            raise RuntimeError("Request timed out (API not responding)")
        except requests.exceptions.ConnectionError:
            raise RuntimeError("Connection failed (API unreachable)")
        except Exception as e:
            raise RuntimeError(f"Streaming failed: {str(e)}")

    def chat(
        self, 
        messages: List[Dict[str, str]], 
        temperature: float = 0.0, 
        max_tokens: int = 500, 
        retry: int = 2, 
        sleep: float = 1.0
    ) -> str:
        """
        Call Naga AI chat completion endpoint with shorter timeout and better error handling.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: 0.0 for deterministic, higher for creative
            max_tokens: Max tokens to generate
            retry: Number of retries on failure (reduced to 2 for faster failure)
            sleep: Base sleep duration between retries
        
        Returns:
            The assistant's response text
            
        Raises:
            RuntimeError: If LLM call fails after all retries
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}", 
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model, 
            "messages": messages, 
            "temperature": temperature, 
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}  # Force JSON mode (OpenAI-compatible)
        }
        
        # Log which model we're using (for debugging)
        print(f"[LLM Call] Using model: {self.model}")
        
        last_error = None
        for attempt in range(retry + 1):
            try:
                # Shorter timeout: fail faster when API is down (20s instead of 60s)
                resp = requests.post(url, json=payload, headers=headers, timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except requests.exceptions.Timeout:
                last_error = "Request timed out (API not responding)"
            except requests.exceptions.ConnectionError:
                last_error = "Connection failed (API unreachable)"
            except Exception as e:
                last_error = str(e)
            
            if attempt < retry:
                time.sleep(sleep * (attempt + 1))
        
        raise RuntimeError(f"LLM call failed after {retry + 1} attempts: {last_error}")


def get_chat_client():
    """
    Factory function to get the appropriate chat client based on settings.
    
    Returns:
        CohereChat or NagaChat instance based on LLM_PROVIDER setting
    """
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "cohere":
        return CohereChat()
    elif provider == "naga":
        return NagaChat()
    else:
        # Default to Naga for backward compatibility
        print(f"[Warning] Unknown LLM_PROVIDER '{provider}', defaulting to Naga")
        return NagaChat()

