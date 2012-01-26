
from zope.interface import implements

from twisted.python import usage
from twisted.plugin import IPlugin
from twisted.application.service import IServiceMaker, MultiService
from twisted.application import internet
import ConfigParser
import os

from epp import server

def loadProxyConfig(conf=False):
	if not conf:
		# First check environment
		filename = os.environ.get('EPP_RPROXY_CONFIG')
		if filename:
			if not os.path.exists(filename):
				raise IOError("File '%s' does not exist" % filename)
			conf = filename
		if not conf:
			# Next, standard loc
			filename = '/etc/epp-rproxy.conf'
			if not os.path.exists(filename):
				raise IOError("File '%s' does not exist" % filename)
			conf = filename
	if not conf:
		raise IOError("File '/etc/epp-rproxy.conf' does not exist and no other conf given")

	config = ConfigParser.ConfigParser({
		'timeout': '10',
		'keepalive_interval': '0',
		'listen_host': '127.0.0.1',
		'debug': '0',
	})

	config.read(conf)

	return config
	
class ServerContextFactory():
	def __init__(self, certificate_file, privatekey_file, cafile=False):
		if not os.path.exists(certificate_file): raise IOError("File '%s' does not exist" % certificate_file)
		if not os.path.exists(privatekey_file): raise IOError("File '%s' does not exist" % privatekey_file)
		if cafile and not os.path.exists(cafile): raise IOError("File '%s' does not exist" % cafile)
		self.cf = certificate_file
		self.kf = privatekey_file
		self.ca = cafile
	def getContext(self):
		from OpenSSL import SSL
		ctx = SSL.Context(SSL.SSLv23_METHOD)
		ctx.use_certificate_file(self.cf)
		ctx.use_privatekey_file(self.kf)
		if self.ca: ctx.load_verify_locations(self.ca)
		return ctx

class Options(usage.Options):
	optParameters = [["conf", "c", None, "Config file (defaults: EPP_RPROXY_CONF, /etc/epp-rproxy.conf"]]


class EPPRProxyServiceMaker(object):

	implements(IServiceMaker, IPlugin)

	tapname = "epp-rproxy"
	description = "AN EPP Reverse Proxy"
	options = Options

	def makeService(self, options):
		""" See http://twistedmatrix.com/projects/core/documentation/howto/tutorial/library.html """
		svc = MultiService()

		config = loadProxyConfig(options['conf'])

		for section in config.sections():
			sslctx = None
			if config.get(section,'proto') == 'ssl':
				sslctx = ServerContextFactory(config.get(section, 'crtfile'), config.get(section, 'keyfile'), config.get(section,'cafile'))

			clientopts = {
				"host": config.get(section,'host'),
				"port": config.getint(section, 'port'),
				"timeout": config.getint(section,'timeout'),
				"sslctx": sslctx,
				"keepalive_interval": config.getint(section,'keepalive_interval'),
			}

			p = internet.TCPServer(config.getint(section, 'listen_port'), 
								   server.EPPProxyServerFactory(clientopts, 
																max_clients=config.getint(section, 'max_clients'), 
																max_retries=config.getint(section, 'max_retries'),
																debug=config.getint(section, 'debug'),
								   ), 
								   interface=config.get(section, 'listen_host')
			)

			p.setServiceParent(svc)

		return svc


# Now construct an object which *provides* the relevant interfaces
# The name of this variable is irrelevant, as long as there is *some*
# name bound to a provider of IPlugin and IServiceMaker.

serviceMaker = EPPRProxyServiceMaker()

