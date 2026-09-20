import contextlib
import copy
import csv
import gzip
import io
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import insider_buying as screen


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'samples' / '2026-09-18'


def snapshot(name='examples'):
    with gzip.open(SAMPLES / name / 'snapshot.json.gz', 'rt') as stream:
        return json.load(stream)


class ScreenerTests(unittest.TestCase):
    def test_saved_reports_reproduce_exactly(self):
        for name, threshold, plans, leadership, count in [
            ('baseline', '100000', False, False, 0),
            ('examples', '100000', False, False, 14),
            ('leadership', '100000', True, True, 9),
            ('all-purchases', '0', False, False, 34),
        ]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                args = SimpleNamespace(out=Path(tmp), min_usd=Decimal(threshold),
                                       exclude_plans=plans, leadership_only=leadership)
                with contextlib.redirect_stdout(io.StringIO()):
                    screen.write_report(snapshot(name), args)
                for file in ['report.md', 'candidates.csv']:
                    self.assertEqual((args.out / file).read_bytes(),
                                     (SAMPLES / name / file).read_bytes())
                with (args.out / 'candidates.csv').open() as stream:
                    self.assertEqual(len(list(csv.DictReader(stream))), count)

    def test_money_preserves_unknown_and_decimal_precision(self):
        self.assertIsNone(screen.money(None))
        self.assertEqual(screen.money('24997.39'), Decimal('24997.39'))

    def test_threshold_nulls_plan_and_role_filters(self):
        base = copy.deepcopy(screen.window_events(snapshot())[0])
        base.update(transaction_code='P', total_value_usd='100000',
                    stake_change_pct=None, is_officer=True, is_director=False,
                    is_ten_percent_owner=True, is_10b5_1=False)
        self.assertEqual(screen.select([base], Decimal('100000'), True, True), [base])
        for changes in [
            {'total_value_usd': '99999.99'}, {'total_value_usd': None},
            {'transaction_code': 'S'}, {'is_10b5_1': True},
            {'is_officer': False, 'is_director': False},
        ]:
            with self.subTest(changes=changes):
                self.assertEqual(screen.select([{**base, **changes}],
                                               Decimal('100000'), True, True), [])

    def test_date_boundaries_and_share_class_deduplication(self):
        data = snapshot()
        event = data['responses'][0]['body']['chart_events'][0]
        entries = [{**event, 'news_uid': str(i), 'transaction_date': day}
                   for i, day in enumerate(['2026-08-19', '2026-08-20',
                                            '2026-09-18', '2026-09-19'])]
        data['responses'] = [
            {'ticker': ticker, 'body': {'chart_events': entries, 'events': entries}}
            for ticker in ['CLASS-A', 'CLASS-B']
        ]
        events = screen.window_events(data)
        self.assertEqual([e['news_uid'] for e in events], ['1', '2'])
        self.assertTrue(all(e['tickers'] == ['CLASS-A', 'CLASS-B'] for e in events))

    def test_replay_needs_no_key_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'result'
            argv = ['insider_buying.py', '--replay',
                    str(SAMPLES / 'examples' / 'snapshot.json.gz'), '--out', str(out)]
            with patch.object(sys, 'argv', argv), patch.dict('os.environ', {}, clear=True), \
                    patch.object(screen, 'fetch', side_effect=AssertionError('network call')), \
                    contextlib.redirect_stdout(io.StringIO()):
                screen.main()
            self.assertEqual((out / 'candidates.csv').read_bytes(),
                             (SAMPLES / 'examples' / 'candidates.csv').read_bytes())

    def test_incomplete_snapshot_produces_no_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = snapshot()
            data['complete'] = False
            source = Path(tmp) / 'incomplete.json'
            source.write_text(json.dumps(data))
            out = Path(tmp) / 'result'
            result = subprocess.run([sys.executable, str(ROOT / 'insider_buying.py'),
                                     '--replay', str(source), '--out', str(out)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('snapshot is incomplete', result.stderr)
            self.assertFalse((out / 'report.md').exists())

    def test_http_failure_keeps_successful_responses(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'result'
            argv = ['insider_buying.py', 'TENX', 'XBP', '--out', str(out)]
            with patch.object(sys, 'argv', argv), \
                    patch.dict('os.environ', {'ALPHAI_API_KEY': 'test-only'}), \
                    patch.object(screen.time, 'sleep'), \
                    patch.object(screen, 'fetch', side_effect=[snapshot()['responses'][0],
                                                              SystemExit('HTTP 429')]), \
                    contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    screen.main()
            saved = json.loads((out / 'snapshot.json').read_text())
            self.assertFalse(saved['complete'])
            self.assertEqual(len(saved['responses']), 1)
            self.assertFalse((out / 'report.md').exists())
            self.assertNotIn('test-only', (out / 'snapshot.json').read_text())


class SecEvidenceTests(unittest.TestCase):
    def rows(self, uid):
        return ET.parse(SAMPLES / 'filings' / f'{uid}.xml').getroot().findall(
            './/nonDerivativeTransaction')

    def test_single_row_examples_against_source_xml(self):
        for uid, value, pct in [
            ('84e12a4ec11d2122', '101760', '2330.7'),
            ('c7b56ce44532b3ac', '500000', '1.2'),
            ('5be80fe447c551ef', '579997.18', None),
        ]:
            with self.subTest(uid=uid):
                row, = self.rows(uid)
                shares = Decimal(row.findtext('transactionAmounts/transactionShares/value'))
                price = Decimal(row.findtext('transactionAmounts/transactionPricePerShare/value'))
                after = Decimal(row.findtext('postTransactionAmounts/sharesOwnedFollowingTransaction/value'))
                before = after - shares
                computed_pct = ((shares / before * 100).quantize(Decimal('0.1'))
                                if before else None)
                self.assertEqual(shares * price, Decimal(value))
                self.assertEqual(computed_pct, Decimal(pct) if pct is not None else None)

    def test_alp_ownership_groups_against_source_xml(self):
        groups = {}
        for row in self.rows('68a38ff9aa5dd705'):
            self.assertEqual(row.findtext('transactionCoding/transactionCode'), 'P')
            form = row.findtext('ownershipNature/directOrIndirectOwnership/value')
            shares = Decimal(row.findtext('transactionAmounts/transactionShares/value'))
            price = Decimal(row.findtext('transactionAmounts/transactionPricePerShare/value'))
            groups.setdefault(form, []).append((shares, shares * price))
        for form, count, shares, value in [('D', 3, '16647', '67856.30'),
                                          ('I', 2, '9900', '41131.07')]:
            self.assertEqual(len(groups[form]), count)
            self.assertEqual(sum(s for s, _ in groups[form]), Decimal(shares))
            self.assertEqual(sum(v for _, v in groups[form]).quantize(Decimal('0.01')),
                             Decimal(value))


if __name__ == '__main__':
    unittest.main()
