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
import ConfigParser, datetime, dateutil, glob, hashlib, logging, os, pickle, sys, time, timeit,warnings, socket
import numpy as np
import scipy.special
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
    return rchc

def loadFIRs(rchc):
    rchc.loadFIRs()


def performIQSweep(rchc, saveToFile=None, doLoopFit=True, verbose=False):
    """

    Returns:  iqData, a dictionary of
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

    """
    LO_freq = rchc.roachController.LOFreq
    LO_span = rchc.config.getfloat(rchc.roachString,'sweeplospan')
    LO_step = rchc.config.getfloat(rchc.roachString,'sweeplostep')
    if verbose: print "in clTools.performIQSweep:  LO_span=",LO_span, "LO_step=",LO_step, LO_span/LO_step
    LO_start = LO_freq - LO_span/2.
    LO_end = LO_freq + LO_span/2.
    if verbose: print "in clTools.performIQSweep:  call rchc.roachController.performIQSweep"
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
    
    if saveToFile is not None:
        if verbose: print "save to file"
        saveIQSweepToFile(rchc, iqData, saveToFile)
    
    if doLoopFit:
        iqData['loopFits'] = []
        freqOffset = iqData['freqOffsets']
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
    newestFile = max(glob.iglob(cryoBossDir+"/*"), key=os.path.getmtime)
    lastLine = tail(newestFile)
    lll = lastLine.split(",")
    retval['timestamp'] = dateutil.parser.parse(lll[0])
    retval['faat'] = float(lll[3])
    return retval

def getTonedef(rchc):
    try:
        return rchc.config.get(rchc.roachString, "tonedigest",0)
    except ConfigParser.NoOptionError:
        return ""

def setTones(rchc, freqListIn = np.array([5.81e9]), fullScaleFraction=0.95):
    """
    For the set of frequencies, calculate the attenuations that will
    use fullScaleFraction of the dynamic range, and load the look up
    tables.

    Use the config parameter roachString, 'tonedigest' to store a has of the input values
    for convenience; no need to reload them

    """
    retval = {}
    retval['tBegin'] = datetime.datetime.now()

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
        dacComb = rchc.roachController.generateDacComb(
            globalDacAtten = globalDacAtten,
            resAttenList = resAttenList)
        highestValue = max(np.abs(dacComb['I']).max(),np.abs(dacComb['Q']).max())
        rchc.roachController.verbose = False

        # mimic what is done in rchc.defineRoachLUTs()
        rchc.roachController.generateFftChanSelection()
        ddsTones = rchc.roachController.generateDdsTones()
        print "from clTools: RoachConnection.defineRoachLUTs:  call loadChanSelection"
        rchc.roachController.loadChanSelection()
        print "from clToosl: RoachConnection.defineRoachLUTs:  call loadDdsLUT"
        rchc.roachController.loadDdsLUT()


        adcAtten = rchc.config.getfloat(rchc.roachString,'adcatten')
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
    
    retval['freqList'] = rchc.roachController.freqList
    retval['attenList'] = rchc.roachController.attenList
    retval['phaseOffsList'] = rchc.roachController.phaseOffsList    
    retval['tEnd'] = datetime.datetime.now()
    return retval
