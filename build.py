import pathlib
import sys

# this module reuses bconds functions heavily
# XXX move to a common module?
from bconds import FEDPKG_CACHEDIR, clone_into, refresh_gitrepo, patch_spec, run, PATCHDIR

# the following bcond things actually do stay there
from bconds import PACKAGES_BCONDS, reverse_id_lookup, build_reverse_id_lookup


REBUILT_MESSAGE = 'Rebuilt for Python 3.11'
BOOTSTRAP_MESSAGE = 'Bootstrap for Python 3.11'
AUTHOR = 'Python Maint <python-maint@redhat.com>'
TARGET = 'rawhide'

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
            message = BOOTSTRAP_MESSAGE
            patch_spec(specpath, bootstrap)
            diff = run('git', '-C', repopath, 'diff').stdout
            patch.write_text(diff)
        else:
            message = REBUILT_MESSAGE

        # Bump and commit only if we haven't already, XXX ability to force this
        head_commit_msg = run('git', '-C', repopath, 'log', '--format=%B', '-n1', 'HEAD').stdout.rstrip()
        if bootstrap or not ('3.11' in head_commit_msg.lower() or 'python' in head_commit_msg.lower()):
            run('rpmdev-bumpspec', '-c', message, '--userstring', AUTHOR, specpath)
            run('git', '-C', repopath, 'commit', '--allow-empty', f'{component_name}.spec', '-m', message, '--author', AUTHOR)

	    #raise NotImplementedError('no pushing yet')
    	run('git', '-C', repopath, 'push')
    	cp = run('fedpkg', 'build', '--fail-fast', '--nowait', '--background', '--target', TARGET, cwd=repopath)
    	print(cp.stdout)

        # XXX prune this directory becasue we don't want no thousands clones?
        # maybe we are not gonna need this?
    except Exception:
        print(sys.argv[1])
        raise

    # XXX prune this directory becasue we don't want no thousands clones?
    # maybe we are not gonna need this?
