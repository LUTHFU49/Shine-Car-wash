from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Usage: {{ my_dict|get_item:some_key }} -- Django templates have no
    built-in way to index a dict with a variable key."""
    if not dictionary:
        return None
    return dictionary.get(key)
