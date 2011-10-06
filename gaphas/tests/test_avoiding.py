

import unittest

from gaphas.item import Item
from gaphas.avoiding import *
from gaphas.canvas import Canvas
from gaphas.view import View

class AspectTestCase(unittest.TestCase):
    """
    Test aspects for items.
    """

    def setUp(self):
        self.canvas = AvoidCanvas()
        self.view = View(self.canvas)

    def test_point_c2i(self):
        line = AvoidLine()
        line.matrix.translate(20, 40)
        self.canvas.add(line)
        self.assertEquals([(0, 0), (20, 40)], list(line.points_c2i((20, 40), (40, 80))))


# vim:sw=4:et:ai
