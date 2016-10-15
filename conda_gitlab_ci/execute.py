from __future__ import print_function, division
import contextlib
import os
import subprocess
from time import sleep

from conda_build.conda_interface import Resolve, get_index
from dask import delayed

from .compute_build_graph import construct_graph, expand_dirty, order_build
from .trigger_gitlab import submit_build, check_build_status
from .build_matrix import load_platforms, expand_build_matrix


def _build(configuration, dependencies, commit_sha=None, passthrough=False,
           sleep_interval=5, run_timeout=86400, **kwargs):
    if passthrough:
        return configuration
    # configuration is the dictionary defined in expand_build_matrix; includes the package to build
    build_id = submit_build(configuration, commit_sha, **kwargs)
    time = 0
    while True:
        status = check_build_status(build_id, commit_sha=commit_sha, **kwargs)
        if status in ('pending', 'running'):
            sleep(sleep_interval)
            if status == 'pending' or time < run_timeout:
                time += sleep_interval
                continue
            raise Exception("Build timed out", (configuration, commit_sha))
        if status == 'success':
            break
        if status == 'failed':
            raise Exception("Build failed", (configuration, commit_sha))

    return commit_sha


def _platform_package_key(name, platform_dict):
    return name + '_' + platform_dict['worker_label']


@contextlib.contextmanager
def checkout_git_rev(checkout_rev, path):
    git_current_rev = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                              cwd=path).rstrip()
    subprocess.check_call(['git', 'checkout', checkout_rev], cwd=path)
    yield
    subprocess.check_call(['git', 'checkout', git_current_rev], cwd=path)


def get_dask_outputs(path, packages=(), filter_dirty=True, git_rev='HEAD', stop_rev=None, steps=0,
                     visualize="", **kwargs):
    checkout_rev = stop_rev or git_rev
    results = {}
    conda_resolve = Resolve(get_index())

    with checkout_git_rev(checkout_rev, path):
        # loop over platforms here because each platform may have different dependencies
        # each platform will be submitted with a different label
        for platform in load_platforms(os.path.join(path, "build_platforms.d")):
            g = construct_graph(path, platform=platform['platform'], bits=platform['arch'],
                                git_rev=git_rev, stop_rev=stop_rev)
            # note that the graph is changed in place here.
            expand_dirty(g, conda_resolve=conda_resolve, steps=steps)
            # sort build order, and also filter so that we have solely dirty nodes in subgraph
            subgraph, order = order_build(g, filter_dirty=filter_dirty)

            for node in order:
                for configuration in expand_build_matrix(node, path,
                                                         label=platform['worker_label']):
                    commit_sha = stop_rev or git_rev
                    build_dependencies = [results[_platform_package_key(n, platform)]
                                          for n in subgraph[node].keys() if n in subgraph]
                    key_name = node + '_' + platform['worker_label']
                    results[key_name] = delayed(_build, pure=True)(configuration=configuration,
                                                                   dependencies=build_dependencies,
                                                                   commit_sha=commit_sha,
                                                                   dask_key_name=key_name,
                                                                   passthrough=visualize,
                                                                   **kwargs)

    output = []
    for platform in load_platforms(os.path.join(path, "build_platforms.d")):
        for node in order:
            key = node + '_' + platform['worker_label']
            if key in results:
                output.append(results[key])
    return output
