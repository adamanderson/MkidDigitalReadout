"""
Help interactive work with the roach board.

If you add a function here, "reload(iTools)" is your friend.

Sample use from iPython:

> import iTools
> rchc = iTools.setup(100, 'chris.cfg') # rchc is a handle to a RoachConnection.
> iTools.plotIQ(rchc) # plot average IQ values as a function of time

and if you make changes to code:

reload(iTools)

> avgIQData = rchc.roachController.takeAvgIQData(100)
# This is a dictionary of 'I' and 'Q' of the 100 measurements at each frequency.


"""
iToolsVersion = 0.2
import numpy as np
import datetime
import ConfigParser
import RoachConnection
reload(RoachConnection)
import IQPlotWindow
reload(IQPlotWindow)
import PhasePlotWindow
reload(PhasePlotWindow)
import os

def getItoolsVersion():
    return iToolsVersion

def connect(roachNumber, configFile):
    rchc = RoachConnection.RoachConnection(roachNumber, configFile)
    return rchc

def loadFreq(rchc):
    rchc.loadFreq()

def setup(roachNumber, configFile):
    """
    for the roach number and confFile, set up the connection and load LUTs to prepare
    for making measurements
    """

    rchc = connect(roachNumber, configFile)
    rchc.loadFreq()
    rchc.defineRoachLUTs()
    rchc.defineDacLUTs()
    return rchc

def plotIQ(rchc):
    reload(IQPlotWindow)
    iqPlotWindow = IQPlotWindow.IQPlotWindow(rchc)
    iqPlotWindow.show()
    return iqPlotWindow

def plotPhases(rchc):
    reload(PhasePlotWindow)
    phasePlotWindow = PhasePlotWindow.PhasePlotWindow(rchc)
    phasePlotWindow.show()
    return phasePlotWindow

def readPhasesTest(rchc):
    freqChan = 0
    duration = 1.0

    hostIP = rchc.config.get('HOST', 'hostIP')
    port = int(rchc.config.get(rchc.roachString,'port'))

    data = rchc.roachController.takePhaseStreamDataOfFreqChannel(
        freqChan=freqChan, duration=duration, hostIP=hostIP, fabric_port=port)
    return data

def doOnePhaseSnapshot(rchc, freqChan, duration, fileName, format="ascii"):
    hostIP = rchc.config.get('HOST', 'hostIP')
    port = int(rchc.config.get(rchc.roachString,'port'))

    data = rchc.roachController.takePhaseStreamDataOfFreqChannel(
        freqChan=freqChan, duration=duration, hostIP=hostIP, fabric_port=port)
    # now write this data to fileName
    if fileName is not None:
	#fileName="/home/mkids/MkidDigitalReadout/DataReadout/ChannelizerControls/test.dat"
	cwd = os.getcwd()
	fileName=os.path.join(cwd,"test.dat") 
	dtime=str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")) 
	sdtime="File created at "+dtime +"\n" 
	sdur = "Duration : %6.3fs\n"%duration
	schan= "Frequency Channel: %d \n"%freqChan
	freq=rchc.roachController.freqChannels
	print schan 
	
        print "now write to ",fileName, dtime
        nfile = open(fileName,'wb')  
	nfile.write(sdtime)
	nfile.write(sdur)
	nfile.write(schan)
	nfile.write("Frequencies: \n")
	np.savetxt(nfile, freq)
	nfile.write("data \n")	     
        np.savetxt(nfile, data)
    return data

