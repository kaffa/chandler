#   Copyright (c) 2003-2007 Open Source Applications Foundation
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
Unit tests for Types
"""

import os, unittest

from chandlerdb.util.RepositoryTestCase import RepositoryTestCase
import chandlerdb.schema.Types
import chandlerdb.item.PersistentCollections

from chandlerdb.schema.Attribute import Attribute
from chandlerdb.util.Path import Path
from chandlerdb.util.c import UUID
from chandlerdb.item.c import ItemRef
from datetime import datetime, timedelta


class TypesTest(RepositoryTestCase):
    """ Test Types """

    def setUp(self):
        super(TypesTest, self).setUp()

        view = self.view
        self.kind = view.findPath(self._KIND_KIND)
        self.itemKind = view.findPath(self._ITEM_KIND)
        self.attrKind = self.itemKind.itsParent['Attribute']
        self.newKind = self.kind.newItem('newKind', view)
        self.typeKind = view.findPath('//Schema/Core/Type')

        self.typenames=['String', 'Symbol', 'Integer', 'Long', 'Float',
                        'Complex', 'Boolean', 'UUID', 'ItemRef', 'Path',
                        'NoneType', 'Class', 'Enumeration', 'Struct',
                        'DateTime', 'TimeDelta',
                        'Collection', 'Dictionary', 'List', 'Lob']

        # make dict of attribute and  type items.
        self.atts = {}
        self.types = {}
        for a in self.typenames:
            tempAtt = Attribute('%sAttribute' % a, view, self.attrKind)
            classobj = eval('chandlerdb.schema.Types.%s' % a)
            typeItem = view.findPath('//Schema/Core/%s' % a)
            self.types[a] = typeItem
            tempAtt.type = typeItem
            self.atts[a] = tempAtt
            self.newKind.addValue('attributes', tempAtt, alias='%sAttribute' % a)

    def testHandlerName(self):
        """ Test that handlerName returns the correct value """

        # None entries mean we don't test -- handlername is unimplmented for these
        handlerNames = { 'String':'unicode', 'Symbol':'str', 'Integer':'int',
                         'Long':'long', 'Float':'float', 'Complex':'complex',
                         'Boolean':'bool', 'UUID':'uuid', 'ItemRef':'ref',
                         'Path':'path', 'NoneType':None, 'Class':'class',
                         'Enumeration':'ref', 'Struct':'ref', 'DateTime':None,
                         'TimeDelta':None,
                         'Collection':None, 'Dictionary':'dict', 'List':'list',
                         'Lob':'lob' }

        for i in handlerNames:
            if handlerNames[i] is not None:
                self.assertEquals(handlerNames[i],
                                  self.newKind.getAttribute('%sAttribute' % i).getAspect('type').handlerName())
                
    def testGetImplementationType(self):
        """ Test getImplementationType() """
        # we don't test NoneType, Enumeration, Struct, Collection, or Lob
        # because they are abstract and have no implementation type
        implTypeNames = { 'String':'unicode', 'Symbol':'str', 'Integer':'int',
                          'Long':'long', 'Float':'float', 'Complex':'complex',
                          'Boolean':'bool', 'UUID':'UUID',
                          'ItemRef':'ItemRef',
                          'Path':'Path', 'Class':'type',
                          'DateTime':'datetime',
                          'TimeDelta':'timedelta',
                          'Dictionary':'chandlerdb.item.PersistentCollections.PersistentDict',
                          'List':'chandlerdb.item.PersistentCollections.PersistentList',
                          'Set':'chandlerdb.item.PersistentCollections.PersistentSet',
                          'Lob':'chandlerdb.persistence.DBLob.DBLob' }
        excludes = ['NoneType','Enumeration','Struct','Collection']

        view = self.view
        for n in [ x for x in self.typenames if x not in excludes ]:
            t = view.findPath("//Schema/Core/%s" % n)
            # types in the list below have no impls -- abstract classes
            if t is not None:
                self.assert_(t.getImplementationType() is eval(implTypeNames[n]))


    def testMakeValue(self):
        """ Test value creation via makeValue """
        # we don't test NoneType, Collection, and Lob because they don't
        # create values
        typeStrings = { 'String':'abcde', 'Symbol':'str', 'Integer':'123',
                        'Long':'456', 'Float':'123.456', 'Complex':'(34.4+3j)',
                        'Boolean':'True', 'UUID':str(self.attrKind.itsUUID),
                        'ItemRef':str(self.attrKind.itsUUID),
                        'Path':'//Schema/Core/Item', 'NoneType':None,
                        'Class':'tests.TestTypes.TypesTest',
                        'Enumeration':'ref',
                        'Struct':'ref', 'DateTime':'2004-01-08 12:34:56.15',
                        'TimeDelta':'-8+45.12',
                        'Collection':None, 'Dictionary':'{"a":"b","c":"d"}',
                        'List':'["one", "two", 3]', 'Lob':'lob' }
        excludes = [ 'NoneType','Enumeration','Struct','Collection' ]

        view = self.view
        for name in [ x for x in typeStrings if x not in excludes ]:
            typeItem = view.findPath('//Schema/Core/%s' % name)
            actualType = type(typeItem.makeValue(typeStrings[name]))
            implType = typeItem.getImplementationType()
            self.assert_(actualType is implType or
                         getattr(implType, '__proxy_for__', None) is actualType or
                         actualType in implType.__bases__, name)

    def _makeValidValues(self):
        """ create valid values of appropriate types"""

        class myStruct(object):
            __slots__ = ('name', 'rank')
            
        view = self.view
        self.uuid = self.attrKind.itsUUID
        self.uuidString = str(self.uuid)
        self.pathString = '//Schema/Core/Item'
        self.path = Path(self.pathString)
        self.itemRef = ItemRef(self.uuid, view)
        self.itemClass = eval('chandlerdb.item.Item.Item')
        self.dateTimeString = '2004-01-08 12:34:56 US/Mountain'
        self.dateTime = datetime(2004, 1, 8, 12, 34, 56,
                                 tzinfo=view.tzinfo.getInstance('US/Mountain'))
        self.timeDeltaString= '-8+45.000012'
        self.timeDelta = timedelta(-8, 45, 12)
        
        self.enum = self.types['Enumeration'].newItem('myEnum', view)
        self.enum.values = ['red', 'green', 'blue']

        self.structType = self.types['Struct'].newItem('myStruct', view)
        self.structType.fields=['name','rank']
        self.structType.implementationTypes = {'python': myStruct }
        self.struct = myStruct()

        self.lob = self.types['Lob'].makeValue("aba;dsjfa;jfdl;ajru87z.vncxyt89q47654", encoding='utf-8', mimetype='text/plain')

    def testMakeString(self):
        """ Test makeString

            Verify the invariant i.makeValue(i.makeString(v)) == v where
            i is a type item for the value
            v is a value of the type recognized by the type item.
            @@@TODO, what about illegal values?
        """

        # Compute some values before creating the dicts.
        self._makeValidValues()

        # we don't test NoneType because it can't create values
        # we don't test Collection and Lob because they are abstract types
        # we don't test Lob because it doesn't implement makeString()
        # dict keyed by type name, values is a legal string value for that type
        typeStrings = { 'String':'abcde', 'Symbol':'str', 'Integer':'123',
                        'Long':'456', 'Float':'123.456', 'Complex':'(2.4+8j)',
                        'Boolean':'True', 'UUID':self.uuidString,
                        'ItemRef':self.uuidString, 'Path':self.pathString,
                        'NoneType':None, 'Class':'chandlerdb.item.Item.Item',
                        'Enumeration':'green',
                        'Struct':'ref',
                        'DateTime':self.dateTimeString,
                        'TimeDelta':self.timeDeltaString,
                        'Collection':None,
                        'Dictionary':'{"a":"b","c":"d"}',
                        'List':'[one, two, 3]', 'Lob':'lob' }

        # dict keyed by typename, value is legal values for that
        typeValues = { 'String':'abcde', 'Symbol':'str', 'Integer':123,
                       'Long':456, 'Float':123.456, 'Complex':2.4+8j,
                       'Boolean':True, 'UUID':self.uuid,
                       'ItemRef':self.itemRef, 'Path':self.path,
                       'NoneType':None, 'Class': self.itemClass,
                       'Enumeration':self.enum, 'Struct':self.struct,
                       'DateTime':self.dateTime,
                       'TimeDelta':self.timeDelta,
                       'Collection':None,
                       'Dictionary':{"a":"b","c":"d"},
                       'List':["one", "two", "3"], 'Lob':'lob' }

        excludes = [ 'NoneType', 'Collection', 'Enumeration', 'Struct',
                     'Lob' ]

        view = self.view
        for name in [ x for x in typeValues if x not in excludes ]:
            typeItem = view.findPath('//Schema/Core/%s' % name)
            try:
                self.assert_(typeItem.makeString(typeValues[name]) is not None)

                typeItem = view.findPath('//Schema/Core/%s' % name)
                self.assert_(typeItem.makeValue(typeStrings[name]) is not None)

                self.assertEquals(typeItem.makeValue(typeItem.makeString(typeValues[name])), typeValues[name])
            except Exception, e: # mostly for debug
                print name, typeValues[name]
                try:
                    print '\t value: ',typeItem.makeValue(typeStrings[name])
                except Exception, e1:
                    print "no value"
                    print e1
                try:
                    print '\t string: ', typeItem.makeString(typeValues[name])
                except Exception, e1:
                    print "no string"
                    print e1
                print "testMakeString: ",e
                self.fail()


    def testRecognizes(self):
        """ Test the recognizes method on types """

        self._makeValidValues()

        # dict of test values keyed by Type name
        # dict values are tuples of a single good value (of the right type)
        #      and a list of bad values (of the wrong type)
        typeValues = { 'String':('abcde',[124]), 'Symbol':('str',[1324]),
                       'Integer':(123,[1234.43]), 'Long':(456,[1.5]),
                       'Float':(123.456,['abcd']), 'Complex':(2.4+8j,['abcd']),
                       'Boolean':(True, ['abcd']), 'UUID':(self.uuid,['abcd']),
                       'ItemRef':(self.itemRef, ['abcde']),
                       'Path':(self.path, ['abcde']),
                       'NoneType':(None, [None]),
                       'Class': (self.itemClass, ['abcde']),
                       'Enumeration':('green', ['abcde']),
#                       'Struct':(str(self.struct.itsUUID), ['abcde']),
                       'DateTime':(self.dateTime,["abacde"]),
                       'TimeDelta':(self.timeDelta, ["abcde"]),
                       'Collection':(None, [None]),
                       'Dictionary':({"a":"b","c":"d"}, ["abcde"]),
                       'List':(["one", "two", "3"], ["abcde"]),
                       'Lob':(self.lob, [123]) }

        view = self.view
        for name in typeValues:
            goodValue, badValues = typeValues[name]
#            print name, goodValue, badValues
            if goodValue != None:
                typeItem = view.findPath('//Schema/Core/%s' % name)
                # special case Enum
                if name == 'Enumeration':
                    typeItem = self.enum
                try:
                    self.assert_(typeItem.recognizes(goodValue))
#                    print "good: %s : %s" % (typeItem , goodValue)
                except:
                    print "Invalid good value for %s: %s" % (name, goodValue)
                    self.fail()
                for bad in badValues:
                    try:
                        self.assert_(not typeItem.recognizes(bad))
#                        print "bad: %s : %s" % (typeItem , goodValue)
                    except:
                        print "Invalid bad value for %s: %s" % (name, bad)
                        self.fail()
#            else:
#                print "fell off the end for ",name

    def testEval(self):
        """ """
        #@@@ right now andi says this is a hack.
        pass

#@@@ disabled until Kind.findTypes is rewritten
    def tstKindFindTypes(self):
        """ Test the findTypes method on the Type Kind """

        self._makeValidValues()

        view = self.view
        typeKind = view.findPath('//Schema/Core/Type')

        # build up lists of types as expected values for findTypes calls
        stringTypes = [ self.types['String'], self.types['Symbol'] ]
        integerTypes = [ self.types['Integer'], self.types['Long'],
                         self.types['Float'] ]
        floatTypes = [ self.types['Float'] ]
        complexTypes = [ self.types['Complex'] ]
        booleanTypes = [ self.types['Boolean'] ]
        itemRefTypes = [ self.types['ItemRef'] ]
        uuidTypes = [ self.types['UUID'] ]
        pathTypes = [ self.types['Path'] ]
        noneTypes = [ view.findPath('//Schema/Core/None'), self.types['Path'], self.types['ItemRef'], self.types['UUID'] ]
        classTypes = [ self.types['Class'] ]
        enumTypes = [ self.types['Enumeration'] ]
        structTypes = [ self.types['Struct'] ]
        dateTimeTypes = [ self.types['DateTime'] ]
        timeDeltaTypes = [ self.types['TimeDelta'] ]
        dictTypes = [ self.types['Dictionary'] ]
        listTypes = [ self.types['List'] ]
        lobTypes = [ self.types['Lob'] ]
        binaryTypes = [ self.types['Binary'] ]

        # dict keyed by values of a type,
        # dict values are the right expected types list for the value
        values = {"abacde":stringTypes, "1234":stringTypes, 123:integerTypes,
                  1234.456:floatTypes, 1.23+45j:complexTypes,
                  True: booleanTypes, False: booleanTypes,
                  self.uuid: uuidTypes, self.itemRef: itemRefTypes,
                  self.path: pathTypes,
                  None:noneTypes, self.itemClass:classTypes,
# findTypes doesn' work for structs and enums
#                  self.enum:enumTypes,
#                  self.struct:structTypes,
                  self.dateTime:dateTimeTypes,
                  self.timeDelta:timeDeltaTypes,
                  self.lob:lobTypes}

        for v in values:
            foundTypes = typeKind.findTypes(v)
            print 'v', v
            print 'foundTypes', foundTypes
            print 'values[v]', values[v]
            print 'equals ?', foundTypes == values[v]
            print "=============="
            self.assertEquals(foundTypes, values[v])

        # special case because lists and dicts are unhashable
        foundTypes = typeKind.findTypes({"a":"b","c":"d"})
        self.assertEquals(foundTypes, dictTypes)
        foundTypes = typeKind.findTypes(["one", "two", "3"])
        self.assertEquals(foundTypes, listTypes)

if __name__ == "__main__":
#    import hotshot
#    profiler = hotshot.Profile('/tmp/TestItems.hotshot')
#    profiler.run('unittest.main()')
#    profiler.close()
    unittest.main()
        
