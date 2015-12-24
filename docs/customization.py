# Adapted from https://hg.python.org/cpython/file/default/Doc/tools/extensions/pyspecific.py .

from sphinx import addnodes
from sphinx.domains.python import PyModulelevel, PyClassmember


class PyCoroutineMixin(object):
    def handle_signature(self, sig, signode):
        ret = super(PyCoroutineMixin, self).handle_signature(sig, signode)
        signode.insert(0, addnodes.desc_annotation('await ', 'await '))
        return ret


class PyAsyncFunction(PyCoroutineMixin, PyModulelevel):
    def run(self):
        self.name = 'py:function'
        return PyModulelevel.run(self)


class PyAsyncMethod(PyCoroutineMixin, PyClassmember):
    def run(self):
        self.name = 'py:method'
        return PyClassmember.run(self)


def setup(app):
    app.add_directive_to_domain('py', 'asyncfunction', PyAsyncFunction)
    app.add_directive_to_domain('py', 'asyncmethod', PyAsyncMethod)
    return {'version': '1.0', 'parallel_read_safe': True}
