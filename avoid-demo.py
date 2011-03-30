#!/usr/bin/env python
"""
A simple demo app.

It sports a small canvas and some trivial operations:

 - Add a line/box
 - Zoom in/out
 - Split a line segment
 - Delete focused item
 - Record state changes
 - Play back state changes (= undo !) With visual updates
 - Exports to SVG and PNG

"""

__version__ = "$Revision$"
# $HeadURL$

try:
    import pygtk
except ImportError:
    pass
else:
    pygtk.require('2.0') 

import logging
import gtk
import cairo
from gaphas import Canvas, GtkView, View
from gaphas.geometry import Rectangle
from gaphas.examples import Box
from gaphas.item import Line
from gaphas.tool import PlacementTool, HandleTool
from gaphas.segment import Segment
import gaphas.guide
from gaphas import state

from gaphas import painter
#painter.DEBUG_DRAW_BOUNDING_BOX = True

# Ensure data gets picked well:
import gaphas.picklers

import libavoid

# Global undo list
undo_list = []

def undo_handler(event):
    global undo_list
    undo_list.append(event)


def factory(view, cls):
    """
    Simple canvas item factory.
    """
    def wrapper():
        item = cls()
        view.canvas.add(item)
        return item
    return wrapper

class AvoidCanvas(Canvas):

    def __init__(self):
        super(AvoidCanvas, self).__init__()
        self.router = libavoid.Router(libavoid.ORTHOGONAL_ROUTING)
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


class MyBox(Box):
    """Box with an example connection protocol.
    """

    def setup_canvas(self):
        super(MyBox, self).setup_canvas()
        self._router_shape = libavoid.ShapeRef(self.canvas.router, self.outline())

    def teardown_canvas(self):
        self.canvas.router.deleteShape(self._router_shape)
        super(MyBox, self).teardown_canvas()

    def pre_update(self, context):
        super(MyBox, self).pre_update(context)

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


class MyLine(Line):
    """Line with experimental connection protocol.
    """
    def __init__(self):
        super(MyLine, self).__init__()
        self.fuzziness = 2

    def setup_canvas(self):
        super(MyLine, self).setup_canvas()
        self._router_shape = libavoid.ConnRef(self.canvas.router)
        self._router_shape.setCallback(self._router_shape_updated)

    def teardown_canvas(self):
        self.canvas.router.deleteConnector(self._router_shape)
        super(MyLine, self).teardown_canvas()

    def pre_update(self, context):
        super(MyLine, self).pre_update(context)

    def router_update(self):
        h = self.handles()
        endpoints = ((h[0].pos.x, h[0].pos.y), (h[-1].pos.x, h[-1].pos.y))
        i2c = self.canvas.get_matrix_i2c(self)
        conn = self._router_shape
        conn.setSourceEndpoint(i2c.transform_point(*endpoints[0]))
        conn.setDestEndpoint(i2c.transform_point(*endpoints[-1]))

    def _router_shape_updated(self):
        try:
            c2i = self.canvas.get_matrix_c2i(self)
            ioutline = map(lambda xy: c2i.transform_point(*xy), self._router_shape.displayRoute)
            self.update_endpoints(ioutline)
            self.canvas.request_update(self, matrix=False)
        except:
            logging.error('Unable to handle callback', exc_info=1)

    def update_endpoints(self, newpoints):
        # TODO: set start and end point.
        # Set points in the middle, split segments, etc.
        print 'Update endpoints to', newpoints
        n_points = len(newpoints)
        while len(self._handles) < n_points:
            self._handles.insert(1, gaphas.Handle())
        while len(self._handles) > n_points:
            del self._handles[1]
        for h, p in zip(self._handles, newpoints):
            h.pos.x = p[0]
            h.pos.y = p[1]

    def draw_head(self, context):
        cr = context.cairo
        cr.move_to(0, 0)
        cr.line_to(10, 10)
        cr.stroke()
        # Start point for the line to the next handle
        cr.move_to(0, 0)

    def draw_tail(self, context):
        cr = context.cairo
        cr.line_to(0, 0)
        cr.line_to(10, 10)
        cr.stroke()


def create_window(canvas, title, zoom=1.0):
    view = GtkView()
    w = gtk.Window()
    w.set_title(title)
    h = gtk.HBox()
    w.add(h)

    # VBox contains buttons that can be used to manipulate the canvas:
    v = gtk.VBox()
    v.set_property('border-width', 3)
    v.set_property('spacing', 2)
    f = gtk.Frame()
    f.set_property('border-width', 1)
    f.add(v)
    h.pack_start(f, expand=False)

    v.add(gtk.Label('Item placement:'))
    
    b = gtk.Button('Add box')

    def on_clicked(button, view):
        #view.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.CROSSHAIR))
        view.tool.grab(PlacementTool(view, factory(view, MyBox), HandleTool(), 2))

    b.connect('clicked', on_clicked, view)
    v.add(b)

    b = gtk.Button('Add line')

    def on_clicked(button):
        view.tool.grab(PlacementTool(view, factory(view, MyLine), HandleTool(), 1))

    b.connect('clicked', on_clicked)
    v.add(b)

    v.add(gtk.Label('Zooming:'))
   
    b = gtk.Button('Zoom in')

    def on_clicked(button):
        view.zoom(1.2)

    b.connect('clicked', on_clicked)
    v.add(b)

    b = gtk.Button('Zoom out')

    def on_clicked(button):
        view.zoom(1/1.2)

    b.connect('clicked', on_clicked)
    v.add(b)

    v.add(gtk.Label('Misc:'))

    b = gtk.Button('Split line')

    def on_clicked(button):
        if isinstance(view.focused_item, Line):
            segment = Segment(view.focused_item, view)
            segment.split_segment(0)
            view.queue_draw_item(view.focused_item)

    b.connect('clicked', on_clicked)
    v.add(b)

    b = gtk.Button('Delete focused')

    def on_clicked(button):
        if view.focused_item:
            canvas.remove(view.focused_item)
            #print 'items:', canvas.get_all_items()

    b.connect('clicked', on_clicked)
    v.add(b)

    v.add(gtk.Label('State:'))
    b = gtk.ToggleButton('Record')

    def on_toggled(button):
        global undo_list
        if button.get_active():
            print 'start recording'
            del undo_list[:]
            state.subscribers.add(undo_handler)
        else:
            print 'stop recording'
            state.subscribers.remove(undo_handler)

    b.connect('toggled', on_toggled)
    v.add(b)

    b = gtk.Button('Play back')
    
    def on_clicked(self):
        global undo_list
        apply_me = list(undo_list)
        del undo_list[:]
        print 'Actions on the undo stack:', len(apply_me)
        apply_me.reverse()
        saveapply = state.saveapply
        for event in apply_me:
            print 'Undo: invoking', event
            saveapply(*event)
            print 'New undo stack size:', len(undo_list)
            # Visualize each event:
            #while gtk.events_pending():
            #    gtk.main_iteration()

    b.connect('clicked', on_clicked)
    v.add(b)

    v.add(gtk.Label('Export:'))

    b = gtk.Button('Write demo.png')

    def on_clicked(button):
        svgview = View(view.canvas)
        svgview.painter = ItemPainter()

        # Update bounding boxes with a temporaly CairoContext
        # (used for stuff like calculating font metrics)
        tmpsurface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 0, 0)
        tmpcr = cairo.Context(tmpsurface)
        svgview.update_bounding_box(tmpcr)
        tmpcr.show_page()
        tmpsurface.flush()
       
        w, h = svgview.bounding_box.width, svgview.bounding_box.height
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(w), int(h))
        cr = cairo.Context(surface)
        svgview.matrix.translate(-svgview.bounding_box.x, -svgview.bounding_box.y)
        cr.save()
        svgview.paint(cr)

        cr.restore()
        cr.show_page()
        surface.write_to_png('demo.png')

    b.connect('clicked', on_clicked)
    v.add(b)

    b = gtk.Button('Write demo.svg')

    def on_clicked(button):
        svgview = View(view.canvas)
        svgview.painter = ItemPainter()

        # Update bounding boxes with a temporaly CairoContext
        # (used for stuff like calculating font metrics)
        tmpsurface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 0, 0)
        tmpcr = cairo.Context(tmpsurface)
        svgview.update_bounding_box(tmpcr)
        tmpcr.show_page()
        tmpsurface.flush()
       
        w, h = svgview.bounding_box.width, svgview.bounding_box.height
        surface = cairo.SVGSurface('demo.svg', w, h)
        cr = cairo.Context(surface)
        svgview.matrix.translate(-svgview.bounding_box.x, -svgview.bounding_box.y)
        svgview.paint(cr)
        cr.show_page()
        surface.flush()
        surface.finish()

    b.connect('clicked', on_clicked)
    v.add(b)

    
    b = gtk.Button('Dump QTree')

    def on_clicked(button, li):
        view._qtree.dump()

    b.connect('clicked', on_clicked, [0])
    v.add(b)


    b = gtk.Button('Pickle (save)')

    def on_clicked(button, li):
        f = open('demo.pickled', 'w')
        try:
            import cPickle as pickle
            pickle.dump(view.canvas, f)
        finally:
            f.close()

    b.connect('clicked', on_clicked, [0])
    v.add(b)


    b = gtk.Button('Unpickle (load)')

    def on_clicked(button, li):
        f = open('demo.pickled', 'r')
        try:
            import cPickle as pickle
            canvas = pickle.load(f)
            canvas.update_now()
        finally:
            f.close()
        create_window(canvas, 'Unpickled diagram')

    b.connect('clicked', on_clicked, [0])
    v.add(b)


    b = gtk.Button('Unpickle (in place)')

    def on_clicked(button, li):
        f = open('demo.pickled', 'r')
        try:
            import cPickle as pickle
            canvas = pickle.load(f)
        finally:
            f.close()
        #[i.request_update() for i in canvas.get_all_items()]
        canvas.update_now()
        view.canvas = canvas

    b.connect('clicked', on_clicked, [0])
    v.add(b)


    b = gtk.Button('Reattach (in place)')

    def on_clicked(button, li):
        view.canvas = None
        view.canvas = canvas

    b.connect('clicked', on_clicked, [0])
    v.add(b)


    # Add the actual View:

    t = gtk.Table(2,2)
    h.add(t)

    w.connect('destroy', gtk.main_quit)

    view.canvas = canvas
    view.zoom(zoom)
    view.set_size_request(250, 120)
    hs = gtk.HScrollbar(view.hadjustment)
    vs = gtk.VScrollbar(view.vadjustment)
    t.attach(view, 0, 1, 0, 1)
    t.attach(hs, 0, 1, 1, 2, xoptions=gtk.FILL, yoptions=gtk.FILL)
    t.attach(vs, 1, 2, 0, 1, xoptions=gtk.FILL, yoptions=gtk.FILL)

    w.show_all()
    
    def handle_changed(view, item, what):
        print what, 'changed: ', item

    view.connect('focus-changed', handle_changed, 'focus')
    view.connect('hover-changed', handle_changed, 'hover')
    view.connect('selection-changed', handle_changed, 'selection')

    
def main():
    ##
    ## State handling (a.k.a. undo handlers)
    ##

    # First, activate the revert handler:
    state.observers.add(state.revert_handler)

    def print_handler(event):
        print 'event:', event

    c=AvoidCanvas()

    create_window(c, 'Line avoiding demo')

    #state.subscribers.add(print_handler)

    ##
    ## Start the main application
    ##


    gtk.main()


if __name__ == '__main__':
    import sys
    if '-p' in sys.argv:
        print 'Profiling...'
        import hotshot, hotshot.stats
        prof = hotshot.Profile('demo-gaphas.prof')
        prof.runcall(main)
        prof.close()
        stats = hotshot.stats.load('demo-gaphas.prof')
        stats.strip_dirs()
        stats.sort_stats('time', 'calls')
        stats.print_stats(20)
    else:
        main()

# vim: sw=4:et:ai
