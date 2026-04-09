import httpx
from src.core.settings import settings


class LlmClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url

    def generate(self, prompt: str, max_tokens: int = 512, temperature: float = 0.1) -> str:
        timeout = httpx.Timeout(
            connect=settings.llm_connect_timeout_sec,
            read=settings.llm_read_timeout_sec,
            write=settings.llm_write_timeout_sec,
            pool=settings.llm_pool_timeout_sec,
        )
        chat_payload = {
            'model': 'local-rag-model',
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'Ты полезный ассистент линии поддержки. '
                        'Отвечай строго по-русски и не повторяй бессмысленные последовательности символов.'
                    ),
                },
                {'role': 'user', 'content': prompt},
            ],
            'max_tokens': max_tokens,
            'temperature': temperature,
            'top_p': 0.9,
            'frequency_penalty': 0.1,
            'presence_penalty': 0.05,
            'stream': False,
        }

        chat_resp = httpx.post(f'{self.base_url}/v1/chat/completions', json=chat_payload, timeout=timeout)
        if chat_resp.status_code < 400:
            chat_data = chat_resp.json()
            choices = chat_data.get('choices') or []
            if choices:
                message = choices[0].get('message', {})
                content = message.get('content')
                if isinstance(content, str) and content.strip():
                    return self._enforce_russian(content.strip(), max_tokens=max_tokens)

        completion_payload = {
            'prompt': prompt,
            'n_predict': max_tokens,
            'temperature': temperature,
            'top_p': 0.9,
            'repeat_penalty': 1.15,
            'stop': ['</s>'],
        }
        completion_resp = httpx.post(f'{self.base_url}/completion', json=completion_payload, timeout=timeout)
        completion_resp.raise_for_status()
        completion_data = completion_resp.json()
        return self._enforce_russian(completion_data.get('content', '').strip(), max_tokens=max_tokens)

    def _enforce_russian(self, answer: str, max_tokens: int) -> str:
        if not answer or self._looks_russian(answer):
            return answer

        timeout = httpx.Timeout(
            connect=settings.llm_connect_timeout_sec,
            read=settings.llm_read_timeout_sec,
            write=settings.llm_write_timeout_sec,
            pool=settings.llm_pool_timeout_sec,
        )
        rewrite_payload = {
            'model': 'local-rag-model',
            'messages': [
                {
                    'role': 'system',
                    'content': (
                        'Ты редактор ответов службы поддержки. '
                        'Переформулируй ответ строго на русском языке без добавления новых фактов.'
                    ),
                },
                {'role': 'user', 'content': answer},
            ],
            'max_tokens': max_tokens,
            'temperature': 0.0,
            'stream': False,
        }
        try:
            rewrite_resp = httpx.post(f'{self.base_url}/v1/chat/completions', json=rewrite_payload, timeout=timeout)
            if rewrite_resp.status_code < 400:
                rewrite_data = rewrite_resp.json()
                choices = rewrite_data.get('choices') or []
                if choices:
                    message = choices[0].get('message', {})
                    content = message.get('content')
                    if isinstance(content, str) and content.strip() and self._looks_russian(content):
                        return content.strip()
        except httpx.HTTPError:
            pass
        return answer

    @staticmethod
    def _looks_russian(text: str) -> bool:
        cyrillic = sum(1 for ch in text if 'а' <= ch.lower() <= 'я' or ch.lower() == 'ё')
        latin = sum(1 for ch in text if 'a' <= ch.lower() <= 'z')
        return cyrillic >= 8 and cyrillic >= latin
