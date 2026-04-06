def collect_images(contexts: list[dict]) -> list[str]:
    images: list[str] = []
    for item in contexts:
        for path in item.get('image_paths', []):
            if path not in images:
                images.append(path)
    return images
