#!/usr/bin/python3
class OttoError(Exception):
    internal_error = False

    def __init__(self, msg=None, **kwds):
        BaseException.__init__(self)
        for key, value in kwds.items():
            setattr(self, key, value)
        self._msg = msg

    def _format(self):
        s = getattr(self, '_msg', None)
        if s is not None:
            return s

        try:
            fmt = getattr(self, "_fmt", None)
            if fmt:
                d = dict(self.__dict__)
                s = fmt % d
                return s
        except Exception as e:
            pass
        else:
            e = None
        return 'Unprintable exception %s: dict=%r, fmt=%r, error=%r' \
            % (self.__class__.__name__,
               self.__dict__,
               getattr(self, '_fmt', None),
               e)

    def __str__(self):
        s = self._format()
        return s

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, str(self))

    @property
    def errorcode(self):
        return self._errorcode if hasattr(self, "_errorcode") else 255

class FileNotFound(OttoError):
    _fmt = "The file '%(filename)s' could not be found"
    _errorcode = 5
    def __init__(self, filename, msg=None):
        OttoError.__init__(self, filename=filename, msg=msg)
        #self.filename = filename

class InvalidArgument(OttoError):
    _msg = "InvalidArgument"
    def __init__(self, msg):
        self.errorcode=2

try:
    raise FileNotFound("MyFile", "This is a bug")
except FileNotFound as exc:
    print("FNF {} {}".format(exc, exc.errorcode))
