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
import warnings

from cloudkitty.api.v1.controllers import rating as rating_api
from cloudkitty.api.v1.controllers.rating import ModulesController  # noqa
from cloudkitty.api.v1.controllers.rating import ModulesExposer  # noqa
from cloudkitty.api.v1.controllers.rating import UnconfigurableController  # noqa


def deprecated():
    warnings.warn(
        ('The billing controllers are deprecated. '
         'Please use rating\'s one instead.'),
        DeprecationWarning,
        stacklevel=3)


deprecated()


class BillingController(rating_api.RatingController):
    """The BillingController is exposed by the API.

    Deprecated, replaced by the RatingController.
    """
