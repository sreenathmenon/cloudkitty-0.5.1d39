# -*- coding: utf-8 -*-
# Copyright 2015 Objectif Libre
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
import copy

import mock
import six
import sqlalchemy
import testscenarios

try: import simplejson as json
except ImportError: import json

from cloudkitty import storage
from cloudkitty import tests
from cloudkitty.tests import samples
from cloudkitty import utils as ck_utils

class StorageTest(tests.TestCase):
    storage_scenarios = [
        ('sqlalchemy', dict(storage_backend='sqlalchemy'))]

    @classmethod
    def generate_scenarios(cls):
        cls.scenarios = testscenarios.multiply_scenarios(
            cls.scenarios,
            cls.storage_scenarios)

    def setUp(self):
        super(StorageTest, self).setUp()
        self._tenant_id = samples.TENANT
        self._other_tenant_id = '8d3ae50089ea4142-9c6e1269db6a0b64'
        self.conf.set_override('backend', self.storage_backend, 'storage',
                               enforce_type=True)
        self.storage = storage.get_storage()
        self.storage.init()

    def insert_data(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append(working_data, self._tenant_id)
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append(working_data, self._other_tenant_id)
        self.storage.commit(self._tenant_id)
        self.storage.commit(self._other_tenant_id)

    def insert_different_data_two_tenants(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        del working_data[1]
        self.storage.append(working_data, self._tenant_id)
        working_data = copy.deepcopy(samples.RATED_DATA)
        del working_data[0]
        self.storage.append(working_data, self._other_tenant_id)
        self.storage.commit(self._tenant_id)
        self.storage.commit(self._other_tenant_id)

    # Filtering
    def test_filter_period(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        usage_start, data = self.storage._filter_period(working_data)
        self.assertEqual(samples.FIRST_PERIOD_BEGIN, usage_start)
        self.assertEqual(samples.RATED_DATA[0]['usage'], data)
        expected_remaining_data = [{
            "period": samples.SECOND_PERIOD,
            "usage": samples.RATED_DATA[1]['usage']}]
        self.assertEqual(expected_remaining_data, working_data)
        usage_start, data = self.storage._filter_period(working_data)
        self.assertEqual(samples.SECOND_PERIOD_BEGIN, usage_start)
        self.assertEqual(samples.RATED_DATA[1]['usage'], data)
        self.assertEqual([], working_data)

    # Data integrity
    def test_has_data_flag_behaviour(self):
        self.assertNotIn(self._tenant_id, self.storage._has_data)
        self.storage.nodata(
            samples.FIRST_PERIOD_BEGIN,
            samples.FIRST_PERIOD_END,
            self._tenant_id)
        self.assertNotIn(self._tenant_id, self.storage._has_data)
        working_data = copy.deepcopy(samples.RATED_DATA)
        working_data = [working_data[1]]
        self.storage.append(working_data, self._tenant_id)
        self.assertTrue(self.storage._has_data[self._tenant_id])
        self.storage.commit(self._tenant_id)
        self.assertNotIn(self._tenant_id, self.storage._has_data)

    def test_notify_no_data(self):
        self.storage.nodata(
            samples.FIRST_PERIOD_BEGIN,
            samples.FIRST_PERIOD_END,
            self._tenant_id)
        working_data = copy.deepcopy(samples.RATED_DATA)
        working_data = [working_data[1]]
        self.storage.append(working_data, self._tenant_id)
        kwargs = {
            'begin': samples.FIRST_PERIOD_BEGIN,
            'end': samples.FIRST_PERIOD_END,
            'tenant_id': self._tenant_id}
        self.assertRaises(
            storage.NoTimeFrame,
            self.storage.get_time_frame,
            **kwargs)
        kwargs['res_type'] = '_NO_DATA_'
        stored_data = self.storage.get_time_frame(**kwargs)
        self.assertEqual(1, len(stored_data))
        self.assertEqual(1, len(stored_data[0]['usage']))
        self.assertIn('_NO_DATA_', stored_data[0]['usage'])

    def test_send_nodata_between_data(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        for period in working_data:
            for service, data in sorted(six.iteritems(period['usage'])):
                sub_data = [{
                    'period': period['period'],
                    'usage': {
                        service: data}}]
                self.storage.append(sub_data, self._tenant_id)
                if service == 'compute':
                    self.storage.nodata(
                        period['period']['begin'],
                        period['period']['end'],
                        self._tenant_id)
            self.storage.commit(self._tenant_id)
        self.assertRaises(
            storage.NoTimeFrame,
            self.storage.get_time_frame,
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.SECOND_PERIOD_END,
            res_type='_NO_DATA_')

    def test_auto_commit_on_period_change(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append(working_data, self._tenant_id)
        stored_data = self.storage.get_time_frame(
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.SECOND_PERIOD_END)
        self.assertEqual(2, len(stored_data))
        expected_data = copy.deepcopy(samples.STORED_DATA)
        # We only stored the first timeframe, the second one is waiting for a
        # commit or an append with the next timeframe.
        del expected_data[2]
        # NOTE(sheeprine): Quick and dirty sort (ensure result consistency,
        # order is not significant to the test result)
        if 'image' in stored_data[0]['usage']:
            stored_data[0]['usage'], stored_data[1]['usage'] = (
                stored_data[1]['usage'], stored_data[0]['usage'])
        self.assertEqual(
            expected_data,
            stored_data)

    def test_create_session_on_append(self):
        self.assertNotIn(self._tenant_id, self.storage._session)
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append(working_data, self._tenant_id)
        self.assertIn(self._tenant_id, self.storage._session)
        self.assertIsInstance(
            self.storage._session[self._tenant_id],
            sqlalchemy.orm.session.Session)

    def test_delete_session_on_commit(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append(working_data, self._tenant_id)
        self.storage.commit(self._tenant_id)
        self.assertNotIn(self._tenant_id, self.storage._session)

    def test_update_period_on_append(self):
        self.assertNotIn(self._tenant_id, self.storage.usage_start)
        self.assertNotIn(self._tenant_id, self.storage.usage_start_dt)
        self.assertNotIn(self._tenant_id, self.storage.usage_end)
        self.assertNotIn(self._tenant_id, self.storage.usage_end_dt)
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append([working_data[0]], self._tenant_id)
        self.assertEqual(
            self.storage.usage_start[self._tenant_id],
            samples.FIRST_PERIOD_BEGIN)
        self.assertEqual(
            self.storage.usage_start_dt[self._tenant_id],
            ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN))
        self.assertEqual(
            self.storage.usage_end[self._tenant_id],
            samples.FIRST_PERIOD_END)
        self.assertEqual(
            self.storage.usage_end_dt[self._tenant_id],
            ck_utils.ts2dt(samples.FIRST_PERIOD_END))
        self.storage.append([working_data[1]], self._tenant_id)
        self.assertEqual(
            self.storage.usage_start[self._tenant_id],
            samples.SECOND_PERIOD_BEGIN)
        self.assertEqual(
            self.storage.usage_start_dt[self._tenant_id],
            ck_utils.ts2dt(samples.SECOND_PERIOD_BEGIN))
        self.assertEqual(
            self.storage.usage_end[self._tenant_id],
            samples.SECOND_PERIOD_END)
        self.assertEqual(
            self.storage.usage_end_dt[self._tenant_id],
            ck_utils.ts2dt(samples.SECOND_PERIOD_END))

    def test_clear_period_info_on_commit(self):
        working_data = copy.deepcopy(samples.RATED_DATA)
        self.storage.append(working_data, self._tenant_id)
        self.storage.commit(self._tenant_id)
        self.assertNotIn(self._tenant_id, self.storage.usage_start)
        self.assertNotIn(self._tenant_id, self.storage.usage_start_dt)
        self.assertNotIn(self._tenant_id, self.storage.usage_end)
        self.assertNotIn(self._tenant_id, self.storage.usage_end_dt)

    # Queries
    # Data
    def test_get_no_frame_when_nothing_in_storage(self):
        self.assertRaises(
            storage.NoTimeFrame,
            self.storage.get_time_frame,
            begin=samples.FIRST_PERIOD_BEGIN - 3600,
            end=samples.FIRST_PERIOD_BEGIN)

    def test_get_frame_filter_outside_data(self):
        self.insert_different_data_two_tenants()
        self.assertRaises(
            storage.NoTimeFrame,
            self.storage.get_time_frame,
            begin=samples.FIRST_PERIOD_BEGIN - 3600,
            end=samples.FIRST_PERIOD_BEGIN)

    def test_get_frame_without_filter_but_timestamp(self):
        self.insert_different_data_two_tenants()
        data = self.storage.get_time_frame(
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.SECOND_PERIOD_END)
        self.assertEqual(3, len(data))

    def test_get_frame_on_one_period(self):
        self.insert_different_data_two_tenants()
        data = self.storage.get_time_frame(
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.FIRST_PERIOD_END)
        self.assertEqual(2, len(data))

    def test_get_frame_on_one_period_and_one_tenant(self):
        self.insert_different_data_two_tenants()
        data = self.storage.get_time_frame(
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.FIRST_PERIOD_END,
            tenant_id=self._tenant_id)
        self.assertEqual(2, len(data))

    def test_get_frame_on_one_period_and_one_tenant_outside_data(self):
        self.insert_different_data_two_tenants()
        self.assertRaises(
            storage.NoTimeFrame,
            self.storage.get_time_frame,
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.FIRST_PERIOD_END,
            tenant_id=self._other_tenant_id)

    def test_get_frame_on_two_periods(self):
        self.insert_different_data_two_tenants()
        data = self.storage.get_time_frame(
            begin=samples.FIRST_PERIOD_BEGIN,
            end=samples.SECOND_PERIOD_END)
        self.assertEqual(3, len(data))

    # State
    def test_get_state_when_nothing_in_storage(self):
        state = self.storage.get_state()
        self.assertIsNone(state)

    def test_get_latest_global_state(self):
        self.insert_different_data_two_tenants()
        state = self.storage.get_state()
        self.assertEqual(samples.SECOND_PERIOD_BEGIN, state)

    def test_get_state_on_rated_tenant(self):
        self.insert_different_data_two_tenants()
        state = self.storage.get_state(self._tenant_id)
        self.assertEqual(samples.FIRST_PERIOD_BEGIN, state)
        state = self.storage.get_state(self._other_tenant_id)
        self.assertEqual(samples.SECOND_PERIOD_BEGIN, state)

    def test_get_state_on_no_data_frame(self):
        self.storage.nodata(
            samples.FIRST_PERIOD_BEGIN,
            samples.FIRST_PERIOD_END,
            self._tenant_id)
        self.storage.commit(self._tenant_id)
        state = self.storage.get_state(self._tenant_id)
        self.assertEqual(samples.FIRST_PERIOD_BEGIN, state)

    # Total
    def test_get_empty_total(self):
        self.insert_data()
        total = self.storage.get_total(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN - 3600),
            end=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN))
        self.assertIsNone(total)

    def test_get_total_without_filter_but_timestamp(self):
        self.insert_data()
        total = self.storage.get_total(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.SECOND_PERIOD_END))
        # FIXME(sheeprine): floating point error (transition to decimal)
        self.assertEqual(1.9473999999999998, total)

    def test_get_total_filtering_on_one_period(self):
        self.insert_data()
        total = self.storage.get_total(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.FIRST_PERIOD_END))
        self.assertEqual(1.1074, total)

    def test_get_total_filtering_on_one_period_and_one_tenant(self):
        self.insert_data()
        total = self.storage.get_total(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.FIRST_PERIOD_END),
            tenant_id=self._tenant_id)
        self.assertEqual(0.5537, total)

    def test_get_total_filtering_on_service(self):
        self.insert_data()
        total = self.storage.get_total(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.FIRST_PERIOD_END),
            service='compute')
        self.assertEqual(0.84, total)

    @mock.patch.object(ck_utils, 'utcnow',
                       return_value=ck_utils.ts2dt(samples.INITIAL_TIMESTAMP))
    def test_get_total_no_filter(self, patch_utcnow_mock):
        self.insert_data()
        total = self.storage.get_total()
        self.assertEqual(1.9473999999999998, total)
        self.assertEqual(2, patch_utcnow_mock.call_count)

    # Tenants
    def test_get_empty_tenant_with_nothing_in_storage(self):
        tenants = self.storage.get_tenants(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.SECOND_PERIOD_BEGIN))
        self.assertEqual([], tenants)

    def test_get_empty_tenant_list(self):
        self.insert_data()
        tenants = self.storage.get_tenants(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN - 3600),
            end=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN))
        self.assertEqual([], tenants)

    def test_get_tenants_filtering_on_period(self):
        self.insert_different_data_two_tenants()
        tenants = self.storage.get_tenants(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.SECOND_PERIOD_END))
        self.assertListEqual(
            [self._tenant_id, self._other_tenant_id],
            tenants)
        tenants = self.storage.get_tenants(
            begin=ck_utils.ts2dt(samples.FIRST_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.FIRST_PERIOD_END))
        self.assertListEqual(
            [self._tenant_id],
            tenants)
        tenants = self.storage.get_tenants(
            begin=ck_utils.ts2dt(samples.SECOND_PERIOD_BEGIN),
            end=ck_utils.ts2dt(samples.SECOND_PERIOD_END))
        self.assertListEqual(
            [self._other_tenant_id],
            tenants)

    def add_invoice(self):

        self.storage.add_invoice(invoice_id=samples.INVOICE_DICT_DEMO['invoice_id'],
                                 invoice_date=ck_utils.ts2dt(samples.INVOICE_DICT_DEMO['invoice_date']),
                                 invoice_period_from=ck_utils.ts2dt(samples.INVOICE_DICT_DEMO['invoice_period_from']),
                                 invoice_period_to=ck_utils.ts2dt(samples.INVOICE_DICT_DEMO['invoice_period_to']),
                                 tenant_id=samples.INVOICE_DICT_DEMO['tenant_id'],
                                 invoice_data=json.dumps(samples.INVOICE_DICT_DEMO['invoice_data']),
                                 tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'],
                                 total_cost=samples.INVOICE_DICT_DEMO['total_cost'],
                                 paid_cost=samples.INVOICE_DICT_DEMO['paid_cost'],
                                 balance_cost=samples.INVOICE_DICT_DEMO['balance_cost'],
                                 payment_status=samples.INVOICE_DICT_DEMO['payment_status'])

        self.storage.add_invoice(invoice_id=samples.INVOICE_DICT_ADMIN['invoice_id'],
                                 invoice_date=ck_utils.ts2dt(samples.INVOICE_DICT_ADMIN['invoice_date']),
                                 invoice_period_from=ck_utils.ts2dt(samples.INVOICE_DICT_ADMIN['invoice_period_from']),
                                 invoice_period_to=ck_utils.ts2dt(samples.INVOICE_DICT_ADMIN['invoice_period_to']),
                                 tenant_id=samples.INVOICE_DICT_ADMIN['tenant_id'],
                                 invoice_data=json.dumps(samples.INVOICE_DICT_ADMIN['invoice_data']),
                                 tenant_name=samples.INVOICE_DICT_ADMIN['tenant_name'],
                                 total_cost=samples.INVOICE_DICT_ADMIN['total_cost'],
                                 paid_cost=samples.INVOICE_DICT_ADMIN['paid_cost'],
                                 balance_cost=samples.INVOICE_DICT_ADMIN['balance_cost'],
                                 payment_status=samples.INVOICE_DICT_ADMIN['payment_status'])


    """"""""""""""""""""""""
    #Admin user - get invoice
    """"""""""""""""""""""""

    # get invoice based on tenant_id
    # admin user
    def test_get_invoice_based_on_tenant_id(self):

        self.add_invoice()
        data = self.storage.get_invoice(
            tenant_id=samples.INVOICE_DICT_ADMIN['tenant_id'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_ADMIN_COMPARE)
        self.assertEqual(working_data, data)

    # get invoice based on payment_status
    # admin user
    def test_get_invoice_based_on_payment_status(self):

        self.add_invoice()
        data = self.storage.get_invoice(
            payment_status=samples.INVOICE_DICT_ADMIN['payment_status'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_ADMIN_COMPARE)
        self.assertEqual(working_data, data)

    # get invoice based on invoice id
    # admin user
    def test_get_invoice_based_on_invoice_id(self):

        self.add_invoice()
        data = self.storage.get_invoice(   
            invoice_id=samples.INVOICE_DICT_ADMIN['invoice_id'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_ADMIN_COMPARE)
        self.assertEqual(working_data, data)
 
    # get invoice based on tenant name
    # admin user
    def test_get_invoice_based_on_tenant_name(self):

        self.add_invoice()
        data = self.storage.get_invoice(
            tenant=samples.INVOICE_DICT_ADMIN['tenant_name'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_ADMIN_COMPARE)
        self.assertEqual(working_data, data)

 
    """"""""""""""""""""""""
    #Non-Admin user - get invoice
    """"""""""""""""""""""""

    # get invoice of admin user as non-admin user
    # should not return invoice
    # asserting not equal to check it
    def test_get_invoice_of_admin_based_on_invoice_id_non_admin(self):

        self.add_invoice()
        data = self.storage.get_invoice_for_tenant(
            invoice_id=samples.INVOICE_DICT_ADMIN['invoice_id'],
	    tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_ADMIN_COMPARE)
        self.assertNotEqual(working_data, data)

    # get invoice based on payment status
    # non admin user
    def test_get_invoice_based_on_payment_status_non_admin(self):

        self.add_invoice()
        data = self.storage.get_invoice_for_tenant(
            payment_status=samples.INVOICE_DICT_DEMO['payment_status'],
            tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertEqual(working_data, data)

    """"""""""""""""""""""""
    #Admin user - list invoice
    """"""""""""""""""""""""
    # list the invoice
    # admin user
    def test_list_invoice(self):

        self.add_invoice()
        data = self.storage.list_invoice(
            tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertEqual(working_data, data)

    # list the invoice - with all tenants options
    # admin user
    def test_list_invoice_all_tenants_option(self):

        self.add_invoice()
        data = self.storage.list_invoice(tenant_name=samples.INVOICE_DICT_ADMIN['tenant_name'], all_tenants='1')
        working_data = copy.deepcopy(samples.ALL_INVOICES)
        self.assertEqual(working_data, data)

    """"""""""""""""""""""""
    #Non-Admin user - list invoice
    """"""""""""""""""""""""
    # list the invoice
    # non-admin user
    def test_list_invoice_non_admin(self):

        self.add_invoice()
        data = self.storage.list_invoice(
            tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertEqual(working_data, data)

    """"""""""""""""""""""""
    #Admin user - show invoice
    """"""""""""""""""""""""
    # show own invoice by simply giving invoice id
    # admin user
    def test_show_invoice(self):

        self.add_invoice()
        data = self.storage.show_invoice(
            invoice_id=samples.INVOICE_DICT_ADMIN['invoice_id'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_ADMIN_COMPARE)
        self.assertEqual(working_data, data)

    # show other's invoice by simply giving invoice id
    # admin user
    def test_show_invoice_others(self):

        self.add_invoice()
        data = self.storage.show_invoice(
            invoice_id=samples.INVOICE_DICT_DEMO['invoice_id'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertEqual(working_data, data)

    """"""""""""""""""""""""
    # Non-Admin user - show invoice
    """"""""""""""""""""""""
    # show own invoice by simply giving invoice id
    # Non-admin user
    def test_show_invoice_non_admin(self):

        self.add_invoice()
        data = self.storage.show_invoice_for_tenant(
	    tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'],
            invoice_id=samples.INVOICE_DICT_DEMO['invoice_id'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertEqual(working_data, data)
    
    # show other's invoice by simply giving invoice id
    # not possible - other users invoice is not accessible
    # Non-admin user
    def test_show_invoice_others_non_admin(self):

        self.add_invoice()
        data = self.storage.show_invoice_for_tenant(
	    tenant_name=samples.INVOICE_DICT_DEMO['tenant_name'],
            invoice_id=samples.INVOICE_DICT_ADMIN['invoice_id'])
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertNotEqual(working_data, data)

    """"""""""""""""""""""""
    # Admin user - update invoice
    """"""""""""""""""""""""
    # update invoice based on the invoice id
    # Admin user
    def test_update_invoice(self):

        self.add_invoice()
        data = self.storage.update_invoice(
            invoice_id=samples.INVOICE_DICT_DEMO['invoice_id'],
            total_cost='3.50',
            paid_cost='1.50',
            balance_cost='2.00',
            payment_status='1')
        working_data = copy.deepcopy(samples.INVOICE_DATA_DEMO_COMPARE)
        self.assertNotEqual(working_data, data)

    """"""""""""""""""""""""
    # Admin user - delete invoice
    """"""""""""""""""""""""
    # delete invoice based on the invoice id
    # Admin user
    def test_show_invoice_admin(self):

        self.add_invoice()
        data = self.storage.delete_invoice(
            invoice_id=samples.INVOICE_DICT_DEMO['invoice_id'])
        working_data = copy.deepcopy(samples.ALL_INVOICES)
        self.assertNotEqual(working_data, data)


    """"""""""""""""""""""""
    # Admin user - Add invoice
    """"""""""""""""""""""""
    # Add invoice with all necessary details
    # Admin user
    def test_add_invoice_admin(self):

        data = self.add_invoice()
        working_data = copy.deepcopy(samples.ALL_INVOICES)
        self.assertNotEqual(working_data, data)

StorageTest.generate_scenarios()
