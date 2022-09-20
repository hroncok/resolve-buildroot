import pathlib
import sys
from datetime import datetime

# this module reuses bconds functions heavily
# XXX move to a common module?
from bconds import FEDPKG_CACHEDIR, clone_into, refresh_gitrepo, patch_spec, run, PATCHDIR, DEFAULT_BRANCH

# the following bcond things actually do stay there
from bconds import PACKAGES_BCONDS, reverse_id_lookup, build_reverse_id_lookup


REBUILT_MESSAGE = 'Rebuilt for Python 3.11'
BOOTSTRAP_MESSAGE = 'Bootstrap for Python 3.11'
AUTHOR = 'Python Maint <python-maint@redhat.com>'
TARGET = 'f37'

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            sys.exit('This requires one argument.')
        component_name = sys.argv[1]

        bootstrap = None
        if ':' in component_name:
            raise NotImplementedError('not yet ready for riscv')
            build_reverse_id_lookup()
            bootstrap = reverse_id_lookup[component_name]
            component_name, *_ = component_name.partition(':')

        # XXX make a reusable function with just refresh_gitrepo/clone_into
        repopath = FEDPKG_CACHEDIR / component_name
        if repopath.exists():
            refresh_gitrepo(repopath, prune_exisitng=True)
        else:
            FEDPKG_CACHEDIR.mkdir(exist_ok=True)
            clone_into(component_name, repopath)

        specpath = repopath / f'{component_name}.spec'

        # Find any patches from previous bootstrap builds
        patch = PATCHDIR / f'{component_name}.patch'
        if patch.exists():
            raise NotImplementedError('not yet ready for riscv')
            if bootstrap:
                raise NotImplementedError('Double bootstrap is not yet supported')
            with patch.open('r') as patchfile:
                run('patch', '-R', '-p1', stdin=patchfile, cwd=repopath)
            patch.unlink()

        if bootstrap:
            raise NotImplementedError('not yet ready for riscv')
            message = BOOTSTRAP_MESSAGE
            patch_spec(specpath, bootstrap)
            diff = run('git', '-C', repopath, 'diff').stdout
            patch.write_text(diff)
        else:
            message = REBUILT_MESSAGE

        commit_hash = run('git', '-C', repopath, 'rev-pasre', 'HEAD').stdout.strip()
        latest_nvr = run('koji', '--config=~/.koji/riscv.conf', '--profile=riscv',
                         'list-tagged', '--quiet',
                         '--latest', 'f37', component_name).stdout.strip().split(' ')[0]
        if '.riscv' in latest_nvr:
            raise NotImplementedError(f'{component_name} needs to be built from a riscv branch')

        # XXX removed --background when the rate of builds was slow, make it configurable
        cp = run('koji', '--config=~/.koji/riscv.conf', '--profile=riscv',
                 'build', TARGET, '--fail-fast', '--nowait',
                 f'git+https://src.fedoraproject.org/rpms/{component_name}.git#{commit_hash}', cwd=repopath)
        print(cp.stdout, file=sys.stderr)
        # XXX prune this directory becasue we don't want no thousands clones?
        # maybe we are not gonna need this?
    except Exception:
        print(sys.argv[1])
        raise

