import inspect
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import sbol2

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from buildcompiler.buildcompiler import BuildCompiler
from buildcompiler.constants import LIGASE, RESTRICTION_ENZYME


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


    def test_from_local_documents_does_not_reindex_prior_documents(self):
        restriction_doc = sbol2.Document()
        enzyme = sbol2.ComponentDefinition('BsaI')
        enzyme.types = [sbol2.BIOPAX_PROTEIN]
        enzyme.roles = [RESTRICTION_ENZYME]
        restriction_doc.add(enzyme)
        restriction_impl = sbol2.Implementation('BsaI_impl')
        restriction_impl.built = enzyme.identity
        restriction_doc.add(restriction_impl)

        ligase_doc = sbol2.Document()
        ligase = sbol2.ComponentDefinition('T4Ligase')
        ligase.types = [sbol2.BIOPAX_PROTEIN]
        ligase.roles = [LIGASE]
        ligase_doc.add(ligase)
        ligase_impl = sbol2.Implementation('T4Ligase_impl')
        ligase_impl.built = ligase.identity
        ligase_doc.add(ligase_impl)

        compiler = BuildCompiler.from_local_documents([restriction_doc, ligase_doc])

        self.assertEqual(len(compiler.restriction_enzyme_implementations), 1)
        self.assertEqual(len(compiler.ligase_implementations), 1)

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




class TestBuildCompilerCollectionIndexing(unittest.TestCase):
    def _make_compiler_without_init(self):
        compiler = BuildCompiler.__new__(BuildCompiler)
        compiler.sbh = MagicMock()
        compiler.sbol_doc = sbol2.Document()
        compiler.indexed_plasmids = []
        compiler.indexed_backbones = []
        compiler.restriction_enzyme_implementations = []
        compiler.ligase_implementations = []
        return compiler

    def test_index_sbol_document_local_does_not_pull(self):
        compiler = self._make_compiler_without_init()

        enzyme = sbol2.ComponentDefinition('BsaI_local')
        enzyme.types = [sbol2.BIOPAX_PROTEIN]
        enzyme.roles = [RESTRICTION_ENZYME]
        compiler.sbol_doc.add(enzyme)
        implementation = sbol2.Implementation('BsaI_local_impl')
        implementation.built = enzyme.identity
        compiler.sbol_doc.add(implementation)

        compiler.index_sbol_document(compiler.sbol_doc, source='local')

        compiler.sbh.pull.assert_not_called()
        self.assertEqual(len(compiler.restriction_enzyme_implementations), 1)

    def test_index_collections_pulls_then_indexes(self):
        compiler = self._make_compiler_without_init()
        call_order = []

        def fake_pull(uris):
            call_order.append('pull')
            return compiler.sbol_doc

        def fake_index(doc, source='local'):
            call_order.append(f'index:{source}')

        compiler.pull_collection_uris = fake_pull
        compiler.index_sbol_document = fake_index

        compiler._index_collections(['https://example.org/collection'])

        self.assertEqual(call_order, ['pull', 'index:synbiohub'])

    def test_pull_failure_has_uri_context(self):
        compiler = self._make_compiler_without_init()
        compiler.sbh.pull.side_effect = ValueError('network timeout')

        with self.assertRaises(RuntimeError) as ctx:
            compiler.pull_collection_uris(['https://example.org/fail'])

        self.assertIn('Failed to pull collection URI: https://example.org/fail', str(ctx.exception))

    def test_indexing_failure_is_distinct_from_pull_failure(self):
        compiler = self._make_compiler_without_init()
        bad_doc = sbol2.Document()
        bad_impl = sbol2.Implementation('impl_missing_built')
        bad_doc.add(bad_impl)

        with self.assertRaises(Exception) as ctx:
            compiler.index_sbol_document(bad_doc, source='local')

        self.assertNotIn('Failed to pull collection URI', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
