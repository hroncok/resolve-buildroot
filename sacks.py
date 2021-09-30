import functools

import dnf

from utils import log

DNF_CACHEDIR = '_dnf_cache_dir'
ARCH = 'x86_64'
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


def sack(repo_key):
    f"""
    Creates a DNF sack from repositories defined in REPOS, based on the given key.
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
    return base.sack


def sack_factory(repo_key):
    """
    Creates a lru_cached function that returns a filled sack for the given key of REPOS.
    """

    @functools.lru_cache(maxsize=1)
    def _sack():
        f"""Returns a DNF sack for {repo_key}"""
        return sack(repo_key)
    return _sack


rawhide_sack = sack_factory('rawhide')
