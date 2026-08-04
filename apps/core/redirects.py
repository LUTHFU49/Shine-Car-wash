from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect_target(request, candidate, fallback):
    """
    Returns `candidate` if it's a same-site, same-scheme URL Django
    considers safe to redirect to, else `fallback`. Use this anywhere a
    'next' (or similar) redirect target comes from request.GET/POST --
    passing it to redirect() unvalidated is an open-redirect: a crafted
    ?next=https://evil.example.com link turns a legitimate action (e.g.
    logging in, marking a notification read) into a handoff to an
    attacker-controlled site.
    """
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure(),
    ):
        return candidate
    return fallback
