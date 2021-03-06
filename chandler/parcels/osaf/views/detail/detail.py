#   Copyright (c) 2004-2008 Open Source Applications Foundation
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""
Classes for the ContentItem Detail View
"""
from __future__ import with_statement

__parcel__ = "osaf.views.detail"

import sys
import application
import re
from application import schema
from application.dialogs import ConflictDialog, RecurrenceDialog
from application.dialogs.CustomRecurrenceDialog import EditRecurrence
from osaf import pim
from osaf.pim.structs import SizeType, RectType
from osaf.framework.attributeEditors import (
     AttributeEditorMapping, DateAttributeEditor,
     EmailAddressAttributeEditor, TimeAttributeEditor, ChoiceAttributeEditor,
     StringAttributeEditor, StaticStringAttributeEditor)
from osaf.framework.blocks import (
     Block, ContainerBlocks, ControlBlocks, Menu,
     FocusEventHandlers, BranchPoint, ToolBar, debugName)
from osaf import sharing
import osaf.pim.mail as Mail
import osaf.pim.notes as notes
from osaf.pim.tasks import TaskStamp
import osaf.pim.calendar.Calendar as Calendar
import osaf.pim.calendar.Recurrence as Recurrence
from osaf.pim.calendar import TimeZoneInfo
from osaf.pim import ContentItem
#import osaf.mail.sharing as MailSharing
from chandlerdb.item.Item import Item
from osaf.pim.types import LocalizableString
import wx
import logging
import PyICU
from PyICU import ICUError
from datetime import datetime, time, timedelta
from i18n import ChandlerMessageFactory as _
from osaf import messages
from util import MultiStateButton
from util.triagebuttonimageprovider import TriageButtonImageProvider
import parsedatetime.parsedatetime as parsedatetime
import parsedatetime.parsedatetime_consts as ptc
from i18n import getLocale

logger = logging.getLogger(__name__)

# helper function
def BroadcastSelect(block, item):
    selection = []
    if item is not None:
        selection.append(item)
    sidebarBPB = block.findBlockByName("SidebarBranchPoint")
    sidebarBPB.childBlocks.first().postEventByName(
       'SelectItemsBroadcast', {'items':selection}
    )
    

class WatchedItemRootBlock(FocusEventHandlers):
    """
    UI that needs to track an item's attributes should inherit from WatchedItemRootBlock
    """
    # This gives us easy access to a proxied version of our contents; where
    # we want the unproxied version, we'll still use self.contents.
    item = property(fget=Block.Block.getProxiedContents, 
                    doc="Return the selected item, or None")

    def getWatchList(self):
        # Tell us if this item's kind changes.
        return [ (self.contents, 'itsKind') ]

    def onItemNotification(self, notificationType, data):
        self.markClean() # we'll do whatever needs to be done here.

        if notificationType != 'itemChange':
            return

        # Ignore notifications during stamping
        (op, uuid, attributes) = data
        item = self.itsView.findUUID(uuid, False)
        if item is None or item.isMutating():
            #logger.debug("%s: ignoring kind change to %s during stamping.", 
                         #debugName(self), debugName(item))
            return

        # It's for us - tell our parent to resync.
        parentBlock = getattr(self, 'parentBlock', None)
        if parentBlock is not None:
            #logger.debug("%s: Resyncing parent block due to kind change on %s", 
                         #debugName(self), debugName(self.contents))
            parentBlock.synchronizeWidget()

    def SelectedItems(self):
        """ 
        Return a list containing the item we're displaying.
        (This gets used for Send)
        """
        return getattr(self, 'contents', None) is not None and [ self.contents ] or []


class DetailRootBlock(WatchedItemRootBlock, ControlBlocks.ContentItemDetail):
    """
    Root of the Detail View. The prototype instance of this block is copied
    by the BranchPointBlock mechanism every time we build a detail view for a
    new distinct item type.
    """
    
    def onDestroyWidget(self):
        item = self.item
        
        if item is not None:
            item.endSession()
        super(DetailRootBlock, self).onDestroyWidget()
        
    def onSetContentsEvent(self, event):
        #logger.debug("%s: onSetContentsEvent: %s, %s", debugName(self), 
                     #event.arguments['item'], event.arguments['collection'])
        Block.Block.finishEdits()
        
        newItem = event.arguments['item']
        oldItem = self.item # Actually, a proxy
        
        if oldItem not in (None, newItem):
            oldItem.endSession()
            
        self.setContentsOnBlock(newItem, event.arguments['collection'])
        
        if newItem is not None:
            # Register with the RecurrenceDialog, so that hitting
            # the [Cancel] button causes the detail view to redraw
            # properly.
            callback = self.widgetGuardedCallback(self.synchronizeWidgetDeep)
            RecurrenceDialog.getProxy(u'ui', newItem, cancelCallback=callback)

            self.item.beginSession()

        # make sure other UI is notified about the item changing
        wx.GetApp().needsUpdateUI = True

    def onFocusSelectItemsEvent(self, event):
        items = event.arguments['items']
        if len(items) == 1:
            self.getRootBlock().postEventByName(
               'SelectItemsBroadcast', {'items': items}
            )
            focus = event.arguments.get('focus', None)
            focusTarget = self.findBlockByName(focus, self)
            if focusTarget is not None:
                focusTarget.widget.SetFocus()

        else:
            event.arguments['continueBubbleUp'] = True
        

    def onSendShareItemEvent (self, event):
        """
        Send or Share the current item.
        """
        # finish changes to previous selected item, then do it.
        Block.Block.finishEdits()
        super(DetailRootBlock, self).onSendShareItemEvent(event)

    def unRender(self):
        # There's a wx bug on Mac (2857) that causes EVT_KILL_FOCUS events to happen
        # after the control's been deleted, which makes it impossible to grab
        # the control's state on the way out. To work around this, the control
        # does nothing in its EVT_KILL_FOCUS handler if it's being deleted,
        # and we'll force the final update here.
        #logger.debug("DetailRoot: unrendering.")
        Block.Block.finishEdits()

        # then call our parent which'll do the actual unrender, triggering the
        # no-op EVT_KILL_FOCUS.
        super(DetailRootBlock, self).unRender()

    def focus(self):
        """
        Put the focus into the Detail View.
        """
        # Currently, just set the focus to the Title/Headline/Subject
        # Later we may want to support the "preferred" block for
        #  focus within a tree of blocks.
        
        titleBlock = self.findBlockByName('HeadlineBlock', hint=self)
        if titleBlock:
            # Defer the set focus and select-all ... otherwise,
            # on Windows, you get the text scrolled all the
            # way over to the right (probably a sizing issue?)
            # c.f.https://bugzilla.osafoundation.org/attachment.cgi?id=5063&action=edit
            def setFocus(block):
                block.widget.SetFocus()
                block.widget.SelectAll()
            wx.CallAfter(setFocus, titleBlock)

    def synchronizeWidgetDeep(self):
        """ Do synchronizeWidget recursively, depth-first. """
        def syncInside(block):
            # process from the children up
            map(syncInside, block.childBlocks)
            block.synchronizeWidget()

        if self.item is not None:
            self.widget.Freeze()
            try:
                syncInside(self)
            finally:
                self.widget.Thaw()

    def getWatchList(self):
        # Tell us if this item is modified
        return [ (self.contents, 'lastModified'),
                 (self.contents, 'itsKind') ] # Track item deletions

    def onItemNotification(self, notificationType, data):
        self.markClean() # we'll do whatever needs to be done here.

        if notificationType != 'itemChange':
            return

        # Ignore notifications during stamping
        (op, uuid, attributes) = data
        item = self.itsView.findUUID(uuid, False)
        if pim.isDead(item):
            # We don't want to be in the situation of having a deleted or
            # deleting item selected in the detail view, so we broadcast
            # a select of None
            BroadcastSelect(self, None)
            return

        if pim.has_stamp(item, Mail.MailStamp):
            wx.GetApp().needsUpdateUI = True

    def selectionEmptiedAfterDelete (self, selectedCollection, oldIndex):
        # when the last item in the selection is deleted, ask the sidebar
        # to select the next item
        sbpb = Block.Block.findBlockByName('SidebarBranchPoint')
        sbpb.childBlocks.first().postEventByName("SelectItemsBroadcast",
                             {'items': [],
                              'collection': selectedCollection })

class DetailBranchPointDelegate(BranchPoint.BranchPointDelegate):
    """ 
    Delegate for managing trees of blocks that compose the detail view.
    """    
    branchStub = schema.One(Block.Block, doc=
        """
        A stub block to copy as the root of each tree-of-blocks we build.
        Normally, this'll be a DetailRootBlock.
        """)

    schema.addClouds(
        copying = schema.Cloud(byRef=[branchStub])
    )

    def _mapItemToCacheKeyItem(self, item, hints):
        """ 
        Overrides to use the item's kind as our cache key.
        """
        if item is None or item.isDeleting():
            # We use Block's kind itself as the key for displaying "nothing";
            # Mimi wants a particular look when no item is selected; we've got a 
            # particular tree of blocks defined in parcel.xml for this Kind,
            # which will never get used for a real Item.
            return Block.Block.getKind(self.itsView)

        # The normal case: we have an item, so use its Kind
        # as the key.
        item = getattr(item, 'inheritFrom', item)
        return item.itsKind

    def _makeBranchForCacheKey(self, keyItem):
        """ 
        Handle a cache miss; build and return the detail tree-of-blocks
        for this keyItem, a Kind.
        """
        # Walk through the keys we have subtrees for, and collect subtrees to use;
        # we decide to use a subtree if _includeSubtree returns True for it.
        # Each subtree we find has children that are the blocks that are to be 
        # collected and sorted (by their 'position' attribute, then their paths
        # to be deterministic in the event of a tie) into the tree we'll use.
        # Blocks without 'position' attributes will naturally be sorted to the end.
        # If we were given a reference to a 'stub' block, we'll copy that and use
        # it as the root of the tree; otherwise, it's assumed that we'll only find
        # one subtree for our key, and use it directly.

        # (Yes, I wrote this as a double nested list comprehension with filtering, 
        # but I couldn't decide how to work in a lambda function, so I backed off and
        # opted for clarity.)
        decoratedSubtreeList = [] # each entry will be (position, path, subtreechild)

        itemKinds = set(keyItem.getInheritedSuperKinds())
        itemKinds.add(keyItem)
        for itemKind in itemKinds:
            subtreeAnnotation = BranchPoint.BranchSubtree(itemKind)
            rootBlocks = getattr(subtreeAnnotation, 'rootBlocks', None)
            if rootBlocks is not None:
                for block in rootBlocks:
                    entryTobeSorted = (getattr(block, 'position', sys.maxint),
                                       block.itsPath,
                                       self._copyItem(block))
                    decoratedSubtreeList.append(entryTobeSorted) 

        if len(decoratedSubtreeList) == 0:
            assert False, "Don't know how to build a branch for this kind!"
            # (We can continue here - we'll end up just caching an empty view.)

        decoratedSubtreeList.sort()

        # Copy our stub block and move the new kids on(to) the block
        branch = self._copyItem(self.branchStub)
        branch.childBlocks.extend([ block for position, path, block in decoratedSubtreeList ])
        return branch

class DetailSynchronizedBehavior(Item):
    """
    Mixin class that handles synchronization and notification common to most
    of the blocks in the detail view.
    """
    hiddenByUser = schema.One(schema.Boolean, initialValue=False)

    def onSetContentsEvent(self, event):
         #logger.debug("%s: onSetContentsEvent: %s, %s", debugName(self), 
                     #event.arguments['item'], event.arguments['collection'])
        self.setContentsOnBlock(event.arguments['item'],
                                 event.arguments['collection'])

    item = property(fget=Block.Block.getProxiedContents, 
                    doc="Return the selected item, or None")

    def synchronizeWidget(self):
        super(DetailSynchronizedBehavior, self).synchronizeWidget()
        self.show(self.item is not None and self.shouldShow(self.item))

    def shouldShow(self, item):
        hiddenByUser = getattr(self, 'hiddenByUser', False)
        return not hiddenByUser

    def show(self, shouldShow):
        # if the show status has changed, tell our widget, and return True
        try:
            widget = self.widget
        except AttributeError:
            return False
        if shouldShow == widget.IsShown():
            return False

        widget.Show(shouldShow)
        self.isShown = shouldShow
        #logger.debug("%s: now %s", debugName(self), 
                     #shouldShow and "visible" or "hidden")

        # Re-layout the sizer on the detail view
        block = self
        while block is not None:
            sizer = block.widget.GetSizer()
            if sizer:
                sizer.Layout()
            if block.eventBoundary:
                break
            block = block.parentBlock
        return True

    def onItemNotification(self, notificationType, data):
        self.markClean() # we'll do whatever needs to be done here.

        if notificationType != 'itemChange' or not hasattr(self, 'widget'):
            return

        # Ignore notifications during stamping or deleting
        (op, uuid, attributes) = data
        changedItem = self.itsView.findUUID(uuid, False)
        if pim.isDead(changedItem) or changedItem.isMutating():
            return

        #logger.debug("%s: Resyncing due to change on %s", 
                     #debugName(self), debugName(changedItem))
        self.synchronizeWidget()

class SynchronizedSpacerBlock(DetailSynchronizedBehavior, 
                              ControlBlocks.StaticText):
    """
    Generic Spacer Block class.
    """

class UnreadTimerBlock(DetailSynchronizedBehavior, ControlBlocks.Timer):
    """ A timer that sets the "read" attribute on any item we display. """
    def onSetContentsEvent(self, event):
        super(UnreadTimerBlock, self).onSetContentsEvent(event)

        # If this item isn't 'read' yet,
        # @@@ and isn't a recurrence (see bug 6702),
        # note that we'll need to set the timer to maybe mark it read.
        #
        # (We only want to bother with this when the item is first selected,
        # but we may not be rendered here, so set a flag; we'll check 
        # it at synchronize time, below.)
        item = getattr(self, 'item', None)
        self.checkReadState = (item is not None and not item.read)        

    def synchronizeWidget(self):
        super(DetailSynchronizedBehavior, self).synchronizeWidget()
        if getattr(self, 'checkReadState', False):
            self.checkReadState = False
            item = getattr(self, 'item', None) 
            if item is not None and not item.read:
                logger.debug("Setting unread timer for %s", debugName(item))
                self.setFiringTime(timedelta(seconds=1))
            else:
                logger.debug("Not setting unread timer for %s", debugName(item))
                self.setFiringTime(None)

    def onUnreadTimeoutEvent(self, event):
        # We change self.contents here because we want the unproxied item
        # (i.e. we don't want this showing up as a user edit).
        item = getattr(self, 'contents', None) 
        if item is not None:
            # changes to read/unread/needs reply should apply to all occurrences
            item = getattr(item, 'proxiedItem', item)
            item = pim.EventStamp(item).getMaster().itsItem
            logger.debug("Clearing unread flag for %s", debugName(item))
            item.read = True

class StaticTextLabelBlock(DetailSynchronizedBehavior, 
                           ControlBlocks.StaticText):
    def staticTextLabelValue(self, item):
        theLabel = self.title
        return theLabel

    def synchronizeLabel(self, value):
        label = self.widget.GetLabel()
        relayout = label != value
        if relayout:
            self.widget.SetLabel(value)
        return relayout

    def synchronizeWidget(self):
        super(StaticTextLabelBlock, self).synchronizeWidget()
        if self.item is not None:
            self.synchronizeLabel(self.staticTextLabelValue(self.item))

class DetailSynchronizedContentItemDetailBlock(DetailSynchronizedBehavior, 
                                               ControlBlocks.ContentItemDetail):
    pass

class DetailSynchronizedAttributeEditorBlock(DetailSynchronizedBehavior,
                                             ControlBlocks.AEBlock):
    """
    A L{ControlBlocks.AEBlock} that participates in detail view synchronization.
    """
    def OnDataChanged(self):
        # (this is how we find out about drag-and-dropped text changes!)
        self.saveValue()

    def OnFinishChangesEvent(self, event):
        self.saveValue()


class DetailTriageButtonBlock(DetailSynchronizedBehavior, ControlBlocks.Button):
    """
    A button that controls the triage state of an item
    """
    def instantiateWidget(self):
        id = self.getWidgetID()
        parentWidget = self.parentBlock.widget
        # Our images are composited by the TriageButtonImageProvider from images
        # named Markup.{Now,Later,Done}.Stamped{,Pressed,Rollover}.{Left,Right}
        self.icon = "Markup"
        multibitmaps = [ 
            MultiStateButton.BitmapInfo(
                stateName="%s.%s" % (self.icon, s.lower()),
                normal="%s.%s.Stamped" % (self.icon, s),
                selected="%s.%s.StampedPressed" % (self.icon, s),
                rollover="%s.%s.StampedRollover" % (self.icon, s))
            for s in "Now", "Later", "Done" ]
        button = ControlBlocks.wxChandlerMultiStateButton (parentWidget, 
            id, 
            wx.DefaultPosition,
            (self.minimumSize.width, self.minimumSize.height),
            helpString = self.helpString,
            multibitmaps = multibitmaps,
            bitmapProvider=TriageButtonImageProvider("Markup.Now.Stamped.png"))

        # For some reason, wx.lib.buttons.GenButton only binds to
        # double-click on windows. So, to get double-click working
        # as in Bug 11911, we enable this on non-Windows platforms, too.
        if wx.Platform != '__WXMSW__':
            button.Bind(wx.EVT_LEFT_DCLICK, self.buttonPressed, id=id)

        parentWidget.Bind(wx.EVT_BUTTON, self.buttonPressed, id=id)
        return button
    
    def getState(self):
        """ If this button has state, return it. """
        state = getattr(self.widget, 'currentState', '')
        dotIndex = state.index('.')
        if dotIndex != -1:
            state = state[dotIndex+1:]
        return state

    def synchronizeWidget(self):
        super(DetailTriageButtonBlock, self).synchronizeWidget()
        self.setState()

    def setState(self):
        # this button to reflect the kind of the selected item
        item = self.item
        if item is not None:
            self.widget.SetState("%s.%s" % (self.icon, item.triageStatus))

    def onButtonPressedEvent(self, event):
        oldState = getattr(self.widget, 'currentState', None)
        if oldState != None:
            assert oldState.startswith('Markup.')
            newState = pim.getNextTriageStatus(getattr(pim.TriageEnum,
                                                       oldState[7:]))
            # always make triage changes apply to the this occurrence
            item = pim.CHANGE_THIS(self.item)
            item.setTriageStatus(newState, pin=True)
            item.resetAutoTriageOnDateChange()
            self.setState()

    def onButtonPressedEventUpdateUI(self, event):
        item = self.item
        enable = item is not None and item.isAttributeModifiable('_triageStatus')
        event.arguments ['Enable'] = enable

class DetailStampButtonBlock(DetailSynchronizedBehavior, 
                             ControlBlocks.StampButton):
    """
    Common base class for the stamping buttons in the Markup Bar.
    """
    unstampedHelpString = schema.One(LocalizableString, initialValue = u'')

    def getWatchList(self):
        # Tell us if this item's stamps change.
        return [ (self.item, pim.Stamp.stampCollections.name) ]

    @property
    def stampClass(self):
        # return the class of this stamp's Mixin Kind (bag of kind-specific attributes)
        raise NotImplementedError, "%s.stampClass()" % (type(self))

    def synchronizeWidget(self):
        super(DetailStampButtonBlock, self).synchronizeWidget()

        # toggle this button to reflect the kind of the selected item
        item = self.item
        if item is not None:
            stampClass = self.stampClass
            if isinstance(item, stampClass.targetType()):
                stamped = pim.has_stamp(item, stampClass)
                if stamped:
                    self.widget.SetToolTipString(self.unstampedHelpString)
                else:
                    self.widget.SetToolTipString(self.helpString)
                self.widget.SetState("%s.%s" % (self.icon,
                                     stamped and "Stamped" or "Unstamped"))
            else:
                self.widget.SetState("%s.%s" % (self.icon, "Unstamped"))

    def onButtonPressedEvent(self, event):
        # Add or remove the associated Stamp type
        Block.Block.finishEdits()
        item = self.item
        if item is None or not self._isStampable(item):
            return

        stampClass = self.stampClass
        if pim.has_stamp(item, stampClass):
            stampClass(item).remove()
        else:
            startTimeExists = hasattr(item, pim.EventStamp.startTime.name)
            stampClass(item).add()

            if stampClass == Calendar.EventStamp and not startTimeExists:
                # If the item is being stamped as CalendarEvent, parse the body
                # of the item for date/time information, if the item does not
                # already have a startTime. 
                startTime, endTime, countFlag, typeFlag = \
                         pim.calendar.Calendar.parseText(self.itsView, item.body)

                statusMsg = { 0:_(u"No date/time found."),
                              1:_(u"Event set to the date/time found."),
                              2:_(u"Multiple date/times found.")}

                # Set the appropriate status message in the status bar
                wx.GetApp().CallItemMethodAsync("MainView", 'setStatusMessage',
                                                statusMsg[countFlag])

                # Set the event's start and end date/time
                pim.calendar.Calendar.setEventDateTime(item, startTime, endTime,
                                                       typeFlag)


    def onButtonPressedEventUpdateUI(self, event):
        item = self.item
        enable = not pim.isDead(item) and self._isStampable(item) and \
               item.isAttributeModifiable('displayName')
        event.arguments ['Enable'] = enable

    def _isStampable(self, item):
        return isinstance(item, self.stampClass.targetType())

class MailMessageButtonBlock(DetailStampButtonBlock):
    """ Mail Message Stamping button in the Markup Bar. """
    stampClass = Mail.MailStamp

class CalendarStampButtonBlock(DetailStampButtonBlock):
    """ Calendar button in the Markup Bar. """
    stampClass = Calendar.EventStamp

class TaskStampButtonBlock(DetailStampButtonBlock):
    """ Task button in the Markup Bar. """
    stampClass = TaskStamp

class PrivateSwitchButtonBlock(DetailSynchronizedBehavior, 
                               ControlBlocks.StampButton):
    """ "Never share" button in the Markup Bar. """
    def synchronizeWidget(self):
        # toggle this button to reflect the privateness of the selected item        
        super(PrivateSwitchButtonBlock, self).synchronizeWidget()
        if self.item is not None:
            self.widget.SetState("%s.%s" % (self.icon,
                                 self.item.private and "Stamped" or "Unstamped"))

    def onButtonPressedEvent(self, event):
        item = self.item
        if item is not None:
            self.postEventByName("FocusTogglePrivate", {'items': [item]})
            # in case the user canceled the dialog, reset markupbar buttons
            self.widget.SetState("%s.%s" % (self.icon,
                                 self.item.private and "Stamped" or "Unstamped"))

    def onButtonPressedEventUpdateUI(self, event):
        item = self.item            
        enable = item is not None and item.isAttributeModifiable('displayName')
        event.arguments ['Enable'] = enable


class ReadOnlyIconBlock(DetailSynchronizedBehavior, ControlBlocks.StampButton):
    """
    "Read Only" icon in the Markup Bar.
    """
    def synchronizeWidget(self):
        # toggle this icon to reflect the read only status of the selected item
        super(ReadOnlyIconBlock, self).synchronizeWidget()

        checked = self.item is not None and sharing.isReadOnly(self.item)
        self.widget.SetState("%s.%s" % (self.icon,
                                        "Stamped" if checked else "Unstamped"))
        if not checked:
            self.widget.SetToolTipString("")

    def onButtonPressedEvent(self, event):
        # We don't actually allow the read only state to be toggled
        pass

    def onButtonPressedEventUpdateUI(self, event):
        """
        Always enable the read-only icon's event.  This causes it to be
        clickable (and the click does nothing), which isn't great, but that
        seems preferable to not displaying a tooltip, which is what happens at
        least on Windows if the button is disabled.
        
        Read-only doesn't really need to be a StampButton, it could be plain
        button that gets hidden in most cases.
        """
        event.arguments ['Enable'] = True

class NewDetailConditionalBehavior(Item):
    def shouldShow(self, item):
        return self.getRootBlock().blockName == u'MainViewRoot'

class NewDetailSpacer(NewDetailConditionalBehavior, ControlBlocks.StaticText):
    pass
    
class NewDetailViewButton(NewDetailConditionalBehavior,
                          DetailSynchronizedBehavior, ControlBlocks.Button):
    """
    "New Detail View" in the markup bar
    """
    def instantiateWidget(self):
        id = self.getWidgetID()
        parentWidget = self.parentBlock.widget

        # for a stamp button, we use "self.icon" as the base name of all bitmaps and look for:
        #
        #   {icon}Normal, {icon}Stamped, {icon}Rollover, {icon}Pressed, {icon}Disabled
        #
        # From these we build two states suffixed "unstamped" and "stamped", which can
        # be used the toggle the appearance of the button.
        #
        assert len(self.icon) > 0
        bminfo = MultiStateButton.BitmapInfo()
        bminfo.normal   = "%sNormal" % self.icon
        bminfo.rollover = "%sRollover" % self.icon
        bminfo.selected = "%sMousedown" % self.icon
        button = ControlBlocks.wxChandlerMultiStateButton(parentWidget, 
                            id, 
                            wx.DefaultPosition,
                            (self.minimumSize.width, self.minimumSize.height),
                            helpString = self.helpString,
                            multibitmaps=(bminfo,))
        button.Bind(wx.EVT_BUTTON, self.buttonPressed)

        return button

    def buttonPressed(self, event):
        self.post(self.event, { 'items' : [self.contents] })

# @@@ Needs to be rewritten as an attribute editor when attachments become important again.
#class AttachmentAreaBlock(DetailSynchronizedContentItemDetailBlock):
    #"""
    #An area visible only when the item (a mail message) has attachments.
    #"""
    #def shouldShow (self, item):
        #return super(AttachmentAreaBlock, self).shouldShow(item) and  item is not None and item.hasAttachments()
#class AttachmentTextFieldBlock(EditTextAttributeBlock):
    #"""
    #A read-only list of email attachments, for now.
    #"""
    #def loadAttributeIntoWidget (self, item, widget):
        ## For now, just list the attachments' filenames
        #if item is None or not item.hasAttachments():
            #value = ""
        #else:
            #value = ", ".join([ attachment.filename for attachment in item.getAttachments() if hasattr(attachment, 'filename') ])
        #widget.SetValue(value)

# @@@ disabled until we start using this UI again
#class AcceptShareButtonBlock(DetailSynchronizedBehavior, ControlBlocks.Button):
    #def shouldShow(self, item):
        #showIt = False
        #if item is not None and not pim.mail.MailStamp(item).isOutbound and super(AcceptShareButtonBlock, self).shouldShow(item):
            #try:
                #MailSharing.getSharingHeaderInfo(item)
            #except:       
                #pass
            #else:
                #showIt = True
        ## logger.debug("AcceptShareButton.shouldShow = %s", showIt)
        #return showIt

    #def onAcceptShareEvent(self, event):
        #url, collectionName = MailSharing.getSharingHeaderInfo(self.item)
        #statusBlock = Block.Block.findBlockByName('StatusBar')
        #statusBlock.setStatusMessage( _(u'Subscribing to collection...') )
        #wx.GetApp().Yield(True)

        ## If this code is ever revived, it should call sharing.subscribe(),
        ## rather than the following:
        ### share = sharing.Share(itsView=self.itsView)
        ### share.configureInbound(url)
        ### share.get()

        #statusBlock.setStatusMessage( _(u'Subscribed to collection') )

        ## @@@ Remove this when the sidebar autodetects new collections
        #collection = share.contents
        #schema.ns("osaf.app", self.itsView).sidebarCollection.add (share.contents)
        ## Need to SelectFirstItem -- DJA

    #def onAcceptShareEventUpdateUI(self, event):
        ## If we're already sharing it, we should disable the button and change the text.
        #enabled = True
        #item = self.item
        #try:
            #url, collectionName = MailSharing.getSharingHeaderInfo(item)
            #existingSharedCollection = sharing.findMatchingShare(self.itsView, url)
        #except:
            #enabled = True
        #else:
            #if existingSharedCollection is not None:
                #self.widget.SetLabel(_(u"(Already sharing this collection)"))
                #enabled = False
        #event.arguments['Enable'] = enabled

def getAppearsInNames(item):
    # Only a recurrence master appears 'in' the collection (for 0.6, anyway)
    # so if this item lets us get its master, do so and use that instead.
    if pim.has_stamp(item, pim.EventStamp):
        item = pim.EventStamp(item).getMaster().itsItem

    sidebar = schema.ns('osaf.app', item.itsView).sidebarCollection
    names = [c.displayName for c in getattr(item, 'appearsIn', ())
             if hasattr(c, 'displayName') and c in sidebar]
    names.sort()
    # L10N: Character separator used when listing collections an item appears in
    return _(u", ").join(names)

class AppearsInAEBlock(DetailSynchronizedAttributeEditorBlock):
    def shouldShow(self, item):
        return super(AppearsInAEBlock, self).shouldShow(item) and len(getAppearsInNames(item)) > 0

class AppearsInAttributeEditor(StaticStringAttributeEditor):
    """
    A read-only list of collections that this item appears in, for now.
    """
    def GetAttributeValue(self, item, attributeName):
        collectionNames = getAppearsInNames(item)

        # logger.debug("Returning new appearsin list: %s" % collectionNames)
        # @@@ I18N: FYI: I expect the label & names to be separate fields before too long...
        return _(u"Appears in: %(collectionNames)s") \
               % {'collectionNames': collectionNames }

# Classes to support blocks that are only shown if the item has a particular
# stamp
class StampConditionalBehavior(Item):
    """
    An C{Item} subclass designed to mixed in with a block that also has
    C{DetailSynchronizedBehavior} mixed into it. Its C{shouldShow()} method
    only allows items that have a certain stamp. If you subclass to add extra
    conditions in C{shouldShow()}, make sure to check C{super}'s value
    first.

    @ivar stampClass: Items must have been stamped with this C{Stamp} subclass
                      for C{shouldShow()} to return C{True}.
    @type stampClass: C{type}
    """
    stampClass = None

    def shouldShow(self, item):
        assert self.stampClass is not None
        return super(StampConditionalBehavior, self).shouldShow(item) and \
               pim.has_stamp(item, self.stampClass)

    def getWatchList(self):
        watchList = super(StampConditionalBehavior, self).getWatchList()
        watchList.extend(((self.item, pim.Stamp.stampCollections.name),),)
        return watchList

class MailConditionalBehavior(StampConditionalBehavior):
    """
    A C{StampConditionalBehavior} subclass that checks for
    C{osaf.pim.mail.MailStamp}"
    """
    stampClass = pim.mail.MailStamp

class EventConditionalBehavior(StampConditionalBehavior):
    """
    A C{StampConditionalBehavior} subclass that checks for C{osaf.pim.EventStamp}"
    """
    stampClass = pim.EventStamp

class TaskConditionalBehavior(StampConditionalBehavior):
    """
    A C{StampConditionalBehavior} subclass that checks for C{osaf.pim.TaskStamp}"
    """
    stampClass = pim.TaskStamp

class MailAreaBlock(MailConditionalBehavior, 
                    DetailSynchronizedContentItemDetailBlock):
    pass

class EventAreaBlock(EventConditionalBehavior, 
                     DetailSynchronizedContentItemDetailBlock):
    pass

class TaskAreaBlock(TaskConditionalBehavior, 
                    DetailSynchronizedContentItemDetailBlock):
    pass

class ConflictConditionalBehaviour(Item):
    def shouldShow(self, item):
        superShouldShow = super(ConflictConditionalBehaviour, self).shouldShow(item)
        isShowable = False
        if superShouldShow and sharing.hasConflicts(self.item):
            isShowable = True
        return isShowable

    def getWatchList(self):
        watchList = super(ConflictConditionalBehaviour, self).getWatchList()
        watchList.append((self.item, sharing.SharedItem.conflictingStates.name))
        return watchList

class ConflictSpacerBlock(ConflictConditionalBehaviour, SynchronizedSpacerBlock):
    pass

# Clickable area that shows/hides itself based on the presence/absence 
# of sharing conflicts
class ConflictWarningButton(ConflictConditionalBehaviour,
                            DetailSynchronizedBehavior, ControlBlocks.Button):
    def instantiateWidget(self):
        # create the button
        drawstyle = {
            "text-align": "left",
            "indent": 6
        }
        button = super(ConflictWarningButton, self).instantiateWidget(drawstyle)
        if button is not None:
            button.SetBackgroundColour('Red') 
            button.SetForegroundColour('White')
            # clicking on it resolves the conflict
            button.Bind(wx.EVT_BUTTON, self.resolveConflict)
        return button

    def synchronizeWidget(self):
        widget = getattr(self, 'widget', None)
        if widget is not None and sharing.hasConflicts(self.item):
            item = getattr(self.item, 'proxiedItem', self.item)
            conflicts = list(sharing.getConflicts(item))
            conflictCount = len(conflicts)
            if conflictCount > 1:
                fmt = _(u"VIEW %(count)d PENDING CHANGES")
                widget.SetLabel(fmt  % { 'count': len(conflicts) })
            else:
                widget.SetLabel(_(u'VIEW 1 PENDING CHANGE'))
        super(ConflictWarningButton, self).synchronizeWidget()

    def resolveConflict(self, event):
        # show the dialog here
        item = getattr(self.item, 'proxiedItem', self.item)
        dialog = ConflictDialog.ConflictDialog(list(sharing.getConflicts(item)))
        dialog.CenterOnScreen()
        dialog.ShowModal()
        dialog.Destroy()
        self.markDirty()

# Classes to support CalendarEvent details - first, areas that show/hide
# themselves based on readonlyness and attribute values

class CalendarAllDayAreaBlock(EventConditionalBehavior, 
                              DetailSynchronizedContentItemDetailBlock):
    def shouldShow(self, item):
        return (super(CalendarAllDayAreaBlock, self).shouldShow(item) and
            item.isAttributeModifiable(pim.EventStamp.allDay.name))

    def getWatchList(self):
        watchList = super(CalendarAllDayAreaBlock, self).getWatchList()
        watchList.append((self.item, pim.EventStamp.allDay.name))
        return watchList

class CalendarLocationAreaBlock(EventConditionalBehavior, 
                                DetailSynchronizedContentItemDetailBlock):
    def shouldShow(self, item):
        attributeName = pim.EventStamp.location.name
        return (super(CalendarLocationAreaBlock, self).shouldShow(item) and 
                (item.isAttributeModifiable(attributeName) or
                 hasattr(item, attributeName)))

    def getWatchList(self):
        watchList = super(CalendarLocationAreaBlock, self).getWatchList()
        watchList.append((self.item, pim.EventStamp.location.name))
        return watchList

class TimeConditionalBehavior(EventConditionalBehavior):
    def shouldShow(self, item):
        event = pim.EventStamp(item)
        return (super(TimeConditionalBehavior, self).shouldShow(item) and
                not event.allDay and
                (item.isAttributeModifiable(pim.EventStamp.startTime.name)
                or not event.anyTime))

    def getWatchList(self):
        watchList = super(TimeConditionalBehavior, self).getWatchList()
        watchList.extend(((self.item, pim.EventStamp.allDay.name), 
                          (self.item, pim.EventStamp.anyTime.name)))
        return watchList

class CalendarConditionalLabelBlock(TimeConditionalBehavior, 
                                    StaticTextLabelBlock):
    pass    

class CalendarTimeAEBlock(TimeConditionalBehavior,
                          DetailSynchronizedAttributeEditorBlock):
    pass

#
# Reminders
#

def timeDeltaMinutes(td):
    """
    Return the number of minutes in this timeDelta. 
    Discards seconds and microseconds.
    """
    return (td.days * 1440) + (td.seconds // 60)

def timeDeltaDetails(td):
    """
    Return (units, scale, isAfter) for this timeDelta,
    where 'units' is a positive integer, and scale is 0 (minutes),
    1 (hours), or 2 (days), and isAfter is True if the original
    timeDelta was greater than zero.
    """
    delta = timeDeltaMinutes(td)
    if delta > 0:
        isAfter = True
    else:
        isAfter = False
        delta = abs(delta)

    if delta % 1440 == 0:
        return (delta / 1440, 2, isAfter) # it's a whole number of days
    if delta % 60 == 0:
        return (delta / 60, 1, isAfter) # it's a whole number of hours
    return (delta, 0, isAfter) # Use minutes

def scaleTimeDelta(units, scale, isAfter):
    """
    The reverse of timeDeltaDetails
    """
    if not isAfter:
        units *= -1
    if scale == 0:
        return timedelta(minutes=units)
    if scale == 1:
        return timedelta(hours=units)
    assert scale == 2
    return timedelta(days=units)

def getReminderType(item):
    """ 
    What kind of user reminder is this?
    Returns 'none', 'before', 'after', or 'custom'
    """
    if getattr(item, pim.Remindable.userReminderTime.name, None) is not None:
        return 'custom'
    delta = getattr(item, pim.EventStamp.userReminderInterval.name, None)
    if delta is None:
        return 'none'

    deltaMinutes = timeDeltaMinutes(delta)
    return deltaMinutes > 0 and 'after' or 'before'

class ReminderConditionalBehavior(Item):
    def shouldShow(self, item):
        # Don't show if we have no reminder and the user can't add one.
        if item is None:
            return False
        reminder = item.getUserReminder()
        return(reminder is not None or
                item.isAttributeModifiable(pim.Remindable.reminders.name))

    def getWatchList(self):
        watchList = super(ReminderConditionalBehavior, self).getWatchList()
        watchList.extend([(self.item, pim.Remindable.reminders.name)])
        return watchList

class ReminderSpacerBlock(ReminderConditionalBehavior,
                          SynchronizedSpacerBlock):
    pass

class ReminderTypeAreaBlock(ReminderConditionalBehavior,
                            DetailSynchronizedContentItemDetailBlock):
    def getWatchList(self):
        watchList = super(ReminderTypeAreaBlock, self).getWatchList()
        watchList.append((self.item, pim.Stamp.stampCollections.name))
        return watchList

class ReminderRelativeAreaBlock(ReminderConditionalBehavior,
                                DetailSynchronizedContentItemDetailBlock):
    def shouldShow(self, item):
        return (super(ReminderRelativeAreaBlock, self).shouldShow(item) and
                (getReminderType(item) in ('before', 'after')))

class ReminderAbsoluteAreaBlock(ReminderConditionalBehavior,
                                DetailSynchronizedContentItemDetailBlock):
    def shouldShow(self, item):
        return (super(ReminderAbsoluteAreaBlock, self).shouldShow(item) and
                (getReminderType(item) == 'custom'))

class ReminderAEBlock(ReminderConditionalBehavior,
                      DetailSynchronizedAttributeEditorBlock):
    def getWatchList(self):
        watchList = super(ReminderAEBlock, self).getWatchList()
        watchList.extend([(self.item, pim.Remindable.reminders.name),
                          (self.item, pim.EventStamp.rruleset.name),
                          (self.item, pim.Stamp.stampCollections.name)])
        return watchList
        
class AbsoluteReminderAEBlock(ReminderAEBlock):
    proxyFactory = staticmethod(pim.CHANGE_THIS)

class ReminderTypeAttributeEditor(ChoiceAttributeEditor):
    reminderIndexes = {
        'none': 0,
        'before': 1,
        'after': 2,
        # Custom omitted - see below.
    }

    def GetControlValue(self, control):
        """
        Get the value from the control: 'none', 'before', 'after',
        or 'custom'
        """
        index = control.GetSelection()
        return (index != wx.NOT_FOUND) and control.GetClientData(index) or 'none'

    def SetControlValue(self, control, value):
        """
        Select the choice that matches this value ('none', 'before', 'after',
        or 'custom')
        """
        # Populate the menu if necessary
        #existingSelectionIndex = control.GetSelection()
        #existingValue = (existingSelectionIndex != wx.NOT_FOUND) \
        #              and control.GetClientData(existingSelectionIndex) \
        #              or None
        isEvent = pim.has_stamp(self.item, pim.EventStamp)

        # @@@ For now, always rebuild the list, so we can remove or add the 
        # Custom choice when recurrence changes.
        if True: # existingValue != value or control.GetCount() != (isEvent and 4 or 2):
            # rebuild the list of choices
            control.Clear()
            # L10N: Entry in the 'alarm' drop-down menu in the detail view
            # L10N: when an item has no alarm. In English, this is translated
            # L10N: as "None", but I didn't want to use "None" in a msgid
            # L10N: because that could be used in other contexts (e.g. the
            # L10N: "timezone" dropdown).
            control.Append(_(u"None (alarm)"), 'none')
            if isEvent:
                control.Append(_(u"Before event"), 'before')
                control.Append(_(u"After event"), 'after')
            control.Append(_(u"Custom"), 'custom')

        # Which choice to select?
        choiceIndex = self.reminderIndexes.get(value, isEvent and 3 or 1)
        control.Select(choiceIndex)

    def GetAttributeValue(self, item, attributeName):
        """
        Get the value from the specified attribute of the item.
        """
        return getReminderType(item)

    def SetAttributeValue(self, item, attributeName, value):
        """
        Set the value of the attribute given by the value.
        """
        if self.ReadOnly((item, attributeName)):
            return

        reminderType = getReminderType(item)
        if value == reminderType:
            return

        self.control.blockItem.stopWatchingForChanges()
        if value == 'none':
            setattr(item, pim.Remindable.userReminderTime.name, None)
            setattr(item, pim.EventStamp.userReminderInterval.name, None)            
        elif value in ('before', 'after'):
            if reminderType in ('before', 'after'):
                # Just change the sign of the old reminder
                delta = getattr(item, pim.EventStamp.userReminderInterval.name)
                (units, scale, isAfter) = timeDeltaDetails(delta)
                setattr(item, pim.EventStamp.userReminderInterval.name,
                        scaleTimeDelta(units, scale, not isAfter))
            else:
                # Make a new 15-minute reminder with the right sign.
                setattr(item, pim.EventStamp.userReminderInterval.name,
                        scaleTimeDelta(15, 0, value == 'after'))
        else:
            assert value == 'custom'
            # Make a reminder at the default new reminder time
            item = pim.CHANGE_THIS(item)
            
            item.userReminderTime= pim.Reminder.defaultTime(item.itsView)

        self.control.blockItem.watchForChanges()

        item.setTriageStatus('auto', pin=True)

        if False:
            active = "\n  ".join(unicode(r) for r in remindable.reminders) or "None"
            logger.debug("Reminders on %s:\n  Expired:\n    %s", 
                         remindable, active)

class ReminderScaleAttributeEditor(ChoiceAttributeEditor):
    choices = [_(u'minutes'),
                _(u'hours'),
                _(u'days')]

    def GetChoices(self):
        return self.choices

    def GetAttributeValue(self, item, attributeName):
        reminderType = getReminderType(item)
        if reminderType not in ('before', 'after'):
            return 0
        delta = getattr(item, pim.EventStamp.userReminderInterval.name)
        (units, scale, isAfter) = timeDeltaDetails(delta)
        return scale

    def SetAttributeValue(self, item, attributeName, value):
        if value is None:
            return
        reminderType = getReminderType(item)
        if reminderType not in ('before', 'after'):
            return

        delta = getattr(item, pim.EventStamp.userReminderInterval.name)
        (units, scale, isAfter) = timeDeltaDetails(delta)
        if scale == value:
            return # unchanged

        setattr(item, attributeName, scaleTimeDelta(units, value, isAfter))
        item.setTriageStatus('auto', pin=True)

    def GetControlValue(self, control):
        choiceIndex = control.GetSelection()
        return None if choiceIndex == wx.NOT_FOUND else choiceIndex

    def SetControlValue(self, control, value):
        existingValue = self.GetControlValue(control)
        if existingValue is None or existingValue != value:
            # rebuild the list of choices
            choices = self.GetChoices()
            if len(choices) != control.GetCount():
                control.Clear()
                control.AppendItems(choices)
            control.SetSelection(value)

class ReminderUnitsAttributeEditor(StringAttributeEditor):    
    def GetAttributeValue(self, item, attributeName):
        # Get the existing reminder, and figure out what kind it is
        reminderType = getReminderType(item)
        if reminderType not in ('before', 'after'):
            return u''

        # Pick an appropriate scale for this delta value
        delta = getattr(item, pim.EventStamp.userReminderInterval.name)
        (units, scale, isAfter) = timeDeltaDetails(delta)
        return unicode(units)

    def SetAttributeValue(self, item, attributeName, valueString):
        reminderType = getReminderType(item)
        if reminderType not in ('before', 'after'):
            assert False
            return

        valueString = valueString.replace('?','').strip()
        if len(valueString) == 0:
            # Put the old value back.
            self.SetControlValue(self.control, 
                                 self.GetAttributeValue(item, attributeName))
            return
        try:
            value = int(valueString)                
        except ValueError:
            self._changeTextQuietly(self.control, "%s ?" % valueString)
            return

        delta = getattr(item, pim.EventStamp.userReminderInterval.name)
        (units, scale, isAfter) = timeDeltaDetails(delta)
        if units != value:
            setattr(item, pim.EventStamp.userReminderInterval.name,
                    scaleTimeDelta(value, scale, isAfter))
            item.setTriageStatus('auto', pin=True)

    def IsValidForWriteback(self, valueString):
        try:
            int(valueString)
        except ValueError:
            return False
        return True

class TransparencyConditionalBehavior(EventConditionalBehavior):
    def shouldShow(self, item):
        # don't show for anyTime or @time events (but do show for allDay
        # events, which happen to be anyTime too)
        if not super(TransparencyConditionalBehavior, self).shouldShow(item):
            return False
        event = pim.EventStamp(item)
        if event.allDay:
            return True
        return (not event.anyTime) and bool(event.duration)

    def getWatchList(self):
        watchList = super(TransparencyConditionalBehavior, self).getWatchList()
        watchList.extend(((self.item, pim.EventStamp.anyTime.name), 
                          (self.item, pim.EventStamp.allDay.name), 
                          (self.item, pim.EventStamp.duration.name)))
        return watchList

class CalendarTransparencySpacerBlock(TransparencyConditionalBehavior, 
                                      SynchronizedSpacerBlock):
    pass

class CalendarTransparencyAreaBlock(TransparencyConditionalBehavior, 
                                    DetailSynchronizedContentItemDetailBlock):
    pass

class TimeZoneConditionalBehavior(EventConditionalBehavior):
    def shouldShow(self, item):
        # Only show for events
        if not super(TimeZoneConditionalBehavior, self).shouldShow(item):
            return False
        # allDay and anyTime items never show the timezone popup
        event = pim.EventStamp(item)
        if event.allDay or event.anyTime:
            return False

        # Otherwise, it depends on the preference
        tzPrefs = schema.ns('osaf.pim', item.itsView).TimezonePrefs
        return tzPrefs.showUI

    def getWatchList(self):
        watchList = super(TimeZoneConditionalBehavior, self).getWatchList()
        tzPrefs = schema.ns('osaf.pim', self.itsView).TimezonePrefs
        watchList.extend(((self.item, pim.EventStamp.allDay.name),
                          (self.item, pim.EventStamp.anyTime.name),
                          (tzPrefs, 'showUI')))
        return watchList

class CalendarTimeZoneSpacerBlock(TimeZoneConditionalBehavior, 
                                  SynchronizedSpacerBlock):
    pass

class CalendarTimeZoneAreaBlock(TimeZoneConditionalBehavior, 
                                DetailSynchronizedContentItemDetailBlock):
    pass

class CalendarTimeZoneAEBlock(DetailSynchronizedAttributeEditorBlock):
    def getWatchList(self):
        watchList = super(CalendarTimeZoneAEBlock, self).getWatchList()
        timezones = TimeZoneInfo.get(self.itsView)
        watchList.append((timezones, 'wellKnownIDs'))
        return watchList

class RecurrenceConditionalBehavior(EventConditionalBehavior):
    # Centralize the recurrence blocks' visibility decisions. Subclass will
    # declare a visibilityFlags class member composed of these bit values:
    showPopup = 1 # Show the area containing the popup
    showCustom = 2 # Show the area containing the "custom" static string
    showEnds = 4 # Show the area containing the end-date editor

    def recurrenceVisibility(self, item):
        result = 0
        if super(RecurrenceConditionalBehavior, self).shouldShow(item):
            freq = RecurrenceAttributeEditor.mapRecurrenceFrequency(item)
            modifiable = item.isAttributeModifiable(pim.EventStamp.rruleset.name)

            # Show the popup only if it's modifiable, or if it's not
            # modifiable but not the default value.
            if modifiable or (freq != RecurrenceAttributeEditor.onceIndex):
                result |= self.showPopup

                if freq == RecurrenceAttributeEditor.customIndex:
                    # We'll show the "custom" flag only if we're custom, duh.
                    result |= self.showCustom | self.showEnds
                elif freq != RecurrenceAttributeEditor.onceIndex:
                    # We're not custom and not "once": We'll show "ends" if we're 
                    # modifiable, or if we have an "ends" value.
                    if modifiable:
                        result |= self.showEnds
                    else:
                        event = pim.EventStamp(item)
                        try:
                            endDate = event.rruleset.rrules.first().until
                        except AttributeError:
                            pass
                        else:
                            result |= self.showEnds
        return result

    def shouldShow(self, item):
        assert self.visibilityFlags
        return super(RecurrenceConditionalBehavior, self).shouldShow(item) \
               and (self.recurrenceVisibility(item) & self.visibilityFlags) != 0

    def getWatchList(self):
        watchList = super(RecurrenceConditionalBehavior, self).getWatchList()
        watchList.append((self.item, pim.EventStamp.rruleset.name))
        if self.visibilityFlags & RecurrenceConditionalBehavior.showEnds:
            event = pim.EventStamp(self.item)
            try:
                firstRRule = event.rruleset.rrules.first()
            except AttributeError:
                pass
            else:
                watchList.append((firstRRule, 'until'))
        return watchList

class CalendarRecurrencePopupSpacerBlock(RecurrenceConditionalBehavior,
                                         SynchronizedSpacerBlock):
    visibilityFlags = RecurrenceConditionalBehavior.showPopup

class CalendarRecurrencePopupAreaBlock(RecurrenceConditionalBehavior,
                                       DetailSynchronizedContentItemDetailBlock):
    visibilityFlags = RecurrenceConditionalBehavior.showPopup


class CalendarRecurrenceAEBlock(DetailSynchronizedAttributeEditorBlock):
    """
    Subclass to deal with the fact that, for recurrence, we are really
    observing attributes of the first rrule of the rruleset of the
    item in question, not the item itself.
    
    By extending our watch list, we can make sure we can respond to changes
    in the rrule itself, as in Bug 8821.
    
    @cvar rruleAttribute: The name of the rrule attribute this block is
                          is interested in. Defaults to C{None} (i.e.
                          don't watch any rrule attribute.
    @type rruleAttribute: str
    """
    rruleAttribute = None
    
    def getWatchList(self):
        watchList = super(DetailSynchronizedAttributeEditorBlock,
                          self).getWatchList()
        rruleset = pim.EventStamp(self.item).rruleset

        if rruleset is not None:
            # Make sure we watch for changes in rrules ...
            watchList.append((rruleset, 'rrules'))
            
            attrName = self.rruleAttribute
            
            # ... as well as the rrule attribute we're interested in
            # (if any). In theory, we should watch all rrules here, 
            # of course.
            if attrName is not None:
                rrules = getattr(rruleset, 'rrules', ())
                if rrules:
                    watchList.append((rrules.first(), attrName))
        
        return watchList
        
class CalendarFrequencyAEBlock(CalendarRecurrenceAEBlock):
    rruleAttribute = 'freq'
    
class CalendarUntilAEBlock(CalendarRecurrenceAEBlock):
    rruleAttribute = 'until'


class CalendarRecurrenceSpacer2Area(RecurrenceConditionalBehavior,
                                    DetailSynchronizedBehavior, 
                                    ControlBlocks.StaticText):
    visibilityFlags = RecurrenceConditionalBehavior.showPopup | \
                    RecurrenceConditionalBehavior.showEnds

class CalendarRecurrenceCustomSpacerBlock(RecurrenceConditionalBehavior,
                                          SynchronizedSpacerBlock):
    visibilityFlags = RecurrenceConditionalBehavior.showCustom

class CalendarRecurrenceCustomAreaBlock(RecurrenceConditionalBehavior,
                                        DetailSynchronizedContentItemDetailBlock):
    visibilityFlags = RecurrenceConditionalBehavior.showCustom

class CalendarRecurrenceEndAreaBlock(RecurrenceConditionalBehavior,
                                     DetailSynchronizedContentItemDetailBlock):
    visibilityFlags = RecurrenceConditionalBehavior.showEnds

# Attribute editor customizations

class CalendarDateAttributeEditor(DateAttributeEditor):    
    def SetAttributeValue(self, item, attributeName, valueString):
        newValueString = valueString.replace('?','').strip()
        if len(newValueString) == 0:
            # Attempting to remove the start date field will set its value to the 
            # "previous value" when the value is committed (removing focus or 
            # "enter"). Attempting to remove the end-date field will set its 
            # value to the "previous value" when the value is committed. In 
            # brief, if the user attempts to delete the value for a start date 
            # or end date, it automatically resets to what value was displayed 
            # before the user tried to delete it.
            self.SetControlValue(self.control, 
                                 self.GetAttributeValue(item, attributeName))
        else:
            oldValue = getattr(item, attributeName, None)
            # Here, the ICUError covers ICU being unable to handle
            # the input value. ValueErrors can occur when I've seen ICU
            # claims to parse bogus  values like "06/05/0506/05/05" 
            #successfully, which causes fromtimestamp() to throw.)
            try:
                dateTimeValue = pim.shortDateFormat.parse(item.itsView, 
                                                           newValueString,
                                                           oldValue)
            except (ICUError, ValueError):
                dateTimeValue = None

            if dateTimeValue is None:
                try:
                    # use parsedatetime to calculate the date
                    cal = parsedatetime.Calendar(ptc.Constants(
                                                        str(getLocale())))
                    (dateVar, invalidFlag) = cal.parse(newValueString)
                    #invalidFlag = 0 implies no date/time
                    #invalidFlag = 2 implies only time, no date
                    if invalidFlag not in (0, 2):
                        dateTimeValue = datetime(*dateVar[:3])
                except (ICUError, ValueError):
                    pass

            if dateTimeValue is None:
                self._changeTextQuietly(self.control, "%s ?" % newValueString)
                return


            # If this results in a new value, put it back.
            value = datetime.combine(dateTimeValue.date(), oldValue.timetz())

            if oldValue != value:
                if attributeName == pim.EventStamp.endTime.name:
                    # Changing the end date or time such that it becomes 
                    # earlier than the existing start date+time will 
                    # change the start date+time to be the same as the 
                    # end date+time (that is, an @time event, or a 
                    # single-day anytime event if the event had already 
                    # been an anytime event).
                    event = pim.EventStamp(item)
                    if value < event.startTime:
                        event.startTime = value
                    # @@@ Expedient workaround for proxy/Calculated
                    # issues (see Bug 10694).
                    event.duration = value - event.startTime
                elif attributeName == pim.EventStamp.startTime.name:
                    setattr(item, attributeName, value)
                else:
                    assert False, "this attribute editor is really just for " \
                                  "start or endtime"
                item.setTriageStatus('auto', pin=True)

            # Refresh the value in place
            self.SetControlValue(self.control, 
                                 self.GetAttributeValue(item, attributeName))

class CalendarTimeAttributeEditor(TimeAttributeEditor):
    durationFormat = PyICU.SimpleDateFormat(u"H:mm")
    zeroHours = durationFormat.parse(u"0:00")

    def GetAttributeValue(self, item, attributeName):
        event = pim.EventStamp(item)
        noTime = getattr(event, 'allDay', False) \
               or getattr(event, 'anyTime', False)
        if noTime:
            value = u''
        else:
            value = super(CalendarTimeAttributeEditor, self).GetAttributeValue(item, attributeName)
        return value

    def SetAttributeValue(self, item, attributeName, valueString):
        view = item.itsView
        event = pim.EventStamp(item)
        newValueString = valueString.replace('?','').strip()
        iAmStart = attributeName == pim.EventStamp.startTime.name
        changed = False
        forceReload = False
        if len(newValueString) == 0:
            if not event.anyTime: # If we're not already anytime
                # Clearing an event's start time (removing the value in it, causing 
                # it to show "HH:MM") will remove both time values (making it an 
                # anytime event).
                if iAmStart:
                    event.anyTime = True
                    changed = True
                else:
                    # Clearing an event's end time will make it an at-time event
                    zeroTime = timedelta()
                    if event.duration != zeroTime:
                        event.duration = zeroTime
                        changed = True
                forceReload = True
        else:
            # We have _something_; parse it.
            oldValue = getattr(item, attributeName)

            # Try to parse it, a couple of different ways; we'll call this
            # generator until it returns something we can parse successfully.
            def generateTimeAttempts(timeString):
                # First, we try as-is. This'll take care of a fully-specified time,
                # including the case of "15:30" in a locale that doesn't use AM/PM.
                yield timeString

                # See if we can get hours, minutes, and maybe am/pm out of 
                # what the user typed.
                localeUsesAMPM = len(pim.ampmNames) > 0
                meridian = ""
                # L10N: Used to parse a date string.
                #       %(meridian)s will evaluate to "AM",
                #       "PM", or "" if the locale uses 24 hour
                #       time.
                #
                format = _(u"%(hour)d:%(minute)02d%(meridian)s")
                if localeUsesAMPM:
                    # This locale uses an am/pm indicator. If one's present,
                    # note it and remove it.
                    (am, pm) = pim.ampmNames
                    (timeString, hasAM) = re.subn(am, '', timeString, 
                                                  re.IGNORECASE)
                    (timeString, hasPM) = re.subn(pm, '', timeString, 
                                                  re.IGNORECASE)
                    if hasAM and hasPM:
                        return # both? bogus.
                    if hasAM or hasPM:
                        meridian = " " + (hasAM and am or pm)
                        timeString = timeString.strip()

                # Now try to get hours & minutes, or just hours, 
                # out of the string. 
                try:
                    hour = int(timeString)
                except ValueError:
                    try:
                        duration = pim.durationFormat.parse(timeString)
                    except (ICUError, ValueError):
                        return # give up.
                    # It looks like a duration:
                    totalSeconds = (duration - CalendarTimeAttributeEditor.zeroHours)
                    hour = int(totalSeconds / 3600)
                    minute = int((totalSeconds % 3600)/ 60)
                else:
                    minute = 0

                if localeUsesAMPM and len(meridian) == 0:
                    # Gotta try to figure out AM vs PM.
                    if hour > 12 and not hasAM:
                        # The hour is unambiguously PM
                        meridian = " " + pm
                        hour -= 12
                    else:
                        # Guess that the user wants the hour closest to the
                        # old time's hour, or noon if we didn't have one.
                        if event.allDay or event.anyTime:
                            oldHour = 12
                        else:
                            oldHour = event.startTime.hour
                        amDiff = abs(oldHour - hour)
                        pmDiff = abs(oldHour - (hour + 12))
                        meridian = " " + (amDiff >= pmDiff and pm or am)

                forceReload = True
                yield format % locals()

            # use parsetime to calculate the time
            gotTime = None
            for valueString in generateTimeAttempts(newValueString):
                try:
                    # use parsedatetime to calculate time
                    cal = parsedatetime.Calendar() 
                    (timeVar, invalidFlag) = cal.parse(valueString)
                    #invalidFlag = 0 implies no date/time
                    #invalidFlag = 1 implies only date, no time
                    if invalidFlag != 0 and invalidFlag != 1:
                        # We'll use the first 7 values from the time 
                        # we got from parsedatetime, as well as our existing
                        # timezone, to build a datetime we can format
                        newTimeWithTZ = list(timeVar[:7])
                        newTimeWithTZ.append(oldValue.tzinfo)
                        newValueString = pim.shortTimeFormat.format(view, 
                            datetime(*newTimeWithTZ))
                        gotTime = pim.shortTimeFormat.parse(view, newValueString, 
                                                         referenceDate=oldValue)
                    else:
                        self._changeTextQuietly(self.control, "%s ?" % newValueString)
                        return
                except (ICUError, ValueError):
                    continue        
                else:
                    break

            if gotTime is None:            
                self._changeTextQuietly(self.control, "%s ?" % newValueString)
                return

            # If we got a new value, put it back.
            value = datetime.combine(oldValue.date(), gotTime.timetz())
            # Preserve the time zone!
            value = value.replace(tzinfo=oldValue.tzinfo)
            if event.anyTime or oldValue != value:
                # Something changed.                
                # Implement the rules for changing one of the four values:
                if event.anyTime:
                    # On an anytime event (single or multi-day; both times 
                    # blank & showing the "HH:MM" hint), entering a valid time 
                    # in either time field will set the other date and time 
                    # field to effect a one-hour event on the corresponding date. 
                    
                    # bug 10251: If this is an occurrence, use our master's TZ
                    # if ours is floating. (It might be floating too, but if it's
                    # not, it wins)
                    master = getattr(item, 'inheritFrom', None)
                    if master is not None and (value.tzinfo == view.tzinfo.floating):
                        masterStart = pim.EventStamp(master).startTime
                        value = value.replace(tzinfo=masterStart.tzinfo)

                    event.anyTime = False
                    if iAmStart:
                        event.startTime = value
                    else:
                        event.startTime = value - timedelta(hours=1)
                    event.duration = timedelta(hours=1)
                else:
                    if not iAmStart:
                        # Per bug 7522:
                        # Changing the end time such that it becomes earlier
                        # than the existing start date+time will change 
                        # the end date to be after the start date, to
                        # handle the case where an evening event crosses midnight.
                        while value < event.startTime:
                            value += timedelta(days=1)
                    # @@@ Expedient workaround for proxy/Calculated
                    # issues (see Bug 10694).
                    if attributeName == pim.EventStamp.endTime.name:
                        event.duration = value - event.startTime
                    else:
                        setattr(item, attributeName, value)
                    event.anyTime = False
                changed = True

        if changed:
            item.setTriageStatus('auto', pin=True)

        if changed or forceReload:
            # Refresh the value in the control
            self.SetControlValue(self.control, 
                             self.GetAttributeValue(item, attributeName))

class RecurrenceAttributeEditor(ChoiceAttributeEditor):
    # These are the values we pass around; they're the same as the menu indices.
    # This is a list of the frequency enumeration names (defined in 
    # Recurrence.py's FrequencyEnum) in the order we present
    # them in the menu... plus "once" at the beginning and "custom" at the end.
    # Note that biweekly is not, in fact, a valid FrequencyEnum frequency, it's a
    # special case.
    # These should not be localized!
    menuFrequencies = [ 'once', 'daily', 'weekdaily', 'weekly', 'biweekly', 'monthly', 'yearly', 'custom']
    onceIndex = menuFrequencies.index('once')
    customIndex = menuFrequencies.index('custom')
    weekdailyIndex = menuFrequencies.index('weekdaily')
    biweeklyIndex = menuFrequencies.index('biweekly')
    weeklyIndex = menuFrequencies.index('weekly')

    @classmethod
    def mapRecurrenceFrequency(theClass, item):
        """
        Map the frequency of this item to one of our menu choices.
        """
        assert not getattr(item, 'itsItem', item).isStale()
        event = pim.EventStamp(item)
        if event.isCustomRule(): # It's custom if it says it is.
            return RecurrenceAttributeEditor.customIndex
        # Otherwise, try to map its frequency to our menu list
        try:
            rrule = event.rruleset.rrules.first() 
            freq = rrule.freq
            # deal with biweekly special case
            if freq == 'weekly':
                if rrule.interval == 2:
                    return RecurrenceAttributeEditor.biweeklyIndex
                elif rrule.isWeekdayRule():
                    return RecurrenceAttributeEditor.weekdailyIndex
        except AttributeError:
            # Can't get to the freq attribute, or there aren't any rrules
            # So it's once.
            return RecurrenceAttributeEditor.onceIndex
        else:
            # We got a frequency. Try to map it.
            index = RecurrenceAttributeEditor.menuFrequencies.index(freq)
        return index

    _editingCustomRecurrence = False

    def EndControlEdit(self, item, attrname, control):
        if self._editingCustomRecurrence:
            return
        super(RecurrenceAttributeEditor, self).EndControlEdit(item, attrname,
                                                              control)

    def onChoice(self, event):
        """Handle the 'occurs' recurrence menu"""
        if self._editingCustomRecurrence:
            event.Skip()
            return

        control = event.GetEventObject()
        newChoice = self.GetControlValue(control)
        
        if newChoice != RecurrenceAttributeEditor.customIndex:
            ## Simple, not custom case
            self.SetControlValue(control, newChoice)            
            self.SetAttributeValue(self.item, self.attributeName, newChoice)
        else:
            ## Custom Case -- bring up dialog
            # I *think* below should be out
            #if not pim.has_stamp(item, pim.EventStamp):
            #    return
            
            self._editingCustomRecurrence = True
            eventItem = pim.EventStamp(self.item)
            
            try:
                customRRuleArgs = EditRecurrence(eventItem, parent=control)
            finally:
                self._editingCustomRecurrence = False

            if not customRRuleArgs:
                # Cancelling
                # Do this to make the UI not take on a new state
                self.parentBlock.synchronizeWidget()
                return
            
            
            self.SetControlValue(control, newChoice)
            # Trick: send the customRRuleArgs as the value as the string
            self.SetAttributeValue(self.item, self.attributeName, customRRuleArgs)

        
        # a bunch of new occurrences were just created, might as well commit
        # them now rather than making some later commit take a surprisingly
        # long time
        self.item.itsView.commit()
                
 
    def GetAttributeValue(self, item, attributeName):
        index = RecurrenceAttributeEditor.mapRecurrenceFrequency(item)
        return index

    def SetAttributeValue(self, item, attributeName, value):
        """
        Set the value of the attribute given by the value.
        """
        
        # Trick: for a custom recurrence, the value is the custom args dict --
        # detect that case.
        customRRuleArgs = None
        if type(value) == type({}):
            customRRuleArgs = value
        
        # Changing the recurrence period on a non-master item could delete 
        # this very 'item'; we'll try to select the "same" occurrence
        # afterwards ...

        # It seems we occasionally get told to save our value after a stamping
        # change has removed eventity (bug 11569). Do nothing when this happens.
        if not pim.has_stamp(item, pim.EventStamp):
            return

        # we may want to prompt the user about destructive rrule changes,
        # but calling changeThisAndFuture on a proxy's rruleset has the
        # worst of both worlds, it prompts, but the change is irrevocable.
        # So don't use the proxy when changing the rule
        event = pim.EventStamp(item)
        oldIndex = self.GetAttributeValue(event, attributeName)

        # If nothing has changed, return. This avoids building
        # a whole new ruleset, and the teardown of occurrences,
        # as in Bug 5526
        if oldIndex == value and not customRRuleArgs:
            return        

        assert customRRuleArgs or value != RecurrenceAttributeEditor.customIndex

        master = event.getMaster()
        recurrenceID = event.recurrenceID or event.startTime

        if value == RecurrenceAttributeEditor.onceIndex:
            firstOccurrence = master.getExistingOccurrence(master.recurrenceID)
            del event.rruleset
            # either master, firstOccurrence, or None will be the only remaining
            # event
            itemToSelect = None
            if not master.itsItem.isDeleted():
                itemToSelect = master.itsItem
            elif not firstOccurrence.itsItem.isDeleted():
                itemToSelect = firstOccurrence.itsItem
            # "is" comparison only works after unwrapping proxies
            itemToSelect = getattr(itemToSelect, 'proxiedItem', itemToSelect)
    
            if itemToSelect is not item:
                BroadcastSelect(self.control.blockItem, itemToSelect)
        else:
            if (recurrenceID == master.recurrenceID and 
                event.modificationFor is None):
                eventInNewSeries = master
            else:
                # if this event is a modification, it may become the new master
                eventInNewSeries = event            

            rruleset = Recurrence.RecurrenceRuleSet(None, itsView=item.itsView)
            
            # 1. It's custom -- use the sent in args
            if customRRuleArgs:
                rruleset.setRuleFromDateUtil(Recurrence.dateutil.rrule.rrule(**customRRuleArgs))
            else:
            # 2. it's biweekly or whatever, set that
            # daily, weekdays, weekly, biweekly, monthly, yearly
                rruleArgs = {'interval': 1}
                if value == RecurrenceAttributeEditor.biweeklyIndex:
                    rruleArgs['interval'] = 2
                    value = RecurrenceAttributeEditor.weeklyIndex
                elif value == RecurrenceAttributeEditor.weekdailyIndex:
                    value = RecurrenceAttributeEditor.weeklyIndex
                    rruleArgs['byweekday'] = [Recurrence.toDateUtilWeekday(day)
                                     for day in Recurrence.RecurrenceRule.WEEKDAYS]
    
                duFreq = Recurrence.toDateUtilFrequency(
                    RecurrenceAttributeEditor.menuFrequencies[value])
                rruleset.setRuleFromDateUtil(Recurrence.dateutil.rrule.rrule(duFreq,
                                             **rruleArgs))
                                             
            rrule = rruleset.rrules.first()
            until = event.getLastUntil()
            if until is not None:
                rrule.until = until
            elif hasattr(rrule, 'until'):
                del rrule.until
            rrule.untilIsDate = True
            
            event.rruleset = rruleset
            
            def cleanup(newEvent, block):
                if not pim.isDead(getattr(newEvent, 'itsItem', None)):
                    newMaster = newEvent.getMaster()
                    newMaster.deleteOffRuleModifications()
                
                    assert not pim.isDead(newMaster.itsItem)
    
                    itemToSelect = newMaster.getFirstOccurrence().itsItem
                else:
                    itemToSelect = None
                BroadcastSelect(block, itemToSelect)
                
            RecurrenceDialog.delayForRecurrenceDialog(event.itsItem, cleanup,  eventInNewSeries, self.control.blockItem)

    def GetControlValue(self, control):
        """
        Get the value for the current selection.
        """ 
        choiceIndex = control.GetSelection()
        return choiceIndex

    def SetControlValue(self, control, value):
        """
        Select the choice that matches this index value.
        """
        # We also take this opportunity to populate the menu
        existingValue = self.GetControlValue(control)
        if existingValue != value or control.GetCount() == 0:
            # rebuild the list of choices
            choices = self.GetChoices()
            control.Clear()
            control.AppendItems(choices)

        control.Select(value)

class RecurrenceCustomAttributeEditor(StaticStringAttributeEditor):
    def GetAttributeValue(self, item, attributeName):
        return pim.EventStamp(item).getCustomDescription()

class RecurrenceEndsAttributeEditor(DateAttributeEditor):
    # If we haven't already, remap the configured item & attribute 
    # name to the actual 'until' attribute deep in the recurrence rule.
    # (Because we might be called from within SetAttributeValue,
    # which does the same thing, we just pass through if we're already
    # mapped to 'until')
    def GetAttributeValue(self, item, attributeName):
        if attributeName != 'until':
            attributeName = 'until'
            try:
                item = pim.EventStamp(item).rruleset.rrules.first()
            except AttributeError:
                return u''
        return super(RecurrenceEndsAttributeEditor, self).\
               GetAttributeValue(item, attributeName)

    def SetAttributeValue(self, item, attributeName, valueString):
        view = item.itsView
        event = pim.EventStamp(item)
        eventTZ = event.startTime.tzinfo
        master = event.getMaster()
        recurrenceID = event.recurrenceID

        if attributeName != 'until':
            attributeName = 'until'        
            try:
                item = event.rruleset.rrules.first()
            except AttributeError:
                # This used to be an assert: "Hey - Setting 'ends' on an event without a recurrence rule?"
                # however, we can get here when a new item has been selected in the DV while this
                # editor has the focus. In this case, the right thing is to do nothing; it'll be hidden
                # shortly.
                return

        # If the user removed the string, remove the attribute.
        newValueString = valueString.replace('?','').strip()
        if len(newValueString) == 0 and hasattr(item, attributeName):
            delattr(item, attributeName)
            BroadcastSelect(self.control.blockItem,
                            master.getRecurrenceID(recurrenceID).itsItem)
        else:
            try:
                oldValue = getattr(item, attributeName, None)
                dateValue = pim.shortDateFormat.parse(view,
                                                      newValueString, 
                                                      referenceDate=oldValue)
            except (ICUError, ValueError):
                self._changeTextQuietly(self.control, "%s ?" % newValueString)
                return

            if dateValue.date() < event.startTime.date():
                self._changeTextQuietly(self.control, _(u"too early ?") )
                return


            # set the end timezone to be the same as the event's timezone,
            # unless it's floating.  Allowing a floating recurrence end timezone 
            # has the nonsensical result that the number of occurrences depends
            # on what timezone you view the calendar in if startTime ever 
            # changes to a non-floating timezone.        
            if eventTZ == view.tzinfo.floating:
                eventTZ == view.tzinfo.default

            value = datetime.combine(dateValue.date(), time(0, tzinfo=eventTZ))
            # don't change the value unless the date the user sees has
            # changed
            if oldValue is None or oldValue.date() != value.date():
                # Refresh the value in place
                self.SetControlValue(self.control, 
                                     pim.shortDateFormat.format(item.itsView, value))

                # Change the value in the domain model, asynchronously
                # (because setting recurrence-end could cause this item
                # to be destroyed, which'd cause this widget to be deleted,
                # and we still have references to it in our call stack)
                def changeRecurrenceEnd(self, item, newEndValue):
                    if event.itsItem.isDeleted():
                        return
                    changed = False
                    if not getattr(item, 'untilIsDate', False):
                        item.untilIsDate = True
                        changed = True
                    if getattr(item, 'until', None) != newEndValue:
                        item.until = newEndValue
                        changed = True
                    if changed:
                        # until occurrences are part of the collection, changing
                        # the recurrence end will likely delete the current
                        # selection, but the detail view won't find out, so
                        # select a new (more appropriate) item when changing
                        # recurrence end.

                        selection = master.getRecurrenceID(recurrenceID)
                        if selection is not None:
                            selection = selection.itsItem
                        BroadcastSelect(self.control.blockItem, selection)

                wx.CallAfter(changeRecurrenceEnd, self, item, value)

class ErrorAEBlock(DetailSynchronizedAttributeEditorBlock):
    def shouldShow(self, item):
        error = getattr(self.item, 'error', None)
        return super(ErrorAEBlock, self).shouldShow(item) and bool(error)

    def getWatchList(self):
        watchList = super(ErrorAEBlock, self).getWatchList()
        watchList.append((self.item, pim.ContentItem.error.name),)
        return watchList

class BylineConditionalBehavior(Item):
    def getWatchList(self):
        watchList = super(BylineConditionalBehavior, self).getWatchList()
        tzPrefs = schema.ns('osaf.pim', self.itsView).TimezonePrefs
        watchList.extend(((self.item, pim.Stamp.stampCollections.name),
                          (self.item, pim.MailStamp.fromMe.name),
                          (self.item, ContentItem.lastModification.name),
                          (self.item, pim.MailStamp.fromAddress.name),
                          (tzPrefs, 'showUI')))
        return watchList

class SendAsLabelBlock(BylineConditionalBehavior, DetailSynchronizedBehavior, ControlBlocks.StaticText):
    def synchronizeWidget(self):
        super(SendAsLabelBlock, self).synchronizeWidget()
        item = self.item
        lastMod = getattr(item, 'lastModification', None)
        if (lastMod in (pim.Modification.edited, pim.Modification.queued) and
            pim.has_stamp(item, pim.mail.MailStamp) and
            pim.MailStamp(item).fromMe):
            label = _(u'Edited by') 
        else:
            label = _(u'Send as')

        self.widget.SetLabel(label)

class BylineAreaBlock(BylineConditionalBehavior, DetailSynchronizedContentItemDetailBlock):
    # We use this block class for the byline (the static representation, like
    # "Sent by Bob Smith on 6/21/06") as well as for the Send As block (the
    # popup representation, like "Send As [Me]") - they're both visible 
    # conditioned on whether this is an outgoing unsent message: SendAs if so,
    # byline if not.
    def shouldShow(self, item):
        if not super(BylineAreaBlock, self).shouldShow(item):
            return False

        lastMod = getattr(self.item, 'lastModification', None)
        isUnsentOutboundMail = (lastMod in (None, 
                                            pim.Modification.edited, 
                                            pim.Modification.created) and
                                pim.has_stamp(item, pim.mail.MailStamp) and
                                (pim.MailStamp(item).fromMe or
                                 getattr(item, pim.MailStamp.fromAddress.name, None) is None))
        return isUnsentOutboundMail == (self.blockName == 'SendAsArea')

class BylineAEBlock(BylineConditionalBehavior, DetailSynchronizedAttributeEditorBlock):
    def onTimeZoneChangeEvent(self, event):
        # timezone changes may require us to show/hide the timezone in the byline date.
        self.synchronizeWidget()

class MailAEBlock(DetailSynchronizedAttributeEditorBlock):
    """
    Changes to MailStamp attributes (from, to, ... etc) should always propagate
    to all occurrences.
    """
    proxyFactory = staticmethod(pim.CHANGE_ALL)

class OriginatorsAEBlock(MailAEBlock):
    def getWatchList(self):
        watchList = super(OriginatorsAEBlock, self).getWatchList()
        watchList.append((self.item, pim.mail.MailStamp.fromAddress.name),)
        return watchList

class OriginatorsAttributeEditor(EmailAddressAttributeEditor):
    """
    We want the "From:" field to display the value from fromAddress if
    there's no 'originators' values.
    """
    def GetAttributeValue(self, item, attributeName):
        assert attributeName == pim.mail.MailStamp.originators.name
        result = super(OriginatorsAttributeEditor, 
            self).GetAttributeValue(item, attributeName)
        if result == u'':
            result = super(OriginatorsAttributeEditor, 
                self).GetAttributeValue(item, pim.mail.MailStamp.fromAddress.name)
            if result == u'':
                # Bug 9353: if accounts aren't set up, this'll be blank. In this 
                # case, just use "me".
                result = messages.ME
        return result

class OutboundEmailAddressAEBlock(MailAEBlock):
    def getWatchList(self):
        watchList = super(OutboundEmailAddressAEBlock, self).getWatchList()
        addressList = Mail.getCurrentMeEmailAddresses(self.itsView)
        watchList.extend(((addressList, pim.mail.EmailAddresses.emailAddresses.name),),)
        return watchList

class OutboundEmailAddressAttributeEditor(ChoiceAttributeEditor):
    """
    An attribute editor that presents a list of the configured email
    accounts.

    If no accounts are configured, the only choice will trigger the
    email-account setup dialog.

    This editor's value is the email address string itself (though
    the "configure accounts" choice is treated as the special string '').
    """

    def CreateControl(self, forEditing, readOnly, parentWidget, 
                      id, parentBlock, font):
        control = super(OutboundEmailAddressAttributeEditor, 
                        self).CreateControl(forEditing, readOnly, parentWidget, 
                                            id, parentBlock, font)
        control.Bind(wx.EVT_LEFT_DOWN, self.onLeftClick)
        return control

    def onLeftClick(self, event):
        control = event.GetEventObject()
        if control.GetCount() == 1 and self.GetControlValue(control) == u'':
            # "config accounts..." is the only choice
            # Don't wait for the user to make a choice - do it now.
            self.onChoice(event)
        else:
            event.Skip()

    def GetChoices(self):
        """
        Get the choices we're presenting.
        """
        addrs = Mail.getCurrentMeEmailAddresses(self.item.itsView)
        choices = []

        for addr in addrs:
            choices.append(addr.format())

        choices.append(_(u"Create outgoing mail account..."))
        return choices

    def GetControlValue(self, control):
        choiceIndex = control.GetSelection()
        if choiceIndex == -1:
            return None
        if choiceIndex == control.GetCount() - 1:
            return u''
        return control.GetString(choiceIndex)

    def SetControlValue(self, control, value):
        """
        Select the choice with the given text.
        """
        # We also take this opportunity to populate the menu
        existingValue = self.GetControlValue(control)
        if existingValue in (None, u'') or existingValue != value:            
            # rebuild the list of choices
            choices = self.GetChoices()
            control.Clear()
            control.AppendItems(choices)

            choiceIndex = control.FindString(value)
            if choiceIndex == wx.NOT_FOUND:
                # Weird, we can't find the selected address. Select the
                # "accounts..." choice, which is last.
                choiceIndex = 0 #len(choices) - 1
            control.Select(choiceIndex)

    def GetAttributeValue(self, item, attributeName):
        attrValue = getattr(item, attributeName, None)
        if attrValue is not None:
            # Just format one address
            value = unicode(attrValue)
        else:
            value = u''
        return value

    def SetAttributeValue(self, item, attributeName, valueString):
        # For 1.0, changes to communication fields should apply to all
        # occurrences, change the master directly
        item = getattr(item, 'proxiedItem', item)
        if pim.has_stamp(item, pim.EventStamp):
            item = pim.EventStamp(item).getMaster().itsItem
        # Process the one address we've got.
        processedAddresses, validAddresses, invalidCount = \
            Mail.EmailAddress.parseEmailAddresses(item.itsView, valueString)
        if invalidCount == 0:
            # The address is valid. Put it back if it's different
            oldValue = self.GetAttributeValue(item, attributeName)
            if oldValue != processedAddresses:
                value = len(validAddresses) > 0 \
                      and validAddresses[0] or None
                setattr(item, attributeName, value)

    def onChoice(self, event):
        control = event.GetEventObject()
        newChoice = self.GetControlValue(control)
        if len(newChoice) == 0:
            response = application.dialogs.AccountPreferences.\
                     ShowAccountPreferencesDialog(account=None, 
                                                  rv=self.item.itsView)
            # rebuild the list in the popup
            self.SetControlValue(control, 
                self.GetAttributeValue(self.item, self.attributeName))
        else:
            #logger.debug("OutboundEmailAddressAttributeEditor.onChoice: "
                         #"new choice is %s", newChoice)
            self.SetAttributeValue(self.item, self.attributeName, \
                                   newChoice)


class HTMLDetailArea(DetailSynchronizedBehavior, ControlBlocks.ItemDetail):
    def getHTMLText(self, item):
        return u"<html><body>" + item + u"</body></html>"


class EmptyPanelBlock(ControlBlocks.ContentItemDetail):
    """
    A bordered panel, which we use when no item is selected in the calendar.
    """
    def instantiateWidget(self):
        # Make a box with a sunken border - wxBoxContainer will take care of
        # getting the background color from our attribute.
        style = wx.Platform == '__WXMAC__' \
              and wx.BORDER_SIMPLE or wx.BORDER_STATIC
        widget = ContainerBlocks.wxBoxContainer(self.parentBlock.widget, -1,
                                                wx.DefaultPosition, 
                                                wx.DefaultSize, 
                                                style)
        widget.SetBackgroundColour(wx.WHITE)
        return widget

class DetailFrameWindow(ContainerBlocks.FrameWindow):

    @classmethod
    def editItem(cls, item):
        view = item.itsView
        
        for fw in cls.iterItems(view):
            if item is getattr(fw, 'contents', None):
                break
        else:
            parent = item.getDefaultParent(view)
            stub = schema.ns(__parcel__, view).DetailRoot
            delegate = DetailBranchPointDelegate(itsParent=parent,
                                                  branchStub=stub)
            block = BranchPoint.BranchPointBlock(
                        itsParent=parent,
                        delegate=delegate,
                        blockName=u"SeparateDetailBranchPoint",
                        border=RectType(0.0, 6.0, 0.0, 6.0),
                    )
            block.selectedItem = item

            main = schema.ns("osaf.views.main", view)

            def copy(block):
                return block.copy(cloudAlias='copying', parent=parent)

            childBlocks = [
                ToolBar(
                    itsParent=parent,
                    blockName=u"SeparateDVToolBar",
                    stretchFactor = 0.0,
                    toolSize = SizeType(32, 32),
                    buttonsLabeled = True,
                    separatorWidth = 20,
                    childBlocks=[copy(main.ApplicationBarSendButton)],
                ),
                block,
            ]
            
            if wx.Platform != '__WXMAC__':

                menuBar = Menu(
                    setAsMenuBarOnFrame=True,
                    itsParent=parent,
                    blockName=u"SeparateDVMenuBar",
                    stretchFactor = 0.0,
                    toolSize = SizeType(32, 32),
                    buttonsLabeled = True,
                    separatorWidth = 20,
                    childBlocks=[
                        copy(main.EditMenu),
                        copy(main.ItemMenu),
                        copy(main.ToolsMenu),
                        copy(main.HelpMenu),
                    ],
                )
                
                childBlocks.append(menuBar)

            fw = cls(
                    itsParent=parent,
                    size=SizeType(600, 600),
                    minimumSize=SizeType(300, 600),
                    childBlocks=childBlocks,
                    contents=item,
                    windowTitle=item.displayName,
                    eventsForNamedLookup=[main.SendMail],
                    orientationEnum="Vertical",
                )
        
        fw.show()


    schema.initialValues(
        blockName=lambda self: '%s-%s' % (type(self).__name__,
                                          self.contents.itsUUID.str16()),
        eventBoundary=lambda self: True
    )

    def show(self):
        # @@@ [grant] imports are totally wonky
        from application.Application import wxBlockFrameWindow
        try:
            window = self.widget.GetTopLevelParent()
        except AttributeError:
            window = wxBlockFrameWindow(
                        None,
                        -1, 
                        self.windowTitle,
                        pos=(self.position.x, self.position.y),
                        size=(self.size.width, self.size.height),
                        style=wx.DEFAULT_FRAME_STYLE)
            window.Bind(wx.EVT_CLOSE, self.OnClose)
            window.ShowTreeOfBlocks(self)
            
            # We have to wire up the detail root. There's probably a way to
            # do the sizers better here ...
            # There's probably a way to wire this up to both MainFrame and
            # this top-level window, eh.
            
            window.MinSize = (self.minimumSize.width, self.minimumSize.height)

            sizer = wx.BoxSizer(wx.HORIZONTAL)
            window.SetSizer(sizer)
            sizer.Add(self.widget,
                   self.stretchFactor, 
                   Block.wxRectangularChild.CalculateWXFlag(self), 
                   Block.wxRectangularChild.CalculateWXBorder(self))

            self.findBlockByName("DetailRoot", self).focus()
            
        window.Show()
        window.Raise()

    def onCloseEvent(self, event):
        # Translate the Close BlockEvent into a wx Close event
        window = self.getTopLevel()
        if window:
            window.Close()
        
    def getTopLevel(self):
        try:
            return self.widget.GetTopLevelParent()
        except AttributeError:
            pass

    def OnClose(self, event):
        if not pim.isDead(self):
            window = self.getTopLevel()

            if window:
                window.OnClose(event)
                if window.treeOfBlocks:
                    del window.treeOfBlocks
                         
            def deleteIt(block):
                for child in getattr(block, 'childBlocks', ()):
                    deleteIt(child)
                block.delete(recursive=True)
                
            deleteIt(self)
                 
            if not (self.itsView.itsStatus & self.itsView.COMMITTING):
                self.itsView.commit()
        

    def getWatchList(self):
        return [(self.contents, 'displayName'), # window title changes
                (self.contents, 'itsKind'), # item deletion
                (self.contents, pim.EventStamp.rruleset.name)] # recurrence

    def onItemNotification(self, notificationType, data):
        if pim.isDead(getattr(self, 'contents', None)):
            window = self.getTopLevel()
            if window:
                wx.CallAfter(window.Close)
        elif notificationType == 'itemChange':
            op, uuid, attrs = data
            if 'displayName' in attrs:
                self.windowTitle = self.contents.displayName
                self.markDirty()
            if pim.EventStamp.rruleset.name in attrs:
                event = pim.EventStamp(self.contents)
                if event == event.getMaster() and event.rruleset is not None:
                    occurrence = event.getFirstOccurrence()
                    self.childBlocks.first().postEventByName(
                       'SelectItemsBroadcast', {'items': [occurrence.itsItem]}
                    )

    def onSelectItemsEvent(self, event):
        displayName = event.arguments['items'][0].displayName
        self.windowTitle = displayName
        self.markDirty()

    def synchronizeWidget(self):
        super(DetailFrameWindow, self).synchronizeWidget()
        self.widget.GetTopLevelParent().Title = self.windowTitle
