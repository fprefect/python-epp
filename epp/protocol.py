#!/usr/bin/env python

from twisted.internet import protocol
from string import Template
import exceptions
import struct
import re


class EPP(protocol.Protocol):
	MAX_LENGTH = 99999

	def __init__(self):
		self.recvd = ""

	def frameReceived(self, frame):
		''' Must be implemented in subclass '''
		raise NotImplementedError

	def lineLengthExceeded(self):
		self.transport.loseConnection()

	def dataReceived(self, recd):
		self.recvd += recd
		while len(self.recvd) >= 4:
			length ,= struct.unpack("!L",self.recvd[:4])
			if length > self.MAX_LENGTH:
				self.lineLengthExceeded()
				return
			if len(self.recvd) < length:
				break
			packet = self.recvd[4:length]
			self.recvd = ''
			self.frameReceived(EPPFrame(packet))

	def sendFrame(self, frame):
		self.transport.write(frame.packed())

class EPPFrame():
	_re_command  = re.compile('<epp[^>]+>\s*<(command|greeting)>\s*<([^>/]+)/?>')
	_re_response = re.compile('<result[^>]+code=("|\')(\d{4})("|\')')

	def __init__(self, xml):
		self.xml = xml
		self._frameType = None

	def frameType(self):
		if self._frameType: 
			return self._frameType

		m = self._re_command.search(self.xml, re.S)
		if m:
			self._frameType = m.group(1) == "command" and m.group(2) or m.group(1)
			return self._frameType

		m = self._re_response.search(self.xml, re.S)
		if m:
			self._frameType = int(m.group(2)) < 2000 and "success" or "error"
			return self._frameType

		self._frameType = "unknown"
		return "unknown"

	def packed(self):
		return struct.pack("!L", len(self.xml) + 4) + self.xml


class EPPTemplateFrame(EPPFrame):
	_re_escape = re.compile('("|&|<|>)')
	_escape_map = {'"':'&quot','&':'&amp;','<':'&lt;','>':'&gt;'}

	xml_error = '''<?xml version="1.0"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
 xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd">
	<response>
		<result code="2500"><msg>${msg}</msg></result>
		<trID><clTRID>${clTRID}</clTRID><svTRID>${svTRID}</svTRID></trID>
	</response>
</epp>'''

	xml_logout = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?><epp xmlns="urn:ietf:params:xml:ns:epp-1.0"><command><logout/><clTRID>${clTRID}</clTRID></command></epp>'''

	xml_logout_response = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?><epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><response><result code="1500"><msg>Command completed successfully; ending session</msg></result><trID><clTRID>${clTRID}</clTRID><svTRID>${svTRID}</svTRID></trID></response></epp>'''
	
	xml_hello = '''<?xml version="1.0" encoding="UTF-8" standalone="no"?><epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><hello/></epp>'''
	
	def __init__(self, type, vars={}):
		self._frameType, self.vars = type, vars
		self._xml = None

	@property
	def xml(self):
		if self._xml: return self._xml
		xml = getattr(self, 'xml_'+self._frameType)
		if not xml:
			raise LookupError(self._frameType)
		if "msg" in self.vars:
			self.vars["msg"] = re.sub(self._re_escape, self._cbEscape, self.vars["msg"])
		if "svTRID" not in self.vars:
			self.vars["svTRID"] = "PROXY-00000"
		if "clTRID" not in self.vars:
			self.vars["clTRID"] = "PROXY-11111"
		t = Template(xml)
		self._xml = t.substitute(self.vars)
		return self._xml

	def _cbEscape(self, m):
		if m.group(0) not in self._escape_map: return m.group(0)
		return self._escape_map[m.group(0)]
