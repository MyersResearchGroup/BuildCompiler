Development
===========

Local checks
------------

Install the package and test dependencies:

.. code-block:: bash

   python -m pip install -e ".[test]"

Run the focused tests for the documented PUDU path:

.. code-block:: bash

   python -m pytest \
       tests/unit/adapters/pudu/test_transformation_json.py \
       tests/unit/adapters/pudu/test_plating_json.py \
       tests/test_buildcompiler_transformation.py

Build docs locally:

.. code-block:: bash

   python -m pip install -r docs/requirements.txt
   sphinx-build -b html docs docs/_build/html

Agent handoff
-------------

Repository-specific agent instructions are in ``AGENTS.md``. Recent handoff
notes for the PUDU integration and notebook artifacts are in
``AGENTS_log.md``.

Read the Docs deployment
------------------------

The repository is configured for Read the Docs with ``.readthedocs.yaml``.
To publish the hosted site:

1. Push this branch to GitHub.
2. Import the GitHub repository in Read the Docs.
3. Select the branch containing ``.readthedocs.yaml``.
4. Trigger a build.

Read the Docs will install the package and docs dependencies, then run Sphinx
against ``docs/conf.py``.
