import logging
import warnings
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery, log_query
from haystack.exceptions import MissingDependency
from haystack.models import SearchResult
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

    def connect(self):
        return MySQLdb.connect(**self.conn_kwargs)

    def update(self, index, iterable):
        """
        Issue an UPDATE query to Sphinx.
        """
        values = []
        # TODO determine fields.
        fields = []
        for item in iterable:
            row = []
            for field_name in fields:
                row.append(getattr(item, field_name))
            values.append(row)
        conn = self.connect()
        try:
            conn.executemany('REPLACE INTO {0} ({1}) VALUES (%s, %s)'.format(self.index_name, ', '.join(fields)), values)
        finally:
            conn.close()

    def remove(self, obj_or_string):
        """
        Issue a DELETE query to Sphinx.
        """
        conn = self.connect()
        try:
            conn.execute('DELETE FROM {0} WHERE id = %s'.format(self.index_name), (id, ))
        finally:
            conn.close()

    def clear(self, models=[], commit=True):
        raise NotImplementedError

    @log_query
    def search(self, query_string, sort_by=None, start_offset=0, end_offset=None,
               fields='', highlight=False, facets=None, date_facets=None, query_facets=None,
               narrow_queries=None, spelling_query=None, within=None,
               dwithin=None, distance_point=None,
               limit_to_registered_models=None, result_class=None, **kwargs):
        if result_class is None:
            result_class = SearchResult
        conn = self.connect()
        try:
            curr = conn.cursor()
            rows = curr.execute('SELECT * FROM {0} WHERE MATCH(\'{1}\')'.format(self.index_name, query_string))
        finally:
            conn.close()
        results = []
        while True:
            row = curr.fetchone()
            if not row:
                break
            results.append(result_class(row))
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
    def build_query_fragment(self, field, filter_type, value):
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
