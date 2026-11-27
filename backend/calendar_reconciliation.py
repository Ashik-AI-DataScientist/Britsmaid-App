"""Compare availability observations without replacing entered booking details."""


def label(value):
    return ' '.join(str(value or '').split()).casefold()


def review_differences(saved, observed):
    differences = [key for key in ('check_in', 'check_out') if saved.get(key) != observed.get(key)]
    # A Direct stay should also be unavailable on connected OTAs. The block is
    # consistent with that stay, not an instruction to cancel or re-channel it.
    direct_availability = (not differences and saved.get('status') == 'confirmed'
        and label(saved.get('ota')) == 'direct' and observed.get('status') == 'blocked'
        and bool(label(observed.get('ota'))) and label(observed.get('ota')) != 'direct')
    if direct_availability:
        return differences
    differences.extend(key for key in ('status', 'ota') if label(saved.get(key)) != label(observed.get(key)))
    saved_name, observed_name = label(saved.get('guest_name')), label(observed.get('guest_name'))
    placeholder = bool(saved_name) and observed_name in ('reserved', 'booked', 'ota guest')
    if saved_name != observed_name and not placeholder:
        differences.append('guest_name')
    return differences
