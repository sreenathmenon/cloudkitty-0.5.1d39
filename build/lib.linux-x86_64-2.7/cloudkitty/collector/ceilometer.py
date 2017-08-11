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
from ceilometerclient import client as cclient
from keystoneauth1 import loading as ks_loading
from oslo_config import cfg

from cloudkitty import collector
from cloudkitty import utils as ck_utils

CEILOMETER_COLLECTOR_OPTS = 'ceilometer_collector'
ks_loading.register_session_conf_options(
    cfg.CONF,
    CEILOMETER_COLLECTOR_OPTS)
ks_loading.register_auth_conf_options(
    cfg.CONF,
    CEILOMETER_COLLECTOR_OPTS)
CONF = cfg.CONF


class ResourceNotFound(Exception):
    """Raised when the resource doesn't exist."""

    def __init__(self, resource_type, resource_id):
        super(ResourceNotFound, self).__init__(
            "No such resource: %s, type: %s" % (resource_id, resource_type))
        self.resource_id = resource_id
        self.resource_type = resource_type


class CeilometerResourceCacher(object):
    def __init__(self):
        self._resource_cache = {}

    def add_resource_detail(self, resource_type, resource_id, resource_data):
        if resource_type not in self._resource_cache:
            self._resource_cache[resource_type] = {}
        self._resource_cache[resource_type][resource_id] = resource_data
        return self._resource_cache[resource_type][resource_id]

    def has_resource_detail(self, resource_type, resource_id):
        if resource_type in self._resource_cache:
            if resource_id in self._resource_cache[resource_type]:
                return True
        return False

    def get_resource_detail(self, resource_type, resource_id):
        try:
            resource = self._resource_cache[resource_type][resource_id]
            return resource
        except KeyError:
            raise ResourceNotFound(resource_type, resource_id)


class CeilometerCollector(collector.BaseCollector):
    collector_name = 'ceilometer'
    dependencies = ('CeilometerTransformer',
                    'CloudKittyFormatTransformer')

    def __init__(self, transformers, **kwargs):
        super(CeilometerCollector, self).__init__(transformers, **kwargs)

        self.t_ceilometer = self.transformers['CeilometerTransformer']
        self.t_cloudkitty = self.transformers['CloudKittyFormatTransformer']

        self._cacher = CeilometerResourceCacher()

        self.auth = ks_loading.load_auth_from_conf_options(
            CONF,
            CEILOMETER_COLLECTOR_OPTS)
        self.session = ks_loading.load_session_from_conf_options(
            CONF,
            CEILOMETER_COLLECTOR_OPTS,
            auth=self.auth)
        self._conn = cclient.get_client(
            '2',
            session=self.session)

    def gen_filter(self, op='eq', **kwargs):
        """Generate ceilometer filter from kwargs."""
        q_filter = []
        for kwarg in kwargs:
            q_filter.append({'field': kwarg, 'op': op, 'value': kwargs[kwarg]})
        return q_filter

    def prepend_filter(self, prepend, **kwargs):
        """Filter composer."""
        q_filter = {}
        for kwarg in kwargs:
            q_filter[prepend + kwarg] = kwargs[kwarg]
        return q_filter

    def user_metadata_filter(self, op='eq', **kwargs):
        """Create user_metadata filter from kwargs."""
        user_filter = {}
        for kwarg in kwargs:
            field = kwarg
            # Auto replace of . to _ to match ceilometer behaviour
            if '.' in field:
                field = field.replace('.', '_')
            user_filter[field] = kwargs[kwarg]
        user_filter = self.prepend_filter('user_metadata.', **user_filter)
        return self.metadata_filter(op, **user_filter)

    def metadata_filter(self, op='eq', **kwargs):
        """Create metadata filter from kwargs."""
        meta_filter = self.prepend_filter('metadata.', **kwargs)
        return self.gen_filter(op, **meta_filter)

    def resources_stats(self,
                        meter,
                        start,
                        end=None,
                        project_id=None,
                        q_filter=None):
        """Resources statistics during the timespan."""
        start_iso = ck_utils.ts2iso(start)
        req_filter = self.gen_filter(op='ge', timestamp=start_iso)
        if project_id:
            req_filter.extend(self.gen_filter(project=project_id))
        if end:
            end_iso = ck_utils.ts2iso(end)
            req_filter.extend(self.gen_filter(op='le', timestamp=end_iso))
        if isinstance(q_filter, list):
            req_filter.extend(q_filter)
        elif q_filter:
            req_filter.append(q_filter)
        resources_stats = self._conn.statistics.list(meter_name=meter,
                                                     period=0, q=req_filter,
                                                     groupby=['resource_id'])
        return resources_stats

    def active_resources(self,
                         meter,
                         start,
                         end=None,
                         project_id=None,
                         q_filter=None):
        """Resources that were active during the timespan."""
        resources_stats = self.resources_stats(meter,
                                               start,
                                               end,
                                               project_id,
                                               q_filter)
        return [resource.groupby['resource_id']
                for resource in resources_stats]

    def get_compute(self, start, end=None, project_id=None, q_filter=None):
        active_instance_ids = self.active_resources('instance', start, end,
                                                    project_id, q_filter)
        compute_data = []
        for instance_id in active_instance_ids:
            if not self._cacher.has_resource_detail('compute', instance_id):
                raw_resource = self._conn.resources.get(instance_id)
                instance = self.t_ceilometer.strip_resource_data('compute',
                                                                 raw_resource)
                self._cacher.add_resource_detail('compute',
                                                 instance_id,
                                                 instance)
            instance = self._cacher.get_resource_detail('compute',
                                                        instance_id)
            compute_data.append(self.t_cloudkitty.format_item(instance,
                                                              'instance',
                                                              1))
        if not compute_data:
            raise collector.NoDataCollected(self.collector_name, 'compute')
        return self.t_cloudkitty.format_service('compute', compute_data)

    def get_image(self, start, end=None, project_id=None, q_filter=None):
        active_image_stats = self.resources_stats('image.size',
                                                  start,
                                                  end,
                                                  project_id,
                                                  q_filter)
        image_data = []
        for image_stats in active_image_stats:
            image_id = image_stats.groupby['resource_id']
            if not self._cacher.has_resource_detail('image', image_id):
                raw_resource = self._conn.resources.get(image_id)
                image = self.t_ceilometer.strip_resource_data('image',
                                                              raw_resource)
                self._cacher.add_resource_detail('image',
                                                 image_id,
                                                 image)
            image = self._cacher.get_resource_detail('image',
                                                     image_id)

            # Convert bytes to GB for rate calculation
            image_size_gb = image_stats.max / 1073741824.0
            image_data.append(self.t_cloudkitty.format_item(image,
                                                            'GB',
                                                            image_size_gb))

        if not image_data:
            raise collector.NoDataCollected(self.collector_name, 'image')
        return self.t_cloudkitty.format_service('image', image_data)

    def get_volume(self, start, end=None, project_id=None, q_filter=None):
        active_volume_stats = self.resources_stats('volume.size',
                                                   start,
                                                   end,
                                                   project_id,
                                                   q_filter)
        volume_data = []
        for volume_stats in active_volume_stats:
            volume_id = volume_stats.groupby['resource_id']
            if not self._cacher.has_resource_detail('volume',
                                                    volume_id):
                raw_resource = self._conn.resources.get(volume_id)
                volume = self.t_ceilometer.strip_resource_data('volume',
                                                               raw_resource)
                self._cacher.add_resource_detail('volume',
                                                 volume_id,
                                                 volume)
            volume = self._cacher.get_resource_detail('volume',
                                                      volume_id)
            volume_data.append(self.t_cloudkitty.format_item(volume,
                                                             'GB',
                                                             volume_stats.max))
        if not volume_data:
            raise collector.NoDataCollected(self.collector_name, 'volume')
        return self.t_cloudkitty.format_service('volume', volume_data)

    def _get_network_bw(self,
                        direction,
                        start,
                        end=None,
                        project_id=None,
                        q_filter=None):
        if direction == 'in':
            resource_type = 'network.incoming.bytes'
        else:
            direction = 'out'
            resource_type = 'network.outgoing.bytes'
        active_tap_stats = self.resources_stats(resource_type,
                                                start,
                                                end,
                                                project_id,
                                                q_filter)
        bw_data = []
        for tap_stat in active_tap_stats:
            tap_id = tap_stat.groupby['resource_id']
            if not self._cacher.has_resource_detail('network.tap',
                                                    tap_id):
                raw_resource = self._conn.resources.get(tap_id)
                tap = self.t_ceilometer.strip_resource_data(
                    'network.tap',
                    raw_resource)
                self._cacher.add_resource_detail('network.tap',
                                                 tap_id,
                                                 tap)
            tap = self._cacher.get_resource_detail('network.tap',
                                                   tap_id)
            tap_bw_mb = tap_stat.max / 1048576.0
            bw_data.append(self.t_cloudkitty.format_item(tap,
                                                         'MB',
                                                         tap_bw_mb))
        ck_res_name = 'network.bw.{}'.format(direction)
        if not bw_data:
            raise collector.NoDataCollected(self.collector_name,
                                            ck_res_name)
        return self.t_cloudkitty.format_service(ck_res_name,
                                                bw_data)

    def get_network_bw_out(self,
                           start,
                           end=None,
                           project_id=None,
                           q_filter=None):
        return self._get_network_bw('out', start, end, project_id, q_filter)

    def get_network_bw_in(self,
                          start,
                          end=None,
                          project_id=None,
                          q_filter=None):
        return self._get_network_bw('in', start, end, project_id, q_filter)

    def get_network_floating(self,
                             start,
                             end=None,
                             project_id=None,
                             q_filter=None):
        active_floating_ids = self.active_resources('ip.floating',
                                                    start,
                                                    end,
                                                    project_id,
                                                    q_filter)
        floating_data = []
        for floating_id in active_floating_ids:
            if not self._cacher.has_resource_detail('network.floating',
                                                    floating_id):
                raw_resource = self._conn.resources.get(floating_id)
                floating = self.t_ceilometer.strip_resource_data(
                    'network.floating',
                    raw_resource)
                self._cacher.add_resource_detail('network.floating',
                                                 floating_id,
                                                 floating)
            floating = self._cacher.get_resource_detail('network.floating',
                                                        floating_id)
            floating_data.append(self.t_cloudkitty.format_item(floating,
                                                               'ip',
                                                               1))
        if not floating_data:
            raise collector.NoDataCollected(self.collector_name,
                                            'network.floating')
        return self.t_cloudkitty.format_service('network.floating',
                                                floating_data)

    def get_cloudstorage(self, start, end=None, project_id=None, q_filter=None):

        # To bill in each and every period
        active_cloud_volume_stats = self.resources_stats('storage.objects.size',
                                                   start,
                                                   end,
                                                   project_id,
                                                   q_filter)
        cloud_volume_data = []

        for cloud_volume_stats in active_cloud_volume_stats:

            cloud_volume_id = cloud_volume_stats.groupby['resource_id']
            if not self._cacher.has_resource_detail('cloudstorage',
                                                    cloud_volume_id):
                raw_resource = self._conn.resources.get(cloud_volume_id)

                cloud_volume = self.t_ceilometer.strip_resource_data('cloudstorage',
                                                               raw_resource)

                self._cacher.add_resource_detail('cloudstorage',
                                                 cloud_volume_id,
                                                 cloud_volume)

            cloud_volume = self._cacher.get_resource_detail('cloudstorage',
                                                      cloud_volume_id)

            # Convert bytes to GB
            cloud_volume_gb = cloud_volume_stats.max / 1073741824.0

            cloud_volume_data.append(self.t_cloudkitty.format_item(cloud_volume,
                                                             'GB',
                                                             cloud_volume_gb))

        if not cloud_volume_data:
            raise collector.NoDataCollected(self.collector_name, 'cloudstorage')
        return self.t_cloudkitty.format_service('cloudstorage', cloud_volume_data)


    # For enabling instance based add-on rates
    def get_instance_addon(self, start, end=None, project_id=None, q_filter=None):
        active_instance_ids = self.active_resources('instance', start, end,
                                                    project_id, q_filter)

        instance_addon_data = []
        for instance_id in active_instance_ids:
            if not self._cacher.has_resource_detail('instance.addon', instance_id):
                raw_resource = self._conn.resources.get(instance_id)

                instance_addon = self.t_ceilometer.strip_resource_data('instance.addon',
                                                                 raw_resource)
                self._cacher.add_resource_detail('instance.addon',
                                                 instance_id,
                                                 instance_addon)
            instance_addon = self._cacher.get_resource_detail('instance.addon',
                                                        instance_id)

            instance_addon_data.append(self.t_cloudkitty.format_item(instance_addon,
                                                              'instance.addon',
                                                              1))

        if not instance_addon_data:
            raise collector.NoDataCollected(self.collector_name, 'instance.addon')
        return self.t_cloudkitty.format_service('instance.addon', instance_addon_data)
