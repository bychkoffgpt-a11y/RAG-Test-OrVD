from urllib.parse import quote, urljoin, urlsplit, urlunsplit


def collect_images(contexts: list[dict]) -> list[str]:
    images: list[str] = []
    for item in contexts:
        for path in item.get('image_paths', []):
            if path not in images:
                images.append(path)
    return images


def _to_public_url(download_url: str, base_url: str | None = None) -> str:
    if download_url.startswith(('http://', 'https://')):
        return _encode_url_path(download_url)
    if not base_url:
        return _encode_url_path(download_url)
    return _encode_url_path(urljoin(base_url, download_url.lstrip('/')))


def _encode_url_path(url: str) -> str:
    parsed = urlsplit(url)
    encoded_path = quote(parsed.path, safe='/%')
    return urlunsplit((parsed.scheme, parsed.netloc, encoded_path, parsed.query, parsed.fragment))


def append_sources_markdown(answer: str, sources: list, base_url: str | None = None) -> str:
    if not sources:
        return answer

    lines: list[str] = []
    seen: set[tuple[str, str]] = set()

    for item in sources:
        source_type = getattr(item, 'source_type', None)
        doc_id = getattr(item, 'doc_id', None)
        download_url = getattr(item, 'download_url', None)
        if not source_type or not doc_id or not download_url:
            continue

        key = (source_type, doc_id)
        if key in seen:
            continue
        seen.add(key)

        public_url = _to_public_url(download_url, base_url)
        lines.append(f'- {source_type}/{doc_id}: [скачать документ]({public_url})')

    if not lines:
        return answer

    return f"{answer}\n\nИсточники для скачивания:\n" + '\n'.join(lines)
