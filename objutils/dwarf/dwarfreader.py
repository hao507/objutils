#!/usr/bin/env python
# -*- coding: utf-8 -*-

__version__ = "0.1.0"

__copyright__ = """
    pyObjUtils - Object file library for Python.

   (C) 2010-2013 by Christoph Schueler <github.com/Christoph2,
                                        cpu12.gems@googlemail.com>

   All Rights Reserved

  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License along
  with this program; if not, write to the Free Software Foundation, Inc.,
  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

from collections import namedtuple

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import struct

from objutils.readers import PlainBinaryReader

from objutils.dwarf import constants

FORM_READERS = {
    constants.DW_FORM_string:       'asciiz',
    constants.DW_FORM_udata:        'uleb',
    constants.DW_FORM_sdata:        'sleb',
    constants.DW_FORM_data1:        'u8',
    constants.DW_FORM_data2:        'u16',
    constants.DW_FORM_data4:        'u32',
    constants.DW_FORM_data8:        'u64',
    constants.DW_FORM_addr:         'u32',  ## TODO: Target word size!!!
    constants.DW_FORM_block:        'block',
    constants.DW_FORM_block1:       'block1',
    constants.DW_FORM_block2:       'block2',
    constants.DW_FORM_block4:       'block4',
    constants.DW_FORM_flag:         'u8',
    constants.DW_FORM_ref_addr:     'u32',
    constants.DW_FORM_ref1:         'u8',
    constants.DW_FORM_ref2:         'u16',
    constants.DW_FORM_ref4:         'u32',
    constants.DW_FORM_ref8:         'u64',
    constants.DW_FORM_ref_udata:    'uleb',
    ###
    constants.DW_FORM_strp:         '', # TODO: This is a offset into string table (.debug_str)!!!
    constants.DW_FORM_indirect:     '', # TODO: uleb value, that represents its form!
    constants.DW_FORM_sec_offset:   '', # This is an offset into the .debug_line/.debug_loc /.debug_macinfo section, p. 162ff
    constants.DW_FORM_exprloc:      '', # This is an unsigned LEB128 length followed by the number of information
                                        # bytes specified by the length (DW_FORM_exprloc).
    constants.DW_FORM_flag_present: '', #  the attribute is implicitly indicated as present, and no value is
                                        # encoded in the debugging information entry itself
    constants.DW_FORM_ref_sig8:     'u64',
}

AbbreviationEntry = namedtuple('Abbreviation', 'tag, children, attrs')

SET_OFFSET      = 1
IGNORE_OFFSET   = 2


class DwarfReader(PlainBinaryReader):

    def __init__(self, image):
        super(DwarfReader, self).__init__(StringIO.StringIO(image), DwarfReader.BIG_ENDIAN)

    def uleb(self):
        result = 0
        shift = 0
        while True:
            bval = self.nextByte()
            result |= ((bval & 0x7f) << shift)
            if bval & 0x80 == 0:
                break
            shift += 7
        return result

    def sleb(self):
        result = 0
        shift = 0
        idx =0
        while True:
            bval = self.nextByte()
            result |= ((bval & 0x7f) << shift)
            shift += 7
            idx += 1
            if bval & 0x80 == 0:
                break
        if (shift < 32) or (bval & 0x40) == 0x40:
            mask = - (1 << (idx * 7))
            result |= mask
        return result

    def _block(self, size):
        _BLOCK_SIZE_READER = {1: self.u8, 2: self.u16, 4: self.u32, -1: self.uleb}
        return [self.u8() for _ in range(_BLOCK_SIZE_READER[size]())]

    def block1(self):
        return self._block(1)

    def block2(self):
        return self._block(2)

    def block4(self):
        return self._block(4)

    def block(self):
        return self._block(-1)


def makeAttrName(value):
    return value.replace('TAG','').title().replace('_', '')


class DebugSectionReader(object):

    def __init__(self, sections):
        self.sections = sections
        self.abbrevs = {}

    def process(self):
        self.processAbbreviations()
        self.processInfoSection()
        #print self.abbrevs

    def processAbbreviations(self):
        image = self.sections['.debug_abbrev'].image
        dr = DwarfReader(image)
        totalSize = len(image)
        abbrevs = {}
        abbrevEntries = {}
        offsetState = SET_OFFSET
        while dr.pos < totalSize:
            if offsetState == SET_OFFSET:
                offset = dr.pos
                offsetState = IGNORE_OFFSET
            code = dr.uleb()
            if code == 0:
                abbrevs[offset] = abbrevEntries
                abbrevEntries = {}
                offsetState = SET_OFFSET
                continue
            tagValue = dr.uleb()
            tag = constants.TAG_MAP.get(tagValue, tagValue)
            children = dr.u8()
            attrSpecs = []
            while True:
                attrValue = dr.uleb()
                attr = constants.AttributeEncoding(attrValue)
                formValue = dr.uleb()
                form = constants.AttributeForm(formValue)
                if attrValue == 0 and formValue == 0:
                    break
                attrSpecs.append((attr, form))
            abbrevEntries[code] = AbbreviationEntry(tag, "DW_CHILDREN_yes" if children == constants.DW_CHILDREN_yes else "DW_CHILDREN_no", attrSpecs)
        self.abbrevs = abbrevs

    def processInfoSection(self):
        image = self.sections['.debug_info'].image
        dr = DwarfReader(image)
        while dr.pos < len(image):
            length = dr.u32()
            stopPosition = dr.pos + length
            dwarfVersion = dr.u16()
            abbrevOffs = dr.u32()
            abbrevs = self.abbrevs[abbrevOffs]
            targetAddrSize = dr.u8()

            while dr.pos < stopPosition:
                number = dr.uleb()
                if number == 0:
                    print "<*** EMPTY ***>"
                    continue
                entry = abbrevs[number]
                print "=" * 80
                print entry.tag, entry.children
                print "=" * 80
                for attr in entry.attrs:
                    attribute, form = attr
                    reader = FORM_READERS[form.value]
                    attrValue = getattr(dr, reader)()
                    print "%s ==> '%s'" % (attribute, attrValue)
