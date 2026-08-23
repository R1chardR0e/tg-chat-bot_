from openai import OpenAI

from api.base_api import BaseAI
from config import API_URL, IO_NET_API_KEY, MODEL_NAME


class IoNetAPI(BaseAI):
    def __init__(self):
        self.client = OpenAI(
            api_key=IO_NET_API_KEY,
            base_url=API_URL,
        )
        self.model_name = MODEL_NAME

    async def get_response(self, prompt: str) -> str:
        # Клиент синхронный, интерфейс провайдера остаётся асинхронным.
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_completion_tokens=300,
        )

        return response.choices[0].message.content.strip()
