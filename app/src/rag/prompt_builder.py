def build_prompt(question: str, contexts: list[dict], visual_evidence: list[dict] | None = None) -> str:
    context_lines = []
    for idx, item in enumerate(contexts, start=1):
        source_label = f"{item['source_type']}/{item['doc_id']}"
        page_number = item.get('page_number')
        page_suffix = f", стр. {page_number}" if page_number is not None else ''
        context_lines.append(
            f"[{idx}] {item['text']} (источник: {source_label}{page_suffix})"
        )

    evidence_lines = []
    for idx, item in enumerate(visual_evidence or [], start=1):
        summary = item.get('summary', '')
        ocr_text = item.get('ocr_text', '')
        confidence = item.get('confidence', 0.0)
        image_path = item.get('image_path', '')
        evidence_lines.append(
            f"[IMG-{idx}] {summary} (confidence={confidence}, path={image_path})\nOCR:\n{ocr_text}"
        )

    context_block = '\n'.join(context_lines)
    evidence_block = '\n\n'.join(evidence_lines) if evidence_lines else 'Нет приложенных скриншотов.'
    return f"""
Ты — помощник первой линии поддержки ЦСВ АНС.
Отвечай только на основе контекста ниже.
Язык ответа: только русский.
Даже если источник или вопрос на другом языке, финальный ответ всегда формулируй по-русски.
Если данных недостаточно — честно скажи об этом.
Если у пользователя есть скриншоты, обязательно учитывай OCR и сигналы из них.
Если отвечаешь нумерованным списком, выводи все пункты полностью, без обрыва слов и строк.
Не добавляй в ответ блоки "Основание", "Источники", маркеры вида [1]/[2] или ссылки на документы.
Источники будут добавлены системой автоматически.

Вопрос:
{question}

Сигналы со скриншотов:
{evidence_block}

Контекст:
{context_block}
""".strip()
