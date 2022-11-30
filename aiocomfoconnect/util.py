""" Helper methods. """

def bytestring(arr):
    """ Join an array of bytes into a bytestring. Unlike `bytes()`, this method supports a mixed array with integers and bytes. """
    return b''.join([i if isinstance(i, bytes) else bytes([i]) for i in arr])
