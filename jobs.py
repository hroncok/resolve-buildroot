import collections
import functools
import sys

from sacks import ARCH, MULTILIB, rawhide_sack
from utils import log


# XXX we need an interface to set this, not constants
OLD_DEPS = (
    'python(abi) = 3.10',
    'libpython3.10.so.1.0()(64bit)',
    'libpython3.10d.so.1.0()(64bit)',
)
NEW_DEPS = (
    'python(abi) = 3.11',
    'libpython3.11.so.1.0()(64bit)',
    'libpython3.11d.so.1.0()(64bit)',
)
EXCLUDED_COMPONENTS = (
    'python3.10',
    'python3.11',
)


class ReverseLookupDict(collections.defaultdict):
    """
    An enhanced defaultdict(list) that can reverse-lookup the keys for given items.
    Unique values in the lists are assumed but not checked.

    Use it like a regular dict, but lookup a key by the key(item) method.

    The lookup is internally cached in a reversed dictionary.

    In our code, we use this with lists of hawkey.Packages,
    but should work with any hashable values.
    """
    def __init__(self):
        super().__init__(list)
        self._reverse_lookup_cache = {}

    def key(self, value):
        if value in self._reverse_lookup_cache:
            return self._reverse_lookup_cache[value]
        for candidate_key, lst in self.items():
            if value in lst:
                self._reverse_lookup_cache[value] = candidate_key
                return candidate_key
        raise KeyError(f'Value {value!r} found in no list in this dict.')


@functools.lru_cache(maxsize=1)
def packages_to_rebuild(old_deps, *, excluded_components=()):
    """
    Given a hashable collection of string-dependencies that are "old",
    queries rawhide for all binary packages that require those
    and returns them in a dict:
     - keys: SRPM-names
     - values: lists of hawkey.Packages

    Excluded_components is an optional hashable collection of component names
    to exclude from the results.

    If rawhide does not contain our newly rebuilt packages (which is expected here),
    the dict will also contain packages that already successfully rebuilt
    (in our side tag or copr, etc.).
    """
    sack = rawhide_sack()
    log('• Querying all packages to rebuild...', end=' ')
    results = sack.query().filter(requires=old_deps, arch__neq='src', latest=1)
    if ARCH in MULTILIB:
        results = results.filter(arch__neq=MULTILIB[ARCH])
    components = ReverseLookupDict()
    anticount = 0
    for result in results:
        if result.source_name not in excluded_components:
            components[result.source_name].append(result)
        else:
            anticount += 1
    # no longer create lists on access to avoid mistakes:
    components.default_factory = None
    log(f'found {len(components)} components ({len(results)-anticount} binary packages).')
    return components


if __name__ == '__main__':
    # this is merely to invoke the function via CLI for easier manual testing
    components = packages_to_rebuild(OLD_DEPS, excluded_components=EXCLUDED_COMPONENTS)
    package_name = sys.argv[1]
    package_obj = rawhide_sack().query().filter(latest=1, name=package_name).run()[0]
    print(components.key(package_obj))
    print(components._reverse_lookup_cache)
