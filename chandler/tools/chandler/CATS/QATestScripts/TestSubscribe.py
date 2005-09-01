import osaf.framework.QAUITestAppLib as QAUITestAppLib
import os
import application.dialogs.SubscribeCollection as SubscribeCollection
import application.Globals as Globals
import wx
from i18n import OSAFMessageFactory as _

App_ns = QAUITestAppLib.App_ns

filePath = os.path.expandvars('$CATSREPORTDIR')
if not os.path.exists(filePath):
    filePath = os.getcwd()

#initialization
fileName = "TestSubscribe.log"
logger = QAUITestAppLib.QALogger(os.path.join(filePath, fileName),"TestSubscribe")

#action
#Webdav Account Setting
logger.Start("WebDAV account setting")
ap = QAUITestAppLib.UITestAccounts(logger)
ap.Open() # first, open the accounts dialog window
ap.CreateAccount("WebDAV")
ap.TypeValue("displayName", "Subscribe Test WebDAV")
ap.TypeValue("host", "qacosmo.osafoundation.org")
ap.TypeValue("path", "home/demo1")
ap.TypeValue("username", "demo1")
ap.TypeValue("password", "ad3leib5")
ap.TypeValue("port", "8080")
ap.ToggleValue("ssl", False)
ap.ToggleValue("default", True)
ap.Ok()
logger.Stop()
#verification
ap.VerifyValues("WebDAV", "Subscribe Test WebDAV", displayName = "Subscribe Test WebDAV", host = "qacosmo.osafoundation.org", username = "demo1",
                password="ad3leib5", port=8080)

#Subscribe dialog
logger.Start("Subscribe dialog")
xrcFile = os.path.join(Globals.chandlerDirectory, 'application', 'dialogs', 'SubscribeCollection_wdr.xrc')
resources = wx.xrc.XmlResource(xrcFile)
win = SubscribeCollection.SubscribeDialog(wx.GetApp().mainFrame, _("Subscribe to Shared Collection"), resources=resources, view=App_ns.itsView, url=None)
win.CenterOnScreen()
win.Show()
wx.GetApp().Yield()
window = GetWindow("Subscribe to Shared Collection")
url = window.toolPanel.GetChildren()[1]
url.SetFocus()
url.Clear()
wx.GetApp().Yield()
QAUITestAppLib.scripting.User.emulate_typing("webcal://qacosmo.osafoundation.org:8080/home/demo1/TestCal.ics")
window.OnSubscribe(None)
win.Destroy()
wx.GetApp().Yield()
logger.Stop()
#verification
logger.SetChecked(True)
if QAUITestAppLib.scripting.User.emulate_sidebarClick("TestCal"):
    logger.ReportPass("(On Subscribe collection)")
else:
    logger.ReportFailure("(On Subscribe collection)")
#report the checkings
logger.Report("Sidebar")

#cleaning
logger.Close()
