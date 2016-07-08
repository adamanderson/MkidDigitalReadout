"""
AUTHOR: Alex Walter
DATE: May 15, 2016

The RoachStateMachine class runs the commands on the readout boards. Uses Roach2Controls Class
"""
import os, sys, time, random
import numpy as np
from PyQt4 import QtCore
from Queue import Queue
from Roach2Controls import Roach2Controls
from lib import iqsweep  # From old SDR code for saving powersweep files

class RoachStateMachine(QtCore.QObject):        #Extends QObject for use with QThreads
    """
    This class defines and executes commands on the readout boards using the Roach2Controls object.
    All the important stuff happens in the executeCommand() function
    
    command enums are class variables
        0 - CONNECT
        1 - LOADFREQ
        2 - etc...
    ie.. RoachStateMachine.CONNECT = 0
         RoachStateMachine.parseCommand(0) = 'Connect'
    
    Commands are encoded as ints and loaded into a queue. The RoachThread pops the command and tells the RoachStateMachine to execute it.
    
    The 'state' attribute contains information about the state of the roach for each command.
    For example. self.state=[2, 2, 1, 1, 0, 0, 0, 0] means that the roach succesfully completed connect, loadFreq commands, and is currently working on DefineLUT and sweep. 
    State enums are class variables
        0 - UNDEFINED
        1 - INPROGRESS
        2 - COMPLETED
        3 - ERROR
    ie.. RoachStateMachine.COMPLETED=2
         RoachStateMachine.parseState(2)='Completed'
    
    TODO:
        uncomment everything in executeCommand()
    """
    #FINISHED_SIGNAL = QtCore.SIGNAL("finishedCommand(int,PyQt_PyObject)")
    #ERROR_SIGNAL = QtCore.SIGNAL("commandError(int,PyQt_PyObject)")
    finishedCommand_Signal = QtCore.pyqtSignal(int,object)
    commandError_Signal = QtCore.pyqtSignal(int,tuple)
    finished = QtCore.pyqtSignal()
    reset = QtCore.pyqtSignal(object)
    
    snapPhase = QtCore.pyqtSignal(int,object)
    timestreamPhase = QtCore.pyqtSignal(int,object)
    
    
    #NUMCOMMANDS = 8
    #CONNECT,LOADFREQ,DEFINELUT,SWEEP,ROTATE,CENTER,LOADFIR,LOADTHRESHOLD = range(NUMCOMMANDS)
    NUMCOMMANDS = 7
    CONNECT,LOADFREQ,DEFINELUT,SWEEP,FIT,LOADFIR,LOADTHRESHOLD = range(NUMCOMMANDS)
    NUMSTATES = 4
    UNDEFINED, INPROGRESS, COMPLETED, ERROR = range(NUMSTATES)
    
    @staticmethod
    def parseCommand(command):
        #commandsString=['Connect','Load Freqs','Define LUTs','Sweep','Rotate','Center','Load FIRs','Load Thresholds']
        commandsString=['Connect','Read Freqs','Define LUTs','Sweep','Fit Loops','Load FIRs','Load Thresholds']
        if command < 0:
            return 'Reset'
        return commandsString[command]
    @staticmethod
    def parseState(state):
        statesString=['Undefined', 'In Progress', 'Completed', 'Error']
        return statesString[state]
    
    def __init__(self, roachNumber, config):
        """
        INPUTS:
            roachNumber - 
            config - ConfigParser Object holding all the parameters needed
        """
        super(RoachStateMachine, self).__init__()
        self.state=[RoachStateMachine.UNDEFINED]*RoachStateMachine.NUMCOMMANDS    # This holds the state for each command type
        self.num=int(roachNumber)
        self.commandQueue=Queue()
        self.config=config
        
        
        FPGAParamFile = self.config.get('Roach '+str(self.num),'FPGAParamFile')
        ip = self.config.get('Roach '+str(self.num),'ipaddress')
        
        self.roachController = Roach2Controls(ip,FPGAParamFile,True,False)
    
    def addCommands(self,command):
        """
        This function adds the specified command and any other neccessary commands to the command queue.
        It also sets the state for each command correctly
        
        This is where the state machine logic comes into play. We check what state the roach is currently in, and decide what to do next. 
        ie. If we're currently only connected, but want to sweep, we need to first load freqs, define LUTs, then sweep. 
        
        The only tricky part is that we want to load FIRs only once or when explicitly asked
        
        INPUTS:
            command - the command we want to ultimately execute
            
        OUPUTS:
            self.state - the state for each command so the GUI can change the colors. (ie. the command will be in progress)
        """
        self.state = self.getNextState(command)
        for com in range(len(self.state)):
            if self.state[com] == RoachStateMachine.INPROGRESS:
                self.pushCommand(com)
        
        return self.state
    
    def getNextState(self,command,_n=0):
        """
        Given the current state and a command, determine the next state. This function is recursive. Don't change default value of _n
        
        NOTE: if command < 0 then it resets everything (with _n=0)
              if command >= RoachStateMachine.NUMCOMMANDS then it ensures every command is completed but doesn't redo any if they're already completed
        
        Inputs:
            command - the command we want to execute. ie. RoachStateMachine.loadThreshold
            _n - Internal parameter for recursion. Determines the level of recursion. External calls should always use default value
        
        Outputs:
            nextState - list of states for the roach. See self.state attribute
        """
        if _n > 100:
            raise ValueError("Too many recursions!")
        
        nextState = np.copy(self.state)
        
        if _n==0: # n==0 means this is the top level command
            if command<RoachStateMachine.CONNECT:
                return [RoachStateMachine.UNDEFINED]*RoachStateMachine.NUMCOMMANDS
                
            # Any previously unfinished commands should be made undefined
            args_unfinished = np.where(nextState==RoachStateMachine.INPROGRESS)
            nextState[args_unfinished] = RoachStateMachine.UNDEFINED
            if command>=RoachStateMachine.NUMCOMMANDS:
                #Make sure everything's completed but don't explicitly run anything if they already are
                command = RoachStateMachine.NUMCOMMANDS-1
                if nextState[command] != RoachStateMachine.COMPLETED: nextState[command] = RoachStateMachine.INPROGRESS
            else:
                #redo the command if explicitly asked
                nextState[command] = RoachStateMachine.INPROGRESS
            #usually higher commands become undefined (except loadFIR)
            args_above = np.where((np.arange(RoachStateMachine.NUMCOMMANDS)>command) & (np.arange(RoachStateMachine.NUMCOMMANDS) != RoachStateMachine.LOADFIR))
            if command==RoachStateMachine.CONNECT:
                args_above = []     #reconnecting shouldn't change anything
            elif command==RoachStateMachine.SWEEP:
                args_above = []     #resweeping shouldn't change anything
            nextState[args_above] = RoachStateMachine.UNDEFINED
        elif nextState[command] != RoachStateMachine.COMPLETED:
            # a lower command needs to be run only if it's not already completed
            nextState[command] = RoachStateMachine.INPROGRESS
        
        if command <= RoachStateMachine.CONNECT:
            #We've reached the bottom of the command list, so return
            return nextState
        
        if _n==0 and command == RoachStateMachine.LOADFIR:  #Special case
            # loading FIRs only requires connect, loadFreqs, and defineLUTs
            nextState[:RoachStateMachine.DEFINELUT+1] = self.getNextState(RoachStateMachine.DEFINELUT,_n+1)[:RoachStateMachine.DEFINELUT+1]
        else:
            # Everything else requires all lower commands be completed
            nextState[:command] = self.getNextState(command-1,_n+1)[:command]
        return nextState
    
    @QtCore.pyqtSlot()
    @QtCore.pyqtSlot(int)
    def resetStateTo(self,command=-1):
        """
        Reset the roach to the state given by command. ie. Pretend we just clicked command and so set higher commands as undefined. But leave the command in the current state
        
        command<0 resets everything
        
        INPUTS:
            command - command to reset state to
        """
        print "Resetting r"+str(self.num)+' to '+RoachStateMachine.parseCommand(command)
        self.state = self.getNextState(command)
        self.state[command]=RoachStateMachine.UNDEFINED
        self.reset.emit(self.state)
        self.finished.emit()
    
    @QtCore.pyqtSlot()
    def executeCommands(self):
        """
        Executes sequentially every command in the command Queue
        
        This slot function is called by a seperate thread from HighTemplar
        """
        while self.hasCommand():
            command=self.popCommand()
            try:
                commandData = self.executeCommand(command)
                #self.emit(RoachStateMachine.FINISHED_SIGNAL,command,commandData)
                self.finishedCommand_Signal.emit(command,commandData)
            except:
                exc_info = sys.exc_info()
                #self.emit(RoachStateMachine.ERROR_SIGNAL,command,exc_info)
                self.commandError_Signal.emit(command,exc_info)
                del exc_info    # if you don't delete this it may prevent garbage collection
        self.finished.emit()
    
    def connect(self):
        '''
        This function connects to the roach2 board and executes any initialization scripts
        '''
        #self.roachController.connect()
        ddsShift = self.config.getint('Roach '+str(self.num),'ddssynclag')
        #self.roachController.loadDdsShift(ddsShift)
        
        return True
    
    def loadFreq(self):
        '''
        Calculates everything we need to load into the LUTs on the Roach and ADC/DAC board
        '''
        loFreq = int(self.config.getfloat('Roach '+str(self.num),'lo_freq'))
        self.roachController.setLOFreq(loFreq)
        
        fn = self.config.get('Roach '+str(self.num),'freqfile')
        fn2=fn.rsplit('.',1)[0]+'_NEW.'+ fn.rsplit('.',1)[1]         # Check if ps_freq#_NEW.txt exists
        if os.path.isfile(fn2): fn=fn2
        freqs, attens = np.loadtxt(fn,unpack=True)
        
        self.roachController.generateResonatorChannels(freqs)
        self.roachController.generateFftChanSelection()
        
        dacAtten = self.config.getfloat('Roach '+str(self.num),'dacatten_start')
        self.roachController.generateDacComb(resAttenList=attens,globalDacAtten=dacAtten)
        self.roachController.generateDdsTones()
        
        return True
        
    def defineLUTs(self):
        '''
        Loads values into ROACH2, ADC/DAC, and IF boards
            DAC atten 1, 2
            ADC atten
            lo freq
            DAC LUT
            DDS LUT
        '''
        adcAtten = self.config.getfloat('Roach '+str(self.num),'adcatten')
        dacAtten = self.config.getfloat('Roach '+str(self.num),'dacatten_start')
        dacAtten1 = np.floor(dacAtten*2)/4.
        dacAtten2 = np.ceil(dacAtten*2)/4.
        #self.roachController.changeAtten(1,dacAtten1)
        #self.roachController.changeAtten(2,dacAtten2)
        #self.roachController.changeAtten(3,adcAtten)

        #self.roachController.loadLOFreq()
        
        #self.roachController.loadChanSelection()
        #self.roachController.loadDdsLUT()
        #self.roachController.loadDacLUT()
        
        return True
    
    def sweep(self):
        '''
        Run power sweep
        If multiple dac attenuation values are specified then we loop over them and save a power sweep file
        See SDR repository for power sweep info. It's uncommented so your guess is as good as mine.
        '''
        
        LO_freq = self.roachController.LOFreq
        LO_span = self.config.getfloat('Roach '+str(self.num),'sweeplospan')
        LO_start = LO_freq - LO_span/2.
        LO_end = LO_freq + LO_span/2.
        LO_step = self.config.getfloat('Roach '+str(self.num),'sweeplostep')
        start_DACAtten = self.config.getfloat('Roach '+str(self.num),'dacatten_start')
        stop_DACAtten = self.config.getfloat('Roach '+str(self.num),'dacatten_stop')
        '''
        powerSweepFile = self.config.get('Roach '+str(self.num),'powersweepfile')
        powerSweepFile = powerSweepFile.rsplit['.',1][0]+'_'+time.strftime("%Y%m%d-%H%M%S",time.localtime())+'.'+powerSweepFile.rsplit['.',1][1]
        for dacAtten in range(start_DACAtten, stop_DACAtten+1):
            iqData = self.roachController.performIQSweep(LO_start/1.e6, LO_end/1.e6, LO_step/1.e6)
            self.I_data = iqData['I']
            self.Q_data = iqData['Q']
            if stop_DACAtten > start_DACAtten:
                # Save the power sweep
                nSteps = len(iqData['I'][0])
                for n in range(len(self.roachController.freqList)):
                    w = iqsweep.IQsweep()
                    w.f0 = self.roachController.freqList[n]
                    w.span = LO_span/1e6
                    w.fsteps = nSteps
                    w.atten1 = self.roachController.attenList[n]
                    w.atten2 = 0
                    w.scale = 1.
                    w.PreadoutdB = -w.atten1 - 20*numpy.log10(w.scale)
                    w.Tstart = 0.100
                    w.Tend = 0.100
                    w.I0 = 0.0
                    w.Q0 = 0.0
                    w.resnum = n
                    w.freq = np.arange(LO_start, LO_end, LO_step, dtype='float32')/1.e9
                    w.I = iqData['I'][n]
                    w.Q = iqData['Q'][n]
                    w.Isd = np.zeros(nSteps)
                    w.Qsd = np.zeros(nSteps)
                    w.time = time.time()
                    w.savenoise = 0
                    w.Save(powerSweepFile,'r'+str(self.num), 'a')
        
        '''
        nfreqs = len(self.roachController.freqList)
        self.I_data = []
        self.Q_data = []
        nSteps = int(LO_span/LO_step)
        for i in range(nfreqs):
            theta = np.linspace(0.,1,nSteps)*2*np.pi
            I = np.cos(theta) + (np.random.rand(nSteps)-0.5)/10.
            Q = np.sin(theta) + (np.random.rand(nSteps)-0.5)/10.
            self.I_data.append(I)
            self.Q_data.append(Q)
        return {'I':self.I_data,'Q':self.Q_data}
    
    def fitLoops(self):
        '''
        Find the center
            - If centerbool is false then use the old center if it exists
        Upload center to ROACH2
        
        Find rotation phase
            - Get average I and Q at resonant frequency
        Rewrite the DDS LUT with new phases
        
        Sets self.centers
        '''
        recenter = self.config.getboolean('Roach '+str(self.num),'centerbool')
        if not hasattr(self, 'centers'): recenter = True
        if recenter: self.fitLoopCenters()
        
        #self.roachController TRANSLATE LOOPS
        
        nIQPoints = 100
        averageIQ = self.roachController.perfomIQ2(nIQPoints)
        avg_I = np.average(averageIQ['I'],1) - self.centers[:,0]
        avg_Q = np.average(averageIQ['Q'],1) - self.centers[:,1]
        rotation_phases = np.arctan2(avg_Q,avg_I)
        
        phaseList = np.copy(self.roachController.ddsPhaseList)
        for i in range(len(self.roachController.freqList)):
            arg = np.where(self.roachController.freqChannels == self.roachController.freqList[i])
            phaseList[arg]-=rotation_phases[i]
        
        self.roachController.generateDdsTones(phaseList=phaseList)
        #self.roachController.loadDdsLUT()
        
        return True
    
    def fitLoopCenters(self):
        '''
        Finds the (I,Q) center of the loops
        sets self.centers - [nFreqs, 2]
        '''
        I_centers = (np.amax(self.I_data,1) + np.amin(self.I_data,1))/2.
        Q_centers = (np.amax(self.Q_data,1) + np.amin(self.Q_data,1))/2.
        
        self.centers = np.transpose(I_centers.flatten(), Q_centers.flatten())
        
    def loadFIRs(self):
        firCoeffFile = self.config.get('Roach '+str(self.num),'fircoefffile')
        #self.roachController.loadFIRCoeffs(firCoeffFile)
        return True
    
    def loadThreshold(self):
        '''
        
        '''
        nfreqs = len(self.roachController.freqList)
        threshSig = self.config.getfloat('Roach '+str(self.num),'numsigs_thresh')
        nSnap = self.config.getint('Roach '+str(self.num),'numsnaps_thresh')
        thresh=[]
        for i in range(nfreqs):
            data=[]
            for k in range(nSnap):
                sys.stdout.write("\rCollecting Phase on Ch: "+str(i)+" Snap "+str(k+1)+'/'+str(nSnap))
                sys.stdout.flush()
                data.append(self.getPhaseFromSnap(i))
            thresh.append(np.std(data)*threshSig)
        #self.roachController.loadThresholds(thresh)
        sys.stdout.write("\n")
        self.roachController.thresholds=thresh
        return True
    
    def executeCommand(self,command):
        """
        Executes individual commands
        
        INPUTS:
            command
        """
        print "Roach ",self.num," Recieved/executing command: ",RoachStateMachine.parseCommand(command)
        self.state[command] = RoachStateMachine.INPROGRESS
        returnData = None
        time.sleep(random.randint(1,3))
        try:
            
            if command == RoachStateMachine.CONNECT:
                returnData = self.connect()
            elif command == RoachStateMachine.LOADFREQ:
                returnData = self.loadFreq()
            elif command == RoachStateMachine.DEFINELUT:
                returnData = self.defineLUTs()
            elif command == RoachStateMachine.SWEEP:
                returnData = self.sweep()
            elif command == RoachStateMachine.FIT:
                returnData = self.fitLoops()
            elif command == RoachStateMachine.LOADFIR:
                returnData = self.loadFIRs()
            elif command == RoachStateMachine.LOADTHRESHOLD:
                returnData = self.loadThreshold()
            else:
                raise ValueError('No command: '+str(command))
            self.state[command] = RoachStateMachine.COMPLETED
        except:
            self.emptyCommandQueue()
            self.state[command] = RoachStateMachine.ERROR
            raise
            
        return returnData
    
    @QtCore.pyqtSlot(int)
    def getPhaseFromSnap(self, channel):
        """
        This function grabs the phase timestream from the snapblock
        
        INPUTS:
            channel - the i'th frequency in the frequency list
        """
        print "r"+str(self.num)+" Getting phase snap"
        data=np.random.uniform(-.1,.1,200)+channel
        self.snapPhase.emit(channel,data)
        return data
    
    @QtCore.pyqtSlot(int,float)
    def getPhaseStream(self, channel, timelen=2):
        """
        This function continuously observes the phase stream for a given amount of time
        
        INPUTS:
            channel - the i'th frequency in the frequency list
            time - [seconds] the amount of time to observe for
        """
        print "r"+str(self.num)+" Collecting phase timestream"
        time.sleep(timelen)
        data=np.random.uniform(-.1,.1,timelen*10.**6)
        self.timestreamPhase.emit(channel,data)
        return data

    def hasCommand(self):
        return (not self.commandQueue.empty())
    def popCommand(self):
        if not self.commandQueue.empty():
            return self.commandQueue.get()
        else:
            return None
    def pushCommand(self,command):
        self.commandQueue.put(command)
    def emptyCommandQueue(self):
        while not self.commandQueue.empty():
            self.commandQueue.get()

