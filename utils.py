import sys


def log(*args, **kwargs):
    """
    A print replacement that prints to stderr.
    """
    kwargs.setdefault('file', sys.stderr)
    return print(*args, **kwargs)


def name_or_str(thing):
    """
    Useful helper to convert various Hawkey/DNF objects to strings.
    Returns the object's name attribute, falls back to the str representation.
    """
    return getattr(thing, 'name', str(thing))


def stringify(lst, separator=', '):
    """
    Converts a list of objects to a single string, using the name_or_str() function.
    If no separator is given, separates the items by comma and space.
    """
    return separator.join(name_or_str(i) for i in lst)
