"""Case-insensitive catalog matching and ranked dimension searches."""
import math
import re
import unicodedata
from functools import lru_cache
from planner_app.units import MetricUnit, ParseImperialLength, FormatLength, imperialModes
from planner_app.catalog import FurnishingCategories
from planner_app.placement_sizing import FurnishingPlacementSize, NominalPlacementSize


searchPunctuation = str.maketrans({"′": "'", "″": '"', "’": "'", "“": '"', "”": '"'})
searchAliases = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
                 "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
                 "mice": "mouse", "children": "child", "shelves": "shelf", "knives": "knife", "dinner": "dining",
                 "inches": "in", "inch": "in", "feet": "ft", "foot": "ft"}


def SortFurnishings(definitions, mode, descending = False, unitsMode = "Millimeters"):
    results = [definition for definition in definitions if definition["key"] != "null"]
    if mode == "Category":
        return results[::-1] if descending else results
    if mode == "Area":
        return sorted(results, key = lambda definition: (math.prod(FurnishingPlacementSize(definition, unitsMode)),
            definition["name"].strip().casefold(), definition["key"]), reverse = descending)
    return sorted(results, key = lambda definition: (
        (NominalPlacementSize(definition[mode.lower()], unitsMode),) if mode in ("Width", "Length") else ()) +
        (definition["name"].strip().casefold(), definition["key"]), reverse = descending)


def FurnishingDimensionText(definition, unitsMode):
    if unitsMode in imperialModes:
        width, length = FurnishingPlacementSize(definition, unitsMode)
        width = FormatLength(width, unitsMode, precision = "Low")
        length = FormatLength(length, unitsMode, precision = "Low")
    else:
        decimals = 2 if unitsMode == "Meters" else 0
        width = FormatLength(definition["width"], unitsMode, adaptive = "cm", decimals = decimals, includeUnit = False)
        length = FormatLength(definition["length"], unitsMode, adaptive = "cm", decimals = decimals, includeUnit = False)
    return f"{width} × {length}"


@lru_cache(maxsize = 4096)
def SearchWords(text):
    """Shared query/catalog normalization, cached independently of mutable definitions."""
    text = unicodedata.normalize("NFKC", text.translate(searchPunctuation)).casefold()
    text = re.sub(r"(?<=\w)'s\b", "", text)
    text = text.replace('"', " in ").replace("'", " ft ")
    words = []
    for word in re.findall(r"\d+(?:\.\d*)?|\.\d+|[^\W\d_]+", text):
        if word in searchAliases:
            word = searchAliases[word]
        elif len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 4 and word.endswith(("ches", "shes", "xes", "zzes")):
            word = word[:-2]
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        if re.fullmatch(r"\d+(?:\.\d*)?|\.\d+", word):
            # Avoid float conversion here: arbitrary catalog text need not fit a float.
            word = word.lstrip("0") or "0"
            if word.startswith("."):
                word = "0" + word
            if "." in word:
                word = word.rstrip("0").rstrip(".")
        words.append(word)
    return tuple(words)


def FindFurnishings(definitions, query, unitsMode):
    query = unicodedata.normalize("NFKC", query.translate(searchPunctuation)).strip().casefold()
    query = re.sub(r"([wl]):\s+", r"\1:", query)
    numberPattern = r"(?:\d+(?:\.\d*)?|\.\d+)"
    # Keep a mixed feet/inches dimension together before tokenizing the query.
    try:
        query = re.sub(r"(\d+(?:\.\d*)?|\.\d+)\s*(?:'|ft)\s*(\d+(?:\.\d*)?|\.\d+)\s*(?:\"|in)",
                       lambda match: format(ParseImperialLength(match[1] + "ft " + match[2] + "in", "Feet and Inches") / 25.4, ".12g") + "in", query)
    except ValueError:
        return []
    query = re.sub(r"(" + numberPattern + r")\s+(mm|cm|m|ft|in|'|\")(?=\s|$|[x×])", r"\1\2", query)
    query = re.sub(r"(?<=\d)(mm|cm|m|ft|in|'|\")?\s*[x×]\s*(?=\d|\.\d)", r"\1 ", query)
    query = re.sub(r"(?<=\w)[-–—](?=\w)|[,;!?()\[\]{}]", " ", query)
    terms = []
    for token in query.split():
        if token == "*":
            continue
        match = re.fullmatch(r"(?:(w|l):)?(\d+(?:\.\d*)?|\.\d+)(mm|cm|m|ft|in|'|\")?", token)
        if match:
            axis, number, unit = match.groups()
            unit = {"'": "ft", '"': "in"}.get(unit, unit)
            number = float(number)
            if not math.isfinite(number):
                return []
            terms.append((token, axis, number, unit))
        elif token.startswith(("w:", "l:")):
            return []
        else:
            terms.append((token, None, None, None))
    if not terms:
        return sorted((definition for definition in definitions if definition["key"] != "null"),
                      key = lambda definition: (definition["name"].casefold(), definition["key"]))
    preferred = MetricUnit(unitsMode, "cm")[1]
    units = [preferred] + [unit for unit in ("cm", "mm", "m", "ft", "in") if unit != preferred]
    divisors = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "ft": 304.8, "in": 25.4}
    dimensionPair = len(terms) > 1 and all(term[2] is not None for term in terms)
    queryWords = tuple(word for token, axis, number, unit in terms for word in SearchWords(token))
    queryPhrase = " " + " ".join(queryWords) + " "
    # Promote product synonyms in names without promoting accessories that
    # merely mention that product in their keywords (for example couch pillows).
    nameSynonyms = {"couch": "sofa", "settee": "sofa", "television": "tv",
                    "fridge": "refrigerator", "refrigerator": "fridge", "washbasin": "basin"}
    indexed = []
    for definition in definitions:
        if definition["key"] == "null":
            continue
        keywords = definition.get("keywords", [])
        if isinstance(keywords, str):
            keywords = [keywords]
        categories = definition.get("categories")
        if categories is None:
            categories = FurnishingCategories(definition.get("category"))
        nameWords = SearchWords(definition["name"])
        keywordWords = SearchWords(" ".join(keywords))
        categoryWords = SearchWords(" ".join(categories))
        fields = tuple(" " + " ".join(words) + " " for words in (nameWords, keywordWords, categoryWords))
        words = frozenset(nameWords + keywordWords + categoryWords)
        # Retain alternate spellings for partial matching without promoting them
        # to whole-word matches or adding them to the fuzzy-search vocabulary.
        partialWords = words | {alias for alias, canonical in searchAliases.items()
                                if canonical in words and canonical.isalpha()}
        indexed.append((definition, fields, words, partialWords))
    variants = {}
    for fuzzy in (False, True):
        if fuzzy:
            # Only attempt one edit or one adjacent transposition, on words of
            # at least four letters, after the entire ordinary search failed.
            vocabulary = {word for definition, fields, words, partialWords in indexed for word in words if word.isalpha()}
            for token, axis, number, unit in terms:
                for word in SearchWords(token):
                    if axis is not None or number is not None or not word.isalpha() or len(word) < 4:
                        continue
                    alternatives = set()
                    for candidate in vocabulary:
                        if abs(len(word) - len(candidate)) > 1:
                            continue
                        if len(word) == len(candidate):
                            differences = [index for index, pair in enumerate(zip(word, candidate)) if pair[0] != pair[1]]
                            close = (len(differences) == 1 or len(differences) == 2 and
                                     differences[1] == differences[0] + 1 and
                                     word[differences[0]:differences[1] + 1] == candidate[differences[0]:differences[1] + 1][::-1])
                        else:
                            longer, shorter = sorted((word, candidate), key = len, reverse = True)
                            close = any(longer[:index] + longer[index + 1:] == shorter for index in range(len(longer)))
                        if close:
                            alternatives.add(candidate)
                    variants[word] = alternatives
            if not any(variants.values()):
                break
        results = []
        for definition, fields, words, partialWords in indexed:
            # Each candidate records occupied axes, worst text tier, total text
            # tier, rounded matches, and unit preference. Text never consumes an axis.
            candidates = {(frozenset(), 0, 0, 0, 0)}
            for token, axis, number, specifiedUnit in terms:
                choices = []
                tokenWords = SearchWords(token)
                phrase = " " + " ".join(tokenWords) + " "
                if axis is None and not dimensionPair and tokenWords:
                    textRank = next((rank for rank, field in enumerate(fields) if phrase in field), None)
                    namePhrase = " " + " ".join(nameSynonyms.get(word, word) for word in tokenWords) + " "
                    if namePhrase in fields[0]:
                        textRank = 0
                    if textRank is None and number is None:
                        if len(tokenWords) == 1 and tokenWords[0].isalpha() and any(tokenWords[0] in word for word in partialWords):
                            textRank = 3
                        elif fuzzy and all(word in words or variants.get(word, set()) & words for word in tokenWords):
                            fieldRanks = []
                            for word in tokenWords:
                                alternatives = variants.get(word, set()) | {word}
                                fieldRanks.append(next(rank for rank, field in enumerate(fields)
                                                       if any(" " + alternative + " " in field for alternative in alternatives)))
                            textRank = 4 + max(fieldRanks)
                    if textRank is not None:
                        choices.append((None, textRank, 0, 0))
                if number is not None:
                    for field in (("width",) if axis == "w" else ("length",) if axis == "l" else ("width", "length")):
                        for unitRank, unit in enumerate(units):
                            if specifiedUnit is not None and unit != specifiedUnit:
                                continue
                            # Explicit metric dimensions always refer to authored
                            # millimeters. Imperial queries use nominal geometry
                            # only when the current placement mode is imperial.
                            dimension = (NominalPlacementSize(definition[field], unitsMode)
                                         if unit in ("ft", "in") and unitsMode in imperialModes else definition[field])
                            target = number * divisors[unit]
                            exact = math.isclose(dimension, target, rel_tol = 1e-9, abs_tol = 1e-4)
                            rounded = False
                            if not exact and unit in ("mm", "cm", "m"):
                                decimals = 2 if unit == "m" else 0
                                rounded = math.isclose(round(dimension / divisors[unit], decimals), number,
                                                       rel_tol = 1e-9, abs_tol = 1e-9)
                            if exact or rounded:
                                choices.append((field, 0 if axis is not None or dimensionPair else 3,
                                                int(not exact), 0 if specifiedUnit else unitRank))
                candidates = {(used | {field} if field else used, max(worst, rank), score + rank,
                               approximate + rounded, unitScore + unitRank)
                              for used, worst, score, approximate, unitScore in candidates
                              for field, rank, rounded, unitRank in choices if field is None or field not in used}
                if not candidates:
                    break
            if candidates:
                score = min((worst, score, approximate, unitScore)
                            for used, worst, score, approximate, unitScore in candidates)
                phraseRank = 0 if fields[0] == queryPhrase else 1 if queryPhrase in fields[0] else 2
                results.append((score, phraseRank, definition["name"].strip().casefold(), definition["key"], definition))
        if results:
            return [item[-1] for item in sorted(results, key = lambda item: item[:-1])]
    return []
