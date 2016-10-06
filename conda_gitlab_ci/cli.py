import argparse
import os
import subprocess
import sys
from functools import partial

from dask import visualize, delayed
import networkx as nx

from .compute_build_graph import construct_graph, expand_dirty, order_build
from .trigger_gitlab import build, expand_build_matrix, load_platforms


@delayed(pure=True)
def _build_noop(deps, graph, *args, **kw):
    for dep in deps:
        _build_noop(graph[deps])
    return deps


def build_cli(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
    parser.add_argument("--build", action='append', default=[])
    parser.add_argument("--dry", action='store_true', default=False,
                        help="Dry run")
    parser.add_argument("--args", action='store', dest='cbargs', default='')
    parser.add_argument("-l", type=int, action='store', dest='level', default=0)
    parser.add_argument("--noautofail", action='store_false', dest='autofail')
    parser.add_argument("--all", action='store_true', dest='_all')
    parser.add_argument('--packages', '-p',
                        default=[],
                        nargs="+",
                        help="Rather than determine tree from git, specify packages to build")
    parser.add_argument('--depth',
                        type=int,
                        help="Used only in git diff (depth of checkout)",
                        default=0),
    parser.add_argument('--steps',
                        type=int,
                        help=("Number of downstream steps to follow in the DAG when "
                              "computing what to build"),
                        default=0),
    parser.add_argument('--git_rev',
                        default='HEAD',
                        help=('start revision to examine.  If stop not '
                              'provided, changes are THIS_VAL~1..THIS_VAL'))
    parser.add_argument('--stop_rev',
                        default=None,
                        help=('stop revision to examine.  When provided,'
                              'changes are git_rev..stop_rev'))
    parser.add_argument('--visualize',
                        help=('Output a PDF visualization of the package build graph, and quit.  '
                              'Argument is output file name (pdf)'),
                        default="")

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

    outputs = []

    for platform in load_platforms(os.path.join(args.path, "platforms.d")):
        try:
            g = construct_graph(args.path, platform=platform['platform'], bits=platform['bits'],
                                git_rev=args.git_rev, stop_rev=args.stop_rev)
            # note that the graph is changed in place here.
            expand_dirty(g, steps=args.steps)
            # sort build order, and also filter so that we have solely dirty nodes in subgraph
            subgraph, order = order_build(g, filter_dirty=(not args._all))

        except:
            raise
        finally:
            subprocess.check_call(['git', 'checkout', git_current_rev], cwd=args.path)

        results = {}

        for node in order:
            for configuration in expand_build_matrix(node, args.path,
                                                     label=platform['worker_label']):
                commit_sha = args.stop_rev or args.git_rev
                dependencies = [results[n] for n in g[node].keys()]
                if args.visualize:
                    results[node] = _build_noop(dependencies)
                else:
                    results[node] = build(configuration=configuration, dependencies=dependencies,
                                         commit_sha=commit_sha, **args.__dict__)

    outputs = [results[node] for node in order]

    if args.visualize:
        # setattr(nx.drawing, 'graphviz_layout', nx.nx_pydot.graphviz_layout)
        # graphviz_graph = nx.draw_graphviz(graph, 'dot')
        # graphviz_graph.draw(args.visualize)
        visualize(*outputs, filename=args.visualize)  # create neat looking graph.
        sys.exit(0)

    # Actually run things
    from distributed import LocalCluster, Client, progress

    # many threads, because this is just the dispatch.  Takes very little compute.
    # Only waiting for build complete.
    cluster = LocalCluster(n_workers=1, threads_per_worker=50, nanny=False)
    client = Client(cluster)

    futures = client.persist(outputs)
    progress(futures)


if __name__ == "__main__":
    build_cli()
