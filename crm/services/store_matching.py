from crm.models import Store


class StoreMatchResult:
    def __init__(self, store=None, needs_review=False, candidates=None, reason=''):
        self.store = store
        self.needs_review = needs_review
        self.candidates = list(candidates or [])
        self.reason = reason


def find_store(store_name, owner_name='', area=''):
    """Exact triple-key match: store name + owner + area."""
    if not store_name:
        return None

    return Store.objects.filter(
        name_normalized=Store.normalize_text(store_name),
        owner_normalized=Store.normalize_text(owner_name),
        area=area or '',
    ).first()


def find_store_candidates(store_name, owner_name='', area=''):
    """Return stores with the same name for admin review when identity is incomplete."""
    if not store_name:
        return Store.objects.none()

    qs = Store.objects.filter(name_normalized=Store.normalize_text(store_name))

    owner_norm = Store.normalize_text(owner_name)
    area_value = area or ''

    if owner_norm:
        qs = qs.filter(owner_normalized=owner_norm)
    if area_value:
        qs = qs.filter(area=area_value)

    return qs.order_by('area', 'owner_name')


def match_store(store_name, owner_name='', area=''):
    """
    Match a voice mention to an existing store.

    Requires all three fields for auto-match. Name-only mentions need review.
    """
    if not store_name:
        return StoreMatchResult(needs_review=True, reason='Store name is missing.')

    if not owner_name or not area:
        candidates = find_store_candidates(store_name)
        return StoreMatchResult(
            needs_review=True,
            candidates=candidates,
            reason='Owner name and area are both required to auto-match a store.',
        )

    store = find_store(store_name, owner_name, area)
    if store:
        return StoreMatchResult(store=store)

    return StoreMatchResult(
        needs_review=True,
        reason='No exact match found. Create a new store or pick an existing candidate.',
        candidates=find_store_candidates(store_name),
    )


def get_or_create_store(store_name, owner_name='', area='', **defaults):
    """Get or create a store using the triple-key identity."""
    store = find_store(store_name, owner_name, area)
    if store:
        return store, False

    store = Store.objects.create(
        store_name=store_name,
        owner_name=owner_name or '',
        area=area or '',
        **defaults,
    )
    return store, True
