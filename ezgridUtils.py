def multiply_slurm_time(time_str, multiplier):
    from datetime import timedelta

    # Parse time string into components
    if "-" in time_str:
        days_str, hms = time_str.split("-")
        days = int(days_str)
    else:
        hms = time_str
        days = 0

    hours, minutes, seconds = map(int, hms.split(":"))

    # Convert to timedelta
    total = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    # Multiply and normalize
    total *= multiplier
    total_seconds = int(total.total_seconds())

    # Break back into SLURM format
    new_days = total_seconds // 86400
    rem = total_seconds % 86400
    new_hours = rem // 3600
    rem %= 3600
    new_minutes = rem // 60
    new_seconds = rem % 60

    return f"{new_days}-{new_hours:02}:{new_minutes:02}:{new_seconds:02}"
