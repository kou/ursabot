from buildbot.plugins import worker


# TODO: support specifying parameters to improve isolation, like:
#   cpu_shares, isolation(cgroups), mem_limit and runtime (which will be
#   required for nvidia builds)
# https://docker-py.readthedocs.io/en/stable/api.html
# docker.api.container.ContainerApiMixin.create_host_config


class WorkerMixin:

    def __init__(self, *args, arch, is_benchmark=None, **kwargs):
        self.arch = arch
        self.is_benchmark = is_benchmark
        super().__init__(*args, **kwargs)


class DockerLatentWorker(WorkerMixin, worker.DockerLatentWorker):
    pass
