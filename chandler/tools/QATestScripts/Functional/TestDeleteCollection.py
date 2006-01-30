import tools.QAUITestAppLib as QAUITestAppLib
import osaf.framework.scripting as scripting

# initialization
fileName = "TestDeleteCollection.log"
logger = QAUITestAppLib.QALogger(fileName, "TestDeleteCollection")

try:
    # creation
    col = QAUITestAppLib.UITestItem("Collection", logger)

    # action
    app_ns=scripting.app_ns()
    sb=app_ns.sidebar
    scripting.User.emulate_sidebarClick(sb,'Untitled') #move focus from collection name text to collection
    col.DeleteCollection()

    # verification
    col.Check_CollectionExistance(expectedResult=False)

finally:
    #cleaning
    pass
    logger.Close()
