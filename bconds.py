import functools
import pathlib
import re
import subprocess
import sys

from utils import CONFIG, log

KOJI_ID_FILENAME = 'koji.id'

reverse_id_lookup = {}


def bcond_cache_identifier(component_name, bcond_config, *, branch='', target=''):
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
    withouts_id = '-'.join(sorted(bcond_config.get('withouts', [])))
    withs_id = '-'.join(sorted(bcond_config.get('withs', [])))
    replacements_id = '-'.join(sorted(bcond_config.get('replacements', {})))
    if branch == CONFIG['distgit']['branch']:
        branch = ''
    identifier = f'{component_name}:{withouts_id}:{withs_id}:{replacements_id}:{branch}:{target}'
    reverse_id_lookup[identifier] = bcond_config
    return identifier   


def run(*cmd, **kwargs):
    kwargs.setdefault('check', True)
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    return subprocess.run(cmd, **kwargs)


def clone_into(component_name, target, branch=''):
    branch = branch or CONFIG['distgit']['branch']
    log(f' • Cloning {component_name} into "{target}"...', end=' ')
    # I would like to use --depth=1 but that breaks rpmautospec
    # https://pagure.io/fedora-infra/rpmautospec/issue/227
    run('fedpkg', 'clone', component_name, target, f'--branch={branch}')
    log('done.')


def refresh_gitrepo(repopath, prune_exisitng=False):
    log(f' • Refreshing "{repopath}" git repo...', end=' ')
    git = 'git', '-C', repopath
    head_before = run(*git, 'rev-parse', 'HEAD').stdout.rstrip()
    run(*git, 'stash')
    run(*git, 'reset', '--hard')
    run(*git, 'pull')
    head_after = run(*git, 'rev-parse', 'HEAD').stdout.rstrip()
    if head_before == head_after:
        if not prune_exisitng:
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


def submit_scratchbuild(repopath, target=''):
    command = ('fedpkg', 'build', '--scratch', '--srpm',
               f'--arches={CONFIG["architectures"]["koji"]}', '--nowait', '--background')
    if target:
        command += (f'--target={target}',)
    try:
        log('   • Submitting Koji scratchbuild...', end=' ')
        fedpkg_output = run(*command, cwd=repopath).stdout
    finally:
        # we must cleanup the generated SRPM no matter what
        # not to confuse it with our Koji-downloaded one later
        if srpm := srpm_path(repopath):
            srpm.unlink()
    for line in fedpkg_output.splitlines():
        if line.startswith('Created task: '):
            koji_task_id = line.split(' ')[-1]
            log(f'task {koji_task_id}')
            koji_id_path = repopath / KOJI_ID_FILENAME
            koji_id_path.write_text(koji_task_id)
            return koji_task_id
    else:
        raise RuntimeError('Carnot parse fedpkg build output')


@functools.cache
def koji_status(koji_id):
    output = run('koji', 'taskinfo', koji_id).stdout.splitlines()
    for line in output:
        if line.startswith('State: '):
            return line.split(' ')[-1]
    raise RuntimeError('Carnot parse koji taskinfo output')


def handle_exisitng_srpm(repopath, *, was_updated):
    srpm = srpm_path(repopath)
    if srpm and not was_updated:
        log(f'   • Found {srpm.name}, will not rebuild; remove it to force me.')
        return srpm
    if srpm:
        srpm.unlink()
    return None


def handle_exisitng_koji_id(repopath, *, was_updated):
    koji_id_path = repopath / KOJI_ID_FILENAME
    if koji_id_path.exists():
        if was_updated:
            koji_id_path.unlink()
            return None
        else:
            koji_task_id = koji_id_path.read_text()
            status = koji_status(koji_task_id)
            if status in ('canceled', 'failed'):
                log(f'   • Koji task {koji_task_id} is {status}; '
                    f'removing {KOJI_ID_FILENAME}.')
                koji_id_path.unlink()
                return None
            else:
                log(f'   • Koji task {koji_task_id} is {status}; '
                    f'not rebuilding (rm {KOJI_ID_FILENAME} to force).')
                return koji_task_id


def scratchbuild_patched_if_needed(component_name, bcond_config, *, branch='', target=''):
    """
    This will:
     1. clone/fetch the given component_name package from Fedora to fedpkg_cache_dir
        in case the repo existed and HEAD was not updated, this ends early if:
          - a SRPM exists
          - a previously stored Koji task ID is present and not canceled or failed
          (both information is added to the provided bcond_config)
     2. change the specfile to apply the given bcond/macro config
     3. scratchbuild the package in Koji (in a given target if specified)
     4. cleanup the generated SRPM
     5. write the Koji ID to KOJI_ID_FILENAME in the repo directory and to bcond_config
     6. return True if something was submitted to Koji
    """
    repopath = pathlib.Path(CONFIG['cache_dir']['fedpkg']) / bcond_config['id']
    if repopath.exists():
        news = refresh_gitrepo(repopath)
    else:
        pathlib.Path(CONFIG['cache_dir']['fedpkg']).mkdir(exist_ok=True)
        clone_into(component_name, repopath, branch=branch)
        news = True

    if srpm := handle_exisitng_srpm(repopath, was_updated=news):
        bcond_config['srpm'] = srpm
        return False

    if koji_id := handle_exisitng_koji_id(repopath, was_updated=news):
        bcond_config['koji_task_id'] = koji_id
        return False

    specpath = repopath / f'{component_name}.spec'
    patch_spec(specpath, bcond_config)
    if 'bootstrap' in bcond_config.get('withs', ()):
        # bump the release not to create an older EVR with ~bootstrap
        # this is useful if we build the testing SRPMs in copr
        run('rpmdev-bumpspec', '--rightmost', specpath)

    bcond_config['koji_task_id'] = submit_scratchbuild(repopath, target=target)
    return True


def download_srpm_if_possible(component_name, bcond_config):
    """
    This will:
     1. inspect the bcond_config for srpm path and a koji build id
     2. if srpm exists or koji build doesn't, do nothing
     3. if koji build is closed, download the srpm and store the path in bcond_config
     4. return True if something was downloaded
    """
    if ('srpm' in bcond_config or
            'koji_task_id' not in bcond_config or
            koji_status(bcond_config['koji_task_id']) != 'closed'):
        return False
    log(' • Downloading SRPM from Koji...', end=' ')
    repopath = pathlib.Path(CONFIG['cache_dir']['fedpkg']) / bcond_config['id']
    command = ('koji', 'download-task', bcond_config['koji_task_id'], '--arch=src', '--noprogress')
    koji_output = run(*command, cwd=repopath).stdout.splitlines()
    if (l := len(koji_output)) != 1:
        raise RuntimeError(f'Cannot parse koji download-task output, expected 1 line, got {l}')
    srpm_filename = koji_output[0].split(' ')[-1]
    if not srpm_filename.endswith('.src.rpm'):
        raise RuntimeError('Cannot parse koji download-task output, expected a *.src.rpm filename, got {srpm_filename}')
    srpm = repopath / srpm_filename
    if not srpm.exists():
        raise RuntimeError('Downloaded SRPM does not exist: {srpm}')
    bcond_config['srpm'] = srpm
    log(srpm_filename)
    return True


def rpm_requires(rpm):
    """
    Returns a collection with Requires of given on-disk RPM package.
    If the package is a source package, those are BuildRequires.
    rpmlib() requires are filtered out.

    The result is a sorted, deduplicated tuple,
    so it can be hashed as an argument to other cached functions.
    """
    raw_requires = run('rpm', '-qp', '--requires', rpm).stdout.splitlines()
    return tuple(sorted({r for r in raw_requires if not r.startswith('rpmlib(')}))


def extract_buildrequires_if_possible(component_name, bcond_config):
    """
    This will:
     1. inspect the bcond_config for srpm path
     2. if srpm does not exist, do nothing
     3. add buildrequires of the found srpm to the bcond_config
     4. return True if srpm was found
    """
    if 'srpm' not in bcond_config:
        if srpm := srpm_path(pathlib.Path(CONFIG['cache_dir']['fedpkg']) / bcond_config['id']):
            bcond_config['srpm'] = srpm
        else:
            return False
    bcond_config['buildrequires'] = rpm_requires(bcond_config['srpm'])
    log(f' • Extracted {len(bcond_config["buildrequires"])} BuildRequires from {bcond_config["srpm"].name}')
    return True


def each_bcond_name_config():
    for component_name, bcond_configs in CONFIG['bconds'].items():
        for bcond_config in bcond_configs:
            bcond_config['id'] = bcond_cache_identifier(component_name, bcond_config)
            yield component_name, bcond_config


def build_reverse_id_lookup():
    for _ in each_bcond_name_config():
        pass


if __name__ == '__main__':
    # build everything
    something_was_submitted = False
    for component_name, bcond_config in each_bcond_name_config():
        something_was_submitted |= scratchbuild_patched_if_needed(component_name, bcond_config)

    # download everything until there's nothing downloaded
    # the idea is that while downloading, other tasks could finish
    something_was_downloaded = True  # bogus initial value to be able to start
    extracted_count = 0
    while something_was_downloaded:
        something_was_downloaded = False
        # while we were downloading, we could have finished Koji builds
        for pkg, bcond_configs in CONFIG['bconds'].items():
            for bcond_config in bcond_configs:
                if 'buildrequires' not in bcond_config:
                    something_was_downloaded |= download_srpm_if_possible(component_name, bcond_config)
                    if extract_buildrequires_if_possible(component_name, bcond_config):
                        extracted_count += 1
        koji_status.cache_clear()

    log(f'Extracted BuildRequires from {extracted_count} SRPMs.')
    if not_extracted_count := sum(len(bcond_configs) for bcond_configs in CONFIG['bconds'].values()) - extracted_count:
        sys.exit(f'{not_extracted_count} SRPMs remain to be built/downloaded/extracted, run this again in a while.')
