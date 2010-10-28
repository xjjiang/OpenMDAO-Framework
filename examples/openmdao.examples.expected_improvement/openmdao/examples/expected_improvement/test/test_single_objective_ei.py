"""
Test for single criteria EI example.
"""
import os
import unittest
import random
from math import sqrt

from numpy import random as numpy_random
from numpy import pi

from pyevolve import Selectors

from openmdao.main.api import set_as_top
from openmdao.examples.expected_improvement.single_objective_ei import Analysis, Iterator
from openmdao.lib.doegenerators.full_factorial import FullFactorial
from openmdao.lib.caserecorders.dbcaserecorder import case_db_to_dict


class SingleObjectiveEITest(unittest.TestCase):
    """Test to make sure the EI sample problem works as it should"""
    
    def test_EI(self): 
        # pyevolve does some caching that causes failures during our
        # complete unit tests due to stale values in the cache attributes
        # below, so reset them here
        Selectors.GRankSelector.cachePopID = None
        Selectors.GRankSelector.cacheCount = None
        Selectors.GRouletteWheel.cachePopID = None
        Selectors.GRouletteWheel.cacheWheel = None

        random.seed(10)
        numpy_random.seed(10)

        analysis = Analysis()
        set_as_top(analysis)
        analysis.DOE_trainer.DOEgenerator = FullFactorial(num_levels=4)
        analysis.iter.iterations = 1
        analysis.run()
        # This test looks for the presence of at least one point close to
        # each optimum.
        
        #print analysis.EI.EI
        #print analysis.branin_meta_model.x
        #print analysis.branin_meta_model.y
        
        self.assertAlmostEqual(analysis.branin_meta_model.x,8.0,1)
        self.assertAlmostEqual(analysis.branin_meta_model.y,1.8,1)
        
if __name__=="__main__": #pragma: no cover
    unittest.main()



