import collections
import functools
import sys

from sacks import ARCH, MULTILIB, rawhide_sack, target_sack
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
EXTRA_COMPONENTS = (
    'python3-docs',
)


class ReverseLookupDict(collections.defaultdict):
    """
    An enhanced defaultdict(list) that can reverse-lookup the keys for given items.
    Unique values in the lists are assumed but not checked.

    Use it like a regular dict, but lookup a key by the key(item) method.
    Use the all_values() method to get a set of all items in all keys at once.

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

    def all_values(self):
        return {value for lst in self.values() for value in lst}


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


@functools.lru_cache(maxsize=1)
def packages_built(new_deps, *, excluded_components=()):
    """
    Given a hashable collection of string-dependencies that are "new",
    queries target for all binary packages that require those
    and returns them in a dict:
     - keys: SRPM-names
     - values: lists of hawkey.Packages

    Excluded_components is an optional hashable collection of component names
    to exclude from the results.
    """
    sack = target_sack()
    log('• Querying all successfully rebuilt packages...', end=' ')
    results = sack.query().filter(requires=new_deps, arch__neq='src', latest=1)
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


def are_all_done(*, packages_to_check, all_components, components_done, blocker_counter, loop_detector):
    """
    Given a collection of (binary) packages_to_check, and dicts of all_components and components_done,
    returns True if ALL packages_to_check are considered "done" (i.e. installable).
    """
    relevant_components = ReverseLookupDict()
    for pkg in packages_to_check:
        relevant_components[all_components.key(pkg)].append(pkg)
    relevant_components.default_factory = None

    log(f'  • {component}: {len(packages_to_check)} packages / {len(relevant_components)} '
        f'components relevant to our problem')
    all_available = True
    blocking_components = set()
    for relevant_component, required_packages in relevant_components.items():
        log(f'    • {relevant_component}')
        count_component = False
        for required_package in required_packages:
            has_older = False
            for done_package in components_done.get(relevant_component, ()):
                # The done packages are from different repo and might have different EVR
                # Hence, we only compare the names
                # For Copr rebuilds, the Copr EVR must be >= Fedora EVR
                # For koji rebuilds, this will be always true anyway
                if done_package.name == required_package.name:
                    if not done_package.evr_lt(required_package):
                        log(f'      ✔ {required_package.name}')
                        break
                    else:
                        has_older = True
            else:
                if has_older:
                    log(f'      ✗ {required_package.name} (older EVR available)')
                else:
                    log(f'      ✗ {required_package.name}')
                all_available = False
                count_component = True
        if count_component:
            blocker_counter['general'][relevant_component] += 1
            blocking_components.add(relevant_component)
    if len(blocking_components) == 1:
        blocker_counter['single'][blocking_components.pop()] += 1
    elif 1 < len(blocking_components) < 10:  # this is an arbitrarily chosen number to avoid cruft
        blocker_counter['combinations'][tuple(sorted(blocking_components))] += 1
    loop_detector[component] = sorted(blocking_components)
    return all_available


def _sort_loop(loop):
    index = loop.index(min(loop))
    return tuple(loop[index:] + loop[:index+1])


def _detect_loop(loop_detector, probed_component, depchain, loops, seen):
    for component in loop_detector[probed_component]:
        seen.add(component)
        if component in PACKAGES_BCONDS:
            # we assume bconds are manually crafted not to have loops
            continue
        if loop_detector.get(component, []) == []:
            continue
        if component in depchain:
            loops.add(_sort_loop(depchain[depchain.index(component):]))
            continue
        _detect_loop(loop_detector, component, depchain + [component], loops, seen)

def report_blocking_components(loop_detector):
    loops = set()
    seen = set()
    for component in loop_detector:
        if component not in seen:
            _detect_loop(loop_detector, component, [component], loops, seen)
    log('\nDetected dependency loops:')
    for loop in sorted(loops, key=lambda t: -len(t)):
        log('    • ' + ' → '.join(loop))

if __name__ == '__main__':
    # this is spaghetti code that will be split into functions later:
    from resolve_buildroot import resolve_buildrequires_of, resolve_requires
    from bconds import PACKAGES_BCONDS, bcond_cache_identifier, extract_buildrequires_if_possible

    components = packages_to_rebuild(OLD_DEPS, excluded_components=EXCLUDED_COMPONENTS)
    for component in EXTRA_COMPONENTS:
        components[component] = []
    components_done = packages_built(NEW_DEPS, excluded_components=EXCLUDED_COMPONENTS)
    binary_rpms = components.all_values()

    blocker_counter = {
        'general': collections.Counter(),
        'single': collections.Counter(),
        'combinations': collections.Counter(),
    }
    loop_detector = {}

    for component in components:
        if len(sys.argv) > 1 and component not in sys.argv[1:]:
            continue

        try:
            component_buildroot = resolve_buildrequires_of(component)
        except ValueError as e:
            log(f'\n  ✗ {e}')
            continue

        ready_to_rebuild = are_all_done(
            packages_to_check=set(component_buildroot) & binary_rpms,
            all_components=components,
            components_done=components_done,
            blocker_counter=blocker_counter,
            loop_detector=loop_detector,
        )

        if ready_to_rebuild:
            # XXX make this configurable
            if True: #  component not in components_done:
                print(component)
        elif component in PACKAGES_BCONDS:
            for config in PACKAGES_BCONDS[component]:
                config['id'] = bcond_cache_identifier(component, config)
                log(f'• {component} not ready and {config["id"]} bcond found, will check that one')
                if 'buildrequires' not in config:
                    extract_buildrequires_if_possible(component, config)
                if 'buildrequires' in config:
                    try:
                        component_buildroot = resolve_requires(tuple(sorted(config['buildrequires'])))
                    except ValueError as e:
                        log(f'\n  ✗ {e}')
                        continue
                    ready_to_rebuild = are_all_done(
                        packages_to_check=set(component_buildroot) & binary_rpms,
                        all_components=components,
                        components_done=components_done,
                        blocker_counter=blocker_counter,
                        loop_detector=loop_detector,
                    )
                    if ready_to_rebuild:
                        if True: #  component not in components_done:
                            print(config['id'])
                else:
                    log(f' • {config["id"]} bcond SRPM not present yet, skipping')

    log('\nThe 50 most commonly needed components are:')
    for component, count in blocker_counter['general'].most_common(50):
        log(f'{count:>5} {component}')

    log('\nThe 20 most commonly last-blocking components are:')
    for component, count in blocker_counter['single'].most_common(20):
        log(f'{count:>5} {component}')

    log('\nThe 20 most commonly last-blocking small combinations of components are:')
    for components, count in blocker_counter['combinations'].most_common(20):
        log(f'{count:>5} {", ".join(components)}')

    report_blocking_components(loop_detector)
