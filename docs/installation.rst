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

Native protocol compilation and PUDU-compatible JSON generation are included in
the core package. To run the pinned simulator or equivalence tests, use Python
3.10 and install:

.. code-block:: bash

   python -m pip install -e ".[simulation,test]"

The equivalence suite additionally needs a PUDU reference checkout, as described
in ``tests/automation/README.md``. Generated native scripts do not need PUDU.
See :doc:`protocols` for compilation, artifact writing and handoffs.

Read the Docs
-------------

This repository includes ``.readthedocs.yaml``. Read the Docs installs the
package, installs ``docs/requirements.txt``, and builds ``docs/conf.py``.

To build the docs locally:

.. code-block:: bash

   python -m pip install -e .
   python -m pip install -r docs/requirements.txt
   sphinx-build -b html docs docs/_build/html
