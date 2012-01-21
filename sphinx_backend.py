import logging
import warnings
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models.loading import get_model
from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery, log_query, EmptyResults
from haystack.constants import ID, DJANGO_CT, DJANGO_ID
from haystack.exceptions import MissingDependency, MoreLikeThisError
from haystack.inputs import PythonData, Clean, Exact
from haystack.models import SearchResult
from haystack.utils import get_identifier
try:
    # TODO: is it possible to use ORM instead?
    import MySQLdb
except ImportError:
    raise MissingDependency("The 'sphinx' backend requires the installation of 'MySQLdb'. Please refer to the documentation.")


class SphinxSearchBackend(BaseSearchBackend):
    def __init__(self, connection_alias, **connection_options):
        pass

    def update(self, index, iterable):
        """
        Issue an UPDATE query to Sphinx.
        """
        raise NotImplementedError

    def remove(self, obj_or_string):
        """
        Issue a DELETE query to Sphinx.
        """
        raise NotImplementedError

    def clear(self, models=[], commit=True):
        raise NotImplementedError

    @log_query
    def search(self, query_string, sort_by=None, start_offset=0, end_offset=None,
               fields='', highlight=False, facets=None, date_facets=None, query_facets=None,
               narrow_queries=None, spelling_query=None, within=None,
               dwithin=None, distance_point=None,
               limit_to_registered_models=None, result_class=None, **kwargs):
        raise NotImplementedError

    def prep_value(self, value):
        return force_unicode(value)

    def more_like_this(self, model_instance, additional_query_string=None, result_class=None):
        raise NotImplementedError("Subclasses must provide a way to fetch similar record via the 'more_like_this' method if supported by the backend.")

    def extract_file_contents(self, file_obj):
        raise NotImplementedError("Subclasses must provide a way to extract metadata via the 'extract' method if supported by the backend.")

    def build_schema(self, fields):
        raise NotImplementedError("Subclasses must provide a way to build their schema.")


class SimpleSearchQuery(BaseSearchQuery):
    def build_query(self):
        pass


class SphinxEngine(BaseEngine):
    backend = SphinxSearchBackend
    query = SphinxSearchQuery