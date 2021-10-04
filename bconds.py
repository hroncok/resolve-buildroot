import os
import pathlib
import re
import subprocess

from utils import log

# XXX ARCH is also defined in sacks.py but technically can be different :/
# Here we prefer the most reliable/fast architecture
KOJI_ARCH = 'x86_64'
KOJI_ID_FILENAME = 'koji.id'


FEDPKG_CACHEDIR = pathlib.Path('_fedpkg_cache_dir')
DEFAULT_BRANCH = 'rawhide'

# XXX we need an actual user-configuration for this
PACKAGES_BCONDS = {
    'python-six': [  # this is a list of know useful non-default configurations
        {'withouts': ['tests']},
    ],
    'python-py': [
        {'withouts': ['tests', 'docs']},
    ],
    'python-pbr': [
        {'withs': ['bootstrap']},
    ],
    'ara': [
        {'replacements': {'with_docs': '0'}},
    ],
}


def job_identifier(component_name, config, *, branch='', target=''):
    """
    Return an unique more or less human-readable string identifier for caching purposes.
    The form of the identifier is more or less:
        component_name:without_configuration:with_configuration:replacements_configuration:branch:target

    With "defaults" empty. E.g. the gcc package built without tests and docs in rawhide would be:
        gcc:docs-tests::::

    And a complex package without docs and tests but with bootstrap with replaced macro on f35 branch in f35-side-1234:
        complex:docs-tests:bootstrap:use_supernatular_forces:f35:f35-side-1234

    If multiple options are present, they are sorted for canonical representation
    and separated with dashes (not possible in macro names).
    The values of replaced macros are not stored, we assume it won't be needed.
    From the above notice, it is obvious the form might change in the future.
    """
    withouts_id = '-'.join(sorted(config.get('withouts', [])))
    withs_id = '-'.join(sorted(config.get('withs', [])))
    replacements_id = '-'.join(sorted(config.get('replacements', {})))
    if branch == DEFAULT_BRANCH:
        branch = ''
    return f'{component_name}:{withouts_id}:{withs_id}:{replacements_id}:{branch}:{target}'


def run(*cmd, **kwargs):
    kwargs.setdefault('check', True)
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    return subprocess.run(cmd, **kwargs)


def clone_into(component_name, target, branch=''):
    branch = branch or DEFAULT_BRANCH
    log(f' • Cloning {component_name} into "{target}"...', end=' ')
    run('fedpkg', 'clone', '-a', component_name, target, '--depth=1', f'--branch={branch}')
    log('done.')


def refresh_gitrepo(repopath):
    log(f' • Refreshing "{repopath}" git repo...', end=' ')
    git = 'git', '-C', repopath
    head_before = run(*git, 'rev-parse', 'HEAD').stdout.rstrip()
    run(*git, 'stash')
    run(*git, 'reset', '--hard')
    run(*git, 'pull')
    head_after = run(*git, 'rev-parse', 'HEAD').stdout.rstrip()
    if head_before == head_after:
        # we try to preserve the changes for local inspection, but if it fails, meh
        run(*git, 'stash', 'pop', check=False)
        log('already up to date.')
        return False
    else:
        log(f'updated {head_before[:10]}..{head_after[:10]}.')
        return True


def srpm_path(directory):
    """
    Returns a path to a single SRPM found in the given directory.
    Returns None if not there.
    Raises RuntimeError when multiple SRPMs are found.
    """
    candidates = list(directory.glob('*.src.rpm'))
    if not candidates:
        return None
    if count := len(candidates) > 1:
        raise RuntimeError(f'Found {count} SRPMs in {directory}.')
    return candidates[0]


def patch_spec(specpath, config):
    run('git', '-C', specpath.parent, 'reset', '--hard')
    spec_text = specpath.read_text()

    lines = []
    for without in sorted(config.get('withouts', ())):
        if without in config.get('withs', ()):
            raise ValueError(f'Cannot have the same with and without: {without}')
        lines.append(f'%global _without_{without} 1')
    for with_ in sorted(config.get('withs', ())):
        lines.append(f'%global _with_{with_} 1')
    for macro, value in config.get('replacements', {}).items():
        spec_text = re.sub(fr'^(\s*)%(define|global)(\s+){macro}(\s+)\S.*$',
                           fr'\1%\2\g<3>{macro}\g<4>{value}',
                           spec_text, flags=re.MULTILINE)
    lines.append(spec_text)
    specpath.write_text('\n'.join(lines))


def submit_scratchbuild(repopath, target=''):
    # I would like to avoid cd'ing and use f'--path={repopath}'
    # But https://pagure.io/rpkg/issue/580
    cwd = os.getcwd()
    command = ('fedpkg', 'build', '--scratch', '--srpm',
               f'--arches={KOJI_ARCH}', '--nowait')
    if target:
        command += (f'--target={target}',)
    try:
        os.chdir(repopath)
        log('   • Submitting Koji scratchbuild...', end=' ')
        fedpkg_output = run(*command).stdout
    finally:
        os.chdir(cwd)
        # we must cleanup the generated SRPM no matter what
        # not to confuse it with our Koji-downloaded one later
        if srpm := srpm_path(repopath):
            srpm.unlink()
    for line in fedpkg_output.splitlines():
        if line.startswith('Created task: '):
            koji_task_id = line.split(' ')[-1]
            log(f'task {koji_task_id}.')
            koji_id_path = repopath / KOJI_ID_FILENAME
            koji_id_path.write_text(koji_task_id)
            return koji_task_id
    else:
        raise RuntimeError('Carnot parse fedpkg build output')


def handle_exisitng_srpm(repopath, *, was_updated):
    srpm = srpm_path(repopath)
    if srpm and not was_updated:
        log(f'   • Found {srpm.name}, will not rebuild; remove it to force me.')
        return True
    if srpm:
        srpm.unlink()
    return False


def handle_exisitng_koji_id(repopath, *, was_updated):
    koji_id_path = repopath / KOJI_ID_FILENAME
    if koji_id_path.exists():
        if was_updated:
            koji_id_path.unlink()
            return None
        else:
            koji_task_id = koji_id_path.read_text()
            # XXX check what is the status of this task, ignore failed/canceled
            log(f'   • Found exisiting Koji task {koji_task_id}, will not rebuild; '
                f'remove {KOJI_ID_FILENAME} to force me.')
            return koji_task_id


def scratchbuild_patched(component_name, config, *, branch='', target=''):
    """
    This will:
     1. clone/fetch the given component_name package from Fedora to FEDPKG_CACHEDIR
        in case the repo existed and HEAD was not updated:
          - return None early if a SRPM exists
          - return previously stored Koji task ID early if it is present
     2. change the specfile to apply the given bcond/macro config
     3. scratchbuild the package in Koji (in a given target if specified)
     4. cleanup the generated SRPM
     5. write the Koji ID to KOJI_ID_FILENAME in the repo directory
    """
    jid = job_identifier(pkg, config, branch=branch, target=target)
    repopath = FEDPKG_CACHEDIR / jid
    if repopath.exists():
        news = refresh_gitrepo(repopath)
    else:
        FEDPKG_CACHEDIR.mkdir(exist_ok=True)
        clone_into(component_name, repopath, branch=branch)
        news = True

    if handle_exisitng_srpm(repopath, was_updated=news):
        return None

    if koji_id := handle_exisitng_koji_id(repopath, was_updated=news):
        return koji_id

    patch_spec(repopath / f'{component_name}.spec', config)

    return submit_scratchbuild(repopath, target=target)


if __name__ == '__main__':
    # this is merely to invoke the function via CLI for easier manual testing
    for pkg, configs in PACKAGES_BCONDS.items():
        for config in configs:
            scratchbuild_patched(pkg, config)
