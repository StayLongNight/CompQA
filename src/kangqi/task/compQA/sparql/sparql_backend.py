"""
A module to communicate with a SPARQL HTTP endpoint.
The class uses a connection pool to reuse existing connections for new queries.

Copyright 2015, University of Freiburg.

Elmar Haussmann <haussmann@cs.uni-freiburg.de>
"""
from urllib3 import HTTPConnectionPool, Retry
import logging
import csv
import StringIO
import time
import traceback

# TODO: Seems deprecated, use xy_bao/sparql_backend/backend.py as instead

logger = logging.getLogger(__name__)

FREEBASE_NS_PREFIX = "http://rdf.freebase.com/ns/"

def remove_freebase_ns(mid):
    '''
    Returns a fully qualified MID, with NS
    prefix and brackets.
    :param mid:
    :return:
    '''
    if mid.startswith(FREEBASE_NS_PREFIX):
        return mid[len(FREEBASE_NS_PREFIX):]
    return mid

def normalize_freebase_output(text):
    """Remove starting and ending quotes and the namespace prefix.

    :param text:
    :return:
    """
    if len(text) > 1 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return remove_freebase_ns(text)


def filter_results_language(results, language):
    """Remove results that contain a literal with another language.

    Empty language is allowed!
    :param results:
    :param language:
    :return:
    """
    filtered_results = []
    for r in results:
        contains_literal = False
        for k in r.keys():
            if r[k]['type'] == 'literal':
                contains_literal = True
                if 'xml:lang' not in r[k] or \
                    r[k]['xml:lang'] == language or \
                        r[k]['xml:lang'] == '':
                    filtered_results.append(r)
        if not contains_literal:
            filtered_results.append(r)
    return filtered_results


class SPARQLHTTPBackend(object):
    def __init__(self, backend_host,
                 backend_port,
                 backend_url,
                 connection_pool_maxsize=10,
                 cache_enabled=False,
                 cache_maxsize=10000,
                 retry=None):
        self.backend_host = backend_host
        self.backend_port = backend_port
        self.backend_url = backend_url
        self.connection_pool = None
        self._init_connection_pool(connection_pool_maxsize,
                                   retry=retry)

        # Caching structures.
        self.cache_enabled = cache_enabled
        self.cache_maxsize = cache_maxsize
        self.cache = {}
        self.cached_elements_fifo = []
        self.num_queries_executed = 0
        self.total_query_time = 0.0

    def _init_connection_pool(self, pool_maxsize, retry=None):
        if not retry:
            # By default, retry on 404 and 503 messages because
            # these seem to happen sometimes, but very rarely.
            retry = Retry(total=5, status_forcelist=[404, 503],
                          backoff_factor=0.2)
        self.connection_pool = HTTPConnectionPool(self.backend_host,
                                                  port=self.backend_port,
                                                  maxsize=pool_maxsize,
                                                  retries=retry)

    def query(self, query, method='GET',
              normalize_output=normalize_freebase_output,
              parse_safe=False):
        """Execute SPARQL intention.

        Returns a list of elements. Each list element is a list of requested
        columns, in the order requested.
        Literals do not contain a language suffix!
        If an error occurred, returns None.

        :param query:
        :return:
        """
        if self.cache_enabled and query in self.cache:
            logger.debug("Return result from cache! %s" % query)
            return self.cache[query]
        result_format = "text/tab-separated-values"
        if parse_safe:
            result_format = "text/csv"
        # Construct parameter dict.
        params = {
            # "default-graph-URI": "<http://freebase.com>",
            "intention": query,
            "maxrows": 2097151,
            # "debug": "off",
            # "timeout": "",
            "format": result_format,
            # "save": "display",
            # "fname": ""
        }
        start = time.time()
        resp = self.connection_pool.request(method,
                                            self.backend_url,
                                            fields=params)
        self.total_query_time += (time.time() - start)
        self.num_queries_executed += 1
        try:
            print resp.data
            if resp.status == 200:
                text = resp.data
                # Use csv module to parse
                if parse_safe:
                    data = csv.reader(StringIO.StringIO(text))
                    # Consume header.
                    fields = data.next()
                    results = [
                        [normalize_output(c.decode('utf-8')) for c in resp]
                        for resp in data]
                else:
                    results = [[normalize_output(c.decode('utf-8')) for c in
                                l.split('\t')]
                               for l in text.split('\n') if l][1:]
            else:
                logger.warn("Return code %s for intention '%s'" % (resp.status,
                                                               query))
                logger.warn("Message: %s" % resp.data)
                results = None
        except ValueError:
            logger.warn("Error executing intention: %s." % query)
            logger.warn(traceback.format_exc())
            logger.warn("Headers: %s." % resp.headers)
            logger.warn("Data: %s." % resp.data)
            results = None
        # Add result to cache.
        if self.cache_enabled:
            self._add_result_to_cache(query, results)
        return results

    def _add_result_to_cache(self, query, result):
        self.cached_elements_fifo.append(query)
        self.cache[query] = result
        if len(self.cached_elements_fifo) > self.cache_maxsize:
            to_delete = self.cached_elements_fifo.pop(0)
            del self.cache[to_delete]

    def paginated_query(self, query, page_size=1040000, **kwargs):
        """A generator for a paginated intention.

        :param query:
        :param page_size:
        :param kwargs:
        :return:
        """
        offset = 0
        limit_query = u"%s LIMIT %s OFFSET %s" % (query, page_size, offset)
        result = self.query(limit_query, **kwargs)
        while result:
            yield result
            if len(result) < page_size:
                break
            offset += page_size
            limit_query = u"%s LIMIT %s OFFSET %s" % (query, page_size, offset)
            result = self.query(limit_query, **kwargs)
        raise StopIteration()


def main():
    sparql = SPARQLHTTPBackend('202.120.38.146', '8999', '/sparql')
    query = '''
    PREFIX fb: <http://rdf.freebase.com/ns/>
    SELECT DISTINCT ?x
    WHERE {
     ?s fb:type.object.name "Albert Einstein"@EN .
     ?s ?p ?o .
     FILTER regex(?p, "profession") .
     ?o fb:type.object.name ?x .
     FILTER (LANG(?x) = "en") }
    '''
    print sparql.query(query)


if __name__ == '__main__':
    main()

