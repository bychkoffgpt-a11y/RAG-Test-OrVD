import httpx
from src.core.settings import settings


class LlmClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url

    def generate(self, prompt: str) -> str:
        payload = {
            'prompt': prompt,
            'n_predict': 512,
            'temperature': 0.1,
            'stop': ['</s>'],
        }
        resp = httpx.post(f'{self.base_url}/completion', json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data.get('content', '').strip()
