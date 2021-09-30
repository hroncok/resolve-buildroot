import fcntl
import pathlib
import subprocess

import pytest

from resolve_buildroot import ARCH
from resolve_buildroot import name_or_str
from resolve_buildroot import buildrequires_of
from resolve_buildroot import resolve_buildrequires_of


TESTS_DIR = pathlib.Path(__file__).parent
RAWHIDE_MOCK = f'fedora-rawhide-{ARCH}'


def run_mock(*cmd, **kwargs):
    kwargs.setdefault('check', True)
    kwargs.setdefault('stdout', subprocess.PIPE)
    kwargs.setdefault('stderr', subprocess.PIPE)
    kwargs.setdefault('text', True)
    with open((TESTS_DIR / RAWHIDE_MOCK).with_suffix('.lock'), 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return subprocess.run(['mock', '-r', RAWHIDE_MOCK, '--no-bootstrap-chroot',
                               '--isolation=simple', *cmd], **kwargs)


def resolve_buildroot_in_mock(package_name):
    run_mock('--init')
    run_mock('--update')
    run_mock('--dnf-cmd', 'builddep', package_name)
    packages = run_mock('--shell', 'rpm -qa --qf=%{NAME}\\\\n').stdout
    return set(packages.splitlines()) - {'gpg-pubkey'}  # pubkey only installed in mock


# XXX this test is sloooooow
# XXX sometimes, we might manually need to scrub our cache as well as mock's (--scrub=dnf-cache)
@pytest.mark.parametrize('package_name', ['pytest',
                                          'python-setuptools',
                                          'python-pip',
                                          'rpm'])
def test_resolve_buildrequires_of(package_name):
    expected = resolve_buildroot_in_mock(package_name)
    got = resolve_buildrequires_of(package_name)
    assert {name_or_str(p) for p in got} == expected


# XXX this test has data copied from simple specfiles, but it can change
@pytest.mark.parametrize('package_name, expected', [
    ('fedora-obsolete-packages', ()),
    ('fedora-repos', ('gnupg', 'sed')),
    ('fedora-release', ('redhat-rpm-config > 121-1', 'systemd-rpm-macros')),
    ('redhat-rpm-config', ('perl-generators',)),
])
def test_buildrequires_simple(package_name, expected):
    assert buildrequires_of(package_name) == expected
