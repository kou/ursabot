# This file is mostly a derivative work of Buildbot.
#
# Buildbot is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright Buildbot Team Members

from buildbot.plugins import util
from buildbot.test.fake import docker
from buildbot.test.fake import fakemaster
from buildbot.worker import docker as dockerworker
from buildbot.test.unit.test_worker_docker import TestDockerLatentWorker

from ursabot.workers import DockerLatentWorker


class TestDockerLatentWorker(TestDockerLatentWorker):

    def setupWorker(self, *args, **kwargs):
        docker.Client.close = lambda self: None
        self.patch(dockerworker, 'docker', docker)
        worker = DockerLatentWorker(*args, **kwargs)
        master = fakemaster.make_master(self, wantData=True)
        fakemaster.master = master
        worker.setServiceParent(master)
        self.successResultOf(master.startService())
        self.addCleanup(master.stopService)
        return worker

    def test_constructor_all_docker_parameters(self):
        # Volumes have their own tests
        bs = self.setupWorker(
            'bot', 'pass', 'unix:///var/run/docker.sock', 'worker_img',
            ['/bin/sh'], dockerfile="FROM ubuntu", version='1.9', tls=True,
            hostconfig={'network_mode': 'fake', 'dns': ['1.1.1.1', '1.2.3.4']}
        )
        assert bs.workername == 'bot'
        assert bs.password == 'pass'
        assert bs.image == 'worker_img'
        assert bs.command == ['/bin/sh']
        assert bs.dockerfile == "FROM ubuntu"
        assert bs.volumes, util.Property('docker_image', default=[])
        assert bs.client_args == {
            'base_url': 'unix:///var/run/docker.sock',
            'version': '1.9',
            'tls': True
        }
        assert isinstance(bs.hostconfig, util.Transform)

    def test_constructor_noimage_nodockerfile(self):
        pass  # don't raise
