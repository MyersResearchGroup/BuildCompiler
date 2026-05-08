import inspect
import os
import sys
import unittest
from unittest.mock import patch

import sbol2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.constants import RESTRICTION_ENZYME


class TestBuildCompilerLocalIndexing(unittest.TestCase):
    def test_constructor_signature_unchanged(self):
        params = list(inspect.signature(BuildCompiler.__init__).parameters.keys())
        self.assertEqual(
            params,
            ['self', 'collections', 'sbh_registry', 'auth_token', 'sbol_doc'],
        )

    def test_from_local_documents_indexes_without_partshop(self):
        collection_doc = sbol2.Document()
        enzyme = sbol2.ComponentDefinition('BsaI')
        enzyme.types = [sbol2.BIOPAX_PROTEIN]
        enzyme.roles = [RESTRICTION_ENZYME]
        collection_doc.add(enzyme)
        implementation = sbol2.Implementation('BsaI_impl')
        implementation.built = enzyme.identity
        collection_doc.add(implementation)

        with patch('sbol2.PartShop', side_effect=AssertionError('PartShop should not be constructed in local mode')):
            compiler = BuildCompiler.from_local_documents([collection_doc])

        self.assertIsNone(compiler.sbh)
        self.assertEqual(len(compiler.indexed_plasmids), 0)
        self.assertEqual(len(compiler.indexed_backbones), 0)
        self.assertEqual(len(compiler.restriction_enzyme_implementations), 1)
        self.assertIsInstance(compiler.restriction_enzyme_implementations, list)
        self.assertIsInstance(compiler.ligase_implementations, list)

    def test_local_mode_raises_when_reference_missing(self):
        doc = sbol2.Document()
        strain = sbol2.ModuleDefinition('strain_missing_ref')
        strain.roles = ['https://identifiers.org/ncit/NCIT:C14419']
        fc = strain.functionalComponents.create('plasmid_ref')
        fc.definition = 'https://example.org/missing_plasmid/1'
        doc.add(strain)

        with self.assertRaises(ValueError) as ctx:
            BuildCompiler.from_local_documents([doc])

        self.assertIn('Local mode does not pull from SynBioHub', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
