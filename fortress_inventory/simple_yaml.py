import re


def load_yaml(path):
    lines = []
    for raw_line in path.read_text().splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        lines.append(raw_line.rstrip())
    if not lines:
        return {}
    value, index = _parse_block(lines, 0, _indent(lines[0]))
    if index != len(lines):
        raise ValueError(f"could not parse {path}: unexpected line {index + 1}")
    return value


def _parse_block(lines, index, indent):
    if index >= len(lines):
        return {}, index
    if _indent(lines[index]) < indent:
        return {}, index
    if lines[index][_indent(lines[index]) :].startswith("- "):
        return _parse_list(lines, index, indent)
    return _parse_dict(lines, index, indent)


def _parse_dict(lines, index, indent):
    result = {}
    while index < len(lines):
        line_indent = _indent(lines[index])
        if line_indent < indent:
            break
        if line_indent > indent:
            raise ValueError(f"unexpected indentation at line {index + 1}")
        text = lines[index][indent:]
        if text.startswith("- "):
            break
        key, raw_value = _split_key_value(text, index)
        index += 1
        if raw_value == "":
            value, index = _parse_block(lines, index, indent + 2)
        else:
            value = _parse_scalar(raw_value)
        result[key] = value
    return result, index


def _parse_list(lines, index, indent):
    result = []
    while index < len(lines):
        line_indent = _indent(lines[index])
        if line_indent < indent:
            break
        if line_indent != indent:
            raise ValueError(f"unexpected list indentation at line {index + 1}")
        text = lines[index][indent:]
        if not text.startswith("- "):
            break
        item_text = text[2:]
        index += 1
        if item_text == "":
            item, index = _parse_block(lines, index, indent + 2)
        elif _looks_like_key_value(item_text):
            key, raw_value = _split_key_value(item_text, index - 1)
            item = {key: _parse_scalar(raw_value) if raw_value else {}}
            if index < len(lines) and _indent(lines[index]) > indent:
                extra, index = _parse_block(lines, index, indent + 2)
                if isinstance(extra, dict):
                    item.update(extra)
        else:
            item = _parse_scalar(item_text)
        result.append(item)
    return result, index


def _parse_scalar(value):
    value = value.strip()
    if value in ("[]", ""):
        return []
    if value == "{}":
        return {}
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None", "~"):
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in _split_inline(inner)]
    if value.startswith("{") and value.endswith("}"):
        inner = value[1:-1].strip()
        if not inner:
            return {}
        result = {}
        for part in _split_inline(inner):
            key, raw_value = _split_key_value(part, 0)
            result[key] = _parse_scalar(raw_value)
        return result
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    return value


def _split_inline(value):
    parts = []
    current = []
    quote = None
    for char in value:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
            current.append(char)
        elif char == ",":
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    return parts


def _split_key_value(text, line_index):
    if ":" not in text:
        raise ValueError(f"expected key/value at line {line_index + 1}")
    key, value = text.split(":", 1)
    key = key.strip().strip("\"'")
    if not key:
        raise ValueError(f"empty key at line {line_index + 1}")
    return key, value.strip()


def _looks_like_key_value(text):
    return ":" in text and not text.startswith(("http://", "https://"))


def _indent(line):
    return len(line) - len(line.lstrip(" "))
