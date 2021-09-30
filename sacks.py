import functools

import dnf

from utils import log

DNF_CACHEDIR = '_dnf_cache_dir'
ARCH = 'x86_64'
MULTILIB = {'x86_64': 'i686'}  # architectures to exclude in certain queries
METALINK = 'https://mirrors.fedoraproject.org/metalink'


REPOS = {
    'rawhide': (
        {
            'repoid': 'rawhide',
            'metalink': f'{METALINK}?repo=rawhide&arch=$basearch',
        },
        {
            'repoid': 'rawhide-source',
            'metalink': f'{METALINK}?repo=rawhide-source&arch=$basearch',
        },
    )
}


@functools.cache
def base(repo_key):
    f"""
    Creates a DNF base from repositories defined in REPOS, based on the given key.
    The sack is filled, which can be extremely slow if not already cached on disk in {DNF_CACHEDIR}.
    Cache is never invalidated here, remove the directory manually if needed.
    """
    base = dnf.Base()
    conf = base.conf
    conf.cachedir = DNF_CACHEDIR
    conf.substitutions['releasever'] = 'rawhide'
    conf.substitutions['basearch'] = ARCH
    for repo in REPOS[repo_key]:
        base.repos.add_new_repo(conf=conf, skip_if_unavailable=False, **repo)
    log(f'• Filling the DNF sack to/from {DNF_CACHEDIR}...', end=' ')
    base.fill_sack(load_system_repo=False, load_available_repos=True)
    log('done.')
    return base


def rawhide_sack():
    """
    A filled sack to perform rawhide repoquries. See base() for details.
    """
    return base('rawhide').sack
