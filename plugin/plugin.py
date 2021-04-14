# EpgImport Filter plugin
# It filters the channels for epgimport

VERSION = "1.2"

import enigma

from Plugins.Plugin import PluginDescriptor

def main(session, **kwargs):
	import ui
	#session.open(ui.EPGImportFilterScreen)
	session.openWithCallback(
		doneConfiguring,
		ui.EPGImportFilterScreen
	)	
	
def doneConfiguring(session, retval):
    "user has closed configuration, check new values...."
	
def Plugins(**kwargs):
	return PluginDescriptor(
		name="EPGImport Filter",
		description="Filter EPGImport data for selected bouquets",
		where=PluginDescriptor.WHERE_PLUGINMENU,
		icon="plugin.png",
		fnc=main)
