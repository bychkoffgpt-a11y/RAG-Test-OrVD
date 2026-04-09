import httpx

from src.llm.client import LlmClient


def test_generate_uses_chat_completions_when_available(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, status_code: int, data: dict):
            self.status_code = status_code
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError('error', request=None, response=None)

    def _fake_post(url, json, timeout):
        calls.append((url, json))
        if url.endswith('/v1/chat/completions'):
            return _Resp(
                200,
                {
                    'choices': [
                        {
                            'message': {
                                'content': 'Нормальный ответ',
                            }
                        }
                    ]
                },
            )
        return _Resp(500, {})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    answer = LlmClient().generate('Что такое ЦСВ?')

    assert answer == 'Нормальный ответ'
    assert len(calls) == 1
    assert calls[0][0].endswith('/v1/chat/completions')


def test_generate_falls_back_to_completion(monkeypatch):
    class _Resp:
        def __init__(self, status_code: int, data: dict):
            self.status_code = status_code
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError('error', request=None, response=None)

    def _fake_post(url, json, timeout):
        if url.endswith('/v1/chat/completions'):
            return _Resp(404, {'detail': 'not found'})
        return _Resp(200, {'content': 'Фолбэк-ответ'})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    answer = LlmClient().generate('Что такое ЦСВ?')

    assert answer == 'Фолбэк-ответ'


def test_generate_rewrites_non_russian_answer(monkeypatch):
    calls: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, status_code: int, data: dict):
            self.status_code = status_code
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError('error', request=None, response=None)

    def _fake_post(url, json, timeout):
        calls.append((url, json))
        if url.endswith('/v1/chat/completions') and len(calls) == 1:
            return _Resp(
                200,
                {
                    'choices': [
                        {
                            'message': {
                                'content': 'Based on the provided information, please check document flow.',
                            }
                        }
                    ]
                },
            )
        if url.endswith('/v1/chat/completions') and len(calls) == 2:
            return _Resp(
                200,
                {
                    'choices': [
                        {
                            'message': {
                                'content': 'По предоставленной информации проверьте маршрут документа.',
                            }
                        }
                    ]
                },
            )
        return _Resp(500, {})

    monkeypatch.setattr(httpx, 'post', _fake_post)

    answer = LlmClient().generate('Почему УПД не пришел?')

    assert answer == 'По предоставленной информации проверьте маршрут документа.'
    assert len(calls) == 2
