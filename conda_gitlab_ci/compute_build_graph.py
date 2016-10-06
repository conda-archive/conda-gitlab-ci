#!/usr/bin/env python
from __future__ import print_function, division

import argparse
import os
import subprocess

import networkx as nx
from conda_build import api
from conda_build.metadata import find_recipe


CONDA_BUILD_CACHE = os.environ.get("CONDA_BUILD_CACHE")


def _git_changed_files(git_rev, stop_rev=None, git_root=''):
    if not git_root:
        git_root = os.getcwd()
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
    if '.git' in files:
        files.remove('.git')
    return files


def git_changed_recipes(git_rev, stop_rev=None, git_root=''):
    """
    Get the list of files changed in a git revision and return a list of
    package directories that have been modified.

    git_rev: if stop_rev is not provided, this represents the changes
             introduced by the given git rev.  It is equivalent to
             git_rev=SOME_REV@{1} and stop_rev=SOME_REV

    stop_rev: when provided, this is the end of a range of revisions to
             consider.  git_rev becomes the start revision.  Note that the
             start revision is *one before* the actual start of examining
             commits for changes.  In other words:

             git_rev=SOME_REV@{1} and stop_rev=SOME_REV   => only SOME_REV
             git_rev=SOME_REV@{2} and stop_rev=SOME_REV   => two commits, SOME_REV and the
                                                             one before it
    """
    changed_files = _git_changed_files(git_rev, stop_rev=stop_rev, git_root=git_root)
    recipe_dirs = []
    for f in changed_files:
        # only consider files that come from folders
        if '/' in f:
            try:
                recipe_dir = f.split('/')[0]
                find_recipe(os.path.join(git_root, recipe_dir))
                recipe_dirs.append(recipe_dir)
            except IOError:
                pass
    return recipe_dirs


def describe_meta(meta):
    """Return a dictionary that describes build info of meta.yaml"""

    # Things we care about and need fast access to:
    #   1. Package name and version
    #   2. Build requirements
    #   3. Build number
    #   4. Recipe directory
    d = {}

    d['build'] = meta.get_value('build/number', 0)
    d['depends'] = get_deps(meta)
    d['version'] = meta.get_value('package/version')
    return d


def get_deps(meta):
    build_reqs = meta.get_value('requirements/build')
    if not build_reqs:
        build_reqs = []
    run_reqs = meta.get_value('requirements/run')
    if not run_reqs:
        run_reqs = []
    test_reqs = meta.get_value('test/requires')
    if not test_reqs:
        test_reqs = []
    deps = build_reqs + run_reqs + test_reqs
    d = {}
    for x in deps:
        x = x.strip().split()
        if len(x) == 2:
            d[x[0]] = x[1]
        else:
            d[x[0]] = ''
    return d


def construct_graph(directory, platform, bits, folders=(), git_rev=None, stop_rev=None):
    '''
    Construct a directed graph of dependencies from a directory of recipes

    Annotate dependencies that don't have recipes in that directory
    '''
    print('construct_graph with args: ', directory)
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

    if not git_rev:
        git_rev = 'HEAD'
    if not folders:
        folders = _git_changed_files(git_rev, stop_rev=stop_rev,
                                        git_root=directory)
        print('changed git directories {}'.format(folders))
    for rd in recipe_dirs:
        recipe_dir = os.path.join(directory, rd)
        try:
            pkg, _, _ = api.render(recipe_dir, platform=platform, bits=bits)
            name = pkg.name()
        except:
            continue

        # add package (in case it has no build deps)
        _dirty = False
        if rd in folders:
            _dirty = True
        g.add_node(name, meta=describe_meta(pkg), recipe=recipe_dir,
                   dirty=_dirty)
        for k, d in get_deps(pkg).items():
            g.add_edge(name, k)
    return g


def expand_dirty(graph, steps=0, changed=None):
    # starting from our initial collection of dirty nodes, trace the tree down to packages
    #   that depend on the dirty nodes.  These packages may need to be rebuilt, or perhaps
    #   just tested.
    changed = changed or set()
    for step in range(steps):
        for node, value in graph.node.items():
            if value.get('dirty'):
                changed.add(node)
                for successor in graph.predecessors(node):
                    changed.add(successor)
                    graph.node[successor]['dirty'] = True
    return changed


def dirty(graph):
    """
    Return a set of all dirty nodes in the graph.

    These include implicit and explicit dirty nodes.
    """
    # Reverse the edges to get true dependency
    return {n for n, v in graph.node.items() if v.get('dirty', False)}


def order_build(graph, packages=None, level=0, filter_dirty=True):
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

    if packages is None and not filter_dirty:
        tmp_global = graph.subgraph(graph.nodes())
    else:
        packages = dirty(graph)
        tmp_global = graph.subgraph(packages)

    # copy relevant node data to tmp_global
    for n in tmp_global.nodes_iter():
        tmp_global.node[n] = graph.node[n]

    return tmp_global, nx.topological_sort(tmp_global, reverse=True)
