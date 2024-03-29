# -*- coding: utf-8 -*-
from enigma import getDesktop, eTimer

from Components.Label import Label
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.Sources.Progress import Progress

from Screens.Screen import Screen
from Screens.MessageBox import MessageBox

from .crossepglib import *
from .crossepg_locale import _

try:
	import httplib
except:
	import http.client as httplib
import xml.etree.cElementTree
import re
import os
import random

from Tools.Directories import resolveFilename, SCOPE_GUISKIN
from Components.Console import Console


class CrossEPG_Rytec_Source(object):
	def __init__(self):
		self.channels_urls = []
		self.epg_urls = []
		self.description = ""


class CrossEPG_Rytec_Update(Screen):
	def __init__(self, session):
		from Components.Sources.StaticText import StaticText
		if (getDesktop(0).size().width() < 800):
			skin = "%s/skins/downloader_sd.xml" % os.path.dirname(sys.modules[__name__].__file__)
			self.isHD = 0
		else:
			skin = "%s/skins/downloader_hd.xml" % os.path.dirname(sys.modules[__name__].__file__)
			self.isHD = 1
		f = open(skin, "r")
		self.skin = f.read()
		f.close()
		Screen.__init__(self, session)
		self.skinName = "downloader"
		Screen.setTitle(self, _("CrossEPG"))

		self.onChangedEntry = []
		self.sources = []
		self.session = session
		self.mirrors = []

		self["background"] = Pixmap()
		self["action"] = Label(_("Updating rytec providers..."))
		self["summary_action"] = StaticText(_("Updating rytec providers..."))
		self["status"] = Label("")
		self["progress"] = ProgressBar()
		self["progress"].hide()
		self["progress_text"] = Progress()

		self.config = CrossEPG_Config()
		self.config.load()

		self.timer = eTimer()
		self.timer.callback.append(self.start)

		self.onFirstExecBegin.append(self.firstExec)

	def firstExec(self):
		if self.isHD:
			try:
				png = resolveFilename(SCOPE_GUISKIN, "crossepg/background_hd.png")
			except:
				print("[CrossEPG] Error: can't find the png file!")
			if png == None or not os.path.exists(png):
				png = "%s/images/background_hd.png" % os.path.dirname(sys.modules[__name__].__file__)
		else:
			try:
				png = resolveFilename(SCOPE_GUISKIN, "crossepg/background.png")
			except:
				print("[CrossEPG] Error: can't find the png file!")
			if png == None or not os.path.exists(png):
				png = "%s/images/background.png" % os.path.dirname(sys.modules[__name__].__file__)
		self["background"].instance.setPixmapFromFile(png)
		self.timer.start(100, 1)

	def start(self):
		self.loadSourceList()
		if self.load():
			self.save(self.config.home_directory + "/providers/")
			self.session.open(MessageBox, _("%d providers updated") % len(self.sources), type=MessageBox.TYPE_INFO, timeout=5)
		else:
			self.session.open(MessageBox, _("Cannot retrieve rytec sources"), type=MessageBox.TYPE_ERROR, timeout=10)
		self.close()

	def loadSourceList(self):
		try:
			from six.moves.urllib.request import urlopen
			import gzip
			try:
				from cStringIO import StringIO
			except:
				from io import StringIO
			url = "http://rytecepg.dyndns.tv/epg_data/crossepgsources.gz"
			print("[crossepg_rytec_update:loadSourceList] downloading source list from %s" % url)
			response = urlopen(url)
			content_raw = response.read()
			if 'gzip' in response.info().getheader('Content-Type'):
				self.mirrors = [x.strip() for x in gzip.GzipFile(fileobj=StringIO(content_raw)).read().strip().split("\n")]
				random.shuffle(self.mirrors)
			else:
				print("[crossepg_rytec_update:loadSourceList] Fetched data is not Gzip format")
				print("[crossepg_rytec_update:loadSourceList] content_raw:", content_raw)
		except Exception as e:
			print("[crossepg_rytec_update:loadSourceList] error fetching:", e)

	def load(self):
		ret = False
		for mirror in self.mirrors:
			mirror = mirror.replace('\t', '')
			try:
				print("downloading from %s" % (mirror))
				smirror = mirror.lstrip("http://")
				host = smirror.split("/")[0]
				path = smirror.lstrip(host)
				conn = httplib.HTTPConnection(host)
				conn.request("GET", path)
				httpres = conn.getresponse()
				if httpres.status == 200:
					f = open("/tmp/crossepg_rytec_tmp", "w")
					f.write(httpres.read())
					f.close()
					self.loadFromFile("/tmp/crossepg_rytec_tmp")
					os.unlink("/tmp/crossepg_rytec_tmp")
					ret = True
				else:
					print("http error: %d (%s)" % (httpres.status, mirror))
			except Exception as e:
				print(str(e))
		return ret

	def getServer(self, description):
		for source in self.sources:
			if source.description == description:
				return source
		return None

	def loadFromFile(self, filename):
		mdom = xml.etree.cElementTree.parse(filename)
		root = mdom.getroot()

		for node in root:
			if node.tag == "source":
				source = CrossEPG_Rytec_Source()
				source.channels_urls.append(node.get("channels"))
				for childnode in node:
					if childnode.tag == "description":
						source.description = childnode.text
					elif childnode.tag == "url":
						source.epg_urls.append(childnode.text)

				oldsource = self.getServer(source.description)
				if oldsource == None:
					self.sources.append(source)
				else:
					if len(source.epg_urls) > 0:
						if source.epg_urls[0] not in oldsource.epg_urls:
							oldsource.epg_urls.append(source.epg_urls[0])
					if len(source.channels_urls) > 0:
						if source.channels_urls[0] not in oldsource.channels_urls:
							oldsource.channels_urls.append(source.channels_urls[0])

	def save(self, destination):
		Console().ePopen("rm -f %s/rytec_*.conf" % destination)
		for source in self.sources:
			p = re.compile('[/:()<>|?*\s-]|(\\\)')
			filename = p.sub('_', source.description).lower()
			if filename[:6] != "rytec_":
				filename = "rytec_" + filename
			f = open(destination + "/" + filename + ".conf", "w")
			f.write("description=" + source.description + "\n")
			f.write("protocol=xmltv\n")
			count = 0
			for url in source.channels_urls:
				f.write("channels_url_" + str(count) + "=" + url + "\n")
				count += 1

			count = 0
			for url in source.epg_urls:
				f.write("epg_url_" + str(count) + "=" + url + "\n")
				count += 1
			f.write("preferred_language=eng")
			f.close()
