import functools
import sys

import hawkey

from sacks import rawhide_sack
from utils import log, stringify

# Some deps are only pulled in when those are installed:
# XXX we would like to resolve the @buildsys-build instead, now copy-pasted
DEFAULT_DEPS = (
    'bash',
    'bzip2',
    'coreutils',
    'cpio',
    'diffutils',
    'fedora-release-common',
    'findutils',
    'gawk',
    'glibc-minimal-langpack',
    'grep',
    'gzip',
    'info',
    'patch',
    'redhat-rpm-config',
    'rpm-build',
    'sed',
    'shadow-utils',
    'tar',
    'unzip',
    'util-linux',
    'which',
    'xz',
)


@functools.cache
def buildrequires_of(package_name, extra_requires=()):
    """
    Given a package name, returns all buildrequires in their string representations.
    The result is a sorted, deduplicated tuple,
    so it can be hashed as an argument to other cached functions.

    This loads the BuildRequires from the rawhide-source repo,
    note that some packages may have different BuildRequires on different architectures
    and the architecture in the source repo is randomly selected by Koji.
    If you know some package is affected by this,
    you can manually add a hashable collection of extra_requires.

    The package name is searched in the source repo
    and this function only works if exactly 1 package is found.
    If multiple are found, something is wrong with the setup -> RuntimeError.
    If none is found, a package by that name does not exist -> ValueError.
    """
    sack = rawhide_sack()
    log(f'• Finding BuildRequires of {package_name}...', end=' ')
    pkgs = sack.query().filter(name=package_name, arch='src', latest=1).run()
    if not pkgs:
        raise ValueError(f'No SRPMs called {package_name} found.')
    if len(pkgs) > 1:
        raise RuntimeError(f'Too many SRPMs called {package_name} found: {pkgs!r}')
    log(f'found {len(pkgs[0].requires)+len(extra_requires)} requirements.')
    return tuple(
        sorted(
            set(str(r) for r in pkgs[0].requires) | set(str(r) for r in extra_requires)
        )
    )


@functools.cache
def resolve_requires(requires, ignore_weak_deps=True):
    """
    Given a hashable collection of requirements,
    resolves all of them and the default buildroot packages in the rawhide repos
    and returns a list of hawkey.Packages (in implicit hawkey order) to be installed.

    If ignore_weak_deps is true (the default), weak dependencies (e.g. Recommends) are ignored,
    which is what happens in mock/Koji as well.

    If hawkey wants to upgrade or erase stuff, something is wrong with the setup -> RuntimeError.
    If hawkey cannot resolve the set, the requires are not installable -> ValueError.
    """
    sack = rawhide_sack()
    goal = hawkey.Goal(sack)
    log(f'• Resolving {len(requires)} requirements...', end=' ')
    for dep in DEFAULT_DEPS + requires:
        selector = hawkey.Selector(sack).set(provides=dep)
        goal.install(select=selector)
    if not goal.run(ignore_weak_deps=ignore_weak_deps):
        raise ValueError(f'Cannot resolve {stringify(DEFAULT_DEPS + requires)}')
    if goal.list_upgrades() or goal.list_erasures():
        raise RuntimeError('Got packages to upgrade or erase, that should never happen.')
    log(f'to {len(goal.list_installs())} installs.')
    return goal.list_installs()


@functools.cache
def resolve_buildrequires_of(package_name, *, extra_requires=(), ignore_weak_deps=True):
    """
    A glue function that takes a package name (and optional keyword arguments)
    and returns a resolved list of hawkey.Packages to install.

    See buildrequires_of() and resolve_requires() for details.
    """
    brs = buildrequires_of(package_name, extra_requires=extra_requires)
    return resolve_requires(brs, ignore_weak_deps=ignore_weak_deps)


if __name__ == '__main__':
    # this is merely to invoke the function via CLI for easier manual testing
    package = sys.argv[1]
    extra_requires = tuple(sys.argv[1:])
    installs = resolve_buildrequires_of(package, extra_requires=extra_requires)
    print(stringify(installs, '\n'))
