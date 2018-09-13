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
import os, sys, warnings, datetime, pickle
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


def performIQSweep(rchc, saveToFile=None):
    LO_freq = rchc.roachController.LOFreq
    LO_span = rchc.config.getfloat(rchc.roachString,'sweeplospan')
    LO_step = rchc.config.getfloat(rchc.roachString,'sweeplostep')
    LO_start = LO_freq - LO_span/2.
    LO_end = LO_freq + LO_span/2.
    iqData = rchc.roachController.performIQSweep(LO_start/1.e6,
                                                 LO_end/1.e6,
                                                 LO_step/1.e6,
                                                 verbose=False)
    iqData['LO_freq']   = LO_freq
    iqData['LO_span']   = LO_span
    iqData['LO_step']   = LO_step
    iqData['LO_start']  = LO_start
    iqData['LO_end']    = LO_end
    iqData['atten1']    = rchc.roachController.attenVal[1]
    iqData['atten2']    = rchc.roachController.attenVal[2]
    iqData['atten3']    = rchc.roachController.attenVal[3]
    iqData['atten4']    = rchc.roachController.attenVal[4]
    iqData['timestamp'] = datetime.datetime.now()
    iqData['freqList']  = rchc.roachController.freqList
    
    if saveToFile is not None:
        print "save to file"
        saveIQSweepToFile(rchc, iqData, saveToFile)
    return iqData

def takeLoopData(rchc, fnPrefix):
    iFile = 0
    while True:
        pklFileName = "%s-%04d.pkl"%(fnPrefix,iFile)
        handle = open(pklFileName,'wb')
        for i in range(100):
            iqData = performIQSweep(rchc)
            pickle.dump(iqData, handle)
            print "%s %5d %s"%(pklFileName, i, str(iqData['timestamp']))
        handle.close()
        iFile += 1
        
def saveIQSweepToFile(rchc, iqData, saveToFile):
    print "saveToFile =",saveToFile
    freqList = rchc.roachController.freqList
    attenList = rchc.roachController.attenList
    for iFreq,f0 in enumerage(freqList):
        w = iqsweep.IQSweep()
        w.f0 = freqList[iFreq]
        w.span = iqData['LO_span']/1e6
        w.fsteps = len(iqData['freqOffsets'])
        # attempt to copy logic in RoachStateMachein after the "save the power sweep" comment
        w.atten1 = attenList[iFreq] + iqData['atten3']
        w.atten2 = attenList[iFreq] + iqData['atten4']
        
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

            
    wp=WritePhaseData.WritePhaseData(filename,format,freqChan,freqs,duration,data)
    ##wp.write()
	   
    return data

def takePhaseData(rchc, nToDo, freqChan, duration, fileNamePrefix):
    for i in range(nToDo):
        fileName = "%s-%04d"%(fileNamePrefix,i)
        print i, fileName
        doOnePhaseSnapshot(rchc, freqChan, duration, ".", fileName, format='hdf5') 
