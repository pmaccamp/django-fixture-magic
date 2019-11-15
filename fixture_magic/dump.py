from __future__ import print_function

from django.core.exceptions import FieldError, ObjectDoesNotExist
from django.core.management.base import CommandError
from django.core.serializers import serialize
from fixture_magic.compat import get_all_related_objects

try:
    from django.db.models import loading
except ImportError:
    from django.apps import apps as loading
import json

from fixture_magic.utils import (add_to_serialize_list, serialize_fully, reorder_json)


def dump_object(model,
                query,
                ids,
                order=[],
                ignore=[],
                additional_serialization_objects_fnc=None,
                format='json',
                kitchensink=True,
                follow_fk=True,
                natural=False,
                natural_foreign=False,
                natural_primary=False):
    serialize_me = []
    seen = set()
    error_text = ('Error\n')

    try:
        # verify input is valid
        try:
            (app_label, model_name) = model.split('.')
        except AttributeError:
            raise CommandError("Specify model as `appname.modelname")

        if ids and query:
            raise CommandError(error_text % 'either use query or id list, not both')
        if not (ids or query):
            raise CommandError(error_text % 'must pass list of --ids or a json --query')
    except IndexError:
        raise CommandError(error_text % 'No object_class or filter clause supplied.')
    except ValueError as e:
        raise CommandError(
            error_text %
            "object_class must be provided in the following format: app_name.model_name"
        )
    except AssertionError:
        raise CommandError(error_text % 'No filter argument supplied.')

    dump_me = loading.get_model(app_label, model_name)
    if query:
        objs = dump_me.objects.filter(**json.loads(query))
    else:
        if ids[0] == '*':
            objs = dump_me.objects.all()
        else:
            try:
                parsers = int, long, str
            except NameError:
                parsers = int, str
            for parser in parsers:
                try:
                    objs = dump_me.objects.filter(pk__in=map(parser, ids))
                except ValueError:
                    pass
                else:
                    break

    if kitchensink:
        fields = get_all_related_objects(dump_me)

        related_fields = [rel.get_accessor_name() for rel in fields if rel.name not in ignore]

        for obj in objs:
            for rel in related_fields:
                try:
                    if hasattr(getattr(obj, rel), 'all'):
                        add_to_serialize_list(getattr(obj, rel).all(), serialize_me, seen)
                    else:
                        add_to_serialize_list([getattr(obj, rel)], serialize_me, seen)

                        # allow user to add additional data apart from standard foreign keys
                        if additional_serialization_objects_fnc and \
                                callable(additional_serialization_objects_fnc):
                            extra_objs = additional_serialization_objects_fnc(getattr(obj, rel))
                            if extra_objs:
                                add_to_serialize_list(extra_objs, serialize_me, seen)

                except FieldError:
                    pass
                except ObjectDoesNotExist:
                    pass

    add_to_serialize_list(objs, serialize_me, seen, prepend=True)

    if follow_fk:
        serialize_fully(serialize_me, seen, ignore, additional_serialization_objects_fnc)
    else:
        # reverse list to match output of serializez_fully
        serialize_me.reverse()

    natural_foreign = (natural or
                       natural_foreign)
    natural_primary = (natural or
                       natural_primary)

    if format:
        data = serialize(format,
                         [o for o in serialize_me if o is not None],
                         indent=4,
                         use_natural_foreign_keys=natural_foreign,
                         use_natural_primary_keys=natural_primary)

        data = reorder_json(
            json.loads(data),
            order,
        )

        return json.dumps(data, indent=4)

    # return unserialized objs
    return [o for o in serialize_me if o is not None]
