""" Canvas block for displaying item collections
"""

__version__ = "$Revision$"
__date__ = "$Date$"
__copyright__ = "Copyright (c) 2004 Open Source Applications Foundation"
__license__ = "http://osafoundation.org/Chandler_0.1_license_terms.htm"

import wx

import osaf.framework.blocks.DragAndDrop as DragAndDrop
import osaf.framework.blocks.Block as Block
import application.Globals as Globals

# @@@ These buttons could become a more general utility

class CanvasTextButton(wx.BitmapButton):
    """ Flat text button, no border.
    
        Currently does not work well on os x, widgets doesn't give us
        a button with no border. Currently implemented by drawing 
        text to a bitmap, but one could imagine other implementations. 
    """
    
    def __init__(self, parent, text, font, fgcolor, bgcolor):
        """

        @param parent: like all controls, requires a parent window
        @type parent: wx.Window
        @param text: the text the button will display
        @type text: string
        @param font: the text font
        @type font: wx.Font
        @param fgcolor: the text color
        @type fgcolor: wx.Colour
        @param bgcolor: the background color of the button
        @type bgcolor: wx.Colour
        """
        
        bitmap = self.buildBitmap(parent, text, font, fgcolor, bgcolor)
        super(CanvasTextButton, self).__init__(parent, -1,
                                               bitmap, style=wx.BORDER_NONE)
        self.text = text
        self.font = font
        self.fgcolor = fgcolor
        self.bgcolor = bgcolor

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)

    def OnEraseBackground(self, event):
        """
        Do nothing on EraseBackground events, to avoid flicker.
        """
        pass

    def buildBitmap(self, window, text, font, fgcolor, bgcolor):
        """ Creates a bitmap with the given text.

        @param window: needs a window to check the text extent
        @type window: wx.Window
        @param text: text to display in the bitmap
        @type text: string
        @param font: font used to display the text
        @type font: wx.Font
        @param fgcolor: color of the text
        @type fgcolor: wx.Colour
        @param bgcolor: background color of the bitmap
        @type bgcolor: wx.Colour
        @return: the bitmap
        @rtype: wx.Bitmap
        """
        
        # Have to ask a window for the text extent, asking
        # the memory dc doesn't work on the mac
        textExtent = window.GetFullTextExtent(text, font)
        bitmap = wx.EmptyBitmap(textExtent[0], textExtent[1])

        dc = wx.MemoryDC()
        dc.SetFont(font)
        dc.SelectObject(bitmap)
        dc.SetBackground(wx.Brush(bgcolor))
        dc.Clear()
        dc.SetTextForeground(fgcolor)
        dc.DrawText(text, (0, 0))
        
        return bitmap
        
    def SetLabel(self, text):
        """ Changes the text on the button.

        @param text: text of the button
        @type text: string
        """
        self.text = text
        bitmap = self.buildBitmap(self.GetParent(), text,
                                  self.font, self.fgcolor, self.bgcolor)
        self.SetBitmapLabel(bitmap)

class CanvasBitmapButton(wx.BitmapButton):
    """ Flat bitmap button, no border.
    
        Currently does not work well on os x, widgets doesn't give us
        a button with no border. 
    """
    
    def __init__(self, parent, path):
        """

        @param parent: like all controls, requires a parent window
        @type parent: wx.Window
        @param path: path to a png file
        @type path: string
        """

        bitmap = wx.Image(path, wx.BITMAP_TYPE_PNG).ConvertToBitmap()
        super(CanvasBitmapButton, self).__init__(parent, -1,
                                                 bitmap, style=wx.BORDER_NONE)

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)

    def OnEraseBackground(self, event):
        """
        Do nothing on EraseBackground events, to avoid flicker.
        """
        pass

class CanvasItem(object):
    """
    Represents a list of items currently on the canvas for hit testing.
    Not responsible for drawing the object on the canvas. This class
    stores the bounds of the item on the canvas, subclasses can be more
    sophisticated.
    """
    
    def __init__(self, bounds, item):
        """
        @param bounds: the bounds of the item as drawn on the canvas.
        @type bounds: wx.Rect
        @param item: the item drawn on the canvas in these bounds
        @type item: Item
        """

        # @@@ scaffolding: resize bounds is the lower 5 pixels
        self.bounds = bounds
        self.item = item

    def isHit(self, point):
        """ Hit testing (used for selection and moving items).

        @param point: point in unscrolled coordinates
        @type point: wx.Point
        @return: True if the point hit the item (includes resize region)
        @rtype: Boolean
        """
        return self.bounds.Inside(point)

    def isHitResize(self, point):
        """ Hit testing of a resize region.

        Subclasses can define to turn on resizing behavior.
        
        @param point: point in unscrolled coordinates
        @type point: wx.Point
        @return: True if the point hit the resize region
        @rtype: Boolean
        """
        return False

    def getItem(self):
        """
        Once we have a hit, give access to the item
        for selection, move, resize, etc.
        
        @return: the item associated with this region on the canvas.
        @rtype: Item
        """
        return self.item

class wxCollectionCanvas(wx.ScrolledWindow,
                         DragAndDrop.DropReceiveWidget,
                         DragAndDrop.DraggableWidget):

    """ Canvas used for displaying an ItemCollection

    This class handles:
    1. Mouse Events: the class sets up methods for selection, move, resize
    2. Scrolling
    3. Double buffered painting: the class sets up methods for drawing

    Subclasses need to handle (by overriding appropriate methods):
    1. Background drawing
    2. Drawing items
    3. Creating regions for hit testing
    4. Resizing items (changing state, drawing the altered item)
    5. Moving/dragging items (changing state, drawing the altered item)

    This class assumes an associated blockItem for some default behavior,
    although subclasses can alter this by overriding the appropriate methods.

    This class currently provides two common fonts for subclasses to use
    in drawing as a convenience, subclasses are free to create their own fonts.

    @ivar bigFont: font size and face of the default big font
    @type bigFont: wx.Font
    @ivar bigFontColor: color of the default big font
    @type bigFontColor: wx.Colour
    @ivar smallFont: font size and face of the default small font
    @type smallFont: wx.Font
    @ivar smallFontColor: color of the default small font
    @type smallFontColor: wx.Colour

    @ivar _isDraggingItem: captures mode of dragging an item in the canvas
    @type _isDraggingItem: Boolean
    @ivar _isResizingItem: captures mode of resizing an item in the canvas
    @type _isResizingItem: Boolean
    @ivar _dragStart: starting point of drag, in scrolled coordinates
    @type _dragStart: wx.Point
    @ivar _dragStartUnscrolled: unscrolled coordinates of drag start
    @type _dragStartUnscrolled: wx.Point
    @ivar _dragBox: canvas location of selected/resized/moved item
    @type _dragBox: CanvasItem
    """
    
    def __init__(self, *arguments, **keywords):
        """
        Same arguments as wx.ScrolledWindow
        Constructor sets up ivars, event handlers, etc.
        """
        super(wxCollectionCanvas, self).__init__(*arguments, **keywords)
        self.canvasItemList = []

        self.Bind(wx.EVT_ERASE_BACKGROUND, self.OnEraseBackground)
        self.Bind(wx.EVT_PAINT, self.OnPaint)
        
        self.Bind(wx.EVT_MOUSE_EVENTS, self.OnMouseEvent)

        self._isDraggingItem = False
        self._isResizingItem = False
        self._dragStart = None
        self._dragBox = None

        # Create common fonts for drawing, @@@ move elsewhere
        if '__WXMAC__' in wx.PlatformInfo:
            self.bigFont = wx.Font(13, wx.NORMAL, wx.NORMAL, wx.NORMAL)
            self.smallFont = wx.Font(10, wx.SWISS, wx.NORMAL, wx.NORMAL,
                                     face="Verdana")
        else:
            self.bigFont = wx.Font(11, wx.NORMAL, wx.NORMAL, wx.NORMAL)
            self.smallFont = wx.Font(8, wx.SWISS, wx.NORMAL, wx.NORMAL,
                                     face="Verdana")

        self.bigFontColor = wx.Colour(64, 64, 64)
        self.bgColor = wx.WHITE
        self.smallFontColor = wx.BLACK


    # Drawing utility -- scaffolding, we'll try using editor/renderers
    def DrawWrappedText(self, dc, text, rect):
        # Simple wordwrap, next step is to not overdraw the rect
        
        lines = text.splitlines()
        y = rect.y
        for line in lines:
            x = rect.x
            wrap = 0
            words = line.split(' ')
            for word in words:
                width, height = dc.GetTextExtent(word)
                if (x + width > rect.x + rect.width):
                    y += height
                    x = rect.x
                dc.DrawText(word, (x, y))
                x += width
                width, height = dc.GetTextExtent(' ')
                dc.DrawText(' ', (x, y))
                x += width
            y += height
        
    # Mouse movement

    def OnMouseEvent(self, event):
        """
        Handles mouse events, calls overridable methods related to:
        1. Selecting an item
        2. Dragging/moving an item
        3. Resizing an item
        """

        position = event.GetPosition()
        unscrolledPosition = self.CalcUnscrolledPosition(position)

        # ignore entering and leaving events
        if (event.Entering() or event.Leaving()):
            return

        # handle dragging
        if self._isDraggingItem:
            if event.Dragging() and event.LeftIsDown():
                self.OnDraggingItem(unscrolledPosition)
            else: # end the drag
                self._isDraggingItem = False
                self.OnEndDragItem()
                self._dragBox = None
                self._dragStart = None
                self.ReleaseMouse()

        # handle resizing
        elif self._isResizingItem:
            if event.Dragging() and event.LeftIsDown():
                self.OnResizingItem(unscrolledPosition)
            else: # end the drag
                self._isResizingItem = False
                self.OnEndResizeItem()
                self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))
                self._dragStart = None
                self.ReleaseMouse()
                
        else: # not dragging an item or rezising

            # Show the resize cursor if we're over a resize area,
            # otherwise restore the cursor
            hoverResize = False
            for box in self.canvasItemList:
                if box.isHitResize(unscrolledPosition):
                    hoverResize = True
            if hoverResize:
                self.SetCursor(wx.StockCursor(wx.CURSOR_SIZENS))
            else:
                self.SetCursor(wx.StockCursor(wx.CURSOR_DEFAULT))

            # create an item on double click
            if event.LeftDClick():
                self.OnCreateItem(unscrolledPosition, False)

            # handle selection if mouse down event, set up drag
            elif event.LeftDown(): 
                hitBox = None
                for box in self.canvasItemList:
                    if box.isHit(unscrolledPosition):
                        hitBox = box

                if hitBox:
                    self.OnSelectItem(hitBox.getItem())
                    self._dragBox = hitBox

                # notice drag start whether or not we hit something
                self._dragStart = position
                self._dragStartUnscrolled = unscrolledPosition

            # look for the beginning of a drag
            elif (event.Dragging() and
                  event.LeftIsDown() and
                  self._dragStart):
                
                tolerance = 2
                dx = abs(position.x - self._dragStart.x)
                dy = abs(position.y - self._dragStart.y)
                if (dx > tolerance or dy > tolerance):
                    if self._dragBox: 
                        resize = self._dragBox.isHitResize(self._dragStartUnscrolled)

                        if resize: # start resizing
                            self._isResizingItem = True
                            self.OnBeginResizeItem()
                            self.SetCursor(wx.StockCursor(wx.CURSOR_SIZENS))
                            self.CaptureMouse()

                        else: # start dragging
                            self._isDraggingItem = True
                            self.OnBeginDragItem()
                            self.CaptureMouse()
                            
                    else: # try creating an item
                        itemBox = self.OnCreateItem(self._dragStartUnscrolled, True)
                        if itemBox: # if we have one, start resizing this item
                            self._dragBox = itemBox
                            self._isResizingItem = True
                            self.OnBeginResizeItem()
                            self.SetCursor(wx.StockCursor(wx.CURSOR_SIZENS))
                            self.CaptureMouse()
                        else: # clear out the drag info, avoid creating more items
                            self._dragStart = None
                            self._dragBox = None
                        

    def OnCreateItem(self, position, createOnDrag):
        """ Creates a new item on the canvas.

        Subclasses can define to create a new item on the canvas.

        If the new item is created during a drag, then this method needs
        to return a CanvasItem for the new item, for smooth dragging.
        (As soon as the new item is created, it becomes a resize operation.)

        @param position: unscrolled coordinates, location of the new item
        @type position: wx.Point
        @param createOnDrag: True if in the middle of a drag (vs double click) 
        @type createOnDrag: Boolean
        @return: the CanvasItem for the newly created item, if createOnDrag
        @rtype: CanvasItem
        """
        return None

    def OnBeginResizeItem(self):
        """ Called when an item resize begins.
        
        Subclasses can define to handle resizing
        """
        pass

    def OnEndResizeItem(self):
        """ Called when an item resize ends.
        
        Subclasses can define to handle resizing
        """
        pass

    def OnResizingItem(self, position):
        """ Called when the mouse moves during a resize.
        
        Subclasses can define to handle resizing
        """
        pass

    def OnBeginDragItem(self):
        """ Called when a drag/move begins.
        
        Subclasses can define to handle dragging
        """
        pass

    def OnEndDragItem(self):
        """ Called when a drag/move ends.
        
        Subclasses can define to handle dragging
        """
        pass

    def OnDraggingItem(self, position):
        """ Called when the mouse moves during a drag.
        
        Subclasses can define to handle dragging
        """
        pass
            
    # Painting and drawing

    def OnEraseBackground(self, event):
        """
        Do nothing on EraseBackground events, to avoid flicker.
        """
        pass

    def OnPaint(self, event):
        """
        """
        # @@@ we currently have a bug where the update regions don't 
        # always match the virtual size, creating a small black band 
        # at the bottom of the virtual window

        # double buffered drawing
        dc = wx.PaintDC(self)
        self.PrepareDC(dc)

        # Find update rect in scrolled coordinates
        updateRect = self.GetUpdateRegion().GetBox()
        (xBuffer, yBuffer) = self.CalcUnscrolledPosition((updateRect.GetLeft(),
                                                          updateRect.GetTop()))
        wBuffer = updateRect.GetWidth()
        hBuffer = updateRect.GetHeight()

        # Create offscreen buffer
        memoryDC = wx.MemoryDC()
        buffer = wx.EmptyBitmap(wBuffer, hBuffer)
        memoryDC.SelectObject(buffer)
        memoryDC.SetDeviceOrigin(-xBuffer, -yBuffer)

        memoryDC.BeginDrawing()

        self.DrawBackground(memoryDC)
        self.DrawCells(memoryDC)

        dc.Blit((xBuffer, yBuffer),
                (wBuffer, hBuffer),
                memoryDC,
                (xBuffer, yBuffer))

        memoryDC.EndDrawing()
        
    def DrawCells(self, dc):
        """
        Subclasses should define to draw the canvas cells
        """
        pass

    def DrawBackground(self, dc):
        """
        Subclasses should define to draw the canvas background
        """
        pass

    # selection

    def OnSelectItem(self, item):
        """ Called when an item is hit, to select the item.

        Subclasses can override to handle item selection.
        """
        self.blockItem.selection = item
        self.blockItem.postSelectionChanged()
        self.wxSynchronizeWidget()

    # DropReceiveWidget
    
    def OnRequestDrop(self, x, y):
        """
        Handles drop target behavior -- @@@ not yet implemented
        """
        return False

    def AddItem(self, itemUUID):
        """
        Handles drop target behavior -- @@@ not yet fully implemented
        """
        item = Globals.repository.findUUID(itemUUID)
        

    def OnHover(self, x, y):
        """
        Handles drop target behavior -- @@@ not yet implemented
        """
        pass

    # DraggableWidget

    def RemoveItem(self, itemUUID):
        """
        Handles drag source behavior -- @@@ not yet implemented
        """
        pass

class CollectionBlock(Block.RectangularChild):
    """
    @ivar selection: selected item
    @type selection: Item
    @ivar widget: widget associated with this block
    @type widget: wx.Window (usually wx.CollectionCanvas)
    """
    def __init__(self, *arguments, **keywords):
        super(CollectionBlock, self).__init__(*arguments, **keywords)
        self.selection = None

    # Event handling
    
    def onSelectionChangedEvent(self, notification):
        """
        Sets the block selection and synchronizes the widget.
        """
        self.selection = notification.data['item']
        self.widget.wxSynchronizeWidget()

    def postSelectionChanged(self):
        """
        Convenience method for posting a selection changed event.
        """
        event = Globals.repository.findPath('//parcels/osaf/framework/blocks/Events/SelectionChanged')
        self.Post(event, {'item':self.selection})

