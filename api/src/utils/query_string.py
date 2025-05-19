import urllib.parse as urllib

unicode = str
DEFAULT_ENCODING = None


def has_variable_name(s):
    """
    Variable name before [
    @param s:
    """
    if s.find("[") > 0:
        return True


def more_than_one_index(s, brackets=2):
    """
    Search for two sets of [] []
    @param s: string to search
    """
    start = 0
    brackets_num = 0
    while start != -1 and brackets_num < brackets:
        start = s.find("[", start)
        if start == -1:
            break
        start = s.find("]", start)
        brackets_num += 1
    if start != -1:
        return True
    return False


def get_key(s):
    """
    Get data between [ and ] remove ' if exist
    @param s: string to process
    """
    start = s.find("[")
    end = s.find("]")
    if start == -1 or end == -1:
        return None
    if s[start + 1] == "'":
        start += 1
    if s[end - 1] == "'":
        end -= 1
    return s[start + 1:end]  # without brackets


def is_number(s):
    """
    Check if s is an int (for indexes in dict)
    @param s: string to check
    """
    if len(s) > 0 and s[0] in ('-', '+'):
        return s[1:].isdigit()
    return s.isdigit()


class MalformedQueryStringError(Exception):
    """
    Query string is malformed, can't parse it :(
    """
    pass


def parser_helper(key, val):
    """
    Helper for parser function
    @param key:
    @param val:
    """
    start_bracket = key.find("[")
    end_bracket = key.find("]")
    pdict = {}
    if has_variable_name(key):  # var['key'][3]
        pdict[key[:key.find("[")]] = parser_helper(key[start_bracket:], val)
    elif more_than_one_index(key):  # ['key'][3]
        newkey = get_key(key)
        newkey = int(newkey) if is_number(newkey) else newkey
        pdict[newkey] = parser_helper(key[end_bracket + 1:], val)
    else:  # key = val or ['key']
        newkey = key
        if start_bracket != -1:  # ['key']
            newkey = get_key(key)
            if newkey is None:
                raise MalformedQueryStringError
        newkey = int(newkey) if is_number(newkey) else newkey
        if key == u'[]':  # val is the array key
            val = int(val) if is_number(val) else val
        if val.lower() in ('null', 'none'):
            val = None
        else:
            val = int(val) if is_number(val) else val
        pdict[newkey] = val
    return pdict


def parse(query_string, unquote=True, normalized=False,  # noqa
          encoding=DEFAULT_ENCODING):  # noqa
    """
    Main parse function
    @param query_string:
    @param unquote: unquote html query string ?
    @param encoding: An optional encoding used to decode the keys and values.
    Defaults to utf-8, which the W3C declares as a default in the W3C
    algorithm for encoding.
    @see http://www.w3.org/TR/html5/forms.html#application/ \
    x-www-form-urlencoded-encoding-algorithm

    @param normalized: parse number key in dict to proper list ?
    """

    mydict = {}
    plist = []
    if query_string == "":
        return mydict

    if isinstance(query_string, bytes):
        query_string = query_string.decode()

    for element in query_string.split("&"):
        try:
            if unquote:
                (var, val) = element.split("=")
                var = urllib.unquote_plus(var)
                val = urllib.unquote_plus(val)
            else:
                (var, val) = element.split("=")
        except ValueError:
            raise MalformedQueryStringError
        if encoding:
            var = var.decode(encoding)
            val = val.decode(encoding)
        plist.append(parser_helper(var, val))
    for di in plist:
        (k, v) = di.popitem()
        tempdict = mydict
        while k in tempdict and type(v) is dict:
            tempdict = tempdict[k]
            (k, v) = v.popitem()
        if k in tempdict and type(tempdict[k]).__name__ == 'list':
            tempdict[k].append(v)
        elif k in tempdict:
            tempdict[k] = [tempdict[k], v]
        else:
            tempdict[k] = v

    if normalized:
        return _normalize(mydict)
    return mydict


def _normalize(d):
    """
    The above parse function generates output of list in dict form
    i.e. {'abc' : {0: 'xyz', 1: 'pqr'}}. This function normalize it and turn
    them into proper data type, i.e. {'abc': ['xyz', 'pqr']}

    Note: if dict has element starts with 10, 11 etc.. this function won't fill
    blanks.
    for eg: {'abc': {10: 'xyz', 12: 'pqr'}} will convert to
    {'abc': ['xyz', 'pqr']}
    """
    newd = {}
    if not isinstance(d, dict):
        return d
    # if dictionary. iterate over each element and append to newd
    for k, v in d.items():
        if isinstance(v, dict):
            first_key = next(iter(v.keys()))
            if isinstance(first_key, int):
                temp_new = []
                for k1, v1 in v.items():
                    temp_new.append(_normalize(v1))
                newd[k] = temp_new
            elif first_key == '':
                newd[k] = v.values()[0]
            else:
                newd[k] = _normalize(v)
        else:
            newd[k] = v
    return newd
