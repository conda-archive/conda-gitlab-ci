from __future__ import print_function, division
import contextlib
import os
import subprocess
from time import sleep

from conda_build.conda_interface import Resolve, get_index
from dask import delayed

from .compute_build_graph import construct_graph, expand_run, order_build
from .trigger_gitlab import submit_job, check_job_status
from .build_matrix import load_platforms, expand_build_matrix


def _job(configuration, dependencies, commit_sha=None, passthrough=False,
           sleep_interval=5, run_timeout=86400, **kwargs):
    if passthrough:
        return configuration
    # configuration is the dictionary defined in expand_build_matrix; includes the package to build
    build_id = submit_job(configuration, commit_sha, **kwargs)
    time = 0
    while True:
        status = check_job_status(build_id, commit_sha=commit_sha, **kwargs)
        if status in ('pending', 'running'):
            sleep(sleep_interval)
            if status == 'pending' or time < run_timeout:
                time += sleep_interval
                continue
            raise Exception("Job timed out", (configuration, commit_sha))
        if status == 'success':
            break
        if status == 'failed':
            raise Exception("Build failed", (configuration, commit_sha))

    return commit_sha


def _platform_package_key(run, name, platform_dict):
    return "{run}_{node}_{label}".format(run=run, node=name,
                                         label=platform_dict['worker_label'])


@contextlib.contextmanager
def checkout_git_rev(checkout_rev, path):
    git_current_rev = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                              cwd=path).rstrip()
    subprocess.check_call(['git', 'checkout', checkout_rev], cwd=path)
    try:
        yield
    except:    # pragma: no cover
        raise  # pragma: no cover
    finally:
        subprocess.check_call(['git', 'checkout', git_current_rev], cwd=path)


def get_dask_outputs(path, packages=(), filter_dirty=True, git_rev='HEAD', stop_rev=None, steps=0,
                     visualize="", test=False, max_downstream=5, **kwargs):
    checkout_rev = stop_rev or git_rev
    results = {}
    conda_build_test = '--{}test'.format("" if test else "no-")

    runs = ['test']
    # not testing means build and test
    if not test:
        runs.insert(0, 'build')

    output = []
    indexes = {}
    with checkout_git_rev(checkout_rev, path):
        for run in runs:
            platform_folder = '{}_platforms.d'.format(run)
            # loop over platforms here because each platform may have different dependencies
            # each platform will be submitted with a different label
            for platform in load_platforms(os.path.join(path, platform_folder)):
                index_key = '-'.join([platform['platform'], str(platform['arch'])])
                if index_key not in indexes:
                    indexes[index_key] = Resolve(get_index(platform=index_key))
                g = construct_graph(path, platform=platform['platform'], bits=platform['arch'],
                                    folders=packages, git_rev=git_rev, stop_rev=stop_rev,
                                    deps_type=run)
                # note that the graph is changed in place here.
                expand_run(g, conda_resolve=indexes[index_key], run=run, steps=steps,
                           max_downstream=max_downstream)
                # sort build order, and also filter so that we have solely dirty nodes in subgraph
                subgraph, order = order_build(g, filter_dirty=filter_dirty)

                for node in order:
                    for configuration in expand_build_matrix(node, path,
                                                            label=platform['worker_label']):
                        configuration['variables']['TEST_MODE'] = conda_build_test
                        commit_sha = stop_rev or git_rev
                        dependencies = [results[_platform_package_key(run, n, platform)]
                                            for n in subgraph[node].keys() if n in subgraph]
                        key_name = _platform_package_key(run, node, platform)
                        # make the test run depend on the build run's completion
                        build_key_name = _platform_package_key("build", node, platform)
                        if build_key_name in results:
                            dependencies.append(results[build_key_name])

                        results[key_name] = delayed(_job, pure=True)(configuration=configuration,
                                                                     dependencies=dependencies,
                                                                     commit_sha=commit_sha,
                                                                     dask_key_name=key_name,
                                                                     passthrough=visualize,
                                                                     **kwargs)

                    output.append(results[key_name])
    return output
