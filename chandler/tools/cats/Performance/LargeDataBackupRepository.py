print """
####
#### WARNING
#### THIS FILE IS NOT BEING USED TO TEST PERFORMANCE 
#### THIS FILE IS STILL IN DEVELOPMENT.  USE THE FILES IN      
#### tools/QATestScripts/Performance                                  
####
"""
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
#   limitations under the License.

import tools.cats.framework.ChandlerTestLib as QAUITestAppLib
import os
import osaf.pim as pim
from tools.cats.framework.ChandlerTestCase import ChandlerTestCase

class LargeDataBackupRepository(ChandlerTestCase):

    def startTest(self):

        # import
        self.logger.startAction('importing Generated3000.ics')
        QAUITestAppLib.UITestView(self.logger, u'Generated3000.ics')
        self.logger.endAction()
        
        # verification of import
        def VerifyEventCreation(title):
            #global logger
            #global App_ns
            #global pim
            self.logger.startAction('verifying imported event ' + title)
            testEvent = self.app_ns.item_named(pim.CalendarEvent, title)
            if testEvent is not None:
                self.logger.endAction(True, "Testing event creation: '%s'" % title)
            else:
                self.logger.endAction(False, "Testing event creation: '%s' not created" % title)
        
        VerifyEventCreation("Go to the beach")
        VerifyEventCreation("Basketball game")
        VerifyEventCreation("Visit friend")
        VerifyEventCreation("Library")
        
        # backup
        # - need to commit first so that the collection in the sidebar
        #   gets saved
        self.app_ns.itsView.commit()
        self.logger.startAction("Backup repository")
        dbHome = self.app_ns.itsView.repository.backup()
        
        # verification of backup
        if os.path.isdir(dbHome):
            self.logger.endAction(True, "Backup exists")
        else:
            self.logger.endAction(False, "Backup does not exist")
        
    
