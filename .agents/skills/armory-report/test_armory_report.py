"""Offline integration tests: python3 -m unittest discover -s .agents/skills/armory-report -p 'test_*.py'."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('generate_armory_report.sh').resolve()
IDS = [651, 652, 653, 654, 332, 333, 334, 731, 68, 67, 1363,
       732, 733, 734, 735, 736, 737, 738, 739, 242, 256, 226, 392, 222]
EMPTY = {'armor': [], 'medical': [], 'temporary': []}
PRICES = {'items': [{'id': i, 'value': {'market_price': 100}} for i in IDS]}


class ArmoryReportTest(unittest.TestCase):
    def run_report(self, inventory=EMPTY, prices=PRICES, curl_exit=0, price_exit=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'bin').mkdir()
            (root / 'generated').mkdir()
            report = root / 'generated/armory-report.md'
            report.write_text('previous valid report')
            for name, payload in [('inventory', inventory), ('prices', prices)]:
                (root / name).write_text(payload if isinstance(payload, str) else json.dumps(payload))
            (root / 'bin/curl').write_text(
                '#!/bin/sh\nprintf "%s\\n" "$*" >> requests\ncat inventory\nexit ' + str(curl_exit) + '\n')
            (root / 'torn').write_text('#!/bin/sh\ncat prices\nexit ' + str(price_exit) + '\n')
            (root / 'bin/curl').chmod(0o755)
            (root / 'torn').chmod(0o755)
            env = {**os.environ, 'TORN_REPO_ROOT': directory, 'TORN_API_KEY': 'test-key',
                   'PATH': str(root / 'bin') + ':' + os.environ['PATH'], 'LC_ALL': 'C'}
            result = subprocess.run(['bash', str(SCRIPT)], env=env, capture_output=True, text=True)
            requests = (root / 'requests').read_text().splitlines()
            self.assertEqual(len(requests), 1)
            self.assertIn('selections=armor,medical,temporary', requests[0])
            self.assertEqual(list((root / 'generated').glob('.armory-report.*')), [])
            return result, report.read_text()

    def test_empty_inventory(self):
        result, report = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Total units needed: 8521', result.stdout)
        self.assertIn('Total cost: $852100', result.stdout)
        self.assertIn('Armory Check Report', report)

    def test_stock_and_loans(self):
        inventory = copy.deepcopy(EMPTY)
        inventory['armor'] = [{'name': 'Combat Boots', 'quantity': 5, 'available': 2, 'loaned': 3}]
        inventory['medical'] = [{'name': 'Empty Blood Bag', 'quantity': 300}]
        inventory['temporary'] = [{'name': 'HEG', 'quantity': 1000, 'available': 900, 'loaned': 100}]
        result, report = self.run_report(inventory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Total units needed: 7319', result.stdout)
        self.assertIn('Total cost: $731900', result.stdout)
        self.assertIn(' | 2 | 3 | 1 | ', report)
        self.assertIn(' | 900 | 100 | 100 | ', report)

    def test_failures_preserve_report(self):
        bad_stock = copy.deepcopy(EMPTY)
        bad_stock['armor'] = [{'name': 'Combat Boots', 'quantity': 3}]
        cases = [dict(curl_exit=22), dict(price_exit=1),
                 dict(inventory={'error': {'code': 5}}), dict(prices={'error': {'code': 5}}),
                 dict(inventory='not json'), dict(prices='not json'),
                 dict(inventory={}), dict(inventory={**EMPTY, 'armor': None}),
                 dict(inventory=bad_stock), dict(prices={'items': PRICES['items'][1:]})]
        for value in [None, 0, -1, '100', 1.5]:
            prices = copy.deepcopy(PRICES)
            prices['items'][0]['value']['market_price'] = value
            cases.append(dict(prices=prices))
        for case in cases:
            with self.subTest(case=case):
                result, report = self.run_report(**case)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(report, 'previous valid report')
                self.assertNotIn('Report generated', result.stdout)


if __name__ == '__main__':
    unittest.main()
