try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(name = "curio",
            description="Curio - Concurrent I/O",
            long_description = """
Curio is a library for performing concurrent I/O in Python 3. 
""",
            license="""BSD""",
            version = "0.1",
            author = "David Beazley",
            author_email = "dave@dabeaz.com",
            maintainer = "David Beazley",
            maintainer_email = "dave@dabeaz.com",
            url = "https://github.com/dabeaz/curio",
            packages = ['curio', 'curio.test'],
            classifiers = [
              'Programming Language :: Python :: 3',
              ]
            )
