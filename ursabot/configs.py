# Copyright 2019 RStudio, Inc.
# All rights reserved.
#
# Use of this source code is governed by a BSD 2-Clause
# license that can be found in the LICENSE_BSD file.
#
# This file contains function or sections of code that are marked as being
# derivative works of Buildbot. The above license only applies to code that
# is not marked as such.

import sys
import operator
import traceback
from pathlib import Path
from functools import reduce
from contextlib import contextmanager

from twisted.python.compat import execfile
from zope.interface import implementer
from buildbot import interfaces
from buildbot.config import ConfigErrors, error, _errors  # noqa
from buildbot.config import MasterConfig as BuildbotMasterConfig
from buildbot.util.logger import Logger
from buildbot.util import ComparableMixin

from .docker import ImageCollection
from .utils import Collection


log = Logger()


@contextmanager
def collect_global_errors(and_raise=False):
    global _errors
    print(_errors)
    _errors = errors = ConfigErrors()

    try:
        yield errors
    except ConfigErrors as e:
        errors.merge(e)
    finally:
        _errors = None
        if errors and and_raise:
            raise errors


def get_global(name, default=None):
    return globals().get(name, default)


class Config(ComparableMixin):

    @classmethod
    def load_from(cls, path, variable, globals=None):
        loader = FileLoader(path, variable=variable)
        config = loader.load()
        assert isinstance(config, cls)
        return config


class ProjectConfig(Config):

    compare_attrs = [
        'name',
        'images',
        'pollers',
        'workers',
        'builders',
        'schedulers',
        'reporters'
    ]

    def __init__(self, name, workers, builders, schedulers, pollers=None,
                 reporters=None, images=None):
        self.name = name
        self.workers = Collection(workers)
        self.builders = Collection(builders)
        self.schedulers = Collection(schedulers)
        self.images = ImageCollection(images or [])
        self.pollers = Collection(pollers or [])
        self.reporters = Collection(reporters or [])

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self.name}>'


class MasterConfig(Config):

    compare_attrs = [
        'auth',
        'authz',
        'change_hook'
        'database_url',
        'projects',
        'secret_providers',
        'title',
        'url',
        'webui_port',
        'worker_port',
    ]

    def __init__(self, title='Ursabot', url='http://localhost:8080',
                 webui_port=8100, worker_port=9989, auth=None, authz=None,
                 database_url='sqlite:///ursabot.sqlite', projects=None,
                 change_hook=None, secret_providers=None):
        self.title = title
        self.url = url
        self.auth = auth
        self.authz = authz
        self.worker_port = worker_port
        self.webui_port = webui_port
        self.database_url = database_url
        self.projects = projects
        self.change_hook = change_hook
        self.secret_providers = secret_providers

    def _from_projects(self, key):
        return reduce(operator.add, (getattr(p, key) for p in self.projects))

    @property
    def images(self):
        return self._from_projects('images')

    @property
    def workers(self):
        return self._from_projects('workers')

    @property
    def builders(self):
        return self._from_projects('builders')

    @property
    def pollers(self):
        return self._from_projects('pollers')

    @property
    def schedulers(self):
        return self._from_projects('schedulers')

    @property
    def reporters(self):
        return self._from_projects('reporters')

    def as_buildbot(self, filename):
        """Returns with the buildbot compatible buildmaster configuration"""

        if self.change_hook is None:
            hook_dialect_config = {}
        else:
            hook_dialect_config = self.change_hook._as_hook_dialect_config()

        buildbot_config_dict = {
            'buildbotNetUsageData': None,
            'title': self.title,
            'titleURL': self.url,
            'buildbotURL': self.url,
            'workers': self.workers,
            'builders': self.builders,
            'schedulers': self.schedulers,
            'services': self.reporters,
            'change_source': self.pollers,
            'secretsProviders': self.secret_providers or [],
            'protocols': {'pb': {'port': self.worker_port}},
            'db': {'db_url': self.database_url},
            'www': {
                'port': self.webui_port,
                'change_hook_dialects': hook_dialect_config,
                'plugins': {
                    'waterfall_view': {},
                    'console_view': {},
                    'grid_view': {}
                }
            }
        }

        # buildbot raises errors for None or empty dict values so only set of
        # they are passed
        if self.auth is not None:
            buildbot_config_dict['www']['auth'] = self.auth
        if self.authz is not None:
            buildbot_config_dict['www']['authz'] = self.authz

        return BuildbotMasterConfig.loadFromDict(buildbot_config_dict,
                                                 filename=filename)


@implementer(interfaces.IConfigLoader)
class FileLoader(ComparableMixin):

    compare_attrs = ['path', 'variable', 'inject_globals']

    def __init__(self, path, variable, inject_globals=None):
        self.path = path
        self.variable = variable
        self.inject_globals = inject_globals or {}

    def load(self):
        # License note:
        #     It is a reimplementation based on the original
        #     buildbot.config.FileLoader and buildbot.config.loadConfigDict
        #     implementation.
        config = Path(self.path).absolute()
        basedir = config.parent

        if not config.exists():
            raise ConfigErrors([
                f"configuration file '{config}' does not exist"
            ])

        try:
            with config.open('r'):
                pass
        except IOError as e:
            raise ConfigErrors([
                f'unable to open configuration file {config}: {e}'
            ])

        log.info(f'Loading configuration from {config}')

        # execute the config file
        local_dict = {
            # inject global variables, useful for including configurations
            **self.inject_globals,
            # TODO(kszucs): is it required?
            'basedir': basedir.expanduser(),
            '__file__': config
        }

        old_sys_path = sys.path[:]
        sys.path.append(str(basedir))
        try:
            try:
                execfile(config, local_dict)
            except ConfigErrors:
                raise
            except SyntaxError:
                exc = traceback.format_exc()
                error(f'encountered a SyntaxError while parsing config file:\n'
                      f'{exc}', always_raise=True)
            except Exception:
                exc = traceback.format_exc()
                error(f'error while parsing config file: {exc} (traceback in '
                      f'logfile)', always_raise=True)
        finally:
            sys.path[:] = old_sys_path

        if self.variable not in local_dict:
            error(f"Configuration file {config} does not define variable"
                  f"'{self.variable}'", always_raise=True)

        return local_dict[self.variable]

    def loadConfig(self):
        with collect_global_errors(and_raise=True):
            return self.load()


class BuildmasterConfigLoader(FileLoader):
    """Loads the buildbot compatible MasterConfig (BuildmasterConfig)"""

    def __init__(self, path, variable='master', inject_globals=None):
        super().__init__(path=path, variable=variable,
                         inject_globals=inject_globals)

    def loadConfig(self):
        with collect_global_errors(and_raise=True):
            return self.load().as_buildbot(self.path)
