import datetime


def human_readable_timedelta(datetime_to_compare):
    # Current time
    now = datetime.datetime.utcnow()

    # Determine if the event is in the past or future
    delta = datetime_to_compare - now
    if delta.total_seconds() > 0:
        event_time = now + delta
        suffix = "from now"
    else:
        event_time = now - delta
        suffix = "ago"

    # Calculate the difference
    diff = now - event_time if delta.total_seconds() > 0 else event_time - now

    # Determine the largest time unit (years, months, etc.)
    seconds = abs(diff.total_seconds())
    minutes = abs(seconds / 60)
    hours = abs(minutes / 60)
    days = abs(diff.days) if diff.days >= 0 else 0
    weeks = abs(days / 7)
    months = abs(days / 30)
    years = abs(days / 365)
    

    # Choose the appropriate time unit and format the string
    if years >= 1:
        return f"{int(years)} years {suffix}" if years >= 2 else "about 1 year ago"
    elif months >= 1:
        return f"{int(months)} months {suffix}" if months >= 2 else "about 1 month ago"
    elif weeks >= 1:
        return f"{int(weeks)} weeks {suffix}" if weeks >= 2 else "about 1 week ago"
    elif days >= 1:
        return f"{int(days)} days {suffix}" if days >= 2 else "1 day ago"
    elif hours >= 1:
        return f"{int(hours)} hours {suffix}" if hours >= 2 else "1 hour ago"
    elif minutes >= 1:
        return f"{int(minutes)} minutes {suffix}" if minutes >= 2 else "1 minute ago"
    elif minutes < 1:
        return f"{int(minutes)} minutes {suffix}" if minutes >= 2 else "less than 1 minute ago"
    else:
        return "just now"
