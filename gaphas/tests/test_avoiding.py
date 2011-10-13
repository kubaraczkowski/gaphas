

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


class AvoidLineTestCase(unittest.TestCase):

    def setUp(self):
        self.canvas = AvoidCanvas()
        self.element = AvoidElement()
        self.line = AvoidLine()
        self.canvas.add(self.element)
        self.canvas.add(self.line)
        self.line.handles()[1].pos = (25, 5)
        self.line.request_update()


    def test_handle_placement(self):
        # if line is connected to a shape:
        self.canvas.router.outputInstanceToSVG("test_handle_placement-before.svg")
        self.canvas.connect_item(self.line, self.line.handles()[0],
                self.element, self.element.ports()[0])
        self.line.request_update()

        self.canvas.router.outputInstanceToSVG("test_handle_placement-after.svg")

        # the handle should be placed on the border of the shape
        self.assertEquals([(10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)], self.element._router_shape.polygon)
        self.assertEquals(self.element._router_shape, self.line._router_conns[0].sourceEndpoint)
        self.assertEquals((10., 5.), self.canvas.get_matrix_i2c(self.line).transform_point(*self.line.handles()[0].pos))


# vim:sw=4:et:ai
