Installation
============

Python version
--------------

BuildCompiler currently targets Python 3.10 and newer.

Editable install
----------------

For development or notebook use from a checkout:

.. code-block:: bash

   python -m pip install -e .

Install test dependencies:

.. code-block:: bash

   python -m pip install -e ".[test]"

Optional automation dependencies
--------------------------------

PUDU and Opentrons support are optional. BuildCompiler can emit PUDU-compatible
JSON without importing PUDU. To generate or simulate OT-2 protocols, install the
automation dependencies or use a local PUDU checkout:

.. code-block:: bash

   python -m pip install -e ".[automation,test]"

In the development environment used for the repository examples, PUDU was
available as a sibling checkout:

.. code-block:: text

   /Users/gonzalovidal/Documents/GitHub/PUDU

Read the Docs
-------------

This repository includes ``.readthedocs.yaml``. Read the Docs installs the
package, installs ``docs/requirements.txt``, and builds ``docs/conf.py``.

To build the docs locally:

.. code-block:: bash

   python -m pip install -e .
   python -m pip install -r docs/requirements.txt
   sphinx-build -b html docs docs/_build/html
