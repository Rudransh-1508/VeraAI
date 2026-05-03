import os
import asyncio
from typing import Optional

import httpx

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency
    load_dotenv = None


ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/{model}:generateContent"
MODEL = "claude-sonnet-4-6"


class LLMClient:
    """
    Async wrapper around Anthropic Messages API.
    Uses a shared httpx.AsyncClient for connection reuse.
    """

    def __init__(self, api_key: Optional[str] = None):
        if load_dotenv:
            load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=False)
        self.provider = os.environ.get("LLM_PROVIDER", "groq")
        self.groq_key = os.environ.get("GROQ_API_KEY", "")
        self.groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.openrouter_model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3-haiku")
        self.gemini_key = os.environ.get("GEMINI_API_KEY", "")
        self.gemini_model = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = httpx.AsyncClient(timeout=60.0)  # Increased from 25.0

    async def complete(self, prompt: str, max_tokens: int = 600) -> str:
        """
        Send a user prompt, return the assistant text response.
        All prompts are self-contained (no conversation history).
        """
        # Priority based on LLM_PROVIDER setting
        if self.provider == "gemini" and self.gemini_key:
            url = GEMINI_API_URL.format(model=f"models/{self.gemini_model}")
            params = {"key": self.gemini_key}
            body = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature": 0.0,
                }
            }
            for attempt in range(3):
                try:
                    resp = await self._client.post(url, params=params, json=body)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                except httpx.TimeoutException:
                    if attempt == 2:
                        print(f"Gemini timeout after 3 attempts")
                        break
                    await asyncio.sleep(0.5 * (attempt + 1))
                except httpx.HTTPStatusError as e:
                    print(f"Gemini HTTP error: {e.response.status_code}")
                    try:
                        print(f"Error details: {e.response.json()}")
                    except:
                        print(f"Error text: {e.response.text[:200]}")
                    break
                except Exception as e:
                    print(f"Gemini error: {type(e).__name__}: {str(e)[:200]}")
                    break
            return ""
        
        if self.provider == "openrouter" and self.openrouter_key:
            headers = {
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost",
                "X-Title": "vera-bot",
            }
            body = {
                "model": self.openrouter_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.0,
            }
            for attempt in range(3):
                try:
                    resp = await self._client.post(
                        OPENROUTER_API_URL, headers=headers, json=body
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                except httpx.TimeoutException:
                    if attempt == 2:
                        print(f"OpenRouter timeout after 3 attempts")
                        break
                    await asyncio.sleep(0.5 * (attempt + 1))
                except httpx.HTTPStatusError as e:
                    print(f"OpenRouter HTTP error: {e.response.status_code}")
                    try:
                        print(f"Error details: {e.response.json()}")
                    except:
                        print(f"Error text: {e.response.text[:200]}")
                    break
                except Exception as e:
                    print(f"OpenRouter error: {type(e).__name__}: {str(e)[:200]}")
                    break
            return ""
        
        # Fallback to Groq
        if self.groq_key:
            headers = {
                "Authorization": f"Bearer {self.groq_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": self.groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0.0,
            }
            for attempt in range(3):
                try:
                    resp = await self._client.post(
                        GROQ_API_URL, headers=headers, json=body
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                except httpx.TimeoutException as e:
                    if attempt == 2:
                        print(f"Groq timeout after 3 attempts")
                        break
                    await asyncio.sleep(0.5 * (attempt + 1))
                except httpx.HTTPStatusError as e:
                    print(f"Groq HTTP error: {e.response.status_code}")
                    try:
                        print(f"Error details: {e.response.json()}")
                    except:
                        print(f"Error text: {e.response.text[:200]}")
                    break
                except Exception as e:
                    print(f"Groq error: {type(e).__name__}: {str(e)[:200]}")
                    break
            return ""

        # Fallback to Anthropic
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        for attempt in range(3):
            try:
                resp = await self._client.post(
                    ANTHROPIC_API_URL, headers=headers, json=body
                )
                resp.raise_for_status()
                data = resp.json()
                return data["content"][0]["text"]
            except httpx.TimeoutException:
                if attempt == 2:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 529 and attempt < 2:
                    await asyncio.sleep(1)
                    continue
                break

        return ""

    async def close(self):
        await self._client.aclose()
