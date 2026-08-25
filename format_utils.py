"""Formatting helpers shared by the desktop UI and document generator."""


def format_percentage(value):
    """Return a clean percentage number without unnecessary trailing zeros.

    Examples: 50 -> ``"50"``, 60.0 -> ``"60"``, and 33.333 -> ``"33.33"``.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")
