def _escape_char(char, at_start):
    allowed = char.isalnum() or char in ":_."
    if allowed and not (at_start and char == "."):
        return char
    return "".join(f"\\x{byte:02x}" for byte in char.encode())


def fortress_systemd_mount_unit(path):
    normalized = "/".join(part for part in str(path).split("/") if part)
    if not normalized:
        return "-.mount"

    escaped = []
    at_start = True
    for char in normalized:
        if char == "/":
            escaped.append("-")
            at_start = True
            continue
        escaped.append(_escape_char(char, at_start))
        at_start = False
    return f"{''.join(escaped)}.mount"


class FilterModule:
    def filters(self):
        return {
            "fortress_systemd_mount_unit": fortress_systemd_mount_unit,
        }
