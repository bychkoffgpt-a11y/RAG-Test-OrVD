def build_prompt(question: str, contexts: list[dict]) -> str:
    context_lines = []
    for idx, item in enumerate(contexts, start=1):
        context_lines.append(
            f"[{idx}] {item['text']} (источник: {item['source_type']}/{item['doc_id']}, стр. {item.get('page_number')})"
        )

    context_block = '\n'.join(context_lines)
    return f"""
Ты — помощник первой линии поддержки ЦСВ АНС.
Отвечай только на основе контекста ниже.
Если данных недостаточно — честно скажи об этом.
В конце добавь короткий блок "Основание" с перечислением источников.

Вопрос:
{question}

Контекст:
{context_block}
""".strip()
