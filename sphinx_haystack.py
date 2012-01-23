import time
import datetime
import logging
import warnings
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_unicode
from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery, log_query
from haystack.exceptions import MissingDependency
from haystack.models import SearchResult
from haystack.utils import get_identifier
from haystack.constants import ID, DJANGO_CT, DJANGO_ID
try:
    import MySQLdb
except ImportError:
    raise MissingDependency("The 'sphinx' backend requires the installation of 'MySQLdb'. Please refer to the documentation.")
try:
    # Pool connections if SQLAlchemy is present.
    import sqlalchemy.pool as pool
    MySQLdb = pool.manage(MySQLdb)
    connection_pooling = True
except ImportError:
    connection_pooling = False

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 9306


class SphinxSearchBackend(BaseSearchBackend):
    # https://github.com/dcramer/django-sphinx/tree/master/djangosphinx/
    def __init__(self, connection_alias, **connection_options):
        # TODO: determine the version number of Sphinx.
        # Parse from server banner "Server version: 1.10-dev (r2153)"
        super(SphinxSearchBackend, self).__init__(connection_alias, **connection_options)
        self.conn_kwargs = {
            'host': connection_options.get('HOST', DEFAULT_HOST),
            'port': connection_options.get('PORT', DEFAULT_PORT),
        }
        try:
            self.index_name = connection_options['INDEX']
        except KeyError:
            raise ImproperlyConfigured('Missing index name for sphinx-haystack. Please define INDEX.')
        self.log = logging.getLogger('haystack')
        if not connection_pooling:
            self.log.warning('Connection pooling disabled. Install SQLAlchemy.')

    def _from_python(self, value):
        if isinstance(value, datetime.datetime):
            value = time.mktime((value.year, value.month, value.day, value.hour, value.minute, value.second, 0, 0, 0))
        elif isinstance(value, bool):
            if value:
                value = 1
            else:
                value = 0
        elif isinstance(value, (list, tuple)):
            value = u','.join([force_unicode(v) for v in value])
        elif isinstance(value, (int, long, float)):
            # Leave it alone.
            pass
        else:
            value = force_unicode(value)
        return value

    def _connect(self):
        return MySQLdb.connect(**self.conn_kwargs)

    def update(self, index, iterable):
        """
        Issue an UPDATE query to Sphinx.
        """
        values = []
        # TODO determine fields.
        fields, field_names = [], ['id']
        for name, field in index.fields.items():
            fields.append((name, field))
            field_names.append(name)
        for item in iterable:
            row = index.full_prepare(item)
            row['id'] = item.id
            values.append([row[f] for f in field_names])
        conn = self._connect()
        try:
            curr = conn.cursor()
            # TODO: is executemany() better than many execute()s?
            curr.executemany('REPLACE INTO {0} ({1}) VALUES ({2})'.format(
                self.index_name,
                # Comma-separated list of field names
                ', '.join(field_names),
                # Comma-separated list of "%s", same number of them as field names.
                ', '.join(('%s', ) * len(field_names))
            ), values)
        finally:
            conn.close()

    def remove(self, obj_or_string):
        """
        Issue a DELETE query to Sphinx.
        """
        id = get_identifier(obj_or_string)
        conn = self._connect()
        try:
            curr = conn.cursor()
            curr.execute('DELETE FROM {0} WHERE id = %s'.format(self.index_name), (id, ))
        finally:
            conn.close()

    def clear(self, models=[], commit=True):
        # Do not issue a DELETE statement for the index. This will just add all
        # the documents to the kill list. If the user actually wants to delete
        # the index, they will need to issue an rm for the index data file and binlog.
        raise NotImplementedError('Cannot delete index via Sphinx Backend.')

    @log_query
    def search(self, query_string, sort_by=None, start_offset=0, end_offset=None,
               fields='', highlight=False, facets=None, date_facets=None, query_facets=None,
               narrow_queries=None, spelling_query=None, within=None,
               dwithin=None, distance_point=None,
               limit_to_registered_models=None, result_class=None, **kwargs):
        if result_class is None:
            result_class = SearchResult
        query = 'SELECT * FROM {0} WHERE MATCH(\'{1}\')'
        if start_offset and end_offset:
            query += ' LIMIT {0}, {1}'.format(start_offset, end_offset)
        if end_offset:
            query += ' LIMIT {0}'.format(end_offset)
        conn = self._connect()
        try:
            curr = conn.cursor()
            rows = curr.execute(query.format(self.index_name, query_string))
        finally:
            conn.close()
        results = []
        # TODO: determine these at run-time:
        app_label = 'notes'
        model_name = 'Note'
        while True:
            row = curr.fetchone()
            if not row:
                break
            #app_label, model_name = row[DJANGO_CT].split('.')
            id, score = row[:2]
            results.append(result_class(app_label, model_name, id, score))
        hits = len(results)
        return {
            'results': results,
            'hits': hits,
        }

    def prep_value(self, value):
        return force_unicode(value)

    def more_like_this(self, model_instance, additional_query_string=None, result_class=None):
        raise NotImplementedError("Subclasses must provide a way to fetch similar record via the 'more_like_this' method if supported by the backend.")

    def extract_file_contents(self, file_obj):
        raise NotImplementedError("Subclasses must provide a way to extract metadata via the 'extract' method if supported by the backend.")

    def build_schema(self, fields):
        raise NotImplementedError("Subclasses must provide a way to build their schema.")


class SphinxSearchQuery(BaseSearchQuery):
    def build_query(self):
        # TODO: any fields that are not "full text" but an attribute in Sphinx, such
        # as an int or timestamp column needs to be handled via regular WHERE clause syntax:
        # ... WHERE attr = 1234 ...
        # However "full text" fields need to be globbed together using the Sphinx Query syntax
        # inside a MATCH() call:
        # ... WHERE MATCH('@text keyword') ...
        # Together this should yield something like:
        # ... WHERE attr = 1234 AND MATCH('@text keyword') ...
        return super(SphinxSearchQuery, self).build_query()

    def build_query_fragment(self, field, filter_type, value):
        # TODO: this probably won't be needed in the future, the functionality here will
        # be handled in build_query. However, since I am unsure how to determine what type
        # of field each field is, we will just treat them all as "full text" fields and let
        # the base implementation glob them for us.
        from haystack import connections
        if field == 'content':
            index_fieldname = '@* '
        else:
            index_fieldname = u'@%s ' % connections[self._using].get_unified_index().get_index_fieldname(field)
        value = value.query_string
        # Build query fragment according to:
        # http://sphinxsearch.com/docs/2.0.2/extended-syntax.html
        filter_types = {
            'contains': '{0}{1}',
            'startswith': '{0}^{1}',
            'exact': '{0}={1}',
        }
        query_frag = filter_types.get(filter_type).format(index_fieldname, value)
        return query_frag


class SphinxEngine(BaseEngine):
    backend = SphinxSearchBackend
    query = SphinxSearchQuery
