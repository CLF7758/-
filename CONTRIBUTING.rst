Prism — Notes For Developers
=============================

Prism is written in Python and PyQt6.


Developing
----------

Optional step: Use pyenv to create a virtual environment::

  pyenv install -v 3.11
  pyenv virtualenv 3.11 prism

Once the vitrual environment is set up, you can enter it with::

  pyenv activate prism


Clone the repository and install prism and its dependencies::

  git clone https://github.com/rbreu/prism.git
  cd prism
  pip install -e .

Install additional development requirements::

  pip install -r requirements/dev.txt

Run unittests with::

  pytest --cov .

This will also generate a coverage report:  ``htmlcov/index.html``.

Run codechecks with::

  flake8 .

Beeref files are sqlite databases, so they can be inspected with any sqlite browser.

For debugging options, run::

  prism --help


Building the app
----------------

To build the app, run::

  pyinstaller Prism.spec

You will find the generated executable in the folder ``dist``.


Website etc.
------------

The Python version badge in the README is generated with pybadges::

  python -m pybadges --left-text=Python --right-text="3.9 | 3.10 | 3.11" > images/python_version_badge.svg

The `website <https://rbreu.github.io/prism/>`_ is hosted via Github pages from the gh-pages branch. You can run it locally if you have Ruby and bundler installed::

  bundle install
  bundle exec jekyll serve --baseurl ""
