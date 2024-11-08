"""
This module contains helper functions to manipulate with distgit repositories:
clone them, refresh their local copies and patch the specfiles.
"""

import re

from utils import CONFIG, log, run


def clone_into(component_name, target, branch=''):
    branch = branch or CONFIG['distgit']['branch']
    log(f' • Cloning {component_name} into "{target}"...', end=' ')
    # I would like to use --depth=1 but that breaks rpmautospec
    # https://pagure.io/fedora-infra/rpmautospec/issue/227
    run('fedpkg', 'clone', component_name, target, f'--branch={branch}')
    log('done.')


def refresh_gitrepo(repopath, prune_existing=False):
    log(f' • Refreshing "{repopath}" git repo...', end=' ')
    git = 'git', '-C', repopath
    head_before = run(*git, 'rev-parse', 'HEAD').stdout.rstrip()
    run(*git, 'stash')
    run(*git, 'reset', '--hard')
    run(*git, 'pull')
    head_after = run(*git, 'rev-parse', 'HEAD').stdout.rstrip()
    if head_before == head_after:
        if not prune_existing:
            # we try to preserve the changes for local inspection, but if it fails, meh
            run(*git, 'stash', 'pop', check=False)
        log('already up to date.')
        return False
    else:
        log(f'updated {head_before[:10]}..{head_after[:10]}.')
        return True


def patch_spec(specpath, bcond_config):
    log(f'   • Patching {specpath.name}')

    run('git', '-C', specpath.parent, 'reset', '--hard')

    spec_text = specpath.read_text()

    lines = []
    for without in sorted(bcond_config.get('withouts', ())):
        if without in bcond_config.get('withs', ()):
            raise ValueError(f'Cannot have the same with and without: {without}')
        lines.append(f'%global _without_{without} 1')
    for with_ in sorted(bcond_config.get('withs', ())):
        lines.append(f'%global _with_{with_} 1')
    for macro, value in bcond_config.get('replacements', {}).items():
        spec_text = re.sub(fr'^(\s*)%(define|global)(\s+){macro}(\s+)\S.*$',
                           fr'\1%\2\g<3>{macro}\g<4>{value}',
                           spec_text, flags=re.MULTILINE)
    lines.append(spec_text)
    specpath.write_text('\n'.join(lines))


def refresh_or_clone(repopath, component_name, *, prune_existing=False, no_git_refresh=False, branch=''):
    """
    Returns True if there's new contents of the repository.
    Returns False if the content of the repository remains the same
    or if no_git_refresh option is set to True
    (we skip the repository update and assume nothing has changed).
    """
    if repopath.exists():
        if no_git_refresh:
            return False
        else:
            return refresh_gitrepo(repopath, prune_existing=prune_existing)
    else:
        repopath.parent.mkdir(exist_ok=True)
        clone_into(component_name, repopath, branch=branch)
        return True
