"""
Elements with support for libavoid, the automatic line router.
"""

import logging
from math import atan2

from gaphas import Canvas
from gaphas.geometry import Rectangle, distance_line_point, distance_rectangle_point
from gaphas.item import Item
from gaphas.connector import Handle, PolygonPort
from gaphas.aspect import HandleInMotion, ItemHandleInMotion, InMotion, Connector, ConnectionSink
from gaphas.segment import Segment
from state import observed, reversible_pair, reversible_property
from gaphas.solver import VERY_STRONG

import libavoid

class AvoidSolver(object):

    def __init__(self):
        #self.router = libavoid.Router(libavoid.ORTHOGONAL_ROUTING)
        self.router = libavoid.Router(libavoid.POLY_LINE_ROUTING)
        #self.router.setRoutingPenalty(libavoid.SEGMENT_PENALTY, 40)
        #self.router.setRoutingPenalty(libavoid.ANGLE_PENALTY, 400)
        #self.router.setRoutingPenalty(libavoid.CROSSING_PENALTY, 4000)
        #self.router.setRoutingPenalty(libavoid.FIXED_SHARED_PATH_PENALTY, 8000)
        #self.router.setRoutingPenalty(libavoid.PORT_DIRECTION_PENALTY, 4000)
        #self.router.setOrthogonalNudgeDistance(14)

    def request_resolve(self):
        pass

    def solve(self):
        self.router.processTransaction()

    # allow to make the right kind of constraint


class AvoidCanvas(Canvas):

    def __init__(self):
        super(AvoidCanvas, self).__init__()
        self._solver = AvoidSolver()

    @property
    def router(self):
        return self._solver.router

    def update_matrix(self, item, parent=None):
        super(AvoidCanvas, self).update_matrix(item, parent)
        try:
            matrix_updated = item.matrix_updated
        except AttributeError:
            pass
        else:
            matrix_updated()
 
    # Set constraints by setting the connection end points

    @observed
    def connect_item(self, item, handle, connected, port, constraint=None, callback=None):
        if self.get_connection(handle):
            raise ConnectionError('Handle %r of item %r is already connected' % (handle, item))

        self._connections.insert(item, handle, connected, port, constraint, callback)

        if handle is item.handles()[0]:
            item._router_shape.setSourceEndPoint(connected._router_shape)
        else:
            item._router_shape.setDestEndPoint(connected._router_shape)


    @observed
    def _disconnect_item(self, item, handle, connected, port, constraint, callback):
        """
        Perform the real disconnect.
        """
        # Same arguments as connect_item, makes reverser easy
        if handle is item.handles()[0]:
            print 'Set shape on head'
            item._router_shape.setSourceEndPoint(None)
        else:
            print 'Set shape on tail'
            item._router_shape.setDestEndPoint(None)

        if callback:
            callback()

        self._connections.delete(item, handle, connected, port, constraint, callback)

    reversible_pair(connect_item, _disconnect_item)


# Make this a constraint-less AvoidElement
class AvoidElementMixin(object):
    """Box with an example connection protocol.
    """

    def setup_canvas(self):
        super(AvoidElementMixin, self).setup_canvas()
        self._router_shape = libavoid.ShapeRef(self.canvas.router, self.outline())

    def teardown_canvas(self):
        self.canvas.router.deleteShape(self._router_shape)
        super(AvoidElementMixin, self).teardown_canvas()

    def pre_update(self):
        i2c = self.canvas.get_matrix_i2c(self)
        coutline = map(lambda xy: i2c.transform_point(*xy), self.outline())
        self.canvas.router.moveShape(self._router_shape, coutline)

    def outline(self):
        h = self.handles()
        m = 0
        r = Rectangle(h[0].pos.x, h[0].pos.y, x1=h[2].pos.x, y1=h[2].pos.y)
        r.expand(5)
        print r
        xMin, yMin = r.x, r.y
        xMax, yMax = r.x1, r.y1
        return ((xMax, yMin), (xMax, yMax), (xMin, yMax), (xMin, yMin))


from gaphas.item import NW, NE, SE, SW

class AvoidElement(Item):
    """
    An Element has 4 handles (for a start)::

     NW +---+ NE
        |   |
     SW +---+ SE
    """

    def __init__(self, width=10, height=10):
        super(AvoidElement, self).__init__()
        self._handles = [ h(strength=VERY_STRONG) for h in [Handle]*4 ]

        self._min_width = width
        self._min_height = height
        # set width/height when minimal size constraints exist
        self.width = width
        self.height = height

        self._ports.append(PolygonPort())


    def setup_canvas(self):
        """
        Called when the canvas is set for the item.
        This method can be used to create constraints.
        """
        super(AvoidElement, self).setup_canvas()

        self._router_shape = libavoid.ShapeRef(self.canvas.router, self.outline())

    def teardown_canvas(self):
        """
        Called when the canvas is unset for the item.
        This method can be used to dispose constraints.
        """
        self.canvas.router.deleteShape(self._router_shape)
        super(AvoidElement, self).teardown_canvas()


    def _set_width(self, width):
        """
        >>> b=AvoidElement()
        >>> b.width = 20
        >>> b.width
        20.0
        >>> b._handles[NW].pos.x
        Variable(0, 40)
        >>> b._handles[SE].pos.x
        Variable(20, 40)
        """
        if width < self.min_width:
            width = self.min_width
        h = self._handles
        h[NE].pos.x = h[SE].pos.x = h[NW].pos.x + width


    def _get_width(self):
        """
        Width of the box, calculated as the distance from the left and
        right handle.
        """
        h = self._handles
        return float(h[NE].pos.x) - float(h[NW].pos.x)

    width = property(_get_width, _set_width)

    def _set_height(self, height):
        """
        >>> b=AvoidElement()
        >>> b.height = 20
        >>> b.height
        20.0
        >>> b.height = 2
        >>> b.height
        10.0
        >>> b._handles[NW].pos.y
        Variable(0, 40)
        >>> b._handles[SE].pos.y
        Variable(10, 40)
        """
        if height < self.min_height:
            height = self.min_height
        h = self._handles
        h[SE].pos.y = h[SW].pos.y = h[NW].pos.y + height

    def _get_height(self):
        """
        Height.
        """
        h = self._handles
        return float(h[SW].pos.y) - float(h[NW].pos.y)

    height = property(_get_height, _set_height)

    @observed
    def _set_min_width(self, min_width):
        """
        Set minimal width.
        """
        if min_width < 0:
            raise ValueError, 'Minimal width cannot be less than 0'

        self._min_width = min_width

    min_width = reversible_property(lambda s: s._min_width, _set_min_width)

    @observed
    def _set_min_height(self, min_height):
        """
        Set minimal height.
        """
        if min_height < 0:
            raise ValueError, 'Minimal height cannot be less than 0'

        self._min_height = min_height

    min_height = reversible_property(lambda s: s._min_height, _set_min_height)

    # Get rid of old solver dependency, so this can be done in pre_update()
    def pre_update(self, ctx):
        print 'update element'
        self.matrix_updated()

    def matrix_updated(self):
        i2c = self.canvas.get_matrix_i2c(self)
        coutline = map(lambda xy: i2c.transform_point(*xy), self.outline())
        self.canvas.router.moveShape(self._router_shape, coutline)

    def outline(self):
        h = self.handles()
        m = 0
        r = Rectangle(h[0].pos.x, h[0].pos.y, x1=h[2].pos.x, y1=h[2].pos.y)
        r.expand(5)
        #print r
        xMin, yMin = r.x, r.y
        xMax, yMax = r.x1, r.y1
        return ((xMax, yMin), (xMax, yMax), (xMin, yMax), (xMin, yMin))
        
    def point(self, pos):
        """
        Distance from the point (x, y) to the item.

        #>>> e = AvoidElement()
        #>>> e.point((20, 10))
        #10.0
        """
        h = self._handles
        pnw, pse = h[NW].pos, h[SE].pos
        return distance_rectangle_point(map(float, (pnw.x, pnw.y, pse.x, pse.y)), pos)






class AvoidLine(Item):
    """
    An implementation of a line backed by a libavoid.ConnRef.

    One ConnRef is created per line segment.
    """

    def __init__(self):
        super(AvoidLine, self).__init__()
        # Handles only for endpoints and checkpoints
        self._handles = [Handle(connectable=True), Handle((10, 10), connectable=True)]
        #self._ports = []
        # TODO: self._update_ports()

        self._line_width = 2
        self._fuzziness = 0
        self._head_angle = self._tail_angle = 0

    @observed
    def _set_line_width(self, line_width):
        self._line_width = line_width

    line_width = reversible_property(lambda s: s._line_width, _set_line_width)

    @observed
    def _set_fuzziness(self, fuzziness):
        self._fuzziness = fuzziness

    fuzziness = reversible_property(lambda s: s._fuzziness, _set_fuzziness)

    def opposite(self, handle):
        """
        Given the handle of one end of the line, return the other end.
        """
        handles = self._handles
        if handle is handles[0]:
            return handles[-1]
        elif handle is handles[-1]:
            return handles[0]
        else:
            raise KeyError('Handle is not an end handle')

    def setup_canvas(self):
        super(AvoidLine, self).setup_canvas()
        self._router_conns = [ libavoid.ConnRef(self.canvas.router) ]
        self._router_conns[0].setCallback(self._router_conns_updated)

    def teardown_canvas(self):
        for conn in self._router_conns:
            self.canvas.router.deleteConnector(conn)
        super(AvoidLine, self).teardown_canvas()

    def pre_update(self, context):
        super(AvoidLine, self).pre_update(context)

        h = self.handles()
        # use canvasprojection?
        endpoints = ((h[0].pos.x, h[0].pos.y), (h[-1].pos.x, h[-1].pos.y))
        transform_point = self.canvas.get_matrix_i2c(self).transform_point
        conns = self._router_conns
        if not isinstance(conns[0].sourceEndpoint, (libavoid.ShapeRef, libavoid.JunctionRef)):
            conns[0].setSourceEndpoint(transform_point(*endpoints[0]))
        if not isinstance(conns[-1].destEndpoint, (libavoid.ShapeRef, libavoid.JunctionRef)):
            conns[-1].setDestEndpoint(transform_point(*endpoints[-1]))
        checkpoints = []
        for h in self._handles[1:-1]:
            checkpoints.append(transform_point(*h.pos))
        conns[0].routingCheckpoints = checkpoints

    def router_update(self):
        pass

    def post_update(self, context):
        """
        """
        super(AvoidLine, self).post_update(context)
        p0, p1 = self._router_conns[0].displayRoute[:2]
        p0, p1 = self.points_c2i(p0, p1)
        self._head_angle = atan2(p1[1] - p0[1], p1[0] - p0[0])
        p1, p0 = self._router_conns[-1].displayRoute[-2:]
        p0, p1 = self.points_c2i(p0, p1)
        self._tail_angle = atan2(p1[1] - p0[1], p1[0] - p0[0])

    def closest_segment(self, pos):
        """
        Obtain a tuple (distance, point_on_line, segment).
        Distance is the distance from point to the closest line segment 
        Point_on_line is the reflection of the point on the line.
        Segment is the line segment closest to (x, y)

        #>>> a = AvoidLine()
        #>>> a.closest_segment((4, 5))
        #(0.70710678118654757, (4.5, 4.5), 0)
        """
        for conn in self._router_conns:
            hpos = self.points_c2i(*conn.displayRoute)
            #self.canvas.
            # create a list of (distance, point_on_line) tuples:
            distances = map(distance_line_point, hpos[:-1], hpos[1:], [pos] * (len(hpos) - 1))
            distances, pols = zip(*distances)
        return reduce(min, zip(distances, pols, range(len(distances))))

    def point(self, pos):
        """
        #>>> a = AvoidLine()
        #>>> a.handles()[1].pos = 25, 5
        #>>> a.point((-1, 0))
        #1.0
        #>>> '%.3f' % a.point((5, 4))
        #'2.942'
        #>>> '%.3f' % a.point((29, 29))
        #'0.784'
        """
        distance, point, segment = self.closest_segment(pos)
        return max(0, distance - self.fuzziness)

    def draw_head(self, context):
        """
        Default head drawer: move cursor to the first handle.
        """
        context.cairo.move_to(0, 0)

    def draw_tail(self, context):
        """
        Default tail drawer: draw line to the last handle.
        """
        context.cairo.line_to(0, 0)


    def draw(self, context):
        """
        Draw the line itself.
        See Item.draw(context).
        """
        def draw_line_end(pos, angle, draw):
            cr = context.cairo
            cr.save()
            try:
                cr.translate(*pos)
                cr.rotate(angle)
                draw(context)
            finally:
                cr.restore()

        cr = context.cairo
        cr.set_line_width(self.line_width)
        draw_line_end(self._handles[0].pos, self._head_angle, self.draw_head)
        transform_point = self.canvas.get_matrix_c2i(self).transform_point
        for conn in self._router_conns:
            for p in self.points_c2i(*conn.displayRoute):
                cr.line_to(*p)
        draw_line_end(self._handles[-1].pos, self._tail_angle, self.draw_tail)
        cr.stroke()


    def points_c2i(self, *points):
        transform_point = self.canvas.get_matrix_c2i(self).transform_point
        return map(apply, [transform_point] * len(points), points)

    def _router_conns_updated(self):
        try:
            # what to do here? redraw?
            self.request_update(matrix=False)
            h = self._handles
            p0 = self._router_conns[0].displayRoute[0]
            p1 = self._router_conns[-1].displayRoute[-1]
            p0, p1 = self.points_c2i(p0, p1)
            h[0].pos.x = p0[0]
            h[0].pos.x = p0[0]
            h[-1].pos.y = p1[1]
            h[-1].pos.y = p1[1]
        except:
            logging.error('Unable to handle callback', exc_info=1)


# TODO: What to do with ports? They don't fit in the libavoid model
# TODO: Make aspect update router_conns.
# TODO: connector: create new line segment on creation, merge one on disconnect
#@Connector.when_type(AvoidLine)
#...

#@ConnectionSink(AvoidLine)
#...
# TODO: connect to shape: create unique Pin, connect to that.
#@ConnectionSink(AvoidElement)
#...


# TODO: create new line splitting handler
@InMotion.when_type(AvoidLine)
class AvoidLineInMotion(object):
    """
    An Avoid Line is not moved. Instead an extra handle is created which is
    moved instead.

    The intermediate handles will function as checkpoints on the line.

    # TODO: How to deal with split lines due to junctions?
    """

    def __init__(self, item, view):
        self.item = item
        self.view = view
        self.last_x, self.last_y = None, None

    def start_move(self, pos):
        self.last_x, self.last_y = pos

    def move(self, pos):
        """
        Move the item. x and y are in view coordinates.
        """
        item = self.item
        view = self.view
        v2i = view.get_matrix_v2i(item)

        x, y = pos
        dx, dy = x - self.last_x, y - self.last_y
        dx, dy = v2i.transform_distance(dx, dy)
        self.last_x, self.last_y = x, y

        item.matrix.translate(dx, dy)
        item.canvas.request_matrix_update(item)

    def stop_move(self):
        pass


@HandleInMotion.when_type(AvoidElement)
class MyLineHandleInMotion(ItemHandleInMotion):

    def __init__(self, item, handle, view):
        super(MyLineHandleInMotion, self).__init__(item, handle, view)

    def set_handle(self, handle, x, y):
        item = self.item
        handles = item.handles()
        if handle is handles[0]:
            if x + item.min_width <= handles[1].pos.x:
                handles[0].pos.x = handles[3].pos.x = x
            if y + item.min_height <= handles[3].pos.y:
                handles[0].pos.y = handles[1].pos.y = y
        elif handle is handles[1]:
            if x - item.min_width >= handles[0].pos.x:
                handles[1].pos.x = handles[2].pos.x = x
            if y + item.min_height <= handles[2].pos.y:
                handles[1].pos.y = handles[0].pos.y = y
        elif handle is handles[2]:
            if x - item.min_width >= handles[0].pos.x:
                handles[2].pos.x = handles[1].pos.x = x
            if y - item.min_height >= handles[1].pos.y:
                handles[2].pos.y = handles[3].pos.y = y
        elif handle is handles[3]:
            if x + item.min_width <= handles[2].pos.x:
                handles[3].pos.x = handles[0].pos.x = x
            if y - item.min_height >= handles[0].pos.y:
                handles[3].pos.y = handles[2].pos.y = y

    def move(self, pos):
        item = self.item
        handle = self.handle
        view = self.view

        v2i = view.get_matrix_v2i(item)

        x, y = v2i.transform_point(*pos)

        self.set_handle(handle, x, y)

        sink = self.glue(pos)

        # do not request matrix update as matrix recalculation will be
        # performed due to item normalization if required
        item.request_update(matrix=False)

        return sink


# vim: sw=4:et:ai
