"""Automatic section names shared by the help viewer and link checks."""
import unicodedata


def HeadingAnchors(document):
    used = set()
    block = document.begin()
    while block.isValid():
        if block.blockFormat().headingLevel():
            # Use rendered text so emphasis, links and code contribute their
            # contents, while Markdown syntax and fenced examples contribute none.
            text = block.text().strip().lower()
            base = "".join("-" if character == " " else character for character in text
                           if character in " -_" or unicodedata.category(character)[0] in "LMN")
            name, suffix = base, 0
            while name in used:
                suffix += 1
                name = f"{base}-{suffix}"
            used.add(name)
            yield block, name
        block = block.next()
