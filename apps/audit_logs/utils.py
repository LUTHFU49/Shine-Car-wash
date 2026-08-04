def field_diff(old_values, new_values):
    """
    Given two dicts of the "before" and "after" state of the same set of
    fields, returns {'before': {...}, 'after': {...}} containing only
    the fields that actually changed -- ready to drop straight into
    AuditLog.metadata (a JSONField). Values are coerced to strings so
    anything JSON-unfriendly (model instances, UUIDs, datetimes,
    Decimal) still serializes cleanly.

    Returns None if nothing changed, so callers can skip writing an
    empty/pointless audit entry.
    """
    before, after = {}, {}
    for field, old_val in old_values.items():
        new_val = new_values.get(field)
        if old_val != new_val:
            before[field] = str(old_val) if old_val is not None else None
            after[field] = str(new_val) if new_val is not None else None
    return {'before': before, 'after': after} if before else None
