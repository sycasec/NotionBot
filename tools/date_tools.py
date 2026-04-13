import logging
from datetime import datetime, timedelta

from langchain_core.tools import tool

log = logging.getLogger(__name__)


@tool
def date_math(expression: str) -> str:
    """Calculate dates relative to today.
    expression: a natural expression like 'today + 30 days', 'today - 2 weeks',
                'today + 3 months', or just 'today'.
    Supported units: days, weeks, months, years.
    Returns the resulting date.
    """
    expr = expression.lower().strip()

    try:
        today = datetime.now().date()

        if expr == "today":
            return f"Today is {today.strftime('%A, %B %d, %Y')}."

        # Parse "today +/- N unit"
        import re
        match = re.match(r"today\s*([+-])\s*(\d+)\s*(days?|weeks?|months?|years?)", expr)
        if not match:
            return (
                f"Could not parse '{expression}'. "
                "Use format like 'today + 30 days', 'today - 2 weeks', "
                "'today + 3 months', or 'today + 1 year'."
            )

        sign = 1 if match.group(1) == "+" else -1
        amount = int(match.group(2)) * sign
        unit = match.group(3).rstrip("s")  # normalize to singular

        if unit == "day":
            result = today + timedelta(days=amount)
        elif unit == "week":
            result = today + timedelta(weeks=amount)
        elif unit == "month":
            # Approximate: 30 days per month
            month = today.month + amount
            year = today.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(today.day, _days_in_month(year, month))
            result = today.replace(year=year, month=month, day=day)
        elif unit == "year":
            year = today.year + amount
            day = min(today.day, _days_in_month(year, today.month))
            result = today.replace(year=year, day=day)
        else:
            return f"Unknown unit '{unit}'. Use days, weeks, months, or years."

        diff = (result - today).days
        direction = "from now" if diff >= 0 else "ago"
        return (
            f"{result.strftime('%A, %B %d, %Y')} "
            f"({abs(diff)} days {direction})"
        )
    except Exception as e:
        log.warning("Date math error for '%s': %s", expression, e)
        return f"Error calculating date: {e}"


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month."""
    import calendar
    return calendar.monthrange(year, month)[1]
