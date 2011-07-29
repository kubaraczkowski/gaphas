
import logging
from gaphas import Canvas
from gaphas.geometry import Rectangle
from gaphas.aspect import HandleInMotion, ItemHandleInMotion
from gaphas.segment import Segment
from state import observed, reversible_pair

import libavoid

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


class AvoidLineMixin(object):

    def setup_canvas(self):
        super(AvoidLineMixin, self).setup_canvas()
        self._router_shape = libavoid.ConnRef(self.canvas.router)
        self._router_shape.setCallback(self._router_shape_updated)

    def teardown_canvas(self):
        self.canvas.router.deleteConnector(self._router_shape)
        super(AvoidLineMixin, self).teardown_canvas()

    def pre_update(self, context):
        super(AvoidLineMixin, self).pre_update(context)

    def router_update(self):
        h = self.handles()
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

    def _router_shape_updated(self):
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
