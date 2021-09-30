import sys


def log(*args, **kwargs):
    kwargs.setdefault('file', sys.stderr)
    return print(*args, **kwargs)


def name_or_str(thing):
    return getattr(thing, 'name', str(thing))


def stringify(lst, sep=None):
    sep = sep or ', '
    return sep.join(name_or_str(i) for i in lst)
