try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

tests_require = ['pytest', 'Sphinx']

long_description = """
Curio is a coroutine-based library for concurrent systems programming.
"""


setup(name="curio",
      description="Curio",
      long_description=long_description,
      license="BSD",
      version="1.5",
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
      python_requires='>= 3.7',
      # This is disabled because it often causes interference with other testing
      # plugins people have written.  Curio doesn't use it for it's own testing.
      # entry_points={"pytest11": ["curio = curio.pytest_plugin"]},
      classifiers=[
          'Programming Language :: Python :: 3',
          "Framework :: Pytest",
      ])
