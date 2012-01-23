A [SmartFile](http://www.smartfile.com/) Open Source project. [Read more](http://www.smartfile.com/open-source.html) about how SmartFile uses and contributes to Open Source software.

![SmartFile](http://www.smartfile.com/images/logo.jpg)

Introduction
====

This is a backend for [haystack](http://haystacksearch.org/) that implements support for [Sphinx RT Indexes](http://sphinxsearch.com/docs/2.0.2/rt-indexes.html).

Sphinx RT indexes are real-time indexes managed via SphinxQL (MySQL compatible API).

Usage
====

You should install this backend using setup.py or pip.

    $ pip install sphinx-haystack

-or-

    $ python setup.py install

This backend uses MySQLdb to connect to Sphinx using it's SQL emulation. 

    $ pip install MySQLdb

The database connection pooling from SQLAlchemy is used if available. It is highly recommended that you install this.

    $ pip install sqlalchemy

Once installed, you must define a connection in your settings.py file:

    HAYSTACK_CONNECTIONS = {
        'default': {
            'ENGINE': 'sphinx_haystack.SphinxEngine',
            # Name of the Sphinx index.
            'INDEX': 'rt',
        },
    }

Sphinx Configuration
====

Traditional Sphinx indexes require a data source to be configured. You would then use the indextool command line program to build the index from the data source. Traditional indexes are not supported by this backend.

This backend works with Sphinx Real-Time indexes. This type of index starts out empty (or as a traditional index "converted" to a real time index) and is populated using SQL INSERT/UPDATE/REPLACE INTO queries. Sphinx emulates MySQL server to allow the user to issue these commands directly to it.

To configure a real-time index, you do the following in /etc/sphinx.conf. The following example is for the haystack example Notes application.

    # realtime index example
    #
    # you can run INSERT, REPLACE, and DELETE on this index on the fly
    # using MySQL protocol (see 'listen' directive below)
    index rt
    {
            # 'rt' index type must be specified to use RT index
            type                    = rt

            # index files path and file name, without extension
            # mandatory, path must be writable, extensions will be auto-appended
            path                    = /var/tmp/indexes/rt

            # RAM chunk size limit
            # RT index will keep at most this much data in RAM, then flush to disk
            # optional, default is 32M
            #
            # rt_mem_limit          = 512M

            # full-text field declaration
            # multi-value, mandatory
            rt_field                = title
            rt_field                = text

            # unsigned integer attribute declaration
            # multi-value (an arbitrary number of attributes is allowed), optional
            # declares an unsigned 32-bit attribute
            #rt_attr_uint           = gid

            # RT indexes currently support the following attribute types:
            # uint, bigint, float, timestamp, string
            #
            rt_attr_bigint                = user_id
            # rt_attr_float         = gpa
            rt_attr_timestamp       = pub_date
            # rt_attr_string                = author
    }

Sphinx is different than other haystack backends as it allows multiple "full text" columns. You can do full text searches against any (or all) of these columns. You can do additional filtering on other "attributes" which are non-indexed columns.
