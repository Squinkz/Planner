"""Validate furnishing SVGs before native parsing, including referenced resources."""
import base64
import io
import re
from xml.etree import ElementTree


svgByteLimit = 8 * 1024 * 1024
svgElementLimit = 50000
svgDepthLimit = 64


def ValidateFurnishingSvg(source):
    payload = source.encode("utf-8") if isinstance(source, str) else bytes(source)
    if len(payload) > svgByteLimit:
        raise ValueError("Furnishing SVG exceeds 8 MiB.")
    if b"\0" in payload:
        raise ValueError("Furnishing SVG must use UTF-8 text.")
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", payload, re.I):
        raise ValueError("SVG document types and entities are unsupported.")
    depth = count = rasterPixels = 0
    root = None
    try:
        for event, element in ElementTree.iterparse(io.BytesIO(payload), events = ("start", "end")):
            if event == "end":
                depth -= 1
            else:
                depth += 1
                count += 1
                if depth > svgDepthLimit or count > svgElementLimit:
                    raise ValueError("Furnishing SVG is too deeply nested or complex.")
                if root is None:
                    root = element
                    if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
                        raise ValueError("A furnishing graphic must be SVG.")
                continue
            if element.tag.rsplit("}", 1)[-1] in ("script", "foreignObject"):
                raise ValueError("Active SVG content is unsupported.")
            for name, value in element.attrib.items():
                field = name.rsplit("}", 1)[-1].lower()
                if name == "{http://www.w3.org/XML/1998/namespace}base" and value.strip():
                    raise ValueError("External SVG base paths are unsupported.")
                if field == "href" and value.strip() and not value.strip().startswith("#"):
                    # Raster images must be portable, bounded PNG data. Never let
                    # Qt open a project-supplied drive, UNC path or network URL.
                    match = re.fullmatch(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)", value.strip(), re.I)
                    if match is None:
                        raise ValueError("SVG resources must use local fragments or embedded PNG data.")
                    raster = base64.b64decode(re.sub(r"\s+", "", match[1]), validate = True)
                    if not raster.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("Invalid embedded SVG image.")
                    from .reference_image import ReadReferenceImage
                    image = ReadReferenceImage(raster)
                    rasterPixels += image.width() * image.height()
                    if rasterPixels > 100000000:
                        raise ValueError("Embedded SVG images exceed 100 million pixels in total.")
            styles = list(element.attrib.values())
            if element.tag.rsplit("}", 1)[-1] == "style":
                styles.append(element.text or "")
            for style in styles:
                if re.search(r"@import\b", style, re.I) or "\\" in style:
                    raise ValueError("External or escaped SVG styles are unsupported.")
                for target in re.findall(r"url\s*\(([^)]*)\)", style, re.I):
                    if not target.strip().strip("\"'").strip().startswith("#"):
                        raise ValueError("External SVG paint resources are unsupported.")
    except ElementTree.ParseError as error:
        raise ValueError("Invalid furnishing SVG.") from error
    if root is None:
        raise ValueError("Empty furnishing SVG.")
    return root
