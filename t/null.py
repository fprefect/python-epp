#!/bin/env python

from twisted.internet import epollreactor
epollreactor.install()

from twisted.internet import reactor, defer, protocol
from twisted.python import log
from OpenSSL import SSL
import sys

from epp.protocol import EPP, EPPFrame

class EPPNullServer(EPP):
	def connectionMade(self):
		log.msg("New connection")
		self.sendFrame(EPPFrame('''<?xml version="1.0"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><greeting><svID>VeriSign Com/Net EPP Registration Server</svID><svDate>2009-10-23T00:54:08.0265Z</svDate><svcMenu><version>1.0</version><lang>en</lang><objURI>urn:ietf:params:xml:ns:domain-1.0</objURI><objURI>urn:ietf:params:xml:ns:host-1.0</objURI><svcExtension><extURI>http://www.verisign.com/epp/idnLang-1.0</extURI><extURI>http://www.verisign-grs.com/epp/namestoreExt-1.1</extURI><extURI>urn:ietf:params:xml:ns:rgp-1.0</extURI><extURI>http://www.verisign.com/epp/whoisInf-1.0</extURI><extURI>http://www.verisign.com/epp/sync-1.0</extURI></svcExtension></svcMenu><dcp><access><all/></access><statement><purpose><admin/><other/><prov/></purpose><recipient><ours/><public/><unrelated/></recipient><retention><indefinite/></retention></statement></dcp></greeting></epp>'''))

	def frameReceived(self, frame):
		log.msg("frameReceived, type =", frame.frameType())
		if(frame.frameType() == 'check'):
			self.sendFrame(EPPFrame('''<?xml version="1.0"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><response><result code="1000"><msg>Command completed successfully</msg></result><resData><domain:chkData xmlns:domain="urn:ietf:params:xml:ns:domain-1.0" xsi:schemaLocation="urn:ietf:params:xml:ns:domain-1.0 domain-1.0.xsd"><domain:cd><domain:name avail="1">eppvalid.com</domain:name></domain:cd></domain:chkData></resData><trID><clTRID>NOIP-X4ae1018f</clTRID><svTRID>482645932-1256259983319</svTRID></trID></response></epp>'''))
		else:
			self.sendFrame(EPPFrame('''<?xml version="1.0"?>
<epp xmlns="urn:ietf:params:xml:ns:epp-1.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="urn:ietf:params:xml:ns:epp-1.0 epp-1.0.xsd"><response><result code="1000"><msg>Command completed successfully</msg></result><trID><clTRID>NOIP-X4ae0feb0</clTRID><svTRID>491730059-1256259248447-47191799582</svTRID></trID></response></epp>'''))
		self.transport.loseConnection()
		if(frame.frameType() == 'logout'):
			self.transport.loseConnection()


log.startLogging(sys.stdout)
f = protocol.Factory()
f.protocol = EPPNullServer
reactor.listenTCP(3200, f)
reactor.run()

