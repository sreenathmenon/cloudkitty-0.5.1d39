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

import six
from stevedore import extension

TRANSFORMERS_NAMESPACE = 'cloudkitty.transformers'


def get_transformers():
    transformers = {}
    transformer_exts = extension.ExtensionManager(
        TRANSFORMERS_NAMESPACE,
        invoke_on_load=True)
    for transformer in transformer_exts:
        t_name = transformer.name
        t_obj = transformer.obj
        transformers[t_name] = t_obj
    return transformers


@six.add_metaclass(abc.ABCMeta)
class BaseTransformer(object):
    def __init__(self):
        pass
