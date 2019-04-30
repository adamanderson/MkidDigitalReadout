"""
Command line tools

If you add a function here, "reload(iTools)" is your friend.

Sample use from iPython:

> import clTools
> rchc = clTools.connect(100, 'chris.cfg') # rchc is a handle to a RoachConnection.
> clTools.setup(rchc)
> data = clTools.readDataTest()
> iTools.plotIQ(rchc) # plot average IQ values as a function of time

and if you make changes to code in this file:

> reload(clTools)

"""
import ConfigParser, binascii, datetime, dateutil, glob, hashlib
import logging, os, pickle, sys, time, timeit,warnings, socket
from socket import inet_aton
import numpy as np
import scipy.special
from scipy.signal import butter, filtfilt, find_peaks
from autoZdokCal import loadDelayCal, findCal
from myQdr import Qdr as myQdr
import casperfpga
import Roach2Controls
# Modules from this package that may be changed during an interactive session
import LoopFitter
reload(LoopFitter)
import RoachConnection
reload(RoachConnection)
import WritePhaseData
reload(WritePhaseData)
import ReceiveFPGAStream
reload(ReceiveFPGAStream)

def init(roachNumber, configFile):
    """ 
    Initialize the Roach board after powering up:
     Upload the program from the config parameter 'fpgPath'
     Call Roach2Controls.loadBoardNum and loadCurTimestamp
     Call Roach2Controls.initializeV7UART
     Call Roach2Controls.initializeV7MB
     Call Roach2Controls.setLOFreq() then .loadLOFreq
     Call Roach2Controls.changeAtten for DAC atten 1&2, ADC atten 1&2 (all to 31.75)
     Call Roach2Controls.sendUARTCommand(0x4) to switch on ADC ZDOK Cal Ramp
     set relative IQ scaling to 1
     Call Roach2Controls.fpga.write_int('run',1)
     do delays and calibrations
     Call Roach2Controls.sendUARTCommand(0x5) to switch off ADC ZDOK Cal Ramp
     run QDR calibrations
     call clTools.connect() to define rchc
     rchc.defineRoachLUTs
     rchc.loadFIRs
Return -- the resulting rchc
    """
    
    config = ConfigParser.ConfigParser()
    config.read(configFile)
    
    # Mimic what is done in InitStateMachine programV6
    roachString = 'Roach '+"%d"%roachNumber
    FPGAParamFile = config.get(roachString,'FPGAParamFile')
    ipaddress = config.get(roachString,'ipaddress')
    roachController = Roach2Controls.Roach2Controls(ipaddress, FPGAParamFile, False, False)
    roachController.connect()
    fpgPath = config.get('Roach '+str(roachNumber),'fpgPath')
    print "set casperfpga.utils logger to INFO"
    casperfpga.utils.LOGGER.setLevel(logging.INFO)
    roachController.fpga.upload_to_ram_and_program(fpgPath)
    print 'Fpga Clock Rate:',roachController.fpga.estimate_fpga_clock()
    roachController.loadBoardNum(roachNumber)
    roachController.loadCurTimestamp()
                                        
    # Mimic what is done in InitStateMachine initV7
    waitForV7Ready = config.getboolean('Roach '+str(roachNumber),'waitForV7Ready')
    roachController.initializeV7UART(waitForV7Ready=waitForV7Ready)
    print 'initialized uart'
    roachController.initV7MB()
    print 'initialized mb'
    #self.config.set('Roach '+str(roachNumber),'waitForV7Ready',False)
    roachController.setLOFreq(2.e9)
    roachController.loadLOFreq()
    print 'Set LO to 2 GHz'
    roachController.changeAtten(1, 31.75)   #DAC atten 1
    roachController.changeAtten(2, 31.75)   #DAC atten 2
    roachController.changeAtten(3, 31.75)   #ADC atten 1
    roachController.changeAtten(4, 31.75)   #ADC atten 2
    print 'Set RF board attenuators to maximum'

    # Mimic what is done in InitStateMachine calZdok
    roachController.sendUARTCommand(0x4)
    print 'switched on ADC ZDOK Cal ramp'
    time.sleep(.1)
    
    nBitsRemovedInFFT = config.getint('Roach '+str(roachNumber),'nBitsRemovedInFFT')
    roachController.fpga.write_int('adc_in_i_scale',2**7) #set relative IQ scaling to 1
    # if(nBitsRemovedInFFT == 0):
    #     rchc.setAdcScale(0.9375) #Max ADC scale value
    # else:
    #     rchc.setAdcScale(1./(2**nBitsRemovedInFFT))

    roachController.fpga.write_int('run',1)
    busDelays = [14,18,14,13]
    busStarts = [0,14,28,42]
    busBitLength = 12
    for iBus in xrange(len(busDelays)):
        delayLut = zip(np.arange(busStarts[iBus],busStarts[iBus]+busBitLength), 
                       busDelays[iBus] * np.ones(busBitLength))
        loadDelayCal(roachController.fpga,delayLut)

    # calDict = findCal(roachController.fpga,nBitsRemovedInFFT)
    calDict = findCal(roachController.fpga)
    print calDict
        
    roachController.sendUARTCommand(0x5)
    print 'switched off ADC ZDOK Cal ramp'
        
    if not calDict['solutionFound']:
        raise ValueError
            
    # Mimic what is done in InitStateMachine calQDR
    bQdrFlip = True
    calVerbosity = 0
    bFailHard = False
    #roachController.fpga.get_system_information()
    results = {}
    for iQdr,qdr in enumerate(roachController.fpga.qdrs):
        mqdr = myQdr.from_qdr(qdr)
        print qdr.name
        results[qdr.name] = mqdr.qdr_cal2(fail_hard=bFailHard,verbosity=calVerbosity)

    print 'Qdr cal results:',results
    for qdrName in results.keys():
        if not results[qdrName]:
            raise ValueError

    rchc = connect(roachNumber, configFile)
    rchc.loadFIRs()
    return rchc

def connect(roachNumber, configFile):
    """ Make a connection and do not do any setup"""
    rchc = RoachConnection.RoachConnection(roachNumber, configFile)
    return rchc

def loadFreq(rchc):
    rchc.loadFreq()


    
def setup(rchc):
    """
    load LUTs to prepare for making measurements

    use "tonedef" in rchc.config to store hash of a combination of phase,atten,freq, and lo_freq
    to save time from reloading again.
    """

    rchc.loadFreq()

    loFreq = int(rchc.config.getfloat(rchc.roachString,'lo_freq'))
    a = rchc.roachController.freqList
    b = loFreq*(rchc.roachController.phaseOffsList + rchc.roachController.attenList)
    m1 = hashlib.md5()
    m1.update(a/b)
    thisTonedef = m1.hexdigest()
    if thisTonedef != getTonedef(rchc): 
        rchc.defineRoachLUTs()
        rchc.defineDacLUTs()
        rchc.config.set(rchc.roachString, "tonedigest", thisTonedef)
        #rchc.loadFIRs() moved to init
    else:
        print "already loaded:  tonedef =",thisTonedef
    attenVals = rchc.roachController.attenVal
    for iAtten in attenVals.keys():
        if attenVals[iAtten] is None:
            rchc.roachController.changeAtten(iAtten, 0)
        
    return rchc

def loadFIRs(rchc):
    rchc.loadFIRs()


def performIQSweep(rchc, saveToFile=None, doLoopFit=True, verbose=False):
    """

    Returns:  iqData, a dictionary of IQ data and parameters defining the sweep.

    if doLoopFit is True:
    'loopFits' -- an array of the loopFit for each frequency.
    
    each loopFit is from LoopFitter.loopFitter, a dictionary of:
      'fValues' -- data frequency values, in Hz
      'iValues' -- data I values, in ADUs
      'qValues' -- data Q values, in ADUs
      'guess'   -- the starting guess used for the fit
      'nsq'     -- the result of least_squares imported from scipy.optimize
      'fFit'    -- fit frequencies, nFit=2000 values, 10% larger than range of fValues
      'iFit'    -- I values from the fit parameters stored in 'nsq'.x
      'qFit'    -- I values from the fit parameters stored in 'nsq'.x
      'fpgaCenters' -- from readCenters(rchc)
    """
    LO_freq = rchc.roachController.LOFreq
    LO_span = rchc.config.getfloat(rchc.roachString,'sweeplospan')
    LO_step = rchc.config.getfloat(rchc.roachString,'sweeplostep')
    if verbose: print "in clTools.performIQSweep:  LO_span=",LO_span, "LO_step=",LO_step, LO_span/LO_step
    LO_offset = float(rchc.config.get(rchc.roachString,'sweeplooffset',
                                      vars={"sweeplooffset":"0.0"}))
    LO_start = LO_freq - LO_span/2. + LO_offset
    LO_end = LO_freq + LO_span/2. + LO_offset
    if verbose:
        print "in clTools.performIQSweep:  call rchc.roachController.performIQSweep"


    iqData = rchc.roachController.performIQSweep(LO_start/1.e6,
                                                 LO_end/1.e6,
                                                 LO_step/1.e6,
                                                 verbose=False)
     
    if verbose: print "in clTools.performIQSweep:  back from rchc.roachController.performIQSweep"
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
    iqData['dacPhaseList'] = rchc.roachController.dacPhaseList
    iqData['centers'] = calculateCenters(iqData['I'],iqData['Q'])
    iqData['fpgaCenters'] = readCenters(rchc)
    if saveToFile is not None:
        if verbose: print "save to file"
        saveIQSweepToFile(rchc, iqData, saveToFile)

    if doLoopFit:
        iqData['loopFits'] = []
        freqOffset = iqData['freqOffsets'] # Is it there?
        for iFreq in range(len(iqData['freqList'])):
            ia = iqData['I'][iFreq]
            qa = iqData['Q'][iFreq]
            freqList = iqData['freqList'][iFreq]
            freqs = freqList + freqOffset
            if verbose: print "in clTools.performIQSweep:  call loopFitter iFreq =",iFreq
            
            loopFit = LoopFitter.loopFitter(freqs, ia, qa, nFit=2000)
            if verbose: print "in clTools.performIQSweep:  done loopFitter iFreq =",iFreq
            iqData['loopFits'].append(loopFit)
    if verbose: print "in clTools.performIQSweep:  return"

    # Store IQ data in RoachController object. This is necessary because
    # subsequent operations using the RoachController object (e.g. rotateLoops)
    # assume that the results of the IQ sweep are data members of the
    # RoachController instance.
    rchc.recentIQData = iqData

    return iqData

def concatenateSweepNew(iqData, continuouseIQ=True):
    freqList = iqData['freqList']
    lenFreqList = len(freqList)
    deltaFreqList = freqList[1:]-freqList[:-1]
    loStep = iqData['LO_step']
    nStep = int(deltaFreqList.max()/loStep)
    nOverlap = len(iqData['I'][0])-nStep
    print "loStep =",loStep
    retval = {}
    return retval

def concatenateSweep(iqData, continuousIQ=True):
    """
    Repackage sweep data taken with a comb of frequencies.

    Return:  dictionary, with keys "freqs", "I", and "Q", in addtion to other values 
    copied from iqData
    """
    freqList = iqData['freqList']
    lenFreqList = len(freqList)
    deltaFreqList = freqList[1:]-freqList[:-1]
    loStep = iqData['LO_step']
    nStep = int(deltaFreqList.max()/loStep)
    nOverlap = len(iqData['I'][0])-nStep
    print "clTools.concatenateSweep:  nStep =",nStep, "     nOverlap =",nOverlap
    for i in range(len(freqList)):
        iData = iqData['I'][i]
        if len(iqData['I'][i])-nStep != nOverlap:
            tuple = (nStep,nOverlap,i,len(iqData['I'][i]))
            msg = "nStep=%d nOverlap=%d not consistent with i=%d len(iqData['I'][i])=%d"%tuple
            raise ValueError(msg)
    nValues = (nStep-nOverlap)*lenFreqList
    freqs = np.zeros(nValues)
    iValues = np.zeros(nValues)
    qValues = np.zeros(nValues)
    freqOffsets = iqData['freqOffsets']
    edges = np.zeros(len(freqList)+1)
    for iFreq,freq in enumerate(freqList):
        edges[iFreq] = freqList[iFreq]+freqOffsets[0]-loStep/2.0
        iv0 = iFreq*(nStep-nOverlap)
        iv1 = (iFreq+1)*(nStep-nOverlap)
        freqs[iv0:iv1] = freqList[iFreq]+freqOffsets[:(nStep-nOverlap)]
        iValues[iv0:iv1] = iqData['I'][iFreq][:(nStep-nOverlap)]
        qValues[iv0:iv1] = iqData['Q'][iFreq][:(nStep-nOverlap)]
    edges[-1] = freqList[-1]+freqOffsets[-1]+loStep/2.0
    if continuousIQ:
        if lenFreqList > 1:
            for iFreq in range(1,lenFreqList):
                iv0 = iFreq*nStep
                iValues[iv0:-1] += iValues[iv0-1]-iValues[iv0]
                qValues[iv0:-1] += qValues[iv0-1]-qValues[iv0]
    retval = {"freqs":freqs, "edges":edges}
    for k in iqData.keys():
        if k=="I":
            retval["I"] = iValues
        elif k=="Q":
            retval["Q"] = qValues
        else:
            retval[k] = iqData[k]
    return retval
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
    for iFreq,f0 in enumerate(freqList):
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

def tail(filepath):
    """
    Utility function to read the last line of a file
    """
    with open(filepath, "rb") as f:
        first = f.readline()      # Read the first line.
        f.seek(-2, 2)             # Jump to the second last byte.
        while f.read(1) != b"\n": # Until EOL is found...
            try:
                f.seek(-2, 1)     # ...jump back the read byte plus one more.
            except IOError:
                f.seek(-1, 1)
                if f.tell() == 0:
                    break
        last = f.readline()       # Read last line.
    return last

def getDewarTemperature(cryoBossDir="/mnt/ppd-115696/log"):
    """
    Find the most recently modified file in cryoBossDir.  Read the last line.
    Assume that it is a CryoBoss csv file.  The datetime string is in position 0 and 
    the temperature is in position 3. 

    Input:  cryoBossDir, defaults to mount location on cmbadr at Fermilab
    
    Ouput:  dictionary with keys "timestamp" and "faat"
    """
    retval = {"timestamp":None, "faat":None}
    try:
        newestFile = max(glob.iglob(cryoBossDir+"/*"), key=os.path.getmtime)
    except ValueError:
        raise SystemError("perhaps you need to mount cryoBossDir with sudo mount -t cifs //ppd-115696.dhcp.fnal.gov/CryoBoss /mnt/ppd-115696 -o credentials=/home/stoughto/credentials.txt")
    lastLine = tail(newestFile)
    lll = lastLine.split(",")
    retval['timestamp'] = dateutil.parser.parse(lll[0])
    retval['faat'] = float(lll[3])
    return retval

def getNewestDewarFile(globString="*", cryoBossDir="/mnt/ppd-115696/log"):
    newestFile = max(glob.iglob(cryoBossDir+"/*"), key=os.path.getmtime)
    return newestFile
    
def getTonedef(rchc):
    try:
        return rchc.config.get(rchc.roachString, "tonedigest",0)
    except ConfigParser.NoOptionError:
        return ""

def setTones(rchc, freqListIn = np.array([5.81e9]),
             fullScaleFraction=0.95):
    """
    For the set of frequencies, calculate the attenuations that will
    use fullScaleFraction of the dynamic range, and load the look up
    tables.

    Use the config parameter roachString, 'tonedigest' to store a has of the input values
    for convenience; no need to reload them

    """
    retval = {}
    retval['tBegin'] = datetime.datetime.now()

    if not isinstance(freqListIn, np.ndarray):
        freqListIn = np.array(freqListIn)
    m1 = hashlib.md5()
    loFreq = int(rchc.config.getfloat(rchc.roachString,'lo_freq'))
    m1.update((1.0+fullScaleFraction)*freqListIn/loFreq)
    thisTonedef = m1.hexdigest()
    
    if thisTonedef != getTonedef(rchc):
        # mimic what is done in rchc.loadFreq()
        resIDs = np.arange(len(freqListIn), dtype=np.float)
        freqs = np.array(freqListIn)
        resAttenList = np.zeros(len(freqs))
        phaseOffsList = np.zeros(len(freqs))
        iqRatioList = np.ones(len(freqs))
        rchc.roachController.generateResonatorChannels(freqs)
        rchc.roachController.resIDs = resIDs
        rchc.roachController.phaseOffsList = phaseOffsList
        rchc.roachController.iqRatioList = iqRatioList

        # Test run on Roach2Controls.generateTones to calculate attenuations to use full scale
        nBitsPerSampleComponent = rchc.roachController.params['nBitsPerSamplePair']/2
        maxAmp = int(np.round(2**(nBitsPerSampleComponent - 1)-1))       # 1 bit for sign
        rchc.roachController.freqList = freqListIn
        # do not set phaseList so random phases will be generated
        rchc.iqRatioList = np.ones(len(freqListIn))
        rchc.iqPhaseOffsList = np.zeros(len(freqListIn))
        loFreq = int(rchc.config.getfloat(rchc.roachString,'lo_freq'))
        rchc.roachController.setLOFreq(loFreq)
        rchc.roachController.verbose = False # True to get some info from generateDacComb
        globalDacAtten = -20*np.log10(len(freqs))-3
        dacComb = rchc.roachController.generateDacComb(
            globalDacAtten = globalDacAtten,
            resAttenList = resAttenList)
        highestValue = max(np.abs(dacComb['I']).max(),np.abs(dacComb['Q']).max())
        gain = float(fullScaleFraction)*maxAmp/highestValue
        gainDb = 20*np.log10(gain)
        resAttenList -= gainDb
        globalDacAtten -= gainDb
        try:
            dacComb = rchc.roachController.generateDacComb(
                globalDacAtten = globalDacAtten,
                resAttenList = resAttenList)
        except ValueError, argument:
            print "HELLO THERE"
            print "argument =",argument
            newGlobalDacAtten = np.floor(4*float(argument.split()[-1]))/4.0
            raise ValueError("globalDacAtten=%f,newGlobalDacAtten=%f"%(globalDacEtten,newGlobalDacAtten))
        
        highestValue = max(np.abs(dacComb['I']).max(),np.abs(dacComb['Q']).max())
        rchc.roachController.verbose = False

        # mimic what is done in rchc.defineRoachLUTs()
        rchc.roachController.generateFftChanSelection()
        ddsTones = rchc.roachController.generateDdsTones()
        print "from clTools: RoachConnection.defineRoachLUTs:  call loadChanSelection"
        rchc.roachController.loadChanSelection()
        print "from clToosl: RoachConnection.defineRoachLUTs:  call loadDdsLUT"
        rchc.roachController.loadDdsLUT()

        try:
            adcAtten = rchc.config.getfloat(rchc.roachString,'adcatten')
        except ConfigParser.NoOptionError:
            adcAtten = 26.75
            rchc.config.set(rchc.roachString,'adcatten',str(adcAtten))
        print "Initializing ADC/DAC board communication"
        rchc.roachController.initializeV7UART()
        print "Setting Attenuators"
        dacAtten1 = dacAtten2 = 0
        rchc.roachController.changeAtten(1,dacAtten1)
        rchc.roachController.changeAtten(2,dacAtten2)
        rchc.roachController.changeAtten(3,adcAtten)
        print "Setting LO Freq"
        rchc.roachController.loadLOFreq()
        print "Loading DAC LUT"
        rchc.roachController.loadDacLUT()
        rchc.config.set(rchc.roachString, "tonedigest", thisTonedef)
        dacPercent = 100*highestValue/maxAmp
        rchc.config.set(rchc.roachString, "dacPercent", str(dacPercent))
    retval['tonedef'] = thisTonedef
    retval['tEnd'] = datetime.datetime.now()
    return retval

def showTones(rchc):
    freqList = rchc.roachController.freqList
    dacPhaseList = rchc.roachController.dacPhaseList
    attenList = rchc.roachController.attenList
    for i,freq,phase,atten in zip(range(len(freqList)),
                                        freqList, dacPhaseList, attenList):
        print i,freq,phase,atten

def setupAndSweep(roachNumber, configFile, nSweep=1):
    rchc = connect(roachNumber, configFile)
    root,ext = os.path.splitext(configFile)
    outputFileName = "iq-%s-%s.pkl"%(root,time.strftime("%Y%m%d-%H%M%S"))
    print "ofn =",outputFileName
    t0 = datetime.datetime.now()
    print "begin setup with t0 = ",t0
    setup(rchc)
    t1 = datetime.datetime.now()
    print "finished setup with t1 = ",t1
    for iSweep in range(nSweep):
        iqData = performIQSweep(rchc,  doLoopFit=False)
        t2 = datetime.datetime.now()
        print "finished sweep with t2 =",t2
        pickle.dump(iqData, open(outputFileName, 'wb'))


def rotateLoops(rchc, nIQPoints = 100):
    # Copy logic from RoachStateMachine.rotateLoops
    # This presumes that self.sweep() was already called, which sets self.centers
    # by calling fitLoopCeneter.
    # In clTools, this is stored in recentIQData['centers'] calculated in a similar way,
    # when performIQSweep was called.
    '''
    Rotate loops so that the on resonance phase=0
    nIQPoints = 100     #arbitrary number. 100 seems fine. Could add this to config file in future

    NOTE: We rotate around I,Q = 0. Not around the center of the loop
          When we translate after, we need to resweep

    Find rotation phase
        - Get average I and Q at resonant frequency
    Rewrite the DDS LUT with new phases

    OUTPUTS:
        dictionary with keywords:
        IonRes - The average I value on resonance for each resonator
        QonRes - The average Q value on resonance for each resonator
        rotation - The rotation angle for each resonator before phasing the DDS LUT
    '''

    if not hasattr(rchc, 'recentIQData'):
        raise AttributeError(
            "rchc does not have recentIQData.  Call clTools.performIQSweep(rchc)")
    averageIQ = rchc.roachController.takeAvgIQData(nIQPoints)
    avg_I = np.average(averageIQ['I'],1) - rchc.recentIQData['centers'][:,0]
    avg_Q = np.average(averageIQ['Q'],1) - rchc.recentIQData['centers'][:,1]
    rotation_phases = np.arctan2(avg_Q,avg_I)

    phaseList = np.copy(rchc.roachController.ddsPhaseList)
    channels, streams = rchc.roachController.getStreamChannelFromFreqChannel()
    for i in range(len(channels)):
        if rchc.verbose:
            print "i =",i," channels[i]=",channels[i]," streams[i]=",streams[i]
            print "   ","rotation_phases[i] =",rotation_phases[i]
        phaseList[channels[i],streams[i]] = phaseList[channels[i],streams[i]] + rotation_phases[i]


    rchc.roachController.generateDdsTones(phaseList=phaseList)
    rchc.roachController.loadDdsLUT()

    return {'IonRes':np.copy(averageIQ['I']),
            'QonRes':np.copy(averageIQ['Q']),
            'rotation':np.copy(rotation_phases)}

def translateLoops(rchc):
    '''
    This function loads the IQ loop center into firmware, 
    taken from rchc.recentIQData['centers']
    '''
    if not hasattr(rchc, 'recentIQData'):
        raise AttributeError(
            "rchc does not have recentIQData.  Call clTools.performIQSweep(rchc)")
    centers = rchc.recentIQData['centers']
    print "clTools.translateLoops:  centers=",centers
    rchc.roachController.loadIQcenters(centers)
    
def calculateCenters(I,Q):
    '''
    Finds the (I,Q) center of the loops
    returns np array of centers:  centers - [nFreqs, 2]

    Logic copied from RoachStateMachine.fitLoopCenters
    '''
    
    I_centers = (np.percentile(I,95,axis=1) + np.percentile(I,5,axis=1))/2.
    Q_centers = (np.percentile(Q,95,axis=1) + np.percentile(Q,5,axis=1))/2.
    centers = np.transpose([I_centers.flatten(), Q_centers.flatten()])
    return centers

def readCenters(rchc):
    """
    Ask the fpga to return the centers it is using
    """
    channels, streams = rchc.roachController.getStreamChannelFromFreqChannel()
    centers = np.empty((len(channels),2))
    for i,(ch,stream) in enumerate(zip(channels, streams)):
        center = rchc.roachController.fpga.read_int(rchc.roachController.params['iqCenter_regs'][stream])
        Q_c = 8*(center & (2**16-1))
        I_c = 8*(center >> 16)
        centers[i,:] = (I_c,Q_c)
    return centers
        
def takeAvgIQData(rchc, numPts = 100, verbose=True):
    # Copy logic in Roach2Controls.takeAvgIQData
        """
        Take IQ data with the LO fixed (at self.LOFreq)
        This collects samples at approximately 10 Hz.
        INPUTS:
            numPts - Number of IQ points to take 
        
        OUTPUTS:
            iqData - Dictionary with following keywords
              I - 2D array with shape = [nFreqs, numPts]
              Q - 2D array with shape = [nFreqs, numPts]
              timestamps - time of each sample = [numPts]
        """
        
        nStreams = rchc.roachController.params['nChannels']/rchc.roachController.params['nChannelsPerStream']
        iqData = np.empty([nStreams,0])
        rchc.roachController.fpga.write_int(rchc.roachController.params['iqSnpStart_reg'],0)        
        iqPt = np.empty([nStreams,rchc.roachController.params['nChannelsPerStream']*4])
        timestamps = np.empty(numPts, dtype='datetime64[us]')
        for i in range(numPts):
            timestamps[i] = np.datetime64(datetime.datetime.now())
            if verbose:
                print timestamps[i],'IQ point #' + str(i)
            if(i%2==0):
                for stream in range(nStreams):
                    rchc.roachController.fpga.snapshots[rchc.roachController.params['iqSnp_regs'][stream]].arm(man_valid = False, man_trig = False) 
            rchc.roachController.fpga.write_int(rchc.roachController.params['iqSnpStart_reg'],1)
            time.sleep(0.001)    # takes nChannelsPerStream/fpgaClockRate seconds to load all the values
            if(i%2==1):
                for stream in range(nStreams):
                    iqPt[stream]=rchc.roachController.fpga.snapshots[rchc.roachController.params['iqSnp_regs'][stream]].read(timeout = 10, arm = False)['data']['iq']
                iqData = np.append(iqData, iqPt,1)
            rchc.roachController.fpga.write_int(rchc.roachController.params['iqSnpStart_reg'],0)
        
        # if odd number of steps then we still need to read out half of the last buffer
        if numPts % 2 == 1:
            rchc.roachController.fpga.write_int(rchc.roachController.params['iqSnpStart_reg'],1)
            time.sleep(0.001)
            for stream in range(nStreams):
                iqPt[stream]=rchc.roachController.fpga.snapshots[rchc.roachController.params['iqSnp_regs'][stream]].read(timeout = 10, arm = False)['data']['iq']
            iqData = np.append(iqData, iqPt[:,:rchc.roachController.params['nChannelsPerStream']*2],1)
            rchc.roachController.fpga.write_int(rchc.roachController.params['iqSnpStart_reg'],0)

        retval = rchc.roachController.formatIQSweepData(iqData)
        retval['timestamps'] = timestamps
        return retval
    

def getPhaseStream(rchc, channel, duration=2):
    """
Continuously observes the phase stream for a given amount of time

INPUTS:
    channel - the i'th frequency in the frequency list
    time - [seconds] the amount of time to observe for
Return:
    dictionary of:
    data - list of phase in radians; collected at ~ 1MHz
    channel - requested channel
    resID - resonator ID of the requested channel
    duration - requested duration
    t0 -- datetime.datetime.now() at start
    t1 -- datetime.datetime.now() at end
    """
    resID = rchc.roachController.resIDs[channel]
    ipaddress = rchc.config.get(rchc.roachString, 'ipaddress')
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((ipaddress,80))
    hostip = s.getsockname()[0]
    port = int(rchc.config.get(rchc.roachString,'port'))
    t0 = datetime.datetime.now()
    data=rchc.roachController.takePhaseStreamDataOfFreqChannel(freqChan=channel,
                                                               duration=duration,
                                                               hostIP=hostip,
                                                               fabric_port=port)
    t1 = datetime.datetime.now()
    retval = {"data":data, "t0":t0, "t1":t1, "duration":duration, "resID":resID}
    retval['attenVal'] = rchc.roachController.attenVal
    retval['faat'] = getDewarTemperature()['faat']    
    return retval

def getTwoSnapshots(rchc):
    # Copy guts of the logic in Roach2Controls.performIQSweep
    fpga = rchc.roachController.fpga
    params = rchc.roachController.params
    nChannels = params['nChannels']
    nChannelsPerStream = params['nChannelsPerStream']
    nStreams = nChannels/nChannelsPerStream
    
    retval = []

    # first time through "for i in range(len(LOFreqs))"
    for stream in range(nStreams):
        fpga.snapshots[params['iqSnp_regs'][stream]].arm(man_valid=False, man_trig=False)
    
    fpga.write_int(params['iqSnpStart_reg'],1)
    time.sleep(0.001)
    fpga.write_int(params['iqSnpStart_reg'],0)

    # second time through "for i in range(len(LOFreqs))"
    fpga.write_int(params['iqSnpStart_reg'],1)
    time.sleep(0.001)
    for stream in range(nStreams):
        ss = fpga.snapshots[params['iqSnp_regs'][stream]].read(timeout=10, arm=False)
        retval.append(ss)
    fpga.write_int(params['iqSnpStart_reg'],0)

    return retval

def snapZdokToFile(rchc, fileNameBase):
    x = rchc.roachController.snapZdok()
    keys = x.keys()
    keys.sort()
    for key in keys:
        fn = "%s-%s.csv"%(fileNameBase,key)
        print "now write ",fn                                            
        with open(fn,'wb') as handle:
            for i,v in enumerate(x[key]):
                line = "%d,%s\n"%(i,str(v))
                handle.write(line)

def iqPeakFinder(iqData, thresholdFraction=0.3):
    I = np.array(iqData['I'])
    Q = np.array(iqData['Q'])
    fo = np.array(iqData['freqOffsets'])
    freqList = np.array(iqData['freqList'])
    
    print "I", I.shape
    print "fo",fo.shape
    print "freqList",freqList.shape
    amps = np.empty(I.shape)
    phases = np.empty(I.shape)
    fas = np.empty(I.shape)
    for iFreq,freq in enumerate(freqList):
        fa = freq + fo
        fas[iFreq,:] =  fa
        ia = I[iFreq, :]
        qa = Q[iFreq, :]
        ff,v,amps[iFreq,:],phases[iFreq,:] = LoopFitter.getFVAP(fa,ia,qa)
        #print iFreq,fa[0],fa[1],fa[-1]
    for iFreq0 in range(len(freqList)-1):
        iFreq1 = iFreq0+1
        xMax = fas[iFreq0,:].max()
        xMin = fas[iFreq1,:].min()
        a0Mean = amps[iFreq0,fas[iFreq0,:]>=xMin].mean()
        a1Mean = amps[iFreq1,fas[iFreq1,:]<=xMax].mean()
        amps[iFreq1,:] *= a0Mean/a1Mean
    fMin = fas[0,0]
    df = iqData['LO_step']
    fMax = fas[-1,-1]+df
    print fMin,df,fMax
    nBins = int((fMax-fMin)/df)
    print "nBins =",nBins
    aSum = np.zeros(nBins)
    fSum = np.zeros(nBins)
    nSum = np.zeros(nBins)
    for iFreq in range(len(freqList)):
        for iSample,f in enumerate(fas[iFreq,:]):
            iBin = int((f-fMin)/df)
            nSum[iBin] += 1
            fSum[iBin] += f
            aSum[iBin] += amps[iFreq,iSample]
    fAvg = fSum/nSum
    aAvg = aSum/nSum
    y = aAvg
    y = (y.max()-y)
    hMin = thresholdFraction * y.max()
    peaks,_ = find_peaks(y, height=hMin)
    return fAvg[peaks]

def takeSomeData(rchc, nStep, baseName, channel=0, duration=10):

    if baseName is not None:
        iqFileName = "%s-iq.pkl"%(baseName)
        if os.path.exists(iqFileName):
            raise OSError("File exists %s"%iqFileName)
        print "do initial sweep"
        loSpanKHz = 1500.0
        loStepKHz = 40.0
        loOffsetHz = 0
        rchc.config.set(rchc.roachString, "sweeplospan",str(loSpanKHz*1e3))
        rchc.config.set(rchc.roachString, "sweeplostep",str(loStepKHz*1e3))
        rchc.config.set(rchc.roachString, "sweeplooffset",str(loOffsetHz))
        performIQSweep(rchc)
        pickle.dump(rchc.recentIQData, open(iqFileName,'wb'))

    t0Prev = None
    for iStep in range(nStep):
        if baseName is not None:
            streamFileName = "%s-%05d.pkl"%(baseName,iStep)
            print streamFileName
            if os.path.exists(streamFileName):
                raise OSError("File exists %s"%streamFileName)
        streamData = getPhaseStream(rchc, channel=channel, duration=duration)
        t0 = streamData['t0']
        if t0Prev is not None:
            d = (t0-t0Prev).total_seconds()
            print iStep, d
        t0Prev = t0
        if baseName is not None:
            pickle.dump(streamData, open(streamFileName,'wb'))


def setAllThresholds(rchc,threshold=0.0):
    nfreqs = len(rchc.roachController.freqList)
    for i in range(nfreqs):
        rchc.roachController.setThreshByFreqChannel(threshold,i)

def loadBeammapCoords(rchc, xCoordOffset=10, yCoordConstant=12):
    """
                beammapDict contains:
                'freqCh' : list of freqCh of resonators.    (index in frequency list)
                'xCoord' : list of x Coordinates
                'yCoord' : list of y Coords
    """
    beammapDict = {'freqCh':[], 'xCoord':[], 'yCoord':[]}
    for iFreq in range(len(rchc.roachController.freqList)):
        beammapDict['freqCh'].append(iFreq)
        beammapDict['xCoord'].append(iFreq+xCoordOffset)
        beammapDict['yCoord'].append(yCoordConstant)
    rchc.roachController.loadBeammapCoords(beammapDict)
    return beammapDict

def turnOffPhotonCapture(rchc):
    """
    Tells the roach to stop photon capture
    """
    roach = rchc.roachController
    roach.fpga.write_int(rchc.config.get('properties','photonCapStart_reg'),0)

def turnOnPhotonCapture(rchc):
    """
    Tells roaches to start photon capture

    Have to be careful to set the registers in the correct order in case we are currently in phase capture mode
    """

    # set up ethernet parameters
    hostIP = rchc.config.get('properties','hostIP')
    dest_ip = binascii.hexlify(inet_aton(hostIP))
    dest_ip = int(dest_ip,16)

    roach = rchc.roachController
    roach.fpga.write_int(rchc.config.get('properties','destIP_reg'),dest_ip)
    roach.fpga.write_int(rchc.config.get('properties','photonPort_reg'),
                         rchc.config.getint('properties','photonCapPort'))
    roach.fpga.write_int(rchc.config.get('properties','wordsPerFrame_reg'),
                         rchc.config.getint('properties','wordsPerFrame'))

    # restart gbe
    roach.fpga.write_int(rchc.config.get('properties','photonCapStart_reg'),0)
    roach.fpga.write_int(rchc.config.get('properties','phaseDumpEn_reg'),0)
    roach.fpga.write_int(rchc.config.get('properties','gbe64Rst_reg'),1)
    time.sleep(.01)
    roach.fpga.write_int(rchc.config.get('properties','gbe64Rst_reg'),0)

    # Start photon caputure
    roach.fpga.write_int(rchc.config.get('properties','photonCapStart_reg'),1)
    print rchc.roachString,'Sending Photon Packets!'

def fpgaStreamToPkl(baseFileName='fpgaStream',nFrames=1000, unpack=True):
    rfs = ReceiveFPGAStream.ReceiveFPGAStream()
    dtn = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    if baseFileName is not None:
        pfn = "%s-%s-%d.pkl"%(baseFileName,dtn,unpack)
        pickleHandle = open(pfn, 'wb')
    else:
        pfn = None
        pickleHandle = None
    dt = 0
    for i in range(nFrames):
        print "%d/%d"%(i,nFrames)
        data = rfs.read()
        if unpack:
            rv = rfs.unpack(data)
        else:
            rv = data
        if pickleHandle is not None:
            pickle.dump(rv,pickleHandle)
        else:
            pass
    return pfn

def fpgaToScreen(nFrames=1, npToPrint=0, readValid=False, frameHeader=True ):
    rfs = ReceiveFPGAStream.ReceiveFPGAStream()
    tPrev = None
    for i in range(nFrames):
        if readValid: print "%d/%d"%(i,nFrames),
        data = rfs.read()
        rv = rfs.unpack(data)
        if readValid: print rv['valid']
        if rv['valid']:
            # Keys are: ['frame', 'packets', 'tag', 'starttime', 'roach', 'valid']
            p = rv['packets']
            np = rv['packets'].shape[0]
            if tPrev is not None:
                dt = rv['starttime'] - tPrev
            else:
                dt = -1
            tPrev = rv['starttime']
            if frameHeader:
                print "frame=%5d starttime=%d dt=%5d roach=%d np=%d nBytesRead=%d"%(rv['frame'],rv['starttime'],dt,rv['roach'],np,len(data))
            for ip in range(npToPrint):
                try:
                    row = p[ip,:]
                    usec = row[5]
                    xc = row[4]
                    yc = row[3]
                    ts = row[2]
                    wvl = row[1]
                    bse = row[0]
                    print "ip=%3d   xc=%2d   yc=%2d   ts=%3d   usec=%5d  baseline=%d"%(ip,xc,yc,ts,usec, bse)
                except:
                    print "out of range"
        
def phasesIntToDouble(phasesIn, nBitsPerPhase=12, binPtPhase=9):
    # Logic copied from Roach2Controls.py
    phases = np.copy(phasesIn) 
    bitmask = int('1'*nBitsPerPhase,2)
    phases = phases & bitmask      
    signBits = np.array(phases / (2**(nBitsPerPhase-1)),dtype=np.bool)
    phases[signBits] = ((~phases[signBits]) & bitmask)+1 # Deal with twos complement
    phases = np.array(phases,dtype=np.double)
    phases[signBits] = -phases[signBits]
    phases /= 2**binPtPhase
    return phases

def setMaxCountRate(rchc, maxCountRate=10000):
    rchc.roachController.setMaxCountRate(maxCountRate)
    
