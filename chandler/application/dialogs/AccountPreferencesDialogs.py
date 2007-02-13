#   Copyright (c) 2003-2006 Open Source Applications Foundation
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

import wx
from Util import ProgressDialog
from application import Globals
from i18n import ChandlerMessageFactory as _
from osaf.mail import constants, autodetect
from osaf.sharing import accounts
from osaf.sharing.WebDAV import WebDAVTester, MorsecodeTester
from osaf.sharing import WebDAV
from osaf.pim.mail import IMAPAccount, IMAPFolder

__all__ = [
         "showOKDialog",
         "showYesNoDialog",
         "MailTestDialog",
         "SharingTestDialog",
         "ChandlerIMAPFoldersDialog",
         "RemoveChandlerIMAPFoldersDialog",
         "AutoDiscoveryDialog",
]

class MailTestDialog(ProgressDialog):
    TIMEOUT = constants.TESTING_TIMEOUT

    def __init__(self, account):
        #XXX add in asserts
        self.account = account
        self.mailInstance = None

        super(MailTestDialog, self).__init__()
        self.initDialog()

    def performAction(self):
        if self.mailInstance is None:
            m = getattr(Globals.mailService, "get%sInstance" % self.account.accountProtocol)
            assert(m is not None)
            self.mailInstance = m(self.account)

        a  = self.account

        reconnect = lambda: MailTestDialog(a)
        self.mailInstance.testAccountSettings(self.OnActionComplete, reconnect)

    def cancelAction(self):
        self.mailInstance.cancelLastRequest()

    def getTimeoutText(self):
        return constants.MAIL_PROTOCOL_CONNECTION_ERROR

    def getTitleText(self):
        return _(u"Testing %(accountType)s Account '%(accountName)s'") % \
                          {'accountType': self.account.accountProtocol,
                           'accountName': self.account.displayName}

    def getStartText(self):
        return _(u"Connecting to server '%(hostName)s'") % \
                 {'hostName': self.account.host}

    def getSuccessText(self, statusValue):
        return constants.MAIL_PROTOCOL_SUCCESS % \
                    {'hostName': self.account.host}

    def getErrorText(self, statusValue):
        return constants.MAIL_PROTOCOL_ERROR % \
                        {'hostName': self.account.host, 'errText': statusValue}




NO_ACCESS    = _(u"Permission denied by server.")
READ_ONLY    = _(u"This account has read access but not write access.")
READ_WRITE   = _(u"This account has read/write access.")
UNKNOWN      = _(u"Test failed with an unknown response.")

class SharingTestDialog(ProgressDialog):
    TIMEOUT = 60

    def __init__(self, displayName=None, host=None, port=None,
                 path=None, username=None, password=None,
                 useSSL=False, view=None, morsecode=False):

        self.displayName = displayName
        self.host = host
        self.port = port
        self.path = path
        self.username = username
        self.password = password
        self.useSSL = useSSL
        self.view = view
        self.morsecode = morsecode

        self.sharingInstance = None

        super(SharingTestDialog, self).__init__()
        self.initDialog()

    def performAction(self):
        d  = self.displayName
        h  = self.host
        p  = self.port
        pa = self.path
        u  = self.username
        ps = self.password
        s  = self.useSSL
        v  = self.view

        if self.sharingInstance == None:
            if self.morsecode:
                self.sharingInstance = MorsecodeTester(h, p, pa, u, ps, s, v)
            else:
                self.sharingInstance = WebDAVTester(h, p, pa, u, ps, s, v)

        reconnect = lambda: SharingTestDialog(d, h, p, pa, u, ps, s, v)

        self.sharingInstance.testAccountSettings(self.OnActionComplete,
                                                reconnect)

    def cancelAction(self):
        self.sharingInstance.cancelLastRequest()

    def getTimeoutText(self):
        return "timeout error"

    def getTitleText(self):
        return _(u"Testing '%(accountName)s'") % \
                  {'accountName': self.displayName}

    def getStartText(self):
        return _(u"Connecting to server '%(hostName)s'") % \
                 {'hostName': self.host}

    def getSuccessText(self, statusValue):
        davCode = statusValue[0]

        msg = constants.MAIL_PROTOCOL_SUCCESS % {'hostName': self.host}
        msg += u"\n\n\t\t"

        if davCode == WebDAV.READ_ONLY:
            msg += READ_ONLY

        else:
            msg += READ_WRITE

        return msg

    def getErrorText(self, statusValue):
        davCode, errText = statusValue

        if davCode == WebDAV.CANT_CONNECT:
            txt = errText

        elif davCode == WebDAV.NO_ACCESS:
            txt = NO_ACCESS

        else:
            txt = UNKNOWN

        return constants.MAIL_PROTOCOL_ERROR % \
                        {'hostName': self.host, 'errText': txt}

class ChandlerIMAPFoldersDialog(ProgressDialog):
    ALLOW_CANCEL      = False
    SUCCESS_TEXT_SIZE = (525, 240)

    def __init__(self, account, callback):
        assert(isinstance(account, IMAPAccount))

        self.TIMEOUT = account.timeout
        self.account = account
        self.callback = callback
        self.mailInstance = None

        super(ChandlerIMAPFoldersDialog, self).__init__()
        self.initDialog()

    def performAction(self):
        self.mailInstance = Globals.mailService.getIMAPInstance(self.account)

        a  = self.account
        cb = self.callback

        reconnect = lambda: ChandlerIMAPFoldersDialog(a, cb)
        self.mailInstance.createChandlerFolders(self.OnActionComplete, reconnect)

    def cancelAction(self):
        # The creation of IMAP folders can not be
        # cancelled since it could leave the IMAP Server
        # in an inconsistent state.
        # However the dialog has no means for the
        # user to manually cancel the action.
        # A call to cancelAction here would
        # only be the result of a timeout
        # in the progress UI which in that
        # case we really do want to cancel.
        self.mailInstance.cancelLastRequest()

    def getTimeoutText(self):
        return constants.MAIL_PROTOCOL_CONNECTION_ERROR

    def getTitleText(self):
        return _(u"Create Chandler IMAP Folders")

    def getStartText(self):
        return _(u"Configuring Chandler IMAP Folders on '%(hostName)s'") % \
                 {'hostName': self.account.host}

    def getSuccessText(self, statusValue):
        return _(u"""\
The following folders have been created in your email account:

Chandler Events - Add messages to this folder add them to your Calendar
Dashboard. Chandler will do its best to parse any date and time information in
the message.

Chandler Mail - Add messages to this folder to add them to your Mail Dashboard.

Chandler Tasks - Add messages to this folder to add them to your Tasks
Dashboard.

All messages added to Chandler folders will show up in your All Dashboard.""")

    def getErrorText(self, statusValue):
        return constants.MAIL_PROTOCOL_ERROR % \
                        {'hostName': self.account.host, 'errText': statusValue}

    def OnError(self, value):
        self.callback((0, None))

    def OnSuccess(self, value):
        self.callback((1, value))


class RemoveChandlerIMAPFoldersDialog(ProgressDialog):
    ALLOW_CANCEL      = False

    def __init__(self, account, callback):
        assert(isinstance(account, IMAPAccount))

        self.TIMEOUT = account.timeout
        self.account = account
        self.callback = callback
        self.mailInstance = None

        super(RemoveChandlerIMAPFoldersDialog, self).__init__()
        self.initDialog()

    def performAction(self):
        self.mailInstance = Globals.mailService.getIMAPInstance(self.account)

        a  = self.account
        cb = self.callback

        reconnect = lambda: RemoveChandlerIMAPFoldersDialog(a, cb)
        self.mailInstance.removeChandlerFolders(self.OnActionComplete, reconnect)

    def cancelAction(self):
        # The removal of IMAP folders can not be
        # cancelled since it could leave the IMAP Server
        # in an inconsistent state.
        # However the dialog has no means for the
        # user to manually cancel the action.
        # A call to cancelAction here would
        # only be the result of a timeout
        # in the progress UI which in that
        # case we really do want to cancel.
        self.mailInstance.cancelLastRequest()

    def getTimeoutText(self):
        return constants.MAIL_PROTOCOL_CONNECTION_ERROR

    def getTitleText(self):
        return _(u"Remove Chandler Folders")

    def getStartText(self):
        return _(u"Removing Chandler IMAP Folders on '%(hostName)s'") % \
                 {'hostName': self.account.host}

    def getSuccessText(self, statusValue):
        return _(u"Chandler IMAP folders have successfully been removed.") % \
                 {"hostname": self.account.host}

    def getErrorText(self, statusValue):
        return constants.MAIL_PROTOCOL_ERROR % \
                        {'hostName': self.account.host, 'errText': statusValue}

    def OnError(self, value):
        self.callback((0, None))

    def OnSuccess(self, value):
        #Call out these values to accout pref layer to cache
        #till the user hits ok
        #Could make changes to the account but not commit
        #if the user hits cancel call self.view.cancel()

        self.callback((1, value))

class AutoDiscoveryDialog(ProgressDialog):
    SUCCESS_TEXT_SIZE = (450, 135)
    APPLY_SETTINGS = True

    def __init__(self, hostname, isOutgoing=False, view=None, callback=None):
        self.hostname = hostname
        self.callback = callback
        self.isOutgoing = isOutgoing
        self.view = view
        self.discoverInstance = None
        self.discoveredAccount = None

        if isOutgoing:
            self.TIMEOUT = 25 #25 seconds
        else:
            self.TIMEOUT = 35 #35 seconds

        super(AutoDiscoveryDialog, self).__init__()
        self.initDialog()

    def performAction(self):
        h = self.hostname
        v = self.view
        o = self.isOutgoing
        c = self.callback

        reconnect = lambda: AutoDiscoveryDialog(h, o, v, c)

        if o:
            self.discoverInstance = autodetect.OutgoingDiscovery(h, self.OnActionComplete,
                                                      reconnect, v)
        else:
            self.discoverInstance = autodetect.IncomingDiscovery(h, self.OnActionComplete,
                                                      reconnect, v)

        self.discoverInstance.discover()


    def cancelAction(self):
        self.discoverInstance.cancelDiscovery()

    def getTimeoutText(self):
        return constants.MAIL_PROTOCOL_CONNECTION_ERROR

    def getTitleText(self):
        return _(u"Autodiscovering  '%(hostname)s'") % \
                          {'hostname': self.hostname}

    def getStartText(self):
        return _(u"Discovering mail settings for server '%(hostName)s'") % \
                 {'hostName': self.hostname}

    def getSuccessText(self, statusValue):
        return _(u"\tThe following settings were returned:\n\n\tType: %(type)s\n\tPort: %(port)s\n\tSecurity: %(security)s\n") % \
                    {"type": self.discoveredAccount.accountProtocol,
                     "port": self.discoveredAccount.port,
                     "security": self.discoveredAccount.connectionSecurity}

    def getErrorText(self, statusValue):
        return _(u"Chandler was unable to Auto-configure account settings\nfor '%(host)s'.") % \
                        {"host": self.hostname}

    def OnSuccess(self, value):
        self.discoveredAccount = value

    def OnApplySettings(self, evt):
        self.callback(self.discoveredAccount)
        self.OnClose(evt)

def showOKDialog(title, msg):
    return showMsgDialog(MsgDialog.OK, title, msg)

def showYesNoDialog(title, msg):
    return showMsgDialog(MsgDialog.YES_NO, title, msg)

def showMsgDialog(type, title, msg):
    win = MsgDialog(type, title, msg)
    win.CenterOnScreen()
    res = win.ShowModal()

    win.Destroy()
    return res

class MsgDialog(wx.Dialog):
    """
        A MessageDialog that always centers
        itself on the screen.

        Depending on the platform the
        wx.MessageDialog may not be centered
    """

    OK = 1
    YES_NO = 2

    def __init__(self, type, title, msg):
        super(MsgDialog, self).__init__(None, -1, title)
        self.title = title
        self.msg = msg
        self.type = type

        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.label = wx.StaticText(self, -1, self.msg)
        self.sizer.Add(self.label, 0, wx.ALIGN_LEFT|wx.ALL, 30)
        self.buttons = []

        self.getButtons()

        for button in self.buttons:
            self.buttonSizer.Add(button, 0, wx.ALIGN_RIGHT|wx.ALL, 5)
            button.Bind(wx.EVT_BUTTON, self.OnClick)

        self.sizer.Add(self.buttonSizer, 0, wx.ALIGN_RIGHT|wx.ALL, 10)
        self.SetSizer(self.sizer)
        self.SetAutoLayout(True)
        self.sizer.Layout()
        self.sizer.SetSizeHints(self)
        self.sizer.Fit(self)

    def OnClick(self, evt):
        if self.type == self.YES_NO:
            self.EndModal(evt.GetId() == wx.ID_YES)

        else:
            self.EndModal(True)

    def getButtons(self):
        if self.type == self.OK:
            self.buttons.append(wx.Button(self, wx.ID_OK))

        elif self.type == self.YES_NO:
            self.buttons.append(wx.Button(self, wx.ID_NO))
            self.buttons.append(wx.Button(self, wx.ID_YES))