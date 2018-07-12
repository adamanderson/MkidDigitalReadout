"""
Command line tools

If you add a function here, "reload(iTools)" is your friend.

Sample use from iPython:

> import clTools
> rchc = clTools.setup(100, 'chris.cfg') # rchc is a handle to a RoachConnection.
> data = clTools.readDataTest()
> iTools.plotIQ(rchc) # plot average IQ values as a function of time

and if you make changes to code in this file:

> reload(clTools)

"""
import os, sys, warnings
import numpy as np
import datetime, socket
import ConfigParser
import RoachConnection
reload(RoachConnection)
import WritePhaseData
reload(WritePhaseData)
    
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
    rchc.loadFIRs()
    return rchc

def loadFIRs(rchc):
    rchc.loadFIRs()


def performIQSweep(rchc):
    LO_freq = rchc.roachController.LOFreq
    LO_span = rchc.config.getfloat(rchc.roachString,'sweeplospan')
    LO_step = rchc.config.getfloat(rchc.roachString,'sweeplostep')
    LO_start = LO_freq - LO_span/2.
    LO_end = LO_freq + LO_span/2.
    iqData = rchc.roachController.performIQSweep(LO_start/1.e6,
                                                 LO_end/1.e6,
                                                 LO_step/1.e6,
                                                 verbose=True)
    return iqData

def readPhasesTest(rchc):
    freqChan = 0
    duration = 1.0

    ipaddress = rchc.config.get(rchc.roachString, 'ipaddress')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((ipaddress,80))
    hostIP = s.getsockname()[0]
    port = int(rchc.config.get(rchc.roachString,'port'))

    data = rchc.roachController.takePhaseStreamDataOfFreqChannel(
        freqChan=freqChan, duration=duration, hostIP=hostIP, fabric_port=port)
    return data

def doOnePhaseSnapshot(rchc, freqChan, duration, outDir,fileName, format="ascii"):
    ipaddress = rchc.config.get(rchc.roachString, 'ipaddress')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((ipaddress,80))
    hostIP = s.getsockname()[0]
    port = int(rchc.config.get(rchc.roachString,'port'))

    data = rchc.roachController.takePhaseStreamDataOfFreqChannel(
        freqChan=freqChan, duration=duration, hostIP=hostIP, fabric_port=port)
    
    freqs=rchc.roachController.freqChannels
    
    # now write this data to fileName
    if outDir is None:
		outDir=cwd = os.getcwd()

    if fileName is not None:
		filename=os.path.join(outDir,fileName)
    else: filename="test"
	
    if format is None :
		format=="ascii"

    wp=WritePhaseData.writePhaseData(filename,format,freqChan,freqs,duration,data)
    wp.Write()
	   
    return data

