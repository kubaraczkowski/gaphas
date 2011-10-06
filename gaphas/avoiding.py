"""
Elements with support for libavoid, the automatic line router.
"""

import logging
from gaphas import Canvas
from gaphas.geometry import Rectangle
from gaphas.item import Item
from gaphas.aspect import HandleInMotion, ItemHandleInMotion
from gaphas.segment import Segment
from state import observed, reversible_pair

import libavoid

class AvoidSolver(object):

    def __init__(self):
        pass

    # implement solver methods
    # allow to make the right kind of constraint
    
class AvoidCanvas(Canvas):

    def __init__(self):
        super(AvoidCanvas, self).__init__()
        #self.router = libavoid.Router(libavoid.ORTHOGONAL_ROUTING)
        self.router = libavoid.Router(libavoid.POLY_LINE_ROUTING)
        self.router.setRoutingPenalty(libavoid.SEGMENT_PENALTY, 40)
        self.router.setRoutingPenalty(libavoid.ANGLE_PENALTY, 400)
        self.router.setRoutingPenalty(libavoid.CROSSING_PENALTY, 4000)
        self.router.setRoutingPenalty(libavoid.FIXED_SHARED_PATH_PENALTY, 8000)
        self.router.setRoutingPenalty(libavoid.PORT_DIRECTION_PENALTY, 4000)
        self.router.setOrthogonalNudgeDistance(14)

    def update_constraints(self, items):
        super(AvoidCanvas, self).update_constraints(items)

        # item's can be marked dirty due to constraint solving
        for item in items.union(self._dirty_items):
            item.router_update()

        self.router.processTransaction()

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



class AvoidElementMixin(object):
    """Box with an example connection protocol.
    """

    def setup_canvas(self):
        super(AvoidElementMixin, self).setup_canvas()
        self._router_shape = libavoid.ShapeRef(self.canvas.router, self.outline())

    def teardown_canvas(self):
        self.canvas.router.deleteShape(self._router_shape)
        super(AvoidElementMixin, self).teardown_canvas()

    def router_update(self):
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


class AvoidLine(Item):

    def __init__(self):
        super(AvoidLine, self).__init__()
        # Handles only for endpoints and checkpoints
        self._handles = [Handle(connectable=True), Handle((10, 10), connectable=True)]
        self._ports = []
        # TODO: self._update_ports()

        self._line_width = 2
        self._fuzziness = 0
        self._head_angle = self._tail_angle = 0

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
        self.canvas.router.deleteConnector(self._router_shape)
        super(AvoidLine, self).teardown_canvas()

    def pre_update(self, context):
        super(AvoidLine, self).pre_update(context)

    def post_update(self, context):
        """
        """
        super(AvoidLine, self).post_update(context)
        h0, h1 = self._handles[:2]
        p0, p1 = h0.pos, h1.pos
        self._head_angle = atan2(p1.y - p0.y, p1.x - p0.x)
        h1, h0 = self._handles[-2:]
        p1, p0 = h1.pos, h0.pos
        self._tail_angle = atan2(p1.y - p0.y, p1.x - p0.x)

    def closest_segment(self, pos):
        """
        Obtain a tuple (distance, point_on_line, segment).
        Distance is the distance from point to the closest line segment 
        Point_on_line is the reflection of the point on the line.
        Segment is the line segment closest to (x, y)

        >>> a = Line()
        >>> a.closest_segment((4, 5))
        (0.70710678118654757, (4.5, 4.5), 0)
        """
        for conn in self._shape_conns:
            hpos = conn.displayRoute
            self.canvas.
            # create a list of (distance, point_on_line) tuples:
            distances = map(distance_line_point, hpos[:-1], hpos[1:], [pos] * (len(hpos) - 1))
            distances, pols = zip(*distances)
        return reduce(min, zip(distances, pols, range(len(distances))))

    def point(self, pos):
        """
        >>> a = Line()
        >>> a.handles()[1].pos = 25, 5
        >>> a._handles.append(a._create_handle((30, 30)))
        >>> a.point((-1, 0))
        1.0
        >>> '%.3f' % a.point((5, 4))
        '2.942'
        >>> '%.3f' % a.point((29, 29))
        '0.784'
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
        for h in self._handles[1:-1]:
            cr.line_to(*h.pos)
        draw_line_end(self._handles[-1].pos, self._tail_angle, self.draw_tail)
        cr.stroke()


    def points_c2i(self, *points):
        transform_point = self.canvas.get_matrix_c2i(self).transform_point
        return map(apply, [transform_point] * len(points), points)

    def router_update(self):
        h = self.handles()
        # use canvasprojection?
        endpoints = ((h[0].pos.x, h[0].pos.y), (h[-1].pos.x, h[-1].pos.y))
        transform_point = self.canvas.get_matrix_i2c(self).transform_point
        conn = self._router_shape
        if not isinstance(conn.sourceEndpoint, libavoid.ShapeRef):
            conn.setSourceEndpoint(transform_point(*endpoints[0]))
        if not isinstance(conn.destEndpoint, libavoid.ShapeRef):
            conn.setDestEndpoint(transform_point(*endpoints[-1]))
        checkpoints = []
        for h in self._handles[1:-1]:
            if getattr(h, 'checkpoint', False):
                checkpoints.append(transform_point(*h.pos))
        conn.routingCheckpoints = checkpoints

    def _router_conns_updated(self):
        try:
            transform_point = self.canvas.get_matrix_c2i(self).transform_point
            route = self._router_shape.displayRoute
            checkpoints = self._router_shape.routingCheckpoints
            newpoints = []
            checkpoint_index = 0
            for p in route:
                if checkpoint_index < len(checkpoints) \
                        and p == checkpoints[checkpoint_index]:
                    newpoints.append((transform_point(*p), True))
                    checkpoint_index += 1
                else:
                    newpoints.append((transform_point(*p), False))
            self.update_endpoints(newpoints)
            self.canvas.request_update(self, matrix=False)
        except:
            logging.error('Unable to handle callback', exc_info=1)

    def update_endpoints(self, newpoints):
        """
        Newpoints is a list of tuple (point, is_checkpoint).
        """
        # TODO: How to determine where to split? Connections will also move

        n_points = len(newpoints)
        segm = Segment(self, None)

        # Find only router points to remove and add
        while len(self._handles) < n_points:
            h, ports = segm.split_segment(0, 2)
        while len(self._handles) > n_points:
            segm.merge_segment(0)

        for h, (p, c) in zip(self._handles, newpoints):
            h.pos.x = p[0]
            h.pos.y = p[1]
            h.routing = c


@HandleInMotion.when_type(AvoidLineMixin)
class MyLineHandleInMotion(ItemHandleInMotion):

    def __init__(self, item, handle, view):
        super(MyLineHandleInMotion, self).__init__(item, handle, view)

    def move(self, pos):
        sink = super(MyLineHandleInMotion, self).move(pos)

        self.handle.checkpoint = True

        self.item.request_update()

        return sink


# vim: sw=4:et:ai
