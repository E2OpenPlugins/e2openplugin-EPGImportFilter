# for localized messages  	 
# for localized messages  	 
# for localized messages  	 
#from . import _

import EPGImportFilterWorker
import os
import time
import enigma
import shutil

from twisted.web.client import downloadPage

from string import maketrans 
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ConfigList import ConfigList, ConfigListScreen
from Components.SelectionList import SelectionList, SelectionEntryComponent
from Components.config import ConfigYesNo, ConfigSelection, ConfigInteger, config, getConfigListEntry
from Components.ActionMap import ActionMap, NumberActionMap
from Components.Label import Label
from os import system
from enigma import eEPGCache, eTimer, getDesktop, eServiceCenter, eServiceReference, iServiceInformation
from Components.ProgressBar import ProgressBar
from Components.VideoWindow import VideoWindow

from enigma import eListboxPythonMultiContent, eListbox, gFont, \
	RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_VALIGN_CENTER, RT_VALIGN_TOP, RT_VALIGN_BOTTOM
from Components.HTMLComponent import HTMLComponent
from Components.GUIComponent import GUIComponent
from operator import itemgetter		

from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN, SCOPE_CURRENT_PLUGIN
from Tools.LoadPixmap import LoadPixmap

from ServiceReference import ServiceReference

from plugin import VERSION

epgWorker = EPGImportFilterWorker.EPGImportFilterWorker()

# structures
# matches[]
mRef      = 0
mProgram  = 1
mSort     = 2
mAutoLoad = 3
# matchhings[]
mcRef     = 0
mcProgram = 1
mcState   = 2
# channels[]t4t
cRef      = 0
cName     = 1
cCompare  = 2
cIndxXMLChannel = 3
# epgChannels[]
eProgram  = 0
eCompare  = 1
# epgSources[]
eName     = 0
eFileName = 1
eChosen   = 2

def getBouquetList(bouquetNames = None):
	bouquets = [ ]
	serviceHandler = eServiceCenter.getInstance()
	bouquet_rootstr = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet'
	bouquet_root = eServiceReference(bouquet_rootstr)
	if config.usage.multibouquet.value:
		list = serviceHandler.list(bouquet_root)
		if list:
			while True:
				s = list.getNext()
				if not s.valid():
					break
				if s.flags & eServiceReference.isDirectory:
					info = serviceHandler.info(s)
					if info:
						bouquets.append((info.getName(s), s))
			return bouquets
	else:
		info = serviceHandler.info(bouquet_root)
		if info:
			bouquets.append((info.getName(bouquet_root), bouquet_root))
		return bouquets
	return None

# mgolem - Finds a first bouquet for the ref starting from the bouqet send as parameter
def findBouquet(ref, bouquet = None):
	rf = ref.lower()
	serviceHandler = eServiceCenter.getInstance()
	bouquet_rootstr = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet'
	bouquet_root = eServiceReference(bouquet_rootstr)
	if config.usage.multibouquet.value:
		list = serviceHandler.list(bouquet_root)
		if list:
			while True:
				s = list.getNext()
				if not s.valid():
					break
				if s.flags & eServiceReference.isDirectory:
					if bouquet is None or bouquet == s:
						info = serviceHandler.info(s)
						if info:
							clist = serviceHandler.list(s)
							if list:
								while True:
									a = clist.getNext()
									if not a.valid():
										break
									if not (a.flags & eServiceReference.isMarker):
										if not (a.toCompareString().lower().find(rf) == -1):
											return s;
	return None

#selectionpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/selectioncross.png"))
selectionpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/lock_on.png"))
redxpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/lock_error.png"))
#redxpng = LoadPixmap(cached=True, path=resolveFilename(SCOPE_CURRENT_PLUGIN, "Extensions/EPGImportFilter/disabled.png")) 
	
class ColoredList(HTMLComponent, GUIComponent):
	def __init__(self):
		GUIComponent.__init__(self)
		
		self.list = []
		self.coloredColor = 0xffc000
		self.color1 = 0xf0e68c # khaki yellow
		self.color2 = 0x00ff00 # green
		self.l = eListboxPythonMultiContent()
		self.l.setBuildFunc(self.buildEntry)
		self.setList(self.list)
		self.l.setFont(0, gFont("Regular", 20))
		self.l.setItemHeight(30)		

	GUI_WIDGET = eListbox

	def buildEntry(self, name, field1, selected, colored, extra_color):
		width = self.l.getItemSize().width()
		res = [ None ]
		
		# posx, posy, width, height, font, flags, text, foreColor, selColor, backColor, selBackColor
		colorN = None
		colorS = (None,self.coloredColor)[colored]
		if extra_color == 1:
			colorN = self.color1
			colorS = colorN
		elif extra_color == 2:
			colorN = self.color2
			colorS = colorN
		elif colored:
			colorN = self.coloredColor
								
		res.append((eListboxPythonMultiContent.TYPE_TEXT, 30, 3, 500, 30, 0, RT_HALIGN_LEFT, name, colorN, colorS))
				
		if selected == 2:
			res.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 0, 0, 30, 30, redxpng))
		elif selected > 0:
			res.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 0, 0, 30, 30, selectionpng))
		
		return res

	def postWidgetCreate(self, instance):
		instance.setContent(self.l)
		#instance.selectionChanged.get().append(self.selectionChanged)
		self.instance.setWrapAround(True)

	def preWidgetRemove(self, instance):
		instance.setContent(None)
		#instance.selectionChanged.get().remove(self.selectionChanged)
		
	def setList(self, list):
		self.list = list
		self.l.setList(list)

	def clearSelections(self):
		for idx in range(0, len(self.list)):					
			item = self.list[idx]
			self.list[idx] = (item[0], item[1], 0, item[3], item[4])
			
		self.setList(self.list)

	def getCurrent(self):
		idx = self.instance.getCurrentIndex()
		if idx < 0 or idx > len(self.list)-1: return ("","",False,False)
		
		return self.list[idx]
		
	def toggleAll(self, setValue = None):
		oneSelected = False; oneUnselected = False
		if len([v for v in self.list if v[2] > 0]) > 0:
			oneSelected = True
		if len([v for v in self.list if v[2] == 0]) > 0:
			oneUnselected = True
			
		for idx,i in enumerate(self.list):
			item = self.list[idx]
			if not (setValue is None):
				ret = setValue
			else:
				if oneSelected and oneUnselected:
					ret = 1
				elif oneSelected and not oneUnselected:
					ret = 0
				elif not oneSelected:
					ret = 1
				else:
					ret = 0
			self.list[idx] = (item[0], item[1], ret, item[3], item[4])
			
		self.setList(self.list)
							
	def toggleSelection(self, setValue = None):
		idx = self.instance.getCurrentIndex()
		if idx < 0 or idx > len(self.list)-1: return
		
		item = self.list[idx]
		if not (setValue is None):
			ret = setValue
		else:
			if item[2] > 0:
				ret = 0
			else:
				ret = 1
			
		self.list[idx] = (item[0], item[1], ret, item[3], item[4])
		self.setList(self.list)
		
		return ret

	def setCurrentToColored(self, setValue):
		idx = self.instance.getCurrentIndex()
		if idx < 0 or idx > len(self.list)-1: return
		
		item = self.list[idx]
		self.list[idx] = (item[0], item[1], item[2], setValue, item[4])
		self.setList(self.list)

	def moveUp(self):
		if self.instance is not None and len(self.list) > 0:
			self.instance.moveSelection(self.instance.moveUp)
		
	def moveDown(self):
		if self.instance is not None and len(self.list) > 0:
			self.instance.moveSelection(self.instance.moveDown)
		
	def pageUp(self):
		if self.instance is not None and len(self.list) > 0:
			self.instance.moveSelection(self.instance.pageUp)
			
	def pageDown(self):
		if self.instance is not None and len(self.list) > 0:
			self.instance.moveSelection(self.instance.pageDown)

class EGPSelectEPGSources(Screen):
	#skin = """<screen name="EPGSelectEPGSourcesScreen" position="center,42" zPosition="2" size="1230,660" title="Select EPG sources" >
		# <ePixmap pixmap="skin_default/div-h.png" position="0,535" zPosition="2" size="1260,2" />
		# <widget name="key_green" position="10,620" zPosition="2" size="130,28" valign="center" halign="left" font="Regular;22" transparent="1" foregroundColor="green" />		
		# <widget name="key_blue" position="140,620" zPosition="2" size="130,28" valign="center" halign="left" font="Regular;22" transparent="1" foregroundColor="blue" />		
		# <widget name="list" position="10,20" size="590,510" scrollbarMode="showOnDemand" />
		# <ePixmap alphatest="on" pixmap="skin_default/icons/clock.png" position="1147,628" size="14,14" zPosition="3"/>
		# <widget font="Regular;18" halign="right" position="1170,623" render="Label" size="55,28" source="global.CurrentTime" transparent="1" valign="center" zPosition="3">
			# <convert type="ClockToText">Default</convert>
		# </widget>
		# <widget name="videoPicture" position="720,20" size="500,273" zPosition="1" backgroundColor="transparent" />
	# </screen>"""
	skin = """<screen name="EPGSelectEPGSourcesScreen" position="fill" zPosition="2" flags="wfNoBorder" title="Select EPG sources" >
		<panel name="PigTemplate"/>
		<panel name="ButtonTemplate_RG"/>   
		<widget name="list" position="590,110" size="600,485" scrollbarMode="showOnDemand" />
	</screen>"""
	
	def __init__(self, session):
		self.session = session
		Screen.__init__(self, session)
		self.setup_title = _("Select EPG sources")
		self.setTitle(self.setup_title)
		
		# load sources into list
		self["list"] = ColoredList()
		for i in epgWorker.epgSources:			
			# display, description, selected, colored,
			if not i[0] in [v[0] for v in self["list"].list]:
				self["list"].list.append((i[eName], i[eFileName], (0,1)[i[eName] in epgWorker.epgSourcesChosen], False, 0))
			
		self.desktopSize = getDesktop(0).size()		
		self["videoPicture"] = VideoWindow(decoder = 0, fb_width = self.desktopSize.width(), fb_height = self.desktopSize.height())
		
		self["choiseActions"] = NumberActionMap(["DirectionActions", "EPGSelectActions", "NumberActions", "OkCancelActions", "ColorActions", "TimerEditActions"],
			{
				"cancel": self.cancel,
				"red": self.proceed,
				"green": self["list"].toggleAll,
				"ok": self["list"].toggleSelection
			}, -2)

		self["key_red"] = Label(_("Proceed"))
		self["key_green"] = Label(_("Select all"))
	
	def proceed(self):
		self.close([(v[0],v[1],v[2]) for v in self["list"].list if v[2] > 0])
		
	def cancel(self):
		self.close([])	
						
class EGPMatchByName(Screen):
	skin = """<screen name="EPGImportFilterScreen" position="center,42" zPosition="2" size="1230,660" title="EPGImport Filter" >
		<ePixmap pixmap="skin_default/div-h.png" position="0,535" zPosition="2" size="1260,2" />
		<ePixmap pixmap="skin_default/div-h.png" position="410,323" zPosition="2" size="840,2" />
		<widget name="key_red" position="10,620" zPosition="2" size="130,28" valign="center" halign="left" font="Regular;22" transparent="1" foregroundColor="red" />
		<ePixmap pixmap="skin_default/buttons/key_1.png" position="120,622" zPosition="2" size="35,25" transparent="1" alphatest="on"/>
		<ePixmap pixmap="skin_default/buttons/key_2.png" position="150,622" zPosition="2" size="35,25" transparent="1" alphatest="on"/>
		<ePixmap pixmap="skin_default/buttons/key_3.png" position="180,622" zPosition="2" size="35,25" transparent="1" alphatest="on"/>
		<widget name="key_refresh" position="214,620" zPosition="2" size="230,28" valign="center" halign="left" font="Regular;19" transparent="1" foregroundColor="white" />
		<ePixmap pixmap="skin_default/buttons/key_4.png" position="385,622" zPosition="2" size="35,25" transparent="1" alphatest="on"/>
		<ePixmap pixmap="skin_default/buttons/key_5.png" position="415,622" zPosition="2" size="35,25" transparent="1" alphatest="on"/>
		<ePixmap pixmap="skin_default/buttons/key_6.png" position="445,622" zPosition="2" size="35,25" transparent="1" alphatest="on"/>
		<widget name="key_filter" position="479,620" zPosition="2" size="230,28" valign="center" halign="left" font="Regular;19" transparent="1" foregroundColor="white" />
		<widget name="key_green" position="640,620" zPosition="2" size="130,28" valign="center" halign="left" font="Regular;22" transparent="1" foregroundColor="green" />		
		<widget name="key_blue" position="760,620" zPosition="2" size="130,28" valign="center" halign="left" font="Regular;22" transparent="1" foregroundColor="blue" />		
		<ePixmap pixmap="skin_default/div-h.png" position="410,323" zPosition="2" size="840,2" />
		<widget name="list1" position="10,20" size="390,510" scrollbarMode="showOnDemand" />
		<widget name="list2" position="410,20" size="400,305" scrollbarMode="showOnDemand" />
		<widget name="text" position="410,340" halign="left" size="400,180" font="Regular;15" />		
		<widget name="text2" position="820,340" halign="left" size="400,180" font="Regular;15" />		
		<widget name="statusbar" position="0,550" halign="right" size="1230,30" font="Regular;20" />
		<widget name="status" position="0,580" halign="right" size="1230,30" font="Regular;20" />
		<ePixmap alphatest="on" pixmap="skin_default/icons/clock.png" position="1147,628" size="14,14" zPosition="3"/>
		<widget font="Regular;18" halign="right" position="1170,623" render="Label" size="55,28" source="global.CurrentTime" transparent="1" valign="center" zPosition="3">
			<convert type="ClockToText">Default</convert>
		</widget>
		<widget name="videoPicture" position="820,20" size="395,215" zPosition="1" backgroundColor="transparent" />
	</screen>"""
	
	def __init__(self, session):
		self.session = session
		Screen.__init__(self, session)
		
		#bouquets = getBouquetList();
		self.waitForEpgWorker = 0
		self.setup_title = _("Advanced matching")
		self.setTitle(self.setup_title)
		
		from Screens.InfoBar import InfoBar
		self.infoBarInstance = InfoBar.instance
		self.epgcache = eEPGCache.getInstance()

		self.offerToSave = False
		self.callback = None
		#cfg = EPGConfig.loadUserSettings()
		# load all working bouquets
		#filter = cfg["sources"]
		#self.bouquets = []
		self.channels = []
		#for x in bouquets:
		#	if x[0]in filter or filter is None:
		#		self.bouquets.append(x[0])
				# (description, value, index, selected)
				#self.bouquets.append(SelectionEntryComponent(x[0], x[1], 0, False))

		self["statusbar"] = Label()
		self["status"] = Label()
		self["text"] = Label()
		self["text2"] = Label()
		self["list1"] = ColoredList()
		self["list2"] = ColoredList()
		self.desktopSize = getDesktop(0).size()		
		#self["videoPicture"] = VideoWindow(decoder = 0, fb_width = 445, fb_height = 263)
		self["videoPicture"] = VideoWindow(decoder = 0, fb_width = self.desktopSize.width(), fb_height = self.desktopSize.height())
		
		self.curFocus = 1
		self["actions"] = NumberActionMap(["DirectionActions", "EPGSelectActions", "NumberActions", "OkCancelActions", "ColorActions", "TimerEditActions"],
			{
				"cancel": self.cancel,
				"red": self.epgLoadCall,
				"green": self.doSave,
				"blue": self.install,
				"nextService": self.right,
				"prevService": self.left,
				"ok": self.zap,
				"up": self.up,
				"down": self.down,
				"left": self.pageUp,
				"right": self.pageDown,
				"1": self.keyed,
				"2": self.keyed,
				"3": self.keyed,
				"4": self.keyed,
				"5": self.keyed,
				"6": self.keyed
			}, -2)

		self["key_red"] = Label(_("Load epg packages"))
		self["key_refresh"] = Label(_("Refresh matches"))
		self["key_filter"] = Label(_("Filter channels"))
		self["key_green"] = Label(_("Save"))
		self["key_blue"] = Label(_("Install"))
		#self["key_green"] = Label(_("Find matches"))
		#self["key_yellow"] = Label(_("Find matches"))

		self.channelMode = 1 # initiate on all channels
		self.updateTimer = enigma.eTimer()
	    	self.updateTimer.callback.append(self.updateStatus)
		
		self.updateStatus()
		self.updateTimer.start(2000)		

		# load all unmapped channels
		if not epgWorker.active and len(epgWorker.channels) == 0:
			#self.doFilterCallback(True)
			self.doChannelLoad()
			self.waitForEpgWorker = 1
		elif epgWorker.active:
			self.waitForEpgWorker = 1
			
		self.onLayoutFinish.append(self.onLoad)			
				
	def updateStatus(self, done = None):
	
		#if epgWorker.download_active > 0:
		#	epgWorker.download_active = epgWorker.download_active + 1
		
		#	if epgWorker.download_active >= 4:
		#		epgWorker.download_active = 0
		#		epgWorker.download_error = True
		#		epgWorker.createFilteredChannelFile(epgWorker.onlyLoad)

		#epgWorker.status = "Active: " + str(epgWorker.download_active) + "," + epgWorker.channelSource
		self["statusbar"].setText(epgWorker.status)
		if epgWorker.active:
			if not (done is None):
				if done > 1:
					self["status"].setText("Processing.. " + str(done) + epgWorker.doneStr)
				else:
					self["status"].setText("Processing.. ")
			elif epgWorker.updateStatus is None:
				if epgWorker.done > 1:
					self["status"].setText("Processing.. " + str(epgWorker.done) + epgWorker.doneStr)
				else:
					self["status"].setText("Processing.. ")
		else:
			self["status"].setText("")	
			
		if self.waitForEpgWorker == 1 and not epgWorker.active:
			self.waitForEpgWorker = 0
			self.refreshChannels()

		if self.waitForEpgWorker == 2 and not epgWorker.active:
			self.waitForEpgWorker = 0
			self.refreshMatches
			
			
	def onLoad(self):
		self.refreshChannels()
		self.refreshActive()
		
	def refreshActive(self):
		if self.curFocus == 1:
			self["list2"].instance.setSelectionEnable(False)
			self["list2"].setCurrentToColored(True)		
			self["list1"].instance.setSelectionEnable(True)
			self["list1"].setCurrentToColored(False)
		else:
			self["list1"].instance.setSelectionEnable(False)
			self["list1"].setCurrentToColored(True)		
			self["list2"].instance.setSelectionEnable(True)
			self["list2"].setCurrentToColored(False)

	def refreshChannels(self):
		# load channels		
		enabled = [v[mcRef] for v in epgWorker.matchings if v[mcState] == 1]
		disabled = [v[mcRef] for v in epgWorker.matchings if v[mcState] == 0]
		c = []
		del self["list1"].list[:]		
		if self.channelMode == 1:
			c = [v for v in epgWorker.channels] # all
		elif self.channelMode == 2:
			c = [v for v in epgWorker.channels if v[cIndxXMLChannel] > 0] # matched by ref
		else:
			c = [v for v in epgWorker.channels if v[cIndxXMLChannel] < 0] # unmatched
			
		for x in c:
			# (description, value, index, selected (0,1,2 - disabled)
			if x[cRef] in enabled:
				state = 1
			elif x[cRef] in disabled:
				state = 2
			else:
				state = 0				
			self["list1"].list.append((x[cName], x[cRef], state, False, 0))
			
		self["list1"].setList(self["list1"].list)			
		self.refreshMatches()

	def refreshMatches(self):
		# load matches
		s = self["list1"].instance.getCurrentIndex()
		if s < 0 or len(self["list1"].list) == 0: 
			del self["list2"].list[:]
			self["list2"].setList(self["list2"].list)			
			self.refreshProgramme()
			return		

		ref = self["list1"].getCurrent()[1]
		del self["list2"].list[:]
		c = [v for v in epgWorker.matches if v[mRef] == self["list1"].list[s][1]]
		c = sorted(c, key=itemgetter(2), reverse = False)
		for x in c:
			# (name, field1, selected, colored, extra_color
			# find if matching exist
			p = [p for p in epgWorker.matchings if p[mcRef] == ref and p[mcProgram] == x[mProgram]]
			state = 0
			if len(p) > 0:
				if p[0][mcState] == 0:
					state = 2
				elif p[0][mcState] == 1:
					state = 1
			# set to color to yellow if auto-matched			
			self["list2"].list.append((x[mProgram], self["list1"].list[s][1], state, False, x[mAutoLoad]))
			
		self["list2"].setList(self["list2"].list)			
		self.refreshProgramme()
	
	def refreshProgramme(self):
		# load programme			
		s = self["list2"].instance.getCurrentIndex()
		if s >= 0: 
		
			if len(self["list2"].list) <= s or len(self["list2"].list[s]) == 0: 
				pass
			else:
				#c = [v for v in epgWorker.epgProgramme if v[0] == self["list2"].list[s][0]]
				try:
					#c = [v for v in epgWorker.epgProgramme[self["list2"].list[s][0]]]
					c = epgWorker.epgProgramme[self["list2"].list[s][0]]
				except: c = []
				if len(c) > 0:
					t = ""
					for x in c:				
						#t = t + x[1] + "\n" #+ x[2] + "\n---\n"
						t = t + x + "\n" #+ x[2] + "\n---\n"
					self["text"].setText(t)
				else:
					self["text"].setText("")
		else:
			self["text"].setText("")
			
		# Get Channel epg program and load it in text2 field
		s = self["list1"].instance.getCurrentIndex()
		if s < 0 or len(self["list1"].list) <= s or len(self["list1"].list[s]) == 0:
			self["text2"].setText("")
			return
			
		sRef		= self["list1"].list[s][1]
		begin       = int(time.mktime(time.localtime()))
		#duration	= time.localtime(20000)
		
		nextEvent = self.epgcache.startTimeQuery(eServiceReference(sRef), begin)
		#+ duration)
		
		if nextEvent == -1:
			self["text2"].setText("No epg data found..")
			return
			
		textField = ""
		i = 0
		while i < 5:
			nextEvent = self.epgcache.getNextTimeEntry()
			if nextEvent <= 0:
				break
			else:
				#data = (0, nextEvent.getEventId(), sRef, nextEvent.getBeginTime(), nextEvent.getDuration(), nextEvent.getEventName(), nextEvent.getShortDescription(), nextEvent.getExtendedDescription())
				textField = textField + time.ctime(nextEvent.getBeginTime()) + " " + nextEvent.getEventName() + "\n"
				i += 1
				
		self["text2"].setText(textField)
		
	def epgLoadCall(self):
		# call matching by name
		if epgWorker.active:
			return
			
		try:
			epgWorker.updateStatus = self.updateStatus
			self.waitForEpgWorker = 2
			#epgWorker.matchByName(True)
			# call epg selection
			self.session.openWithCallback(self.proceedEpgLoadCall, EGPSelectEPGSources)		
			#self.session.openWithCallback(epgWorker.epgLoad, MessageBox, _("EPGImport Filter Plugin\nChannels name comparing will start\nThis may take a few minutes\nIs this ok?"), MessageBox.TYPE_YESNO, timeout = 15, default = True)
		except Exception, e:
			epgWorker.status = "Failed to start: " + str(e)

		self.updateStatus()

	def proceedEpgLoadCall(self, sources):
		epgWorker.epgLoad(sources)
				
	def doChannelLoad(self):		
		if epgWorker.active:
			return
		try:
			epgWorker.updateStatus = self.updateStatus
			epgWorker.createFilteredChannelFile(True)
		except Exception, e:
			epgWorker.status = "Failed to start: " + str(e)

		self.updateStatus()

	def doFilterCallback(self, confirmed):		
		if not confirmed:
			return
		if epgWorker.active:
			return
		try:
			#epgWorker.bouquets = self.bouquets
			epgWorker.updateStatus = self.updateStatus
			#epgWorker.doneLoading = self.doneLoadingChannels
			epgWorker.createFilteredChannelFile()
		except Exception, e:
			epgWorker.status = "Failed to start: " + str(e)

		self.updateStatus()

	def up(self):
		if self.curFocus == 1:
			self["list1"].moveUp()
			self.refreshMatches()
		else:
			self["list2"].moveUp()
			self.refreshProgramme()
			
	def down(self):
		if self.curFocus == 1:
			self["list1"].moveDown()
			self.refreshMatches()
		else:
			self["list2"].moveDown()
			self.refreshProgramme()

	def pageUp(self):
		if self.curFocus == 1:
			self["list1"].pageUp()
			self.refreshMatches()
		else:
			self["list2"].pageUp()
			self.refreshProgramme()
			
	def pageDown(self):
		if self.curFocus == 1:
			self["list1"].pageDown()
			self.refreshMatches()
		else:
			self["list2"].pageDown()
			self.refreshProgramme()
			
	def left(self):
		if self.curFocus == 2:
			self.curFocus = 1
			self.refreshActive()
		
	def keyed(self, number):
		if number >= 4 and number <= 6:
			# change channel filtering
			if number == 4:
				self.channelMode = 1
			elif number == 5:
				self.channelMode = 2
			elif number == 6:
				self.channelMode = 3
				
			self.refreshChannels()
		else:
			s = self["list1"].instance.getCurrentIndex()
			if s < 0 or len(self["list1"].list) <= s or len(self["list1"].list[s]) == 0: return

			# load the matches
			#epgWorker.compareNames(self["list1"].list[s][0][1], number)
			epgWorker.compareNames(self["list1"].list[s][1], number)
			self.refreshMatches()
	
	def right(self):	
		s = self["list1"].instance.getCurrentIndex()
		if s < 0 or len(self["list1"].list) <= s or len(self["list1"].list[s]) == 0: return

		if len(self["list2"].list) == 0:		
			# load the matches
			epgWorker.compareNames(self["list1"].list[s][1], 1)
			self.refreshMatches()
			
		if len(self["list2"].list) > 0:
			self.curFocus = 2		
			self.refreshActive()

	def zap(self):
		if self.curFocus == 1:
			s = self["list1"].instance.getCurrentIndex()
			if s < 0: return		

			if len(self["list1"].list) > s:
				# Find the service
				#s = self.findBouquet(cur[2], self.bouquetList[self.currentBouquetIndex][1])
				#if s is None:
				b = findBouquet(self["list1"].list[s][1])
				if not (b is None):
					ref = self["list1"].list[s][1]
					self.infoBarInstance.epg_bouquet = b
					self.infoBarInstance.zapToService(eServiceReference(ref))

			self.right()
		else:
			if len(self["list2"].list) > 0:
				ref   = self["list1"].getCurrent()[1]
				mname = self["list2"].getCurrent()[0]
				state = self["list2"].getCurrent()[2] # selected state
				#self["list2"].clearSelections()
				# find the matching for this channel
				v = [i for i,v in enumerate(epgWorker.matchings) if v[mcRef] == ref]
				if state == 0 or state == 2:
					if len(v) > 0:						
						# ref, name, selected indicator (0 - disable, 1 - enable)
						epgWorker.matchings[v[0]] = (ref, mname, 1)
					else:
						epgWorker.matchings.append((ref, mname, 1))
						
					self["list1"].toggleSelection(True)
				elif len(v) > 0:
					# delete the matching or make auto-generated disabled
					if self["list2"].getCurrent()[4] == 1:
						epgWorker.matchings[v[0]] = (ref, mname, 0)
						self["list1"].toggleSelection(2)
					else:
						del epgWorker.matchings[v[0]]
						self["list1"].toggleSelection(0)
						
						
				self.refreshMatches()
				
			self.left()
			self.offerToSave = True

	def doSave(self):
		if self.offerToSave:
			self.offerToSave = False
		self.save(None)
		
	def save(self, callback):
		if self.offerToSave:
			self.callback = callback
			self.session.openWithCallback(self.proceedSave, MessageBox, _("EPGImport Filter Plugin\nDo you want to save your changes?"), MessageBox.TYPE_YESNO, timeout = 15, default = True)
		else:
			self.callback = callback
			self.proceedSave(True)
		
	def proceedSave(self, confirmed):
		if confirmed:
			self.offerToSave = False
				
			epgWorker.storeAll()
			if len(epgWorker.channels) > 0:
				del epgWorker.channels[:]

		if not(self.callback is None):
			callback = self.callback
			self.callback = None
			callback()
			
	def install(self):		
		# install
		if epgWorker.active:
			return
			
		if not os.path.isfile("/etc/epgimport/rytec.sources.xml"):
			self.session.open(MessageBox, _("EPGImport is not installed.."), MessageBox.TYPE_ERROR, timeout = 1000, close_on_any_key = True)			
			return
					
		if self.offerToSave: self.offerToSave = False
		self.save(self.proceedInstall)

		if len(epgWorker.bouquets) == 0:
			self.session.open(MessageBox, _("You must choose at least one bouquet!"), MessageBox.TYPE_ERROR, timeout = 1000, close_on_any_key = True)						
			return
			
		#EPGConfig.storeUserSettings(sources=self.bouquets)		

	def proceedInstall(self):		
		self.session.openWithCallback(self.doFilterCallback, MessageBox, _("EPGImport Filter Plugin\nChannels filtering will start\nThis may take a few minutes\nIs this ok?"), MessageBox.TYPE_YESNO, timeout = 15, default = True)	
		
	def cancel(self):
		self.updateTimer.stop()	
		epgWorker.updateStatus = None
		if self.offerToSave:
			self.save(self.proceedCancel)
		else:
			self.proceedCancel()
	
	def proceedCancel(self):
		self.close(self.session, False)
					
class EPGImportFilterScreen(Screen):
	#skin = """<screen name="EPGImportFilterScreen" position="center,center" zPosition="2" size="700,610" title="EPGImport Filter" >
	# <ePixmap pixmap="skin_default/div-h.png" position="0,510" zPosition="2" size="700,2" />
	# <widget name="key_red" position="10,580" zPosition="2" size="130,28" valign="center" halign="center" font="Regular;22" transparent="1" foregroundColor="red" />
	# <widget name="key_green" position="130,580" zPosition="2" size="130,28" valign="center" halign="center" font="Regular;22" transparent="1" foregroundColor="green" />
	# <widget name="key_yellow" position="250,580" zPosition="2" size="180,28" valign="center" halign="center" font="Regular;22" transparent="1" foregroundColor="yellow" />
	# <widget name="key_blue" position="390,580" zPosition="2" size="130,28" valign="center" halign="right" font="Regular;22" transparent="1" foregroundColor="blue" />		
	# <widget name="list" position="10,20" size="690,485" scrollbarMode="showOnDemand" />
	# <widget name="statusbar" position="10,520" halign="right" size="680,30" font="Regular;20" />
	# <widget name="status" position="10,550" halign="right" size="680,30" font="Regular;20" />
	#<ePixmap pixmap="skin_default/div-h.png" position="0,510" zPosition="2" size="700,2" />
	skin = """<screen name="EPGImportFilterScreen" position="fill" title="EPGImport Filter" flags="wfNoBorder">
		<panel name="PigTemplate"/>
		<panel name="ButtonTemplate_RGYB"/>   
		<widget name="list" position="590,110" size="600,485" scrollbarMode="showOnDemand" />
		<widget name="statusbar" position="85,520" halign="left" size="417,30" font="Regular;20" />
		<widget name="status" position="85,550" halign="left" size="417,30" font="Regular;20" />				
	</screen>"""

	def __init__(self, session):
		self.session = session
		Screen.__init__(self, session)
		self.setup_title = _("EPG Import Filter") + " v" + VERSION + " by Acds"
		self.setTitle(self.setup_title)
		
		#cfg = EPGConfig.loadUserSettings()
		#filter = cfg["sources"]
		self.offerToSave = False
		self.callback = None
		bouquets = getBouquetList()
		filter = epgWorker.bouquets
		sources = [
			# (description, value, index, selected)
			SelectionEntryComponent(x[0], x[1], 0, (filter is None) or (x[0] in filter))
			for x in bouquets
			]
		self["statusbar"] = Label()
		self["status"] = Label()
		self["list"] = SelectionList(sources)
		self["setActions"] = ActionMap(["OkCancelActions", "ColorActions", "TimerEditActions"],
			{
				"cancel": self.cancel,
				"red": self.uninstall,
				"green": self.selectAll,
				"yellow": self.advanced,
				"blue": self.install,
				"ok": self.toggle
			}, -2)

		self["key_red"] = Label(_("Uninstall"))
		self["key_green"] = Label(_("Select All"))
		self["key_yellow"] = Label(_("Advanced"))
		self["key_blue"] = Label(_("Install"))

		self.updateTimer = enigma.eTimer()
	    	self.updateTimer.callback.append(self.updateStatus)
		
		self.updateStatus()
		self.updateTimer.start(2000)		
		
	def toggle(self):
		self["list"].toggleSelection()
		# remove channel data so it's reloaded on next advanced / install action
		self.offerToSave = True
			
	def updateStatus(self, done = None):
		self["statusbar"].setText(epgWorker.status)
		if epgWorker.active:
			if not (done is None):
				self["status"].setText("Processing.. " + str(done) + epgWorker.doneStr)
		else:
			self["status"].setText("")			
	
	def advanced(self):
		#if epgWorker.active:
		#	return
		if self.offerToSave:
			self.save(self.proceedAdvanced)
		else:
			self.proceedAdvanced()
	
	def proceedAdvanced(self):
		epgWorker.updateStatus = None
		self.session.openWithCallback(None, EGPMatchByName)	
		
	def uninstall(self):
		self.session.openWithCallback(self.proceedUninstall, MessageBox, _("EPGImport Filter Plugin\nDo you want to remove EPGImport channel filtering?"), MessageBox.TYPE_YESNO, timeout = 15, default = True)
	
	def proceedUninstall(self, confirmed):
		if confirmed:
			# removing all files
			try:
				os.remove("/etc/epgimport/filteredchannels.xml")
				os.remove("/etc/epgimport/filteredrytec.sources.xml")
			except: pass
			self.session.open(MessageBox, _("EPGImport Filter Service removed.."), MessageBox.TYPE_INFO, timeout = 1000, close_on_any_key = True)
			self.updateTimer.stop()	
			self.updateTimer.stop()	
			epgWorker.updateStatus = None
			self.proceedCancel()		
	
	def selectAll(self):
		#selected = [ item[0][1] for item in self["list"].list if item[0][3]]
		oneSelected = False
		oneUnSelected = False
		for idx,item in enumerate(self["list"].list):
			item = self["list"].list[idx][0]
			if item[3]:
				oneSelected = True
			else:
				oneUnSelected = True			
		# Select all or unselect all if all selected
		if (oneSelected and not oneUnSelected) or (oneUnSelected and not oneSelected):
			for idx,item in enumerate(self["list"].list):
				item = self["list"].list[idx][0]
				self["list"].list[idx] = SelectionEntryComponent(item[0], item[1], item[2], not item[3])
			self["list"].setList(self["list"].list)			
		if oneSelected and oneUnSelected:
			for idx,item in enumerate(self["list"].list):
				item = self["list"].list[idx][0]
				self["list"].list[idx] = SelectionEntryComponent(item[0], item[1], item[2], True)
			self["list"].setList(self["list"].list)			
		
		self.offerToSave = True
		
	def save(self, callback):
		if self.offerToSave:
			self.callback = callback
			self.session.openWithCallback(self.proceedSave, MessageBox, _("EPGImport Filter Plugin\nDo you want to save your changes?"),MessageBox.TYPE_YESNO, timeout = 15, default = True)
		else:
			self.callback = callback
			self.proceedSave(True)
		
	def proceedSave(self, confirmed):
		if confirmed:
			self.offerToSave = False
				
			epgWorker.bouquets = []
			for idx,item in enumerate(self["list"].list):
					item = self["list"].list[idx][0]
					if item[3]:
						epgWorker.bouquets.append(item[0])
						
			epgWorker.storeAll()
			if len(epgWorker.channels) > 0:
				del epgWorker.channels[:]

		if not(self.callback is None):
			callback = self.callback
			self.callback = None
			callback()
				
	def install(self):		
		# install
		if epgWorker.active:
			return

		if len(epgWorker.channels) > 0:
			del epgWorker.channels[:]
					
		if not os.path.isfile("/etc/epgimport/rytec.sources.xml"):
			self.session.open(MessageBox, _("EPGImport is not installed.."), MessageBox.TYPE_ERROR, timeout = 1000, close_on_any_key = True)			
			return
					
		if self.offerToSave: self.offerToSave = False
		self.save(None)

		if len(epgWorker.bouquets) == 0:
			self.session.open(MessageBox, _("You must choose at least one bouquet!"), MessageBox.TYPE_ERROR, timeout = 1000, close_on_any_key = True)						
			return
			
		#EPGConfig.storeUserSettings(sources=self.bouquets)		
		self.session.openWithCallback(self.doFilterCallback, MessageBox, _("EPGImport Filter Plugin\nChannels filtering will start\nThis may take a few minutes\nIs this ok?"), MessageBox.TYPE_YESNO, timeout = 15, default = True)
		
	def doFilterCallback(self, confirmed):
		if not confirmed:
			return
		try:
			#epgimportfilterworker.onDone = nothingForNow
			#epgWorker.bouquets = self.bouquets
			epgWorker.updateStatus = self.updateStatus
			epgWorker.createFilteredChannelFile()
		except Exception, e:
			self.session.open(MessageBox, _("EPGImport Filter Plugin\nFailed to start:\n") + str(e), MessageBox.TYPE_ERROR, timeout = 15, close_on_any_key = True)

		self.updateStatus()
					
	def cancel(self):
		self.updateTimer.stop()	
		epgWorker.updateStatus = None
		if self.offerToSave:			
			self.save(self.proceedCancel)
		else:
			self.proceedCancel()

	def proceedCancel(self):
		self.close(self.session, False)
