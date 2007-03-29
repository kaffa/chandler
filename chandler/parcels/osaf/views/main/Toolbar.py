#   Copyright (c) 2007 Open Source Applications Foundation
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

__parcel__ = "osaf.views.main"

from osaf.framework.blocks import *
from osaf.views.detail import WatchedItemRootBlock
import osaf.pim.items as items

class SendToolbarItem(WatchedItemRootBlock, ToolbarItem):
    """
    The "Send"/"Update" toolbar item
    """
    def OnSetBitmapEvent(self, event, bitmapName):
        # get the toolbar
        # toolbar = self.GetToolbar()?
        parent = getattr(self, 'parentBlock', None)
        if parent is not None:
            toolbar = getattr(parent, 'widget', None)
            if toolbar is not None:
                # get the named bitmap
                bitmap = wx.GetApp().GetImage(bitmapName)
                if bitmap is not None:
                    toolbar.SetToolNormalBitmap(self.toolID, bitmap)
                    toolbar.Realize()
