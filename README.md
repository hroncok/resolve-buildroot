# whatdoibuild

This is proof of concept work that should make Fedora Python 3.N+1 rebuilds in Copr and Koji easier.
It is designed to support similar use cases as well but does not (yet) aim to be a general-purpose tool.


## Assumptions

 - We need to rebuild a set of packages that require certain things
   (e.g. in our case `python(abi) = 3.N` or `libpython3.N.so`) on Fedora Rawhide.
 - We rebuild packages in a different repository (Copr, Koji side tag)
   and they will change their requirements (e.g. to `python(abi) = 3.N+1`).
 - Interpackage-dependencies after the rebuild are close to the same as in Fedora Rawhide.
 - We have a well-known set of bootstrapping bconds for some of our packages,
   to resolve build order loops.


## Preparations

For Python,
we assume the very initial bootstrap build of the Python interpreter is ready
and that we Python RPM dependency generators work before we can use this.

For now, this is prepared in a copr repository.

## Dependencies

The tool currently invokes the following commands in subprocess:

 - `git`
 - `fedpkg` (`clone -a`, `build --srpm --scratch`)
 - `koji` (`taskinfo`, `download-task`)
 - `rpm -qp`
 - `rpmdev-bumpspec`

The tests also use `mock -r fedora-rawhide-x86_64`.

So make sure to run it on a supported system (e.g. on Fedora)
and to be logged in with your packager credentials
(i.e. run `fkinit` before you start).

It also uses the `dnf` and `hawkey` Python modules.


## Installation

TODO


## Invocation

For now, run the scripts with Python from the cloned repository.


## Configuration

Currently, everything is hardcoded in Python constants.
Making this nicer is on the TODO list.

 - `jobs.py` contains information about what are we rebuilding
 - `sacks.py` contains repository metadata
 - `bconds.py` contains a list of known bconds that are considered useful


## Getting a cache of BuildRequires for bcond'ed builds

The file `bconds.py` contains a dictionary of known bconds that help us resolve bootstrap loops.
Run the script (it can take several minutes) to build a local cache of SRPMs that will be later used to query their BuildRequires.
The cache is currently about 300 MiBs.

The script will clone the repos and submit Koji scratchbuilds and/or download the SRPMs that are finished.
It might need running again after a while to fetch all the SRPMs that were not yet finished.

When a local SRPM exists and it was built from the same commit hash,
this does nothing. When a new commit exists, the SRPM is deleted and rebuilt.

When you change the bcond logic in packages, occasionally refresh this cache.


## Getting a list of packages to rebuild

Running the `jobs.py` script will put a lot of debug information to stderr
and a list of packages that (TODO need to be and) can already be rebuilt to stdout.
Bconded builds have colons (`:`) in them and you can find the meaning of that in `jobs.py`
(function `bcond_cache_identifier()`).
Regular builds only have component names.

### How is this list created

 1. All packages that require the "old requires" are collected from rawhide, grouped by their components.
 2. All packages that require the "new requires" are collected from the target repo, grouped by their components.
 3. A difference between the two is considered as "needs to be built".
 4. For each component (TODO in need of rebuilding), a list of packages that would be installed in the buildroot is resolved.
 5. If none of the to-be-installed packages needs a rebuild, this component is ready to be rebuilt. If some packages are not yet rebuilt, the builder would not be able to resolve the dependencies; bcond'ed builds are considered in that case if in the cache.

## Caveats

As of now, this does not rebuild anything.
It only tells you what can be rebuilt.
Currently running builds are not considered at all.
As of now, all packages that can be rebuilt are printed --
we want to be able to print just the once that are still needed.

Packages that were already rebuilt (even in a bconded state)
will never be reported again as in need of another rebuild.

BuildRequires are fetched from the rawhide-source repository.
That means the SRPMs were produced on an unknown architecture --
some packages can have different BuildRequires on different architectures
and this method might get incomplete information (and hence report incorrect data).
If this will be a real problem, more information will need to be supplied manually.
