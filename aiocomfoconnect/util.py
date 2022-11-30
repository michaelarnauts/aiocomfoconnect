""" Helper methods. """

def bytestring(arr):
    """ Join an array of bytes into a bytestring. Unlike `bytes()`, this method supports a mixed array with integers and bytes. """
    return b''.join([i if isinstance(i, bytes) else bytes([i]) for i in arr])

def version_decode(version):
    """Decode the version number to a string."""
    v1 = (version >> 30) & 3
    v2 = (version >> 20) & 1023
    v3 = (version >> 10) & 1023
    v4 = version & 1023

    if v1 == 0:
        v1 = "U"
    elif v1 == 1:
        v1 = "D"
    elif v1 == 2:
        v1 = "P"
    elif v1 == 3:
        v1 = "R"

    return "%s%s.%s.%s" % (v1, v2, v3, v4)
