from abc import ABC, abstractmethod


class BaseAI(ABC):
    @abstractmethod
    async def get_response(self, prompt: str) -> str:
        pass
