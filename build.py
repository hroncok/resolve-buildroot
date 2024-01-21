import pathlib
import sys

# this module reuses bconds functions heavily
# XXX move to a common module?
from bconds import clone_into, refresh_gitrepo, patch_spec, run

# the following bcond things actually do stay there
from bconds import reverse_id_lookup, build_reverse_id_lookup

from utils import CONFIG


PATCHDIR = pathlib.Path('patches_dir')
FEDPKG_CACHEDIR = pathlib.Path(CONFIG['cache_dir']['fedpkg'])

if __name__ == '__main__':
    try:
        if len(sys.argv) != 2:
            sys.exit('This requires one argument.')
        component_name = sys.argv[1]

        bootstrap = None
        if ':' in component_name:
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
            if bootstrap:
                raise NotImplementedError('Double bootstrap is not yet supported')
            with patch.open('r') as patchfile:
                run('patch', '-R', '-p1', stdin=patchfile, cwd=repopath)
            patch.unlink()

        if bootstrap:
            message = CONFIG['distgit']['bootstrap_commit_message']
            patch_spec(specpath, bootstrap)
            diff = run('git', '-C', repopath, 'diff').stdout
            patch.write_text(diff)
        else:
            message = CONFIG['distgit']['commit_message']

        # Bump and commit only if we haven't already, XXX ability to force this
        head_commit_msg = run('git', '-C', repopath, 'log', '--format=%B', '-n1', 'HEAD').stdout.rstrip()
        if False:  # and bootstrap or head_commit_msg != message:
            run('rpmdev-bumpspec', '-c', message, '--userstring', CONFIG['distgit']['author'], specpath)
            run('git', '-C', repopath, 'commit', '--allow-empty', f'{component_name}.spec', '-m', message, '--author', CONFIG['distgit']['author'])

            #raise NotImplementedError('no pushing yet')
            run('git', '-C', repopath, 'push')
        run('fedpkg', 'build', '--fail-fast', '--nowait', '--target', CONFIG['koji']['target'], cwd=repopath)  # '--background'

        # XXX prune this directory because we don't want no thousands clones?
        # maybe we are not gonna need this?
    except Exception:
        print(sys.argv[1])
        raise

    # XXX prune this directory because we don't want no thousands clones?
    # maybe we are not gonna need this?
