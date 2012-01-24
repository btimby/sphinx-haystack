import time
import datetime
import logging
import warnings
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.encoding import force_unicode
from django.contrib.contenttypes.models import ContentType
from haystack.backends import BaseEngine, BaseSearchBackend, BaseSearchQuery, log_query
from haystack.exceptions import MissingDependency, SearchBackendError
from haystack.utils import get_identifier
from haystack.constants import ID, DJANGO_CT, DJANGO_ID
from sphinx_haystack.models import Document
try:
    import MySQLdb
except ImportError:
    raise MissingDependency("The 'sphinx' backend requires the installation of 'MySQLdb'. Please refer to the documentation.")
try:
    # Pool connections if SQLAlchemy is present.
    import sqlalchemy.pool as pool
    # TODO: troubleshoot 'MySQL server has gone away'
    # For now disable connection pool.
    # MySQLdb = pool.manage(MySQLdb)
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
        self.log = logging.getLogger('haystack')
        self.conn_kwargs = {
            'host': connection_options.get('HOST', DEFAULT_HOST),
            'port': connection_options.get('PORT', DEFAULT_PORT),
        }
        if self.conn_kwargs.get('host') == 'localhost':
            self.log.warning('Using the host \'localhost\' will connect via the MySQL socket. Sphinx listens on a TCP socket.')
        try:
            self.index_name = connection_options['INDEX_NAME']
        except KeyError, e:
            raise ImproperlyConfigured('Missing index name for sphinx-haystack. Please define %s.' % e.args[0])
        if not connection_pooling:
            self.log.warning('Connection pooling disabled for sphinx-haystack. Install SQLAlchemy.')

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
        Issue a REPLACE INTO query to Sphinx. This will either insert or update
        a document in the index. If the document ID exists, an update is performed.
        Otherwise a new document is inserted.
        """
        values = []
        # TODO determine fields.
        fields, field_names = [], ['id']
        for name, field in index.fields.items():
            fields.append((name, field))
            field_names.append(name)
        # TODO: use a transaction to remove documents if we are
        # unsuccessful in saving to Sphinx.
        for item in iterable:
            document, created = Document.objects.get_or_create(
                content_type = ContentType.objects.get_for_model(item),
                object_id = item.pk
            )
            row = index.full_prepare(item)
            row['id'] = document.pk
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
        Issue a DELETE query to Sphinx. Deletes a document by it's document ID.
        """
        if isinstance(obj_or_string, basestring):
            app_label, model_name, object_id = obj_or_string.split('.')
            content_type = ContentType.objects.get_by_natural_key(app_label, model_name)
        else:
            content_type = ContentType.objects.get_for_model(obj_or_string)
            object_id = obj_or_string.pk
        try:
            document = Document.objects.get(
                content_type=content_type,
                object_id=object_id
            )
        except Document.DoesNotExist:
            # Already removed?
            return
        conn = self._connect()
        try:
            # TODO: use a transaction to delete both atomically.
            curr = conn.cursor()
            curr.execute('DELETE FROM {0} WHERE id = %s'.format(self.index_name), (document.pk, ))
            document.delete()
        finally:
            conn.close()

    def clear(self, models=[], commit=True):
        """
        Clears all contents from index. This method iteratively gets a list of document
        ID numbers, then deletes them from the index. It does this in a while loop because
        Sphinx will limit the result set to 1,000.
        """
        conn = self._connect()
        try:
            # TODO: use transaction to delete all atomically.
            curr = conn.cursor()
            while True:
                ids = [d.pk for d in Document.objects.all()[:1000]]
                if not ids:
                    break
                curr.execute('DELETE FROM {0} WHERE id IN ({1})'.format(self.index_name, ','.join(map(str, ids))))
                Document.objects.filter(id__in=ids).delete()
        finally:
            conn.close()

    @log_query
    def search(self, query_string, sort_by=None, start_offset=0, end_offset=None,
               fields='', highlight=False, facets=None, date_facets=None, query_facets=None,
               narrow_queries=None, spelling_query=None, within=None,
               dwithin=None, distance_point=None,
               limit_to_registered_models=None, result_class=None, **kwargs):
        if result_class is None:
            result_class = Document
        query = 'SELECT * FROM {0} WHERE MATCH(%s)'
        if start_offset and end_offset:
            query += ' LIMIT {0}, {1}'.format(start_offset, end_offset)
        if end_offset:
            query += ' LIMIT {0}'.format(end_offset)
        if sort_by:
            fields, reverse = [], None
            for field in sort_by:
                if field.startswith('-'):
                    if reverse == False:
                        raise SearchBackendError('Sphinx can only sort by ASC or DESC, not a mix of the two.')
                    reverse = True
                else:
                    if reverse == True:
                        raise SearchBackendError('Sphinx can only sort by ASC or DESC, not a mix of the two.')
                    reverse = False
                fields.append(field)
            query += ' ORDER BY {0}'.format(', '.join(fields))
            if reverse:
                query += ' DESC'
            else:
                query += 'ASC'
        conn = self._connect()
        try:
            curr = conn.cursor()
            rows = curr.execute(query.format(self.index_name), (query_string, ))
        finally:
            conn.close()
        results = []
        while True:
            row = curr.fetchone()
            if not row:
                break
            id, score = row[:2]
            document = Document.objects.get(pk=id)
            document.score = score
            results.append(document)
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
        # TODO: Any fields that are not "full text" but an attribute in Sphinx, such
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
