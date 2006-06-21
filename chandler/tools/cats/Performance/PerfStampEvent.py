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
from tools.cats.framework.ChandlerTestCase import ChandlerTestCase

class PerfStampEvent(ChandlerTestCase):

    def startTest(self):
    
        filePath = os.getenv('CATSREPORTDIR')
        if not filePath:
            filePath = os.getcwd()
 
        # creation
        note = QAUITestAppLib.UITestItem("Note", self.logger)
    
        # action
        note.StampAsCalendarEvent(True)
        
        # verification
        note.Check_DetailView({"stampEvent":True})

