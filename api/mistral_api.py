import json

import httpx

from api.base_api import BaseAI
from config import MISTRAL_API_KEY


class MistralAPI(BaseAI):
    def __init__(self):
        self.api_key = MISTRAL_API_KEY
        self.endpoint = "https://api.mistral.ai/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def get_response(self, prompt: str) -> str:
        payload = {
            "model": "mixtral-8x7b-instruct",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 300,
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                headers=self.headers,
                data=json.dumps(payload),
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
