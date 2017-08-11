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
try: import simplejson as json
except ImportError: import json
from oslo_db.sqlalchemy import models
import sqlalchemy
from sqlalchemy.ext import declarative

from cloudkitty import utils as ck_utils

Base = declarative.declarative_base()


class RatedDataFrame(Base, models.ModelBase):
    """A rated data frame.

    """
    __table_args__ = {'mysql_charset': "utf8",
                      'mysql_engine': "InnoDB"}
    __tablename__ = 'rated_data_frames'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True)
    tenant_id = sqlalchemy.Column(sqlalchemy.String(32),
                                  nullable=True)
    begin = sqlalchemy.Column(sqlalchemy.DateTime,
                              nullable=False)
    end = sqlalchemy.Column(sqlalchemy.DateTime,
                            nullable=False)
    unit = sqlalchemy.Column(sqlalchemy.String(255),
                             nullable=False)
    qty = sqlalchemy.Column(sqlalchemy.Numeric(),
                            nullable=False)
    res_type = sqlalchemy.Column(sqlalchemy.String(255),
                                 nullable=False)
    rate = sqlalchemy.Column(sqlalchemy.Float(),
                             nullable=False)
    desc = sqlalchemy.Column(sqlalchemy.Text(),
                             nullable=False)

    def to_cloudkitty(self, collector=None):
        # Rating informations
        rating_dict = {}
        rating_dict['price'] = self.rate

        # Volume informations
        vol_dict = {}
        vol_dict['qty'] = self.qty.normalize()
        vol_dict['unit'] = self.unit
        res_dict = {}

        # Encapsulate informations in a resource dict
        res_dict['rating'] = rating_dict
        res_dict['desc'] = json.loads(self.desc)
        res_dict['vol'] = vol_dict
        res_dict['tenant_id'] = self.tenant_id

        # Add resource to the usage dict
        usage_dict = {}
        usage_dict[self.res_type] = [res_dict]

        # Time informations
        period_dict = {}
        period_dict['begin'] = ck_utils.dt2iso(self.begin)
        period_dict['end'] = ck_utils.dt2iso(self.end)

        # Add period to the resource informations
        ck_dict = {}
        ck_dict['period'] = period_dict
        ck_dict['usage'] = usage_dict
        return ck_dict

class InvoiceDetails(Base, models.ModelBase):
    """Invoice details table.
    """
    __table_args__ = {'mysql_charset': "utf8",
                      'mysql_engine': "InnoDB"}
    __tablename__ = 'invoice_details'

    id = sqlalchemy.Column(sqlalchemy.Integer,
                           primary_key=True)
    invoice_date = sqlalchemy.Column(sqlalchemy.DateTime,
                              nullable=False)
    invoice_period_from = sqlalchemy.Column(sqlalchemy.DateTime,
                              nullable=False)
    invoice_period_to = sqlalchemy.Column(sqlalchemy.DateTime,
                              nullable=False)
    tenant_id = sqlalchemy.Column(sqlalchemy.String(255),
                                  nullable=False)
    tenant_name = sqlalchemy.Column(sqlalchemy.String(255),
                                  nullable=False)
    invoice_id = sqlalchemy.Column(sqlalchemy.String(255),
                             nullable=False)
    invoice_data = sqlalchemy.Column(sqlalchemy.Text(),
                             nullable=False)
    total_cost = sqlalchemy.Column(sqlalchemy.Float(precision='13,2'),
                             nullable=True)
    paid_cost = sqlalchemy.Column(sqlalchemy.Float(precision='13,2'),
                             nullable=True)
    balance_cost = sqlalchemy.Column(sqlalchemy.Float(precision='13,2'),
                             nullable=True)
    payment_status = sqlalchemy.Column(sqlalchemy.Integer,
                             nullable=True)

    def to_cloudkitty(self):

        invoice_dict = {}
        invoice_dict['id'] = self.id
        invoice_dict['invoice_date'] = ck_utils.dt2iso(self.invoice_date)
        invoice_dict['invoice_period_from'] = ck_utils.dt2iso(self.invoice_period_from)
        invoice_dict['invoice_period_to'] = ck_utils.dt2iso(self.invoice_period_to)
        invoice_dict['tenant_id'] = self.tenant_id
        invoice_dict['tenant_name'] = self.tenant_name
        invoice_dict['invoice_id'] = self.invoice_id
        invoice_dict['invoice_data'] = json.loads(self.invoice_data)
        invoice_dict['total_cost'] = json.dumps(self.total_cost, use_decimal=True)
        invoice_dict['paid_cost'] = json.dumps(self.paid_cost, use_decimal=True)
        invoice_dict['balance_cost'] = json.dumps(self.balance_cost, use_decimal=True)
        invoice_dict['payment_status'] = self.payment_status

        return invoice_dict
