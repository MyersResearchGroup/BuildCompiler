BuildCompiler
=============

BuildCompiler compiles SBOL designs into practical synthetic biology build
workflows. It indexes available parts, plasmids, backbones, and reagents, then
plans the build steps needed to produce constructs through domestication,
MoClo assembly, transformation, and plating.

The repository currently exposes two useful layers:

* A legacy, artifact-producing compiler in :mod:`buildcompiler.buildcompiler`
  that is used by the offline notebooks and PUDU examples.
* A newer modular API in :mod:`buildcompiler.api`, :mod:`buildcompiler.stages`,
  :mod:`buildcompiler.planning`, and :mod:`buildcompiler.execution`.

The examples in this documentation focus on offline, reproducible workflows
using the SBOL fixture collections in ``tests/test_files``.

Core workflow
-------------

.. code-block:: text

   SBOL design + local SBOL collections
      -> BuildCompiler inventory/indexing
      -> domestication / assembly level 1 / assembly level 2
      -> transformation
      -> plating
      -> SBOL artifacts + PUDU JSON + optional OT-2 protocols

Representative use cases
------------------------

* Run a level-1 MoClo assembly from a local abstract design.
* Generate PUDU-compatible assembly JSON for OT-2 protocol generation.
* Transform an assembled plasmid into a chassis strain.
* Simulate the PUDU assembly, transformation, and plating protocol chain.
* Run a full build that can trigger upstream stages when inputs are missing.

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   installation
   quickstart
   examples/offline_lvl1
   examples/transformation_pudu
   examples/full_build
   notebooks

.. toctree::
   :hidden:

   Tutorials

.. toctree::
   :maxdepth: 2
   :caption: Reference

   API_Reference
   development
