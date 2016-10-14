import argparse
import sys

from dask import visualize

from .execute import get_dask_outputs


def build_cli(parse_this=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("path", default='.')
    parser.add_argument("--build", action='append', default=[])
    parser.add_argument("--dry", action='store_true', default=False,
                        help="Dry run")
    parser.add_argument("--args", action='store', dest='cbargs', default='')
    parser.add_argument("-l", type=int, action='store', dest='level', default=0)
    parser.add_argument("--noautofail", action='store_false', dest='autofail')
    package_specs = parser.add_mutually_exclusive_group()
    package_specs.add_argument("--all", action='store_true', dest='_all')
    package_specs.add_argument('--packages', '-p',
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

    filter_dirty = any(args.packages) or not args._all

    outputs = get_dask_outputs(args.path, packages=args.packages, filter_dirty=filter_dirty,
                               git_rev=args.git_rev, stop_rev=args.stop_rev, steps=args.steps,
                               visualize=args.visualize)

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
