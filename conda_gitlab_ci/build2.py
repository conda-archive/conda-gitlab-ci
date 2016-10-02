#!/usr/bin/env python
from __future__ import print_function, division

import argparse
import psutil
import os
import subprocess
import time
import networkx as nx
import sys

from conda_build import api
from conda_build.metadata import MetaData, find_recipe


CONDA_BUILD_CACHE = os.environ.get("CONDA_BUILD_CACHE")


def last_changed_git_branch(git_root):
    args = ['git', 'for-each-ref',
            '--sort=-committerdate', 'refs/heads/', ]
    proc = subprocess.Popen(args,
                            cwd=git_root,
                            stdout=subprocess.PIPE)
    if proc.wait():
        raise ValueError('Bad return code '
                         'from git branch sort', proc.poll())
    head_1 = proc.stdout.read().decode().splitlines()[0]
    branch = head_1.split()[-1]
    print('Last changed branch: ', branch)
    return branch


def git_changed_files(git_rev, stop_rev=None, git_root=''):
    """
    Get the list of files changed in a git revision and return a list of
    package directories that have been modified.

    git_rev: if stop_rev is not provided, this represents the changes
             introduced by the given git rev.  It is equivalent to
             git_rev=SOME_REV~1 and stop_rev=SOME_REV

    stop_rev: when provided, this is the end of a range of revisions to
             consider.  git_rev becomes the start revision.
    """
    if stop_rev:
        git_rev = "{0}..{1}".format(git_rev, stop_rev)
    proc = subprocess.Popen(['git', 'diff-tree', '--no-commit-id',
                             '--name-only', '-r', git_rev
                             ],
                            cwd=git_root,
                            stdout=subprocess.PIPE)
    if proc.wait():
        raise ValueError('Bad git return code: {}'.format(proc.poll()))
    files = proc.stdout.read().decode().splitlines()
    return files


def read_recipe(path):
    return MetaData(path)


def describe_meta(meta):
    """Return a dictionary that describes build info of meta.yaml"""

    # Things we care about and need fast access to:
    #   1. Package name and version
    #   2. Build requirements
    #   3. Build number
    #   4. Recipe directory
    d = {}

    d['build'] = meta.get_value('build/number', 0)
    d['depends'] = format_deps(meta.get_value('requirements/build'))
    d['version'] = meta.get_value('package/version')
    return d


def format_deps(deps):
    d = {}
    for x in deps:
        x = x.strip().split()
        if len(x) == 2:
            d[x[0]] = x[1]
        else:
            d[x[0]] = ''
    return d


def get_build_deps(recipe):
    return format_deps(recipe.get_value('requirements/build'))


def construct_graph(directory, filter_by_git_change=True,
                    git_rev=None, stop_rev=None):
    '''
    Construct a directed graph of dependencies from a directory of recipes

    Annotate dependencies that don't have recipes in that directory
    '''
    print('construct_graph with args: ', directory, filter_by_git_change)
    g = nx.DiGraph()
    directory = os.path.abspath(directory)
    assert os.path.isdir(directory)

    # get all immediate subdirectories
    other_top_dirs = [d for d in os.listdir(directory)
                      if os.path.isdir(os.path.join(directory, d)) and
                      not os.path.exists(os.path.join(directory, d, 'meta.yaml')) and
                      not d.startswith('.')]
    recipe_dirs = []
    for recipe_dir in other_top_dirs:
        try:
            find_recipe(os.path.join(directory, recipe_dir))
            recipe_dirs.append(recipe_dir)
        except IOError:
            pass

    if filter_by_git_change:
        if not git_rev:
            git_rev = 'HEAD'
        changed_dirs = git_changed_files(git_rev, stop_rev=stop_rev,
                                            git_root=directory)
        print('changed git directories {}'.format(changed_dirs))
    for rd in recipe_dirs:
        recipe_dir = os.path.join(directory, rd)
        try:
            pkg = read_recipe(recipe_dir)
            name = pkg.name()
        except:
            continue

        # add package (in case it has no build deps)
        if filter_by_git_change:
            _dirty = False
            if rd in changed_dirs:
                _dirty = True
        else:
            _dirty = True
        g.add_node(name, meta=describe_meta(pkg), recipe=recipe_dir,
                   dirty=_dirty)
        # TODO: build deps may be platform specific (selectors), so we need a way to specify what
        #    platform we're targeting
        for k, d in get_build_deps(pkg).items():
            g.add_edge(name, k)
    return g


def dirty(graph, implicit=True):
    """
    Return a set of all dirty nodes in the graph.

    These include implicit and explicit dirty nodes.
    """
    # Reverse the edges to get true dependency
    dirty_nodes = {n for n, v in graph.node.items() if v.get('dirty', False)}
    if not implicit:
        return dirty_nodes

    # Get implicitly dirty nodes (all of the packages that depend on a dirty package)
    dirty_nodes.update(*map(set, (graph.predecessors(n) for n in dirty_nodes)))
    return dirty_nodes


def build_order(graph, packages=None, level=0, filter_by_git_change=True):
    '''
    Assumes that packages are in graph.
    Builds a temporary graph of relevant nodes and returns it topological sort.

    Relevant nodes selected in a breadth first traversal sourced at each pkg
    in packages.

    Values expected for packages is one of None, sequence:
       None: build the whole graph
       empty sequence: build nodes marked dirty
       non-empty sequence: build nodes in sequence
    '''

    if packages is None and not filter_by_git_change:
        tmp_global = graph.subgraph(graph.nodes())
    else:
        if packages:
            packages = set(packages)
        else:
            packages = dirty(graph, implicit=False)
        tmp_global = graph.subgraph(packages)

        if level > 0:
            # for each level, add all deps
            _level = level

            currlevel = packages
            while _level > 0:
                newcurr = set()
                for p in currlevel:
                    newcurr.update(set(graph.successors(p)))
                    tmp_global.add_edges_from(graph.edges_iter(p))
                currlevel = newcurr
                _level -= 1

    # copy relevant node data to tmp_global
    for n in tmp_global.nodes_iter():
        tmp_global.node[n] = graph.node[n]

    return tmp_global, nx.topological_sort(tmp_global, reverse=True)


def make_deps(graph, package, dry=False, extra_args='',
              level=0, autofail=True, jobtimeout=3600,
              timeoutbuffer=600):
    g, order = build_order(graph, package, level=level)
    # Filter out any packages that don't have recipes
    order = [pkg for pkg in order if g.node[pkg].get('meta')]
    print("Build order:\n{}".format('\n'.join(order)))
    elapsed = 0.0
    failed = set()
    not_tested = set()
    build_times = {x: None for x in order}
    for pkg in order:
        print("Building ", pkg)
        try:
            # Autofail package if any dependency build failed
            if any(p in failed for p in order):
                print(failed)
                failed_deps = [p for p in g.node[pkg]['meta']['depends'].keys()
                               if p in failed]
                print("Building {} failed because one or more of its "
                      "dependencies failed to build: ".format(pkg), end=' ')
                print(', '.join(failed_deps))
                failed.add(pkg)
                continue
            build_time = make_pkg(g.node[pkg], dry=dry)

            build_times[pkg] = build_time
            if build_time is None:
                failed.add(pkg)
            elapsed += build_times[pkg].elapsed
            if elapsed > jobtimeout - timeoutbuffer:
                idx = order.index(pkg) + 1
                if idx >= len(order):
                    not_tested = set()
                else:
                    not_tested = set(order[idx:])
                print('TIMEOUT within protoci, NOT_TESTED', not_tested)
                break
            if build_times[pkg].returncode:
                failed.add(pkg)
        except KeyboardInterrupt:
            print('KeyboardInterrupt')
            break
        except subprocess.CalledProcessError:
            failed.add(pkg)
            continue

    return list(set(order) - failed - not_tested), list(failed), \
        list(not_tested), build_times


def make_pkg(package, dry=False):
    path = package['recipe']
    print("===========> Building ", path)
    now = time.time()
    if not dry:
        api.build(path)
    return time.time() - now


def expand_dirty_label(g, changed=None):
    changed = changed or set()
    for node, value in g.node.items():
        if value.get('dirty'):
            changed.add(node)
            for successor in g.predecessors(node):
                changed.add(successor)
                g.node[successor]['dirty'] = True
    return changed


def sequential_build_main(packages, g=None, args=None):
    '''
        sequential_build_main(parse_this=None)
        Params:
            parse_this = None or iterable of sys.argv like
                         list to sequential_build_cli

            g = a graph from construct_graph()
                or None to call construct_graph with
                filter_by_git_diff *False*
        Notes: This operates in several modes:
            if args.packages is a list of packages:
                build them in order from start to finish of list
                exit 0 if no exception
            elif args.json_file_key is an list/tuple:
                1st element: json file name
                2nd elements to end: keys in that json dict in json file
                    (keys are high level packages, values are
                     dependencies to build in order, followed by
                     the key package)
            else:
                using args.build or args.buildall
                to build a package or packages
                with
    '''
    try:
        build_times = {x: None for x in packages}
        success, fail = [], []
        for package in packages:
            recipe = g.node[package]
            if 'meta' not in recipe:
                continue
            build_time = None
            try:
                print('BUILD_PACKAGE:', package)
                build_time = make_pkg(recipe, dry=args.dry)
                success.append(package)
                build_time = time.time() - build_time
                build_times[package] = build_time
            except Exception as e:
                print('Failed on make_pkg for', package, 'with:', repr(e))
                fail.append(package)
        print("BUILD SUMMARY:")
        print("SUCCESS: [{}]".format(', '.join(success)))
        print("FAIL: [{}]".format(', '.join(fail)))

        return len(fail)
    except:
        raise


def build_cli(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
    parser.add_argument("--build", action='append', default=[])
    parser.add_argument("--dry", action='store_true', default=False,
                        help="Dry run")
    parser.add_argument("--args", action='store', dest='cbargs', default='')
    parser.add_argument("-l", type=int, action='store', dest='level', default=0)
    parser.add_argument("--noautofail", action='store_false', dest='autofail')
    parser.add_argument('--packages', '-p',
                        default=[],
                        nargs="+",
                        help="Rather than determine tree, build the --packages in order")
    parser.add_argument('--depth',
                        required=False,
                        type=int,
                        help="Used only in git diff (depth of changed packages)",
                        default=0),
    parser.add_argument('--git_rev',
                        default='HEAD',
                        help=('start revision to examine.  If stop not '
                              'provided, changes are THIS_VAL~1..THIS_VAL'))
    parser.add_argument('--stop_rev',
                        default=None,
                        help=('stop revision to examine.  When provided,'
                              'changes are git_rev..stop_rev'))

    if not parse_this:
        args = parser.parse_args()
    else:
        args = parser.parse_args(parse_this)
    if not args.build:
        args.build = None

    git_current_rev = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                              cwd=args.path).rstrip()

    if args.stop_rev:
        checkout_rev = args.stop_rev
    else:
        checkout_rev = args.git_rev
    subprocess.check_call(['git', 'checkout', checkout_rev], cwd=args.path)

    try:
        g = construct_graph(args.path, filter_by_git_change=True,
                            git_rev=args.git_rev, stop_rev=args.stop_rev)
        changed = set()
        for repeat in range(args.depth):
            changed = expand_dirty_label(g, changed)
        g, order = build_order(g)
        sequential_build_main(packages=order, g=g, args=args)
    except:
        raise
    finally:
        subprocess.check_call(['git', 'checkout', git_current_rev], cwd=args.path)


if __name__ == "__main__":
    build_cli()
