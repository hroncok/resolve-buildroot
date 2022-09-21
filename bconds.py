import functools
import pathlib
import re
import subprocess
import sys

from utils import log

# XXX ARCH is also defined in sacks.py but technically can be different :/
# Here we prefer the most reliable/fast architecture
KOJI_ARCH = 'x86_64'
KOJI_ID_FILENAME = 'koji.id'

FEDPKG_CACHEDIR = pathlib.Path('_fedpkg_cache_dir')
DEFAULT_BRANCH = 'f37'

PATCHDIR = pathlib.Path('patches_dir')

# XXX we need an actual user-configuration for this
PACKAGES_BCONDS = {
    #'gdb': [{'replacements': {'_without_python': '1'}}],
    #'python-setuptools': [{'withs': ['bootstrap'], 'withouts': ['tests']}],
    #'pyparsing': [{'withs': ['bootstrap']}],
    #'python-packaging': [{'withs': ['bootstrap'], 'withouts': ['tests', 'docs']}],
    #'python-wheel': [{'withs': ['bootstrap']}],
    #'python-pip': [{'withouts': ['tests', 'doc']}],
    #'python-setuptools': [{'withouts': ['tests']}],
    # XXX: build.py cannot handle double bootstrap yet

    #'python-six': [{'withouts': ['tests']}],
    #'python-toml': [{'withouts': ['tests']}],
    #'python-tomli': [{'withs': ['bootstrap']}],
    #'python-tomli-w': [{'withouts': ['check']}],
    #'python-setuptools_scm': [{'withouts': ['tests']}],
    #'python-py': [{'withouts': ['docs', 'tests']}],
    #'python-chardet': [{'withouts': ['tests']}],
    #'python-pbr': [{'withs': ['bootstrap']}],
    #'python-mock': [{'withouts': ['tests']}],
    #'python-extras': [{'withs': ['bootstrap']}], # XXX the bootstrap build has fewer runtime deps
    #'python-testtools': [{'withs': ['bootstrap']}], # XXX this might newer be reported as ready due to ^
    #'python-attrs': [{'withouts': ['tests']}],
    #'python-pluggy': [{'withouts': ['tests']}],
    #'python-sortedcontainers': [{'withouts': ['docs', 'tests']}],
    #'python-hypothesis': [{'withouts': ['doc', 'tests']}],
    #'python-pysocks': [{'replacements': {'with_python3_tests': '0'}}],
    #'python-pygments': [{'withouts': ['docs', 'tests']}],
    #'python-filelock': [{'withouts': ['docs', 'tests']}],
    #'python-elementpath': [{'withouts': ['tests']}],
    #'python-iniconfig': [{'withouts': ['tests']}],
    'Cython': [{'withouts': ['tests']}],
    #'python-more-itertools': [{'withouts': ['tests']}],
    #'python-atomicwrites': [{'withouts': ['docs', 'tests']}],
    #'python-fixtures': [{'withs': ['bootstrap']}],
    #'python-wcwidth': [{'withouts': ['tests']}],
    #'pytest': [{'withouts': ['tiemout', 'tests', 'docs']}],
    #'python-virtualenv': [{'withouts': ['tests']}],
    #'babel': [{'withs': ['bootstrap']}],
    #'python-jinja2': [{'withouts': ['docs']}],
    #'python-sphinx_rtd_theme': [{'withs': ['bootstrap']}],
    #'python-urllib3': [{'withouts': ['tests']}],
    #'python-requests': [{'withouts': ['tests']}],
    #'python-sphinxcontrib-applehelp': [{'withouts': ['check']}],
    #'python-sphinxcontrib-devhelp': [{'withouts': ['check']}],
    #'python-sphinxcontrib-htmlhelp': [{'withouts': ['check']}],
    #'python-sphinxcontrib-jsmath': [{'withouts': ['check']}],
    #'python-sphinxcontrib-qthelp': [{'withouts': ['check']}],
    #'python-sphinxcontrib-serializinghtml': [{'withouts': ['check']}],
    #'python-sphinx': [{'withouts': ['tests', 'websupport']}],
    #'python-jedi': [{'withouts': ['tests']}],
    #'python-dateutil': [{'withouts': ['tests']}],
    #'python-jsonschema': [{'withouts': ['tests']}],
    #'python-sphinxcontrib-websupport': [{'withouts': ['optional_tests']}],
    #'python-soupsieve': [{'withouts': ['tests']}],
    #'python-towncrier': [{'withouts': ['tests']}],
    #'python-pytest-asyncio': [{'withouts': ['tests']}],
    #'python-pytest-cov': [{'withouts': ['tests']}],
    #'python-flit': [{'withouts': ['tests']}],
    #'python-async-timeout': [{'withouts': ['tests']}],
    #'python-trio': [{'withouts': ['tests']}],
    #'python-Automat': [{'withouts': ['tests']}],
    #'python-invoke': [{'withouts': ['tests']}],
    #'python-jupyter-client': [{'withouts': ['doc', 'tests']}],
    'python-matplotlib': [{'withouts': ['check']}],
    #'ipython': [{'withouts': ['check', 'doc']}],
    #'python-ipykernel': [{'withouts': ['intersphinx', 'tests']}],
    'pybind11': [{'withouts': ['tests']}],
    #'python-nbconvert': [{'withouts': ['check', 'doc']}],
    #'python-nbclient': [{'withouts': ['check']}],
    #'python-pyquery': [{'withouts': ['tests']}],
    #'python-cherrypy': [{'withouts': ['tests']}],
    #'freeipa-healthcheck': [{'withouts': ['tests']}],
    #'python-zbase32': [{'withs': ['bootstrap']}],
    'python-Traits': [{'withs': ['bootstrap']}],
    #'python-lit': [{'withouts': ['check']}],
    #'python-pcodedmp': [{'withs': ['bootstrap']}],
    #'ara': [{'replacements': {'with_docs': '0'}}],
    #'python-libcst': [{'withouts': ['tests']}],
    'python-databases': [{'withs': ['bootstrap']}],
    #'python-molecule': [{'withouts': ['doc']}],
    'scipy': [{'withouts': ['pythran']}],
    'python-pandas': [{'withs': ['bootstrap']}],
    'grpc': [{'withs': ['bootstrap']}],
    'python-zope-interface': [{'withouts': ['docs']}],
    #'python-tqdm': [{'withouts': ['tests']}],
    'python-cryptography': [{'withouts': ['tests']}],
    #'python-decopatch': [{'withouts': ['tests']}],
    #'python-geopandas': [{'withouts': ['tests']}],
    'python-astropy': [{'withouts': ['check']}],
    'python-pyerfa': [{'withouts': ['tests']}],
    #'python-fsspec': [{'withs': ['bootstrap']}],
    #'python-pyface': [{'withs': ['bootstrap']}],
    #'python-oletools': [{'withs': ['bootstrap']}],
    #'python-google-api-core': [{'withouts': ['tests']}],
    #'python-googleapis-common-protos': [{'withs': ['bootstrap']}],
    #'python-proto-plus': [{'withouts': ['tests']}],
    #'python-networkx': [{'withs': ['bootstrap']}],
    'python-lxml': [{'withouts': ['buildrequire_extras']}],
    #'python-constantly': [{'withouts': ['tests']}],
}
reverse_id_lookup = {}


def bcond_cache_identifier(component_name, config, *, branch='', target=''):
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
    identifier = f'{component_name}:{withouts_id}:{withs_id}:{replacements_id}:{branch}:{target}'
    reverse_id_lookup[identifier] = config
    return identifier   


def run(*cmd, **kwargs):
    kwargs.setdefault('check', True)
    kwargs.setdefault('capture_output', True)
    kwargs.setdefault('text', True)
    return subprocess.run(cmd, **kwargs)


def clone_into(component_name, target, branch=''):
    branch = branch or DEFAULT_BRANCH
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


def patch_spec(specpath, config):
    log(f'   • Patching {specpath.name}')

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
    command = ('fedpkg', 'build', '--scratch', '--srpm',
               f'--arches={KOJI_ARCH}', '--nowait', '--background')
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
        if False:
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
                    f'not rebulding (rm {KOJI_ID_FILENAME} to force).')
                return koji_task_id


def scratchbuild_patched_if_needed(component_name, config, *, branch='', target=''):
    """
    This will:
     1. clone/fetch the given component_name package from Fedora to FEDPKG_CACHEDIR
        in case the repo existed and HEAD was not updated, this ends early if:
          - a SRPM exists
          - a previously stored Koji task ID is present and not canceled or failed
          (both information is added to the provided config)
     2. change the specfile to apply the given bcond/macro config
     3. scratchbuild the package in Koji (in a given target if specified)
     4. cleanup the generated SRPM
     5. write the Koji ID to KOJI_ID_FILENAME in the repo directory and to config
     6. return True if something was submitted to Koji
    """
    repopath = FEDPKG_CACHEDIR / config['id']
    if repopath.exists():
        news = refresh_gitrepo(repopath)
    else:
        FEDPKG_CACHEDIR.mkdir(exist_ok=True)
        clone_into(component_name, repopath, branch=branch)
        news = True

    if srpm := handle_exisitng_srpm(repopath, was_updated=news):
        config['srpm'] = srpm
        return False

    if koji_id := handle_exisitng_koji_id(repopath, was_updated=news):
        config['koji_task_id'] = koji_id
        return False

    specpath = repopath / f'{component_name}.spec'
    patch_spec(specpath, config)
    if 'bootstrap' in config.get('withs', ()):
        # bump the release not to create an older EVR with ~bootstrap
        # this is useful if we build the testing SRPMs in copr
        run('rpmdev-bumpspec', '--rightmost', specpath)

    config['koji_task_id'] = submit_scratchbuild(repopath, target=target)
    return True


def download_srpm_if_possible(component_name, config):
    """
    This will:
     1. inspect the config for srpm path and a koji build id
     2. if srpm exists or koji build doesn't, do nothing
     3. if koji build is closed, download the srpm and store the path in config
     4. return True if something was downloaded
    """
    if ('srpm' in config or
            'koji_task_id' not in config or
            koji_status(config['koji_task_id']) != 'closed'):
        return False
    log(' • Downloading SRPM from Koji...', end=' ')
    repopath = FEDPKG_CACHEDIR / config['id']
    command = ('koji', 'download-task', config['koji_task_id'], '--arch=src', '--noprogress')
    koji_output = run(*command, cwd=repopath).stdout.splitlines()
    if (l := len(koji_output)) != 1:
        raise RuntimeError(f'Cannot parse koji download-task ouptut, expected 1 line, got {l}')
    srpm_filename = koji_output[0].split(' ')[-1]
    if not srpm_filename.endswith('.src.rpm'):
        raise RuntimeError('Cannot parse koji download-task ouptut, expected a *.src.rpm filename, got {srpm_filename}')
    srpm = repopath / srpm_filename
    if not srpm.exists():
        raise RuntimeError('Downloaded SRPM does not exist: {srpm}')
    config['srpm'] = srpm
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


def extract_buildrequires_if_possible(component_name, config):
    """
    This will:
     1. inspect the config for srpm path
     2. if srpm does not exist, do nothing
     3. add buildrequires of the found srpm to the config
     4. return True if srpm was found
    """
    if 'srpm' not in config:
        if srpm := srpm_path(FEDPKG_CACHEDIR / config['id']):
            config['srpm'] = srpm
        else:
            return False
    config['buildrequires'] = rpm_requires(config['srpm'])
    log(f' • Extracted {len(config["buildrequires"])} BuildRequires from {config["srpm"].name}')
    return True


def each_bcond_name_config():
    for component_name, configs in PACKAGES_BCONDS.items():
        for config in configs:
            config['id'] = bcond_cache_identifier(component_name, config)
            yield component_name, config


def build_reverse_id_lookup():
    for _ in each_bcond_name_config():
        pass


if __name__ == '__main__':
    # build everything
    something_was_submitted = False
    for component_name, config in each_bcond_name_config():
        something_was_submitted |= scratchbuild_patched_if_needed(component_name, config)

    # download everything until there's nothing downloaded
    # the idea is that while downloading, other tasks could finish
    something_was_downloaded = True  # bogus initial value to be able to start
    extracted_count = 0
    while something_was_downloaded:
        something_was_downloaded = False
        # while we were downloading, we could have finished Koji builds
        for pkg, configs in PACKAGES_BCONDS.items():
            for config in configs:
                if 'buildrequires' not in config:
                    something_was_downloaded |= download_srpm_if_possible(component_name, config)
                    if extract_buildrequires_if_possible(component_name, config):
                        extracted_count += 1
        koji_status.cache_clear()

    log(f'Extracted BuildRequires from {extracted_count} SRPMs.')
    if not_extracted_count := sum(len(configs) for configs in PACKAGES_BCONDS.values()) - extracted_count:
        sys.exit(f'{not_extracted_count} SRPMs remain to be built/downloaded/extracted, run this again in a while.')
