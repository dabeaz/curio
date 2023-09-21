# Adapted from https://hg.python.org/cpython/file/default/Doc/tools/extensions/pyspecific.py .

from sphinx import addnodes, __version__

if tuple(map(int,__version__.split('.'))) >= (4, 0, 0):
    from sphinx.domains.python import PyAttribute, PyFunction
else:
    from sphinx.domains.python import PyModulelevel, PyClassmember
    PyFunction, PyAttribute = PyModulelevel, PyClassmember


class PyCoroutineMixin(object):

    def handle_signature(self, sig, signode):
        ret = super(PyCoroutineMixin, self).handle_signature(sig, signode)
        signode.insert(0, addnodes.desc_annotation('await ', 'await '))
        return ret


class PyAsyncFunction(PyCoroutineMixin, PyFunction):

    def run(self):
        self.name = 'py:function'
        return PyFunction.run(self)


class PyAsyncMethod(PyCoroutineMixin, PyAttribute):

    def run(self):
        self.name = 'py:method'
        return PyAttribute.run(self)


def setup(app):
    app.add_directive_to_domain('py', 'asyncfunction', PyAsyncFunction)
    app.add_directive_to_domain('py', 'asyncmethod', PyAsyncMethod)
    return {'version': '1.0', 'parallel_read_safe': True}
