import functools

import dnf

from utils import log

DNF_CACHEDIR = '_dnf_cache_dir'
ARCH = 'x86_64'
METALINK = 'https://mirrors.fedoraproject.org/metalink'


@functools.lru_cache(maxsize=1)
def rawhide_sack():
    base = dnf.Base()
    conf = base.conf
    conf.cachedir = DNF_CACHEDIR
    conf.substitutions['releasever'] = 'rawhide'
    conf.substitutions['basearch'] = ARCH
    for repo_name in 'rawhide', 'rawhide-source':
        base.repos.add_new_repo(
            repo_name,
            conf,
            metalink=f'{METALINK}?repo={repo_name}&arch=$basearch',
            skip_if_unavailable=False,
        )
    log('• Filling the DNF sack, can take minutes if not cached...', end=' ')
    base.fill_sack(load_system_repo=False, load_available_repos=True)
    log('done.')
    return base.sack
