import unittest
from datetime import datetime, time
from PyICU import *
from osaf.pim.calendar import DateTimeUtil

class AbstractTestCase(unittest.TestCase):
    """
    An abstract class that sets global PyICU locale and timezone
    settings at setUp time, and then restores the defaults in
    test tearDown. This makes for more reproducible
    parsing/formatting unit tests.
    
    @ivar locale: Override to run your test class with a different
                  locale.
    @type locale: PyICU.Locale

    @ivar tzinfo:
    @type tzinfo: PyICU.ICUtzinfo
    """

    locale = Locale.getUS()
    tzinfo = ICUtzinfo.getInstance("US/Pacific")

    def setUp(self):
        self.__savedLocale = Locale.getDefault()
        self.__savedTzinfo = ICUtzinfo.default

        Locale.setDefault(self.locale)
        TimeZone.setDefault(self.tzinfo.timezone)

    def tearDown(self):
        TimeZone.setDefault(self.__savedTzinfo.timezone)
        Locale.setDefault(self.__savedLocale)



class ShortDateParse(AbstractTestCase):

    def testSimple(self):
        parsed = DateTimeUtil.shortDateFormat.parse("12/11/04")

        self.failUnlessEqual(parsed, datetime(2004,12,11))

    def testFullYear(self):
        parsed = DateTimeUtil.shortDateFormat.parse("3/7/2005")

        self.failUnlessEqual(parsed, datetime(2005,3,7))

    def testOutOfRangeYear(self):
        # Whoa, dude, that's a crazy year. But it triggers
        # bug 5650 on all platforms (e.g. 1904 works on
        # Unixes).
        parsed = DateTimeUtil.shortDateFormat.parse("4/18/102")

        self.failUnlessEqual(parsed, datetime(102,4,18))

    def testSimpleWithReference(self):
        tzinfo = ICUtzinfo.getInstance("US/Eastern")
        parsed = DateTimeUtil.shortDateFormat.parse(
                    "12/11/04",
                    datetime(2006, 1, 1,tzinfo=tzinfo))

        self.failUnlessEqual(parsed, datetime(2004,12,11, tzinfo=tzinfo))

    def testFullYearWithReference(self):
        tzinfo = ICUtzinfo.getInstance("Asia/Shanghai")
        parsed = DateTimeUtil.shortDateFormat.parse(
                    "3/7/2005",
                    datetime(2002, 1, 9,tzinfo=tzinfo))

        self.failUnlessEqual(parsed, datetime(2005,3,7, tzinfo=tzinfo))

    def testOutOfRangeYearWithReference(self):
        tzinfo = ICUtzinfo.getInstance("Europe/Rome")
        parsed = DateTimeUtil.shortDateFormat.parse(
                    "4/18/102",
                    datetime(1999,9,9,tzinfo=tzinfo))

        self.failUnlessEqual(parsed, datetime(102,4,18, tzinfo=tzinfo))


class ShortTimeParse(AbstractTestCase):

    def testPM(self):
        parsed = DateTimeUtil.shortTimeFormat.parse("12:03 PM")

        self.failUnlessEqual(parsed.timetz(), time(12, 3))

    def testAM(self):
        parsed = DateTimeUtil.shortTimeFormat.parse("12:52 AM")

        self.failUnlessEqual(parsed.timetz(), time(0, 52))


"""
Tests to write:

- Other formatters in DateTimeUtil.py
- Output tests
- Other locales/timezones

"""

if __name__ == "__main__":
    unittest.main()
