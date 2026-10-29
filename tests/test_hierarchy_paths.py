"""Ordered-tree mapping regression: duplicate labels are not lookup keys."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from psyrig import compatible_hierarchy
from asset_survey import check_keys


def joint(name,children=()):return dict(name=name,children=list(children),channels=[])


class HierarchyPathTests(unittest.TestCase):
    def test_duplicate_names_match_only_their_ordered_paths(self):
        a=joint('root',[joint('left',[joint('tip')]),joint('right',[joint('tip')])])
        b=joint('prefix|root',[joint('left',[joint('tip')]),joint('right',[joint('tip')])])
        self.assertTrue(compatible_hierarchy(a,b))
        b['children'].reverse();self.assertFalse(compatible_hierarchy(a,b))

    def test_equal_flat_names_with_different_parentage_are_rejected(self):
        a=joint('root',[joint('bone',[joint('bone')])])
        b=joint('root',[joint('bone'),joint('bone')])
        self.assertFalse(compatible_hierarchy(a,b))

    def test_duplicate_named_targets_cannot_be_swapped(self):
        root=joint('root',[joint('tip'),joint('tip')])
        for j,value in zip(root['children'],([1,2,3],[4,5,6])):
            j['channels']=[dict(type=0,keys=[dict(frame=0,value=value)])]
        g=dict(skins=[dict(joints=[0,1,2])],nodes=[dict(name='root',children=[1,2]),dict(name='tip'),dict(name='tip')],animations=[dict(channels=[dict(sampler=0,target=dict(node=1,path='translation')),dict(sampler=1,target=dict(node=2,path='translation'))],samplers=[dict(input=0,output=1),dict(input=0,output=2)])])
        arrays=[np.array([[0.]]),np.array([[1,2,3.]]),np.array([[4,5,6.]])]
        with patch('asset_survey.read',return_value=(g,lambda i:arrays[i])):
            self.assertEqual(check_keys(None,dict(data=dict(root=root))),2)
            g['animations'][0]['channels'][0]['target']['node']=2
            with self.assertRaisesRegex(ValueError,'wrong indexed joint'):check_keys(None,dict(data=dict(root=root)))


if __name__=='__main__':unittest.main()
