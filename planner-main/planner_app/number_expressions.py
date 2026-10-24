"""Bounded arithmetic for numeric editors, without executing source code."""
import math
import re


numberPattern = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
literalPattern = re.compile(numberPattern + r"(?:\s*(?:feet|ft|'|′)(?:\s*" + numberPattern
                            + r"\s*(?:inches|inch|in|\"|″))?|\s*(?:inches|inch|in|\"|″))?", re.I)


def EvaluateNumberExpression(text, current, parseLiteral = float):
    """Parse +, -, *, / and parentheses. A leading +, * or / uses current."""
    if len(text) > 256:
        raise ValueError("Expression is too long.")
    text = text.strip()
    if text.startswith(("+", "*", "/")):
        text = repr(float(current)) + text
    tokens = []
    position = 0
    while position < len(text):
        if text[position].isspace():
            position += 1
            continue
        literal = literalPattern.match(text, position)
        if literal is not None:
            value = parseLiteral(literal.group())
            if not math.isfinite(value) or abs(value) > 1e100:
                raise ValueError("Number is too large.")
            tokens.append(value)
            position = literal.end()
        elif text[position] in "+-*/()":
            tokens.append(text[position])
            position += 1
        else:
            raise ValueError("Only numbers and arithmetic operators are supported.")
        if len(tokens) > 128:
            raise ValueError("Expression is too complex.")
    index = 0

    def ParseExpression(minimumPrecedence = 0, depth = 0):
        nonlocal index
        if depth > 16 or index >= len(tokens):
            raise ValueError("Incomplete or overly nested expression.")
        token = tokens[index]
        index += 1
        if token in ("+", "-"):
            result = ParseExpression(3, depth + 1)
            if token == "-":
                result = -result
        elif token == "(":
            result = ParseExpression(0, depth + 1)
            if index >= len(tokens) or tokens[index] != ")":
                raise ValueError("Unmatched parentheses.")
            index += 1
        elif isinstance(token, (int, float)):
            result = token
        else:
            raise ValueError("Expected a number.")
        while index < len(tokens):
            operator = tokens[index]
            precedence = 1 if operator in ("+", "-") else 2 if operator in ("*", "/") else -1
            if precedence < minimumPrecedence:
                break
            index += 1
            right = ParseExpression(precedence + 1, depth + 1)
            if operator == "+":
                result += right
            elif operator == "-":
                result -= right
            elif operator == "*":
                result *= right
            elif right:
                result /= right
            else:
                raise ValueError("Cannot divide by zero.")
            if not math.isfinite(result) or abs(result) > 1e100:
                raise ValueError("Result is too large.")
        return result

    result = ParseExpression()
    if index != len(tokens):
        raise ValueError("Unexpected input after the expression.")
    return result
