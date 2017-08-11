# -*- coding: utf-8 -*-
# Copyright 2014 Objectif Libre
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Stéphane Albert
#
import abc

from oslo_config import cfg
import six
from stevedore import driver

from cloudkitty import transformer
import cloudkitty.utils as ck_utils

collect_opts = [
    cfg.StrOpt('collector',
               default='ceilometer',
               help='Data collector.'),
    cfg.IntOpt('window',
               default=1800,
               help='Number of samples to collect per call.'),
    cfg.IntOpt('period',
               default=3600,
               help='Rating period in seconds.'),
    cfg.IntOpt('wait_periods',
               default=2,
               help='Wait for N periods before collecting new data.'),
    cfg.ListOpt('services',
                default=['compute',
                         'image',
                         'volume',
                         'network.bw.in',
                         'network.bw.out',
                         'network.floating',
                         'cloudstorage',
                         'instance.addon',
                         'tenant.addon',],
                help='Services to monitor.'), ]

CONF = cfg.CONF
CONF.register_opts(collect_opts, 'collect')

COLLECTORS_NAMESPACE = 'cloudkitty.collector.backends'


def get_collector(transformers=None):
    if not transformers:
        transformers = transformer.get_transformers()
    collector_args = {
        'period': CONF.collect.period,
        'transformers': transformers}
    collector = driver.DriverManager(
        COLLECTORS_NAMESPACE,
        CONF.collect.collector,
        invoke_on_load=True,
        invoke_kwds=collector_args).driver
    return collector


class TransformerDependencyError(Exception):
    """Raised when a collector can't find a mandatory transformer."""

    def __init__(self, collector, transformer):
        super(TransformerDependencyError, self).__init__(
            "Transformer '%s' not found, but required by %s" % (transformer,
                                                                collector))
        self.collector = collector
        self.transformer = transformer


class NoDataCollected(Exception):
    """Raised when the collection returned no data.

    """

    def __init__(self, collector, resource):
        super(NoDataCollected, self).__init__(
            "Collector '%s' returned no data for resource '%s'" % (
                collector, resource))
        self.collector = collector
        self.resource = resource


@six.add_metaclass(abc.ABCMeta)
class BaseCollector(object):
    collector_name = None
    dependencies = []

    def __init__(self, transformers, **kwargs):
        try:
            self.transformers = transformers
            self.period = kwargs['period']
        except IndexError as e:
            raise ValueError("Missing argument (%s)" % e)

        self._check_transformers()

    def _check_transformers(self):
        """Check for transformer prerequisites

        """
        for dependency in self.dependencies:
            if dependency not in self.transformers:
                raise TransformerDependencyError(self.collector_name,
                                                 dependency)

    @staticmethod
    def last_month():
        month_start = ck_utils.get_month_start()
        month_end = ck_utils.get_month_end()
        start_ts = ck_utils.dt2ts(month_start)
        end_ts = ck_utils.dt2ts(month_end)
        return start_ts, end_ts

    @staticmethod
    def current_month():
        month_start = ck_utils.get_month_start()
        return ck_utils.dt2ts(month_start)

    @classmethod
    def _res_to_func(cls, resource_name):
        trans_resource = 'get_'
        trans_resource += resource_name.replace('.', '_')
        return trans_resource

    def retrieve(self,
                 resource,
                 start,
                 end=None,
                 project_id=None,
                 q_filter=None):
        trans_resource = self._res_to_func(resource)
        if not hasattr(self, trans_resource):
            raise NotImplementedError(
                "No method found in collector '%s' for resource '%s'."
                % (self.collector_name, resource))
        func = getattr(self, trans_resource)
        return func(start, end, project_id, q_filter)
