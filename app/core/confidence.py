def is_reliable(confidence, threshold) -> bool:
    try:
        if confidence is None:
            return False
        return float(confidence) >= float(threshold)
    except (TypeError, ValueError):
        return False
