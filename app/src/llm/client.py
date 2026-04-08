import httpx
from src.core.settings import settings


class LlmClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.1) -> str:
        payload = {
            'prompt': prompt,
            'n_predict': max_tokens,
            'temperature': temperature,
            'stop': ['</s>'],
        }
        timeout = httpx.Timeout(
            connect=settings.llm_connect_timeout_sec,
            read=settings.llm_read_timeout_sec,
            write=settings.llm_write_timeout_sec,
            pool=settings.llm_pool_timeout_sec,
        )
        resp = httpx.post(f'{self.base_url}/completion', json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get('content', '').strip()
