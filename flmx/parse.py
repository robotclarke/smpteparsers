from datetime import datetime
from lxml.etree import XMLSyntaxError
import logging, requests, json, os

from facility import FacilityParser
from sitelist import SiteListParser
from error import FlmxParseError, FlmxPartialError

# setup logger - __ to ensure it's not accessible from outside
_logger = logging.getLogger(__name__)

# FLM-x shortcut parser
def parse(sitelist_url, username=u'', password=u'', last_ran=datetime.min, failures_file=u'failures.json'):
    """See __init__.py's parse method for documentation
    """

    sp = get_sitelist(sitelist_url, username=username, password=password)
    sites = sp.get_sites(last_ran)

    facilities = {}

    with open(os.path.join(os.path.dirname(__file__), failures_file), u'w+') as f:
        try:
            failures = json.load(f)
        # If failures.json is not a valid json file then assume no failures
        except ValueError:
            _logger.warning(failures_file + ' could not be opened, the file will be cleared')
            failures = {}
        prev_failures = failures[sitelist_url] if sitelist_url in failures else []
        new_failures = []

        # Ensure we don't check the failures twice
        for site in set(prev_failures) | set(sites.keys()):
            try:
                fp = get_facility(site, sitelist_url, username=username, password=password)
            except (requests.exceptions.RequestException, FlmxParseError, FlmxPartialError, XMLSyntaxError) as e:
                _logger.warning(str(e))
                new_failures.append(site)
            else:
                facilities[site] = fp

        failures[sitelist_url] = new_failures
        json.dump(failures, f)

    _logger.info('returning '+ str(len(facilities)) + ' facilities for ' + sitelist_url) 
    return facilities

def request(url, username=u'', password=u''):
    res = None
    if username and password:
        res = requests.get(url, auth=(username, password), stream=True)
    else:
        res = requests.get(url, stream=True)

    return res

def get_sitelist(sitelist_url, username=u'', password=u''):
    # Get sitelist from URL using authentication if necessary
    res = request(sitelist_url, username=username, password=password)

    # Raise the HTTPError from requests if there was a problem
    if res.status_code != requests.codes.ok:
        # This reraises a HTTPError stored by the requests API
        _logger.warning('Could not access ' + sitelist_url + ': HTTP Response code ' + str(res.status_code))
        res.raise_for_status()

    # response.text auto-converts the response body to a unicode string.
    # This is not compatible with lxml validation so we have to get the raw HTTPResponse,
    # read it, and then wrap it in StringIO so the validator can read it again.
    # If efficiency becomes a problem this is an obvious bottleneck.
    return SiteListParser(res.raw)

def get_facility(facility, facility_url, username=u'', password=u''):
    # Ensure facility URL ends in a /
    if facility_url[-1] != u'/':
        facility_url += u'/'

    res = request(facility_url + facility, username=username, password=password)

    # If there's a problem with obtaining an FLM
    if res.status_code != 200:
        # This reraises a HTTPError stored by the requests API
        _logger.warning('Could not access ' + facility_url + ': HTTP Response code ' + res.status_code)
        res.raise_for_status()

    try:
        _logger.info('Parsing FLM at ' + facility)
        return FacilityParser(res.raw)
    except FlmxParseError as e:
        raise FlmxParseError(u"Problem parsing FLM at " + facility + u". Error message: " + e.msg)
    except XMLSyntaxError, e:
        msg = u"FLM at " + facility + u" failed validation.  Error message: " + e.msg
        _logger.warning(msg)
        raise XMLSyntaxError(msg)
