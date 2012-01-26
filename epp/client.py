
from twisted.internet import defer, reactor
from twisted.protocols.policies import TimeoutMixin
from epp import protocol

class ClientTimeoutError(Exception):
	def __str__(self): return "client timeout"

class ClientInUseError(Exception):
	def __str__(self): return "client already in use"

class ClientClosedError(Exception):
	def __str__(self): return "client closed"

class EPPClient(protocol.EPP, TimeoutMixin):

	def __init__(self, timeout=0):
		protocol.EPP.__init__(self)
		self.timeout = timeout

		self.logged_in = False
		self.closed    = False
		self.timed_out = False

		self.state = None
		self._waiting  = None

	def connectionMade(self):
		if self.timeout > 0:
			self.setTimeout(self.timeout)
		self.state = 'WELCOME'

	def connectionLost(self, reason):
		if self.timeout > 0:
			self.setTimeout(None)
		self.closed = True
		if self._waiting:
			d, self._waiting = self._waiting, None
			if self.timed_out: d.errback(ClientTimeoutError())
			else: d.errback(ClientClosedError())

	def timeoutConnection(self):
		self.timed_out = True
		self.transport.loseConnection()

	def frameReceived(self, frame):
		if self.timeout > 0:
			self.setTimeout(None)
		state, self.state = self.state, None
		state = getattr(self, 'state_' + state)(frame) or state
		if self.state is None:
			self.state = state

	def sendCommand(self, frame):
		assert self.state == 'READY', "State should be 'READY' but it's "+repr(self.state)
		if self._waiting:
			return defer.fail(ClientInUserError())
		self.state = 'COMMAND'
		if self.timeout > 0:
			self.setTimeout(self.timeout)
		self.sendFrame(frame)
		self._waiting = defer.Deferred()
		return self._waiting

	def state_WELCOME(self, frame):
		# Make sure we have an appropriate greeting
		if frame.frameType() != 'greeting':
			self.transport.loseConnection()
			return None
		reactor.callLater(0, self.serverGreeting, frame)
		return 'READY'

	def state_READY(self, data):
		""" The server isn't supposed to send us anything in this state """

	def state_COMMAND(self, frame):
		d, self._waiting = self._waiting, None
		reactor.callLater(0, d.callback, frame)
		return 'READY'

	def login(self, frame):
		d = self.sendCommand(frame)
		d.addCallback(self._login)
		return d

	def _login(self, frame):
		if frame.frameType() == 'success':
			self.logged_in = True
		return frame

	def command(self, frame):
		return self.sendCommand(frame)

	def logout(self, frame=None):
		if not frame:
			frame = protocol.EPPTemplateFrame('logout')
		d = self.sendCommand(frame)
		d.addCallback(self._logout)
		return d

	def _logout(self, frame):
		self.logged_in = False
		return frame

	def isReady(self):
		return (self.closed != True and self.state == 'READY')

	def serverGreeting(self, frame):
		""" Override - called when the server has sent it's greeting """


if __name__ == "__main__":

	from twisted.python import log
	from twisted.internet.protocol import ClientCreator
	import sys

	def logoutResponse(frame, p):
		log.msg("logoutResponse: frame="+repr(frame.xml))
		log.msg("state should be READY, state="+repr(p.state))
		reactor.stop()

	def helloResponse(frame, p):
		log.msg("helloResponse: frame="+repr(frame.xml))
		log.msg("state should be READY, state="+repr(p.state))
		p.logout().addCallback(logoutResponse, p)
		
	def runTest(p):
		log.msg("state should be READY, state="+repr(p.state))
		p.command(protocol.EPPTemplateFrame('hello')).addCallbacks(helloResponse, gotErr, callbackArgs=(p,))

	def gotErr(e):
		print "[ERROR] "+repr(e)
		reactor.stop()

	class MyEPPClient(EPPClient):
		def serverGreeting(self, frame):
			log.msg("serverGreeting: frame="+repr(frame))
			reactor.callLater(0, runTest, self)

 	log.startLogging(sys.stdout)
	c = ClientCreator(reactor, MyEPPClient, timeout=5)
	c.connectTCP('127.0.0.1', 32700).addErrback(gotErr)
	
	reactor.run()
