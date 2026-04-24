import httpx
from src.core.settings import settings


class LlmClient:
    def __init__(self) -> None:
        self.base_url = settings.llm_base_url

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
        trace: dict | None = None,
    ) -> str:
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
        if trace is not None:
            trace['chat_payload'] = chat_payload
            trace['chat_status_code'] = chat_resp.status_code
        if chat_resp.status_code < 400:
            chat_data = chat_resp.json()
            choices = chat_data.get('choices') or []
            if choices:
                message = choices[0].get('message', {})
                content = message.get('content')
                if isinstance(content, str) and content.strip():
                    normalized = self._enforce_russian(content.strip(), max_tokens=max_tokens)
                    final_answer = self._continue_if_truncated(
                        answer=normalized,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        trace=trace,
                    )
                    if trace is not None:
                        trace['transport'] = 'chat_completions'
                        trace['answer'] = final_answer
                    return final_answer

        completion_payload = {
            'prompt': prompt,
            'n_predict': max_tokens,
            'temperature': temperature,
            'top_p': 0.9,
            'repeat_penalty': 1.15,
            'stop': ['</s>'],
        }
        completion_resp = httpx.post(f'{self.base_url}/completion', json=completion_payload, timeout=timeout)
        if trace is not None:
            trace['completion_payload'] = completion_payload
            trace['completion_status_code'] = completion_resp.status_code
        completion_resp.raise_for_status()
        completion_data = completion_resp.json()
        normalized = self._enforce_russian(completion_data.get('content', '').strip(), max_tokens=max_tokens)
        final_answer = self._continue_if_truncated(
            answer=normalized,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            trace=trace,
        )
        if trace is not None:
            trace['transport'] = 'completion'
            trace['answer'] = final_answer
        return final_answer

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

    def _continue_if_truncated(
        self,
        answer: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        trace: dict | None = None,
    ) -> str:
        if not self._looks_truncated(answer):
            return answer

        continuation_budget = max(64, min(256, max_tokens // 2))
        timeout = httpx.Timeout(
            connect=settings.llm_connect_timeout_sec,
            read=settings.llm_read_timeout_sec,
            write=settings.llm_write_timeout_sec,
            pool=settings.llm_pool_timeout_sec,
        )

        continuation_prompt = (
            'Ниже ответ был оборван. Продолжи строго с места обрыва, '
            'сохрани структуру списка, не добавляй новых фактов и закончи мысль полностью.\n\n'
            f'Вопрос:\n{prompt}\n\n'
            f'Текущий ответ:\n{answer}'
        )
        payload = {
            'model': 'local-rag-model',
            'messages': [
                {
                    'role': 'system',
                    'content': 'Ты редактор ответов поддержки. Дополняй только хвост ответа без новых фактов.',
                },
                {'role': 'user', 'content': continuation_prompt},
            ],
            'max_tokens': continuation_budget,
            'temperature': max(0.0, min(temperature, 0.2)),
            'stream': False,
        }
        if trace is not None:
            trace['continuation_payload'] = payload
        try:
            continuation_resp = httpx.post(f'{self.base_url}/v1/chat/completions', json=payload, timeout=timeout)
            if trace is not None:
                trace['continuation_status_code'] = continuation_resp.status_code
            if continuation_resp.status_code < 400:
                continuation_data = continuation_resp.json()
                choices = continuation_data.get('choices') or []
                if choices:
                    message = choices[0].get('message', {})
                    content = message.get('content')
                    if isinstance(content, str) and content.strip():
                        extended = self._merge_continuation(answer, content.strip())
                        return self._enforce_russian(extended, max_tokens=max_tokens)
        except httpx.HTTPError:
            return answer
        return answer

    @staticmethod
    def _merge_continuation(answer: str, continuation: str) -> str:
        if continuation.startswith(answer):
            return continuation
        return f'{answer.rstrip()} {continuation.lstrip()}'.strip()

    @staticmethod
    def _looks_truncated(answer: str) -> bool:
        trimmed = answer.rstrip()
        if len(trimmed) < 80:
            return False
        if trimmed.endswith(('.', '!', '?', ':', ';', '"', '»', ')')):
            return False
        if trimmed.endswith(('…', '...')):
            return True
        if '\n' in trimmed and any(f'\n{i}.' in trimmed for i in range(2, 20)):
            return True
        return trimmed[-1].isalnum()
