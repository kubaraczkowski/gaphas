"""
Elements with support for libavoid, the automatic line router.
"""

import logging
from math import atan2

from gaphas import Canvas
from gaphas.geometry import Rectangle, distance_line_point, distance_rectangle_point, intersect_line_line
from gaphas.item import Item
from gaphas.connector import Handle, PolygonPort
from gaphas.aspect import HandleInMotion, ItemHandleInMotion, InMotion, Connector, ItemConnector
from gaphas.segment import Segment
from state import observed, reversible_pair, reversible_property
from gaphas.solver import VERY_STRONG

import libavoid

class AvoidSolver(object):
    """
    AvoidSolver - the constraint solver for libavoid.

    The minimal solver interface has been implemented, meaning adding and
    removing constraints and running the solver.
    """
    def __init__(self):
        #self.router = libavoid.Router(libavoid.ORTHOGONAL_ROUTING)
        self.router = libavoid.Router(libavoid.POLY_LINE_ROUTING)
        #self.router.setRoutingPenalty(libavoid.SEGMENT_PENALTY, 40)
        #self.router.setRoutingPenalty(libavoid.ANGLE_PENALTY, 400)
        #self.router.setRoutingPenalty(libavoid.CROSSING_PENALTY, 4000)
        self.router.setRoutingPenalty(libavoid.FIXED_SHARED_PATH_PENALTY, 80000)
        self.router.setRoutingPenalty(libavoid.PORT_DIRECTION_PENALTY, 4000)
        self.router.setOrthogonalNudgeDistance(14)

    def request_resolve(self):
        pass

    def solve(self):
        self.router.processTransaction()

    def add_constraint(self, constraint):
        item = constraint.item
        handle = constraint.handle
        connected = constraint.connected
        if handle is item.handles()[0]:
            item._router_conns[0].setSourceEndpoint(connected._router_shape)
        else:
            item._router_conns[-1].setDestEndpoint(connected._router_shape)

    def remove_constraint(self, constraint):
        assert constraint, 'No constraint (%s)' % (constraint,)
        item = constraint.item
        handle = constraint.handle
        connected = constraint.connected
        cpos = item.canvas.get_matrix_i2c(item).transform_point(*handle.pos)
        if handle is item.handles()[0]:
            item._router_conns[0].setSourceEndpoint(cpos)
        else:
            item._router_conns[-1].setDestEndpoint(cpos)


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
        self.matrix_updated()

    def matrix_updated(self):
        i2c = self.canvas.get_matrix_i2c(self)
        outline = self.outline()
        coutline = map(lambda xy: i2c.transform_point(*xy), outline)
        self.canvas.router.moveShape(self._router_shape, coutline)
        self._ports[0].polygon = outline

    def outline(self):
        h = self.handles()
        m = 0
        r = Rectangle(h[0].pos.x, h[0].pos.y, x1=h[2].pos.x, y1=h[2].pos.y)
        #r.expand(5)
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
        After constraint solving, the handles should be placed on the
        boundries of the element they're connected to (if any).
        """
        def place_handle(shape, p0, p1):
            #item = self.canvas.get_connection(self._handles[0])
            poly = shape.polygon
            for sp0, sp1 in zip(poly, poly[1:] + poly[:1]):
                i = intersect_line_line(p0, p1, sp0, sp1)
                if i:
                    return self.canvas.get_matrix_c2i(self).transform_point(*i)

        super(AvoidLine, self).post_update(context)

        src = self._router_conns[0]
        if isinstance(src.sourceEndpoint, libavoid.ShapeRef):
            self._handles[0].pos = place_handle(src.sourceEndpoint, *src.displayRoute[:2])

        dst = self._router_conns[-1]
        if isinstance(dst.destEndpoint, libavoid.ShapeRef):
            self._handles[-1].pos = place_handle(dst.destEndpoint, *dst.displayRoute[-2:])

        # Update angles
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
        #draw_line_end(self._handles[0].pos, self._head_angle, self.draw_head)
        cr.move_to(*self._handles[0].pos)
        transform_point = self.canvas.get_matrix_c2i(self).transform_point
        for conn in self._router_conns:
            # TODO: skip first point and last point. Those are handle positions.
            for p in self.points_c2i(*conn.displayRoute[1:-1]):
                cr.line_to(*p)
        #draw_line_end(self._handles[-1].pos, self._tail_angle, self.draw_tail)
        cr.line_to(*self._handles[-1].pos)
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
def AvoidLineConnector(ItemConnector):

    def __init__(self, item, handle):
        super(AvoidLineConnector, self).__init__(item, handle)

    def allow(self, sink):
        return hasattr(sink.item, '_router_shape')

    def connect_handle(self, sink, callback=None):
        canvas = self.item.canvas
        handle = self.handle
        item = self.item

        constraint = None

        canvas.connect_item(item, handle, sink.item, sink.port,
            constraint, callback=callback)



#@ConnectionSink(AvoidLine)
#...
# TODO: connect to shape: create unique Pin, connect to that.
#@ConnectionSink(AvoidElement)
#def AvoidElementConnectionSink


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
