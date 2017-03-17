try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

tests_require = ['pytest', 'Sphinx']

long_description = """
Curio is a library for performing concurrent I/O with coroutines in Python 3.
"""


setup(name="curio",
      description="Curio - Concurrent I/O",
      long_description=long_description,
      license="BSD",
      version="0.7",
      author="David Beazley",
      author_email="dave@dabeaz.com",
      maintainer="David Beazley",
      maintainer_email="dave@dabeaz.com",
      url="https://github.com/dabeaz/curio",
      packages=['curio'],
      tests_require=tests_require,
      extras_require={
          'test': tests_require,
      },
      classifiers=[
          'Programming Language :: Python :: 3',
      ])
