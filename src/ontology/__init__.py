# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Logical ontology (v0).

Implements the spec at ``docs/ontology/ontology.md``: a logical,
backend-neutral ontology described in YAML, with entities, relationships,
properties, keys, and single-parent inheritance.
"""

from .loader import load_ontology
from .loader import load_ontology_from_string
from .models import Cardinality
from .models import Entity
from .models import Keys
from .models import Ontology
from .models import Property
from .models import PropertyType
from .models import Relationship

__all__ = [
    "Cardinality",
    "Entity",
    "Keys",
    "Ontology",
    "Property",
    "PropertyType",
    "Relationship",
    "load_ontology",
    "load_ontology_from_string",
]
