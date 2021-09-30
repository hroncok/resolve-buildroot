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
def buildrequires_of(package_name):
    sack = rawhide_sack()
    log(f'• Finding BuildRequires of {package_name}.')
    pkgs = sack.query().filter(name=package_name, arch='src', latest=1).run()
    if not pkgs:
        raise ValueError(f'No SRPMs called {package_name} found.')
    if len(pkgs) > 1:
        raise ValueError(f'Too many SRPMs called {package_name} found: {pkgs!r}')
    # let's return a hashable type, so we can cache the result of resolving it:
    return tuple(sorted(str(dep) for dep in pkgs[0].requires))


@functools.cache
def resolve_requires(requires):
    sack = rawhide_sack()
    goal = hawkey.Goal(sack)
    log(f'• Resolving {len(requires)} requires.')
    for dep in DEFAULT_DEPS + requires:
        selector = hawkey.Selector(sack).set(provides=dep)
        goal.install(select=selector)
    if not goal.run(ignore_weak_deps=True):
        raise RuntimeError(f'Cannot resolve {stringify(DEFAULT_DEPS + requires)}')
    if goal.list_upgrades() or goal.list_erasures():
        raise RuntimeError('Got packages to upgrade or erase, that should never happen.')
    return goal.list_installs()


@functools.cache
def resolve_buildrequires_of(package_name):
    brs = buildrequires_of(package_name)
    return resolve_requires(brs)


if __name__ == '__main__':
    print(stringify(resolve_buildrequires_of(sys.argv[1]), '\n'))
