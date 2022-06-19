import functools

import dnf

from utils import log

DNF_CACHEDIR = '_dnf_cache_dir'
ARCH = 'x86_64'
MULTILIB = {'x86_64': 'i686'}  # architectures to exclude in certain queries
METALINK = 'https://mirrors.fedoraproject.org/metalink'
KOJI = 'http://kojipkgs.fedoraproject.org'
COPR = 'https://copr-be.cloud.fedoraproject.org'


REPOS = {
    'rawhide': (
        {
            'repoid': 'rawhide',
            # 'metalink': f'{METALINK}?repo=rawhide&arch=$basearch',
            'baseurl': [f'{KOJI}/repos/rawhide/latest/$basearch/'],
            'metadata_expire': 60*60*24*365,
        },
        {
            'repoid': 'rawhide-source',
            # 'metalink': f'{METALINK}?repo=rawhide-source&arch=$basearch',
            'baseurl': [f'{KOJI}/repos/rawhide/latest/src/'],
            'metadata_expire': 60*60*24*365,
        },
    ),
    # XXX Make this configurable, it can be a koji side tag, etc.
    'target': (
        {
            'repoid': 'python3.11',
            #'baseurl': [f'{COPR}/results/@python/python3.11/fedora-rawhide-$basearch/'],
            'baseurl': [f'{KOJI}/repos/f37-python/latest/$basearch/'],
            'metadata_expire': 60,
        },
    ),
}


@functools.cache
def _base(repo_key):
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
    log(f'• Filling the DNF {repo_key} sack to/from {DNF_CACHEDIR}...', end=' ')
    base.fill_sack(load_system_repo=False, load_available_repos=True)
    log('done.')
    return base


def rawhide_group(group_id):
    """
    Return a rawhide comps group of a given id (a.k.a. name)
    """
    base = _base('rawhide')
    log('• Reading the comps information...', end=' ')
    base.read_comps()
    log('done.')
    for group in base.comps.groups_by_pattern(group_id):
        if group.id == group_id:
            return group
    raise ValueError(f'No such group {group_id}')


def rawhide_sack():
    """
    A filled sack to perform rawhide repoquries. See base() for details.
    """
    return _base('rawhide').sack


def target_sack():
    """
    A filled sack to perform target repoquries. See base() for details.
    """
    return _base('target').sack
