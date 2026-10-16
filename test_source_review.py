import copy
import unittest
try:
    from src.source_review import make_proof, require_proof, validate_review
except ImportError:
    from source_review import make_proof, require_proof, validate_review


class SourceReviewTests(unittest.TestCase):
    def fixture(self):
        source = 'The council opened a road in Duzce. Four people were injured in the incident.'
        fields = {'title': 'Düzcede yol açıldı', 'description': 'Belediye yeni yolu açtı'}
        review = {'valid': True, 'reason': 'test fixture only', 'evidence': [
            {'field': key, 'supported': True, 'source_quote': 'The council opened a road in Duzce.'}
            for key in fields]}
        payload = {'fields': fields, 'tts_text': 'Düzcede yol açıldı', 'source': source}
        return source, fields, review, payload

    def test_missing_field_cannot_be_approved_by_one_true_boolean(self):
        source, fields, review, payload = self.fixture()
        review['evidence'].pop()
        with self.assertRaisesRegex(ValueError, 'Every publication field'):
            make_proof(payload, fields, source, review)

    def test_false_empty_invented_duplicate_and_unknown_evidence_is_rejected(self):
        source, fields, review, _ = self.fixture()
        for edit in ({'supported': False}, {'source_quote': ''},
                     {'source_quote': 'The council opened a road in Uskudar.'},
                     {'field': 'description'}, {'field': 'unknown'}):
            bad = copy.deepcopy(review)
            bad['evidence'][0].update(edit)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                validate_review(bad, fields, source)

    def test_text_metadata_tts_source_or_review_changes_invalidate_approval(self):
        source, fields, review, payload = self.fixture()
        proof = make_proof(payload, fields, source, review)
        require_proof(payload, fields, source, review, proof)
        for mutated in (dict(payload, tts_text='different speech'), dict(payload, tags=['new claim']),
                        dict(payload, fields={**fields, 'description': 'Üsküdarda yol açıldı'})):
            with self.subTest(payload=mutated), self.assertRaises(ValueError):
                require_proof(mutated, fields, source, review, proof)
        with self.assertRaises(ValueError):
            require_proof(payload, {**fields, 'title': 'changed title'}, source, review, proof)
        with self.assertRaises(ValueError):
            require_proof(payload, fields, source + ' Source updated.', review, proof)
        with self.assertRaises(ValueError):
            require_proof(payload, fields, source, dict(review, reason='modified decision'), proof)

    def test_old_boolean_only_approval_is_not_reused(self):
        source, fields, review, payload = self.fixture()
        with self.assertRaises(ValueError):
            require_proof(payload, fields, source, review, {'valid': True})

    def test_rejection_always_wins_even_with_complete_evidence(self):
        source, fields, review, _ = self.fixture()
        with self.assertRaises(ValueError):
            validate_review(dict(review, valid=False), fields, source)
