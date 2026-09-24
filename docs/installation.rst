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

Python protocol compilation and structured handoffs are included in the core
package. The ``automation`` extra includes JSON protocol compilation, the
Opentrons simulator and inventory integration:

.. code-block:: bash

   python -m pip install -e ".[automation]"

To run the pinned simulator and equivalence tests, use Python 3.10 and add the
test dependencies:

.. code-block:: bash

   python -m pip install -e ".[test,automation]"

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
