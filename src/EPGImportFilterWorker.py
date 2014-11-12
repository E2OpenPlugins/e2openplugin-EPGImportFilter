# EPGImportFilter Worker

import os
import time
import enigma
import shutil
import calendar
import codecs

import localdifflib

from twisted.internet import reactor, threads
from twisted.web.client import downloadPage
import twisted.python.runtime

from string import maketrans 
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.ConfigList import ConfigList, ConfigListScreen
from Components.SelectionList import SelectionList, SelectionEntryComponent
from Components.config import ConfigYesNo, ConfigSelection, ConfigInteger, config, getConfigListEntry
from Components.ActionMap import ActionMap
from Components.Label import Label
from os import system
from enigma import eTimer, getDesktop, eServiceCenter, eServiceReference, iServiceInformation
from Components.ProgressBar import ProgressBar
from operator import itemgetter		

from ServiceReference import ServiceReference

from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN, SCOPE_CURRENT_PLUGIN

import cPickle as pickle

def bigStorage(minFree, default, *candidates):
	try:
            diskstat = os.statvfs(default)
            free = diskstat.f_bfree * diskstat.f_bsize
            if (free > minFree) and (free > 2000000):
                return default
        except Exception, e:
            pass
        mounts = open('/proc/mounts', 'rb').readlines()
		# format: device mountpoint fstype options #
        mountpoints = [x.split(' ', 2)[1] for x in mounts]
        for candidate in candidates:
            if candidate in mountpoints:
                try:
                    diskstat = os.statvfs(candidate)
		    free = diskstat.f_bfree * diskstat.f_bsize
		    if free > minFree: 
                        return candidate
                except:
                    pass
    	return default
		
class SettingsMgr:
	def __init__(self, sections):
		self.settingsFile = resolveFilename(SCOPE_CURRENT_PLUGIN, "Extensions/EPGImportFilter/settings.conf")
		self.sections = sections
			
	def loadUserSettings(self):
		#self.sources = {}
		sources = {}
		for i in self.sections:
			sources.update({i: []})
		try:
			with open(self.settingsFile,'rb') as fp:			
				for i in self.sections:
					try:
						#self.sources.update(pickle.load(fp))
						sources.update(pickle.load(fp))
					except: pass
		except: pass	
		return sources		
		
	def storeUserSettings(self, sources):
		with open(self.settingsFile,'wb') as fp:			
			for i in self.sections:
				try:
					m = sources[i]
					container = {i: m}
					pickle.dump(container, fp, pickle.HIGHEST_PROTOCOL)
				except: pass
					
settingsMgr = SettingsMgr(["sources", "bouquets", "matches", "matchings"])
		
class TimeMgr: 

	def __init__(self):
		self.dateParser = None
		self.dateformat = '%Y%m%d%H%M%S'
		if self.dateformat.startswith('%Y%m%d%H%M%S'):
			self.dateParser = self.quickptime
		else:
			self.dateParser = lambda x: time.strptime(x, self.dateformat) 

	# %Y%m%d%H%M%S 
	def quickptime(self, str):
		return time.struct_time((int(str[0:4]), int(str[4:6]), int(str[6:8]),
                             int(str[8:10]), int(str[10:12]), 0,
                             -1, -1, 0))
							 
	def get_time_utc(self, timestring):
		try:
			values = timestring.split(' ')
			
			tm = self.dateParser(values[0])
			timegm = calendar.timegm(tm)
			#suppose file says +0300 => that means we have to substract 3 hours from localtime to get gmt
			timegm -= (3600*int(values[1])/100)
			return timegm
		except Exception, e:
			print "[XMLTVConverter] get_time_utc error:", e
			return 0
		
timeMgr = TimeMgr()

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
# channels[]
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
		
class EPGImportFilterWorker: 
	# Worker
	def __init__(self):
		self.bouquets = [] 
		self.status = ""
		self.done = 0
		self.doneStr = "%"
		self.updateStatus = None
		#self.doneLoading = None
		self.onlyLoad = False
		self.channels = []
		self.active = False
		self.epgSources = []
		self.epgChannels = []
		#self.epgProgramme = []
		self.epgProgramme = {}
		self.matches = [] # matching pairs
		self.matchings = [] # user matching clicks
		# epgloading
		self.epgLoadCounter = 0	
		self.epgLoadSources	= []
		self.epgSourcesChosen = []
		# load all matches and matchings from previous sessions
		self.loadAll()
		
		self.channelSource = ""
		intab  = "+'=!@#$%-/?,*"  
		outtab = "             "
		self.trantab = maketrans(intab, outtab)

	def getCompareName(self, name):
		#d = name
		#return d.lower().translate(self.trantab).replace(' ','').strip()
		return name.lower().translate(self.trantab).replace('hd','').replace('tv','').replace(' ','').strip()

	def getCompareRef(self, ref):	
		# move leading zero on 6th field
		r = ref.split(":", 6)
		if len(r) >= 7:
			l = r[5]
			if len(l) > 0 and l[0] == "0":
				try:
					l = int(l)
				except: return ref
				return r[0] +":"+ r[1] +":"+ r[2] +":"+ r[3] +":"+ r[4] +":"+ str(l) +":"+ r[6]
			else:
				return ref
		else:
			return ref
		
	def getChannelList(self, bouquetNames = None):
		channels = [ ]
		serviceHandler = eServiceCenter.getInstance()
		bouquet_rootstr = '1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "bouquets.tv" ORDER BY bouquet'
		bouquet_root = eServiceReference(bouquet_rootstr)
		r = 0; idx = 0
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
							if bouquetNames is None or info.getName(s) in bouquetNames:
								clist = serviceHandler.list(s)
								if clist:
									while True:
										a = clist.getNext()
										if not a.valid(): break
										if not (a.flags & eServiceReference.isMarker):
											#if not (a.toCompareString().lower() in (v[0] for v in channels)):
											i = serviceHandler.info(a)
											#cur = i.getTransponderData(a)
											#pp = (cur.getattribute("orbital_position", 0))
											name = self.getCompareName(i.getName(a))
											# Ref, full name, compare name, indicator of mapping, #matches 
											channels.append([a.toCompareString().lower(), i.getName(a), name, -1, idx]) #, 0])
											idx += 1
											r += 1
											self.done += 1
											if r >= 100:			
												if not (self.updateStatus is None): self.updateStatus(self.done)
												r = 0
				# remove duplicate channels
				c = sorted(channels, key=itemgetter(0))
				d = []
				lastRef = ""
				for p in c:
					if p[0] == lastRef:
						d.append(p[4])
					lastRef = p[0]
				# now sort delete idx list by descending and delete
				d = sorted(d, reverse=True)
				l = 0
				for p in d:
					l += 1
					del channels[p]
				return channels
		#else:
		#	info = serviceHandler.info(bouquet_root)
		#	if info:
		#		bouquets.append((info.getName(bouquet_root), bouquet_root))
		#	return channels
		text_file.close()
		return None
		
	def createFilteredChannelFile(self, onlyLoad = False):
		self.status = "Downloading channel file.."
		self.active = True
		self.done = 0
		# Parse Rytec_sources.xml
		inChannels = False; inSources = False; sourceName = ""
		if self.channelSource == "":
			for line in open('/etc/epgimport/rytec.sources.xml','r'):				
					try:
						line = line.encode('utf-8')
					except Exception, e: pass
					if not line.find("</channel>") == -1 and inChannels:
						inChannels = False
					elif not line.find("channel name=") == -1:
						inChannels = True
					elif self.channelSource == "" and inChannels and line.find("<url>"):					
						# find only first channel source for now
						self.channelSource = line.split(">")[1].split("<")[0]
					elif not line.find("</source>") == -1 and inSources:
						inSources = False
					elif not line.find("source type=") == -1:
						inSources = True
					elif inSources and not line.find("<description>") == -1:
						sourceName = line.split(">",1)[1].split("<",1)[0]
					elif inSources and not line.find("<url>") == -1:
						# Load epg source file download links
						# name, filename, chosen on epg load
						self.epgSources.append([sourceName, line.split(">")[1].split("<")[0]])
		
		if self.channelSource == "":
			self.status = "No channel download links found in /etc/epgimport/rytec.sources.xml.."
			self.active = 0
			return
		
		self.onlyLoad = onlyLoad
		self.downloadFile(self.channelSource, self.proceedCreateFilteredChannelFile, self.downloadFail)	
								
	def downloadFile(self, sourcefile, afterDownload, downloadFail):
		path = bigStorage(2000000, '/tmp', '/media/cf', '/media/usb', '/media/hdd')
		s = sourcefile.split("/")		
		filename = os.path.join(path, s[len(s)-1])
		downloadPage(sourcefile, filename).addCallbacks(afterDownload, downloadFail, callbackArgs=(filename, True))	
		return filename
		
	def downloadFail(self, failure):
		self.status = "Error: " + failure + " while downloading files.."
		self.active = False
		
	def proceedCreateFilteredChannelFile(self, result, filename, deleteFile = False):
		if twisted.python.runtime.platform.supportsThreads():
			threads.deferToThread(self.proceedCreateFilteredChannelFileThread, result, filename, False).addCallback(lambda ignore: None)
		else:
			proceedCreateFilteredChannelFileThread(result, filename, False)
		
	def proceedCreateFilteredChannelFileThread(self, result, filename, deleteFile = False):
		# proceed with installation after downloading the channel file
		self.done = 0
		if not (self.updateStatus is None): self.updateStatus(self.done)
		self.doneStr = ""
		self.status = "Reading channels.."

		channelPath = filename
		if filename.endswith('.gz'):
			system("gunzip " + filename)
			channelPath = filename.split(".gz")[0]

		if not os.path.isfile(channelPath):
			self.status = "Error when opening file:" + filename
			self.active = False
			return
		
		# Read all services for marked bouquets
		self.channels = self.getChannelList(self.bouquets)
		
		xmlChannels = []
		# structure
		xRef = 0; xName = 1; xCompare = 2; xIdxChannel = 3; xId = 4
		# First load all channels from .xml file
		cnt = -1
		self.status = "Parsing XML channels.."
		self.done = 0
		self.doneStr = "%"
		if not (self.updateStatus is None): self.updateStatus(self.done)
		fileSize = os.path.getsize(channelPath)
		fileDone = 0; r = 0
		try:
			# Channel line convert from latin-1 to utf-8
			for line in codecs.open(channelPath, "r", "latin-1"): 
			#for line in codecs.open("/etc/epgimport/arytec.channels.xml", "r", "latin-1"): 
				line = line.encode('utf-8').strip()
				fileDone += len(line); r += 1
				if r >= 100:
					self.done = round(float(fileDone) / fileSize * 100)
					if not (self.updateStatus is None): self.updateStatus(self.done)
					r = 0

				if (not len(line) < 9 and line[:11] == "<channel id"):
				#if not (line.find("<channel id") == -1):
					try: name = line.split('"',1)[1].split('"',1)[0]
					except: name = ""
					compareName = self.getCompareName(name)
					try: ref = line.split('">')[1].split("</channel")[0].strip().lower()
					except: ref = ""
					# reference, name, compareName, channel mapped idx, id
					cnt += 1
					xmlChannels.append([ref, name, compareName, -1, cnt])
		except Exception, e:
			self.status = "Error on reading channel file:" + str(e)
			self.active = False
			return
				
		s = [self.getCompareRef(v[xRef]) for v in xmlChannels]
		matchesChannels = [self.getCompareRef(v[mRef]) for v in self.matches]
		matchingsChannels = [self.getCompareRef(v[mcRef]) for v in self.matchings]
				
		# First find all channels that matching reference
		cntFound = 0
		self.status = "Comparing channels.."
		self.done = 0
		if not (self.updateStatus is None): self.updateStatus(self.done)
		l = len(self.channels); cnt = 0; r = 0
		
		for x in range(0, l):
			cnt += 1; r += 1
			if r >= 100:
				self.done = round(float(cnt) / l * 100)
				if not self.updateStatus is None: self.updateStatus(self.done)
				r = 0
				
			try: indx = s.index(self.getCompareRef(self.channels[x][cRef]))
			except: indx = -1
			if indx >= 0:
				self.channels[x][cIndxXMLChannel] = indx
				xmlChannels[indx][xIdxChannel] = x
				cntFound += 1
				# add manual match and matchings indicator
				# ref, epgProgramName, sort, auto-entry
				# if match exists or matching already exists dont' add it
				if not self.getCompareRef(self.channels[x][cRef]) in matchesChannels:
					self.matches.append([self.channels[x][cRef], xmlChannels[indx][xName], 0, 1]) # match index will be used for sorting
				if not self.getCompareRef(self.channels[x][cRef]) in matchingsChannels:
					self.matchings.append((self.channels[x][cRef], xmlChannels[indx][xName], 1))
				
		if not self.onlyLoad:
			#text_file = open("/etc/epgimport/filteredchannels.xml", "w")				
			try:
				self.status = "Creating channels file.."
				self.done = 0; fileDone = 0; cnt = -1; r = 0
				if not (self.updateStatus is None): self.updateStatus(self.done)

				text_file = open("/etc/epgimport/filteredchannels.xml", "w")				
				#text_file = codecs.open("/etc/epgimport/filteredchannels.xml", "w", "latin-1")
				text_file.truncate()		
				text_file.write('<?xml version="1.0" encoding="latin-1"?>\n')
				text_file.write('<!-- service references can be found in /etc/enigma2/lamedb -->\n')
				text_file.write('<channels>\n')

				v = [v for v in self.matchings if v[mcState] > 0]
				fileSize = len(v)
				for i in v:
						fileDone += 1; r += 1
						if r >= 100:
							self.done = round(float(fileDone) / fileSize * 100) 
							if not (self.updateStatus is None): self.updateStatus(self.done)
							r = 0
							
						line = '<channel id="' + i[mcProgram] + '">' + i[mcRef] + '</channel> <!-- -->\n'
						line = line.decode("utf-8").encode("latin-1")
						text_file.write(line)
				text_file.write('</channels>\n')
				text_file.close()
			except Exception,e:
				self.status = "Error when writing channels: " + str(e)
				self.active = False
				return
				
		# create new channels file
		os.remove(channelPath)
		
		# Create new sources file
		if not self.onlyLoad:
			self.status = "Creating sources file.."
			text_file = open("/etc/epgimport/filteredrytec.sources.xml", "w")				
			text_file.truncate()
			inChannels = False
			for line in open('/etc/epgimport/rytec.sources.xml','r'):	
					line = line.encode('utf-8')
					if not line.find("</channel>") == -1 and inChannels:
						inChannels = False
					elif inChannels:
						inChannels = True
					elif not line.find("channels=") == -1:
						r = line.split("channels=")
						s = r[0] + 'channels="filteredchannels.xml">\n'
						text_file.write(s)				
					elif not line.find("channel name=") == -1:
						inChannels = True
					elif not line.find("<description>") == -1:
						r = line.split("<description>")
						s = r[0] + '<description>Filtered ' + r[1]
						text_file.write(s)
					else:
						text_file.write(line)				
			text_file.close()		
			
		# Give info
		self.status = str(len(self.channels)) + " channels " + str(cntFound) + " mapped.."
		self.done = 100		
		self.active = False		
				
	def epgLoad(self, sources):	
		if len(sources) == 0:
			return
				
		self.epgLoadCounter = -1
		self.epgLoadSources	= sources
		self.epgSourcesChosen = [v[0] for v in self.epgLoadSources]		
		self.epgChannels = []
		#self.epgProgramme = []		
		self.epgProgramme = {}
		self.dispatchEpgLoad()
	
	def dispatchEpgLoad(self):	
		if len(self.epgLoadSources) > self.epgLoadCounter + 1:
			self.epgLoadCounter += 1		
			self.status = "Downloading epg data.."
			self.active = True
			self.done = 0
			if not (self.updateStatus is None): self.updateStatus(self.done)
			self.downloadFile(self.epgLoadSources[self.epgLoadCounter][1], self.proceedEpgLoad, self.downloadFail)	
		else:
			self.active = False	
	
	def proceedEpgLoad(self, result, filename, deleteFile = False):
		if twisted.python.runtime.platform.supportsThreads():
			threads.deferToThread(self.proceedEpgLoadThread, result, filename, False).addCallback(lambda ignore: None)
		else:
			proceedEpgLoadThread(result, filename, False)
		
	def proceedEpgLoadThread(self, result, filename, deleteFile = False):
		# If the file is gz extract it
		self.done = 0
		self.status = "Parsing epg " + self.epgLoadSources[self.epgLoadCounter][0]
		self.doneStr = "%"		
		if not (self.updateStatus is None): self.updateStatus(self.done)

		epgSourcePath = filename
		if filename.endswith('.gz'):
			system("gunzip " + filename)
			epgSourcePath = filename.split(".gz")[0]
		
		# Parse epg.xml file
		inProgramme = False; programName = ""; cnt = 0
		lastProgramName = ""; titleName = ""; subtitleName = ""; startTime = 0; endTime = 0
		fileSize = os.path.getsize(epgSourcePath); fileDone = 0; r = 0		
		self.done = 0
		if not (self.updateStatus is None): self.updateStatus(self.done)
		
		#text_file = open("/etc/epgimport/what.xml", "w")				
		#text_file.truncate()		
		max_entries = 5
		prog = []; errors = False
		# Find file encoding
		for line in open(epgSourcePath,'r'):
			encoding = line.split('encoding="')[1].split('"')[0]
			break
		try:
			curTime = time.time()
			for line in codecs.open(epgSourcePath, "r", encoding): 
			#for line in open(epgSourcePath,'r'):					
				fileDone += len(line); r += 1
				if r >= 100:
					self.done = round(float(fileDone) / fileSize * 100)
					if not (self.updateStatus is None): self.updateStatus(self.done)
					r = 0
						
				line = line.strip().encode('utf-8')
				if inProgramme and (not len(line) < 11 and line[:12] == "</programme>"):
					inProgramme = False
					if cnt < 5 and endTime >= curTime:
						# use only 3 program data for now
						# programName, titleName
						#self.epgProgramme.append([programName, titleName])
						prog.append((titleName))
						cnt += 1
				elif not inProgramme and (not len(line) < 16 and line[:17] == "<programme start="):
					inProgramme = True
					elem = line.split('"')
					programName = elem[5].strip()
					if not (programName == lastProgramName):
						if len(prog) > 0:
							# add program as indexed to program
							self.epgProgramme.update({lastProgramName: prog})
							prog = []					
						compareName = self.getCompareName(programName)
						if programName not in (v[eProgram] for v in self.epgChannels):
							self.epgChannels.append([programName, compareName])
						cnt = 0
					endTime = timeMgr.get_time_utc(elem[3])				
					if cnt < 5 and endTime >= curTime:
						startTime = timeMgr.get_time_utc(elem[1])				
					lastProgramName = programName
					titleName = ""; subtitleName = ""
				elif inProgramme and cnt < 5 and endTime >= curTime and (not len(line) < 11 and line[:12] == '<title lang='):
					titleName = time.ctime(startTime) + " " + line.split(">",1)[1].split("<",1)[0].strip()
				#elif inProgramme and not line.find('<sub-title lang="') == -1:
				#	subtitleName = line.split(">",1)[1].split("<",1)[0].strip()
				
		except Exception, e:
			self.status = "Error on reading epg: " + str(e) 
			errors = True

		# add last that's not added
		if len(prog) > 0:
			# add program as indexed to program
			self.epgProgramme.update({lastProgramName: prog})
			
		# Remove epg file
		os.remove(epgSourcePath)

		# Give info
		if not errors:
			self.status = str(len(self.epgProgramme)) + " epg programs loaded.."
		self.done = 100		
		
		self.dispatchEpgLoad()

	def compareNames(self, channelRef, deep):
		# Compare by name specified channel
		# Find the channel
		k = [i for i,v in enumerate(self.channels) if v[cRef] == channelRef.lower()][0]
		if k < 0: return
				
		d = self.channels[k]
		# now compare with programmeNames and create matches
		# remove previous entries in matches
		p = [idx for idx,v in enumerate(self.matches) if v[mRef] == d[cRef] and v[mAutoLoad] == 0]
		if len(p) > 0:
			p = sorted(p, reverse = True)
			for v in p:				
				del self.matches[v]
									
		count = 10
		if deep == 1:
			s = [v[eCompare] for v in self.epgChannels if v[eCompare][0] == d[cCompare][0]]
			count = 10
		elif deep == 2:
			s = [v[eCompare] for v in self.epgChannels if v[eCompare][0] == d[cCompare][0]]
			count = 30
		else:
			s = [v[eCompare] for v in self.epgChannels]
			count = 50
		
		match = localdifflib.get_close_matches(d[cCompare], s, count, 0.5)
		if len(match) < count:
			match = localdifflib.get_close_matches(d[cCompare], s, count, 0.10)

		k = [idx for idx,v in enumerate(self.epgChannels) if v[eCompare] in match]
		if len(k) > 0:
			for o in k:
				p = self.epgChannels[o][eProgram]
				match_index = match.index(self.epgChannels[o][eCompare])
				# ref, epgProgramName, sort, auto-entry
				# First check if match exists and if yes update it													
				s = [idx for idx,v in enumerate(self.matches) if v[mRef] == d[cRef] and v[mProgram] == p]
				if len(s) > 0:
					self.matches[s[0]] = (d[cRef], p, match_index, self.matches[s[0]][mAutoLoad]) 
				else:
					self.matches.append([d[cRef], p, match_index, False]) # match index will be used for sorting
				
	def storeAll(self):
		autoGeneratedMatches  = [v[mRef] +","+ v[mProgram] for v in self.matches if v[mAutoLoad] == 1]
		
		# store only matchings that are disable - 0 or not autogenerated matching match
		matchings = [v for v in self.matchings if v[mcState] == 0 or not (v[mcRef] +","+ v[mcProgram] in autoGeneratedMatches)]
		matchingsIds = [v[mcRef] +','+ v[mcProgram] for v in matchings]
		matches = [v for v in self.matches if v[mAutoLoad] != 1 and v[mRef] +','+ v[mProgram] in matchingsIds]
		
		self.status = "Saved " + str(len(matchings)) + " entries.."
		
		settingsMgr.storeUserSettings(sources = {"sources" : self.epgSourcesChosen, "bouquets":self.bouquets, "matches": matches, "matchings": matchings})
	
	def loadAll(self):
		cfg = settingsMgr.loadUserSettings()
		
		self.bouquets = cfg["bouquets"]
		self.matches = cfg["matches"]
		self.matchings = cfg["matchings"]
		self.epgSourcesChosen = cfg["sources"]

		# Assign all matches to 2 - auto loaded from last save but not auto-generated
		idx = [idx for idx,v in enumerate(self.matches) if v[mAutoLoad] == 0]
		if len(idx) > 0:
			for i in idx:
				self.matches[i] = (self.matches[i][0], self.matches[i][1], self.matches[i][2], 2)
				