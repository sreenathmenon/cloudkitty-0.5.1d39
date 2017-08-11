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

from cloudkitty import collector as ck_collector
from cloudkitty import utils as ck_utils

storage_opts = [
    cfg.StrOpt('backend',
               default='sqlalchemy',
               help='Name of the storage backend driver.')
]

CONF = cfg.CONF
CONF.register_opts(storage_opts, group='storage')

STORAGES_NAMESPACE = 'cloudkitty.storage.backends'


def get_storage(collector=None):
    storage_args = {
        'period': CONF.collect.period,
        'collector': collector if collector else ck_collector.get_collector()}
    backend = driver.DriverManager(
        STORAGES_NAMESPACE,
        cfg.CONF.storage.backend,
        invoke_on_load=True,
        invoke_kwds=storage_args).driver
    return backend


class NoTimeFrame(Exception):
    """Raised when there is no time frame available."""

    def __init__(self):
        super(NoTimeFrame, self).__init__(
            "No time frame available")


@six.add_metaclass(abc.ABCMeta)
class BaseStorage(object):
    """Base Storage class:

        Handle incoming data from the global orchestrator, and store them.
    """
    def __init__(self, **kwargs):
        self._period = kwargs.get('period', CONF.collect.period)
        self._collector = kwargs.get('collector')

        # State vars
        self.usage_start = {}
        self.usage_start_dt = {}
        self.usage_end = {}
        self.usage_end_dt = {}
        self._has_data = {}

    @staticmethod
    def init():
        """Initialize storage backend.

        Can be used to create DB schema on first start.
        """
        pass

    def _filter_period(self, json_data):
        """Detect the best usage period to extract.

        Removes the usage from the json data and returns it.
        :param json_data: Data to filter.
        """
        candidate_ts = None
        candidate_idx = 0

        for idx, usage in enumerate(json_data):
            usage_ts = usage['period']['begin']
            if candidate_ts is None or usage_ts < candidate_ts:
                candidate_ts = usage_ts
                candidate_idx = idx

        if candidate_ts:
            return candidate_ts, json_data.pop(candidate_idx)['usage']

    def _pre_commit(self, tenant_id):
        """Called before every commit.

        :param tenant_id: tenant_id which information must be committed.
        """

    @abc.abstractmethod
    def _commit(self, tenant_id):
        """Push data to the storage backend.

        :param tenant_id: tenant_id which information must be committed.
        """

    def _post_commit(self, tenant_id):
        """Called after every commit.

        :param tenant_id: tenant_id which information must be committed.
        """
        if tenant_id in self._has_data:
            del self._has_data[tenant_id]
        self._clear_usage_info(tenant_id)

    @abc.abstractmethod
    def _dispatch(self, data, tenant_id):
        """Process rated data.

        :param data: The rated data frames.
        :param tenant_id: tenant_id which data must be dispatched to.
        """

    def _update_start(self, begin, tenant_id):
        """Update usage_start with a new timestamp.

        :param begin: New usage beginning timestamp.
        :param tenant_id: tenant_id to update.
        """
        self.usage_start[tenant_id] = begin
        self.usage_start_dt[tenant_id] = ck_utils.ts2dt(begin)

    def _update_end(self, end, tenant_id):
        """Update usage_end with a new timestamp.

        :param end: New usage end timestamp.
        :param tenant_id: tenant_id to update.
        """
        self.usage_end[tenant_id] = end
        self.usage_end_dt[tenant_id] = ck_utils.ts2dt(end)

    def _clear_usage_info(self, tenant_id):
        """Clear usage information timestamps.

        :param tenant_id: tenant_id which information needs to be removed.
        """
        self.usage_start.pop(tenant_id, None)
        self.usage_start_dt.pop(tenant_id, None)
        self.usage_end.pop(tenant_id, None)
        self.usage_end_dt.pop(tenant_id, None)

    def _check_commit(self, usage_start, tenant_id):
        """Check if the period for a given tenant must be committed.

        :param usage_start: Start of the period.
        :param tenant_id: tenant_id to check for.
        """
        usage_end = self.usage_end.get(tenant_id)
        if usage_end is not None and usage_start >= usage_end:
            self.commit(tenant_id)
        if self.usage_start.get(tenant_id) is None:
            self._update_start(usage_start, tenant_id)
            self._update_end(usage_start + self._period, tenant_id)

    @abc.abstractmethod
    def get_state(self, tenant_id=None):
        """Return the last written frame's timestamp.

        :param tenant_id: tenant_id to filter on.
        """

    # Modified by Muralidharan.s for applying a logic for getting 
    # Total value based on Instance
    @abc.abstractmethod
    def get_total(self, begin=None, end=None, tenant_id=None, service=None, instance_id=None):
        """Return the current total.

        :param begin: When to start filtering.
        :type begin: datetime.datetime
        :param end: When to stop filtering.
        :type end: datetime.datetime
        :param tenant_id: Filter on the tenant_id.
        :type res_type: str
        :param service: Filter on the resource type.
        :type service: str
        :param service: Filter on the instance_id.
        :type service: str
        """

    # Get invoice for admin tenant
    @abc.abstractmethod
    def get_invoice(self, tenant_id=None, tenant=None, invoice_id= None, payment_status=None):
        """Return the invoice.

        :param tenant_id: Filter on the tenant_id.
        :type res_type: str
        :param tenant: Filter on the tenant name as input
        :type res_type: str
        :param invoice_id: Filter on the invoice_id.
        :type res_type: str
        :param payment_status: Filter on the payment_status.
        :type res_type: str
        """

    # Get Invoice for non-admin tenant
    @abc.abstractmethod
    def get_invoice_for_tenant(self, tenant_name, invoice_id= None, payment_status=None):
        """Return the invoice.

	:param tenant_name: tenant_name from request
	:type res_type: str
        :param invoice_id: Filter on the invoice_id.
        :type res_type: str
        :param payment_status: Filter on the payment_status.
        :type res_type: str
        """

    # Invoice list for admin and non-admin
    @abc.abstractmethod
    def list_invoice(self, tenant_name, all_tenants=None):
        """Return the invoice list.

        :param tenant_name: Filter on the tenant_name.
        :type res_type: str
        :param all_tenants: param for getting all tenant details
        :type res_type: str
        """


    # Invoice show for non-admin
    @abc.abstractmethod
    def show_invoice_for_tenant(self, tenant_name, invoice_id):
        """Show the invoice for tenant.

        :param tenant_name: Filter on the tenant_name.
        :type res_type: str
        :param invoice_id: param for getting invoice id
        :type res_type: str
        """

    # Invoice show for admin
    @abc.abstractmethod
    def show_invoice(self, invoice_id):
        """Show the invoice for admin.

        :param invoice_id: param for getting invoice id
        :type res_type: str
        """

    # Add invoice method
    @abc.abstractmethod
    def add_invoice(self, invoice_id, invoice_date, invoice_period_from, invoice_period_to, tenant_id, invoice_data, tenant_name, total_cost, paid_cost, balance_cost, payment_status):
        """Add the invoice.

        :param invoice_id: invoice_id values
        :type res_type: str
        :param invoice_date: invoice_date values
        :type res_type: str
        :param invoice_period_from: invoice start date
        :type res_type: str
        :param invoice_period_to: invoice end date
        :type res_type: str
        :param tenant_id: tenant_id values
        :type res_type: str
        :param invoice_data: invoice date cost details and itemized details
        :type res_type: str
        :param tenant_name: tenant name details
        :type res_type: str
        :param total_cost: total cost detail 
        :type res_type: str
        :param paid_cost: paid_cost detail
        :type res_type: str
        :param balance_cost: balance cost
        :type res_type: str
        :param payment_status: payment status of invoice
        :type res_type: str
        """


    # Update invoice method
    @abc.abstractmethod
    def update_invoice(self, invoice_id=None, total_cost=None, paid_cost=None, balance_cost=None, payment_status=None):
        """Update the invoice.

        :param invoice_id: invoice_id values
        :type res_type: str
        :param total_cost: total cost detail 
        :type res_type: str
        :param paid_cost: paid_cost detail
        :type res_type: str
        :param balance_cost: balance cost
        :type res_type: str
        :param payment_status: payment status of invoice
        :type res_typ
        """

    # delete invoice method
    @abc.abstractmethod
    def delete_invoice(self, invoice_id=None):
        """Delete the invoice.

        :param invoice_id: invoice_id values
        :type res_type: str
        """

    @abc.abstractmethod
    def get_tenants(self, begin=None, end=None):
        """Return the list of rated tenants.

        :param begin: When to start filtering.
        :type begin: datetime.datetime
        :param end: When to stop filtering.
        :type end: datetime.datetime
        """

    @abc.abstractmethod
    def get_time_frame(self, begin, end, **filters):
        """Request a time frame from the storage backend.

        :param begin: When to start filtering.
        :type begin: datetime.datetime
        :param end: When to stop filtering.
        :type end: datetime.datetime
        :param res_type: (Optional) Filter on the resource type.
        :type res_type: str
        :param tenant_id: (Optional) Filter on the tenant_id.
        :type res_type: str
        """

    def append(self, raw_data, tenant_id):
        """Append rated data before committing them to the backend.

        :param raw_data: The rated data frames.
        :param tenant_id: Tenant the frame is belonging to.
        """
        while raw_data:
            usage_start, data = self._filter_period(raw_data)
            self._check_commit(usage_start, tenant_id)
            self._dispatch(data, tenant_id)

    def nodata(self, begin, end, tenant_id):
        """Append a no data frame to the storage backend.

        :param begin: Begin of the period with no data.
        :param end: End of the period with no data.
        :param tenant_id: Tenant to update with no data marker for the period.
        """
        self._check_commit(begin, tenant_id)

    def commit(self, tenant_id):
        """Commit the changes to the backend.

        :param tenant_id: Tenant the changes belong to.
        """
        self._pre_commit(tenant_id)
        self._commit(tenant_id)
        self._post_commit(tenant_id)
