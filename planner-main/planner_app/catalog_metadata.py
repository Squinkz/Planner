"""Catalog metadata normalization without graphics, model or file dependencies."""


def FurnishingCategories(value):
    """Accept a single category or a list, preserving order without duplicates."""
    if value is None:
        value = []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(category, str) for category in value):
        raise ValueError("Categories must be text or a list of text")
    categories, seen = [], set()
    for category in value:
        category = category.strip()
        if category and category.casefold() not in seen:
            categories.append(category)
            seen.add(category.casefold())
    return categories or ["Miscellaneous"]


