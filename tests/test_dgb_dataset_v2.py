"""Regression mutations for DGB V2 generated reference data.

Only tests strict deterministic data/text matching, not engineering feasibility.
"""
from __future__ import annotations
import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from validate_dgb_dataset import offline  # noqa: E402

class GeneratedDatasetContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d=ROOT/'DGB_Design_Dataset'
        cls.cases=[json.loads(s) for s in (d/'data/design_cases.jsonl').read_text().splitlines()]
        cls.requests=[json.loads(s) for s in (d/'data/user_requests.jsonl').read_text().splitlines()]
        cls.schema=json.loads((d/'schema/DGBCase_v2.schema.json').read_text())

    def test_baseline(self):
        self.assertEqual(offline(self.cases,self.requests,self.schema),(80,80))

    def bad_request(self,idx,mutator):
        b=copy.deepcopy(self.requests);mutator(b[idx]);
        with self.assertRaises(ValueError):offline(self.cases,b,self.schema)

    def bad_case(self,idx,mutator):
        a=copy.deepcopy(self.cases);mutator(a[idx]);
        with self.assertRaises(ValueError):offline(a,self.requests,self.schema)

    def test_radial_load_token_overlapping_number(self):
        self.bad_request(0,lambda r:r.__setitem__('text',r['text'].replace('Fr=300 N','Fr=3000 N')))

    def test_speed_substring(self):
        self.bad_request(0,lambda r:r.__setitem__('text',r['text'].replace('15000 rpm','150000 rpm')))

    def test_reverse_life_inequality(self):
        self.bad_request(0,lambda r:r.__setitem__('text',r['text'].replace('不低于20000小时','不高于20000小时')))

    def test_constraint_unit_wrong(self):
        self.bad_request(0,lambda r:r.__setitem__('text',r['text'].replace('20000小时','20000 W')))

    def test_lock_Z_removed_from_free_list(self):
        i=7;v=self.requests[i]['text'];self.assertIn('实际待优化变量',v)
        self.assertNotIn('待优化变量为Dw、Z、Dpw',v)
        self.bad_request(i,lambda r:r.__setitem__('text',r['text'].replace('待优化变量为','待优化变量为Z、')))

    def test_power_hard_becomes_soft(self):
        i=2;self.assertIn('摩擦功耗必须不超过',self.requests[i]['text'])
        self.bad_request(i,lambda r:r.__setitem__('text',r['text'].replace('摩擦功耗必须不超过','摩擦功耗希望不超过')))

    def test_ambient_mutation(self):
        i=2;self.assertIn('环境参考温度',self.requests[i]['text'])
        self.bad_request(i,lambda r:r.__setitem__('text',r['text'].replace('环境参考温度','环境参考温度999')))

    def test_incorrect_reference_ratio(self):
        self.bad_case(0,lambda r:r['quality']['reference_screen'].__setitem__('life_min_C_ratio',0.001))

    def test_wrong_ref_model(self):
        self.bad_case(0,lambda r:r['bearing'].__setitem__('reference_model','6305'))

    def test_hidden_constraint(self):
        self.bad_case(0,lambda r:r['requirements']['constraints'][0].__setitem__('value',50000))

    def test_user_request_missing(self):
        b=copy.deepcopy(self.requests);b.pop(0)
        with self.assertRaises(ValueError):offline(self.cases,b,self.schema)

    def test_default_no_false_engineering_approval(self):
        for r in self.cases:
            self.assertFalse(r['quality']['engineering_reviewed'])
            self.assertFalse(r['quality']['solver_verified'])

if __name__=='__main__':unittest.main()
