import datetime, time, os, socket
from PyQt4 import QtGui, uic
from PyQt4.QtCore import QThread, pyqtSignal, QTimer
import numpy as np
from collections import deque
from scipy.signal import welch
import sys
import WritePhaseData
reload(WritePhaseData)
import pdb
#import PlotProcessor
#reload(PlotProcessor)

Nevents=100000
roachData=False

dqs = deque()
dqToWriter = deque()
dqToProcessor = deque()

class PhasePlotWindow(QtGui.QMainWindow):
    signalToRoachReader = pyqtSignal(str)
    signalToWriter = pyqtSignal(str)
    signalToStreamer = pyqtSignal(str)
    signalToProcessor = pyqtSignal(dict)
    
    def __init__(self, rc):
        super(PhasePlotWindow,self).__init__()
        self.rc = rc
        thisDir = os.path.dirname(os.path.abspath(__file__))
       # uic.loadUi('PhasePlotWidget.ui', self)
        uic.loadUi(os.path.join(thisDir,'PhasePlotWidget.ui'), self)
        self.topPlot =    self.graphicsLayoutWidget.addPlot()
        #self.bottomPlot = self.graphicsLayoutWidget.addPlot()
        self.stop.clicked.connect(self.doStop)
        self.stop.setStyleSheet(ssColor("red"))
        self.duration.currentIndexChanged.connect(self.durationChanged)
        self.runState.clicked.connect(self.doRunState)
        self.runState.setText("Running")
        self.doRunState()


        self.writeDataState.clicked.connect(self.doWriteDataState)
        self.writeDataState.setText("Writing Data")
        self.doWriteDataState()

        self.setWindowTitle('PhasePlot')
        self.roachReader = RoachReader(self)
        self.roachReader.signalFromRoachReader.connect(self.signalFromRoachReader)
        self.roachReader.duration = float(self.duration.currentText())
        self.writer = Writer(self)

        
        self.plotprocessor = PlotProcessor(self)
        self.plotprocessor.signalFromProcessor.connect(self.updatePlots)
        
	# stream data to a file to read by KST

        self.streamToKST.clicked.connect(self.doStreamToKST)
        self.streamToKST.setText("streaming paused")
        self.stream2KST=False
        self.kstfile=open("phase2kst.dat","wb")
        self.streamer = Streamer(self)
        self.timer=QTimer()
        self.timer.timeout.connect(self.doTimer)
        self.timer.start(500)
      
        
        if roachData is True:
            items = []
            for resID,resFreq,atten in zip(rc.roachController.resIDs,
                                     rc.roachController.freqList,
                                     rc.roachController.attenList):
                items.append("%4d %s %5.1f"%(resID, "{:,}".format(resFreq),atten))
                
            self.iFreq.addItems(items)
    
        self.iFreq.currentIndexChanged.connect(self.iFreqChanged)
        self.iFreq.setCurrentIndex(0)
        self.iFreqChanged(0)
        self.recentPhases = None
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)
        self.amode = str(self.howToAve.currentText()).strip()
        self.howToAve.currentIndexChanged.connect(self.howToAveChanged)
        self.show()
        self.writer.start()
        #self.streamer.start()
        self.roachReader.start()
        self.plotprocessor.start()
        
    def closeEvent(self, event):
        """
        Called when the window is closed.  Call doStop
        """
        self.doStop()

    def doStop(self):
        """
        Shut down the worker and close the window
        """
        self.signalToRoachReader.emit('Stop')
        self.signalToWriter.emit('Stop')
        self.signalToStreamer.emit('Stop')
        self.signalToProcessor.emit({'processorLive':False})
        #self.timer.stop()
        
        self.close()

    def durationChanged(self, index):
        value = float(self.duration.itemText(index))
        print "duration: value =",value
        self.signalToRoachReader.emit("duration %f"%value)
        

    def doRunState(self):
        """
        Connected to runState.clicked.  Toggle between "Running" and "Paused",
        and then signal the worker the new state
        """
        if self.runState.text() == "Running":
            self.runState.setText("Paused")
            self.runState.setStyleSheet(ssColor("lightPink"))
        else:
            self.runState.setText("Running")
            self.runState.setStyleSheet(ssColor("lightGreen"))
        self.signalToRoachReader.emit(self.runState.text())

    def doWriteDataState(self):
        """
        Connected to writeData.clicked.  Toggle between "Writing Data" and "Paused Data Writing",
        and then signal the Writer the new state
        """
        if self.writeDataState.text() == "Writing Data":
            self.writeDataState.setText("Paused Data Writing")
            self.writeDataState.setStyleSheet(ssColor("lightPink"))
            self.writeData = False
        else:
            self.writeDataState.setText("Writing Data")
            self.writeDataState.setStyleSheet(ssColor("lightGreen"))
            self.writeData = True
        self.signalToWriter.emit(self.writeDataState.text())

    def doStreamToKST(self):
        if self.streamToKST.text() == "streaming to KST":
            self.streamToKST.setText("streaming paused")
            self.streamToKST.setStyleSheet(ssColor("lightPink"))
            self.signalToStreamer.emit("paused")
            self.stream2KST=False 
            print "Streaming to KST stopped"
        else:
            self.streamToKST.setText("streaming to KST")
            self.streamToKST.setStyleSheet(ssColor("lightGreen"))
            self.signalToStreamer.emit("streaming")
            self.stream2KST=True 
            print "Streaming to KST: file phase2kst.dat"

    def iFreqChanged(self, index):
        self.iFreqIndex = index
        
        if roachData is True:
            self.iFreqResID = self.rc.roachController.resIDs[index]
            self.iFreqFreq  = self.rc.roachController.freqList[index]
            self.iFreqAtten = self.rc.roachController.attenList[index]
    
    def signalFromWorker(self,dict):
        # The dict is defined as "dictToEmit" in the function "run" of the class "Worker
        pass
    
    def signalFromRoachReader(self,dict):
        pass
    
    def whatToPlotChanged(self, index):
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.processData()

    def howToAveChanged(self, index):
        self.amode = str(self.howToAve.currentText()).strip()
        self.processData()      

    def processData(self):
        # self.recentPhases is a dictionary of:  phases
        prDict={"wtp":self.wtp,"amode":self.amode,"processorLive":True}
        self.signalToProcessor.emit(prDict)

    def updatePlots(self,prcsEvts):

        self.domain = str(prcsEvts['domain'])
        self.mode = str(prcsEvts['mode'])
        self.values = prcsEvts['values']
        self.frqs = prcsEvts['freqs']
        
        if self.values is not None:
            self.topPlot.clear()
            pdata = self.values
            if self.domain == "time":   
                self.topPlot.setLogMode(None, None)
                self.topPlot.plot(pdata)
                        #self.topPlot.setLabel('left','radians')
                        #self.topPlot.setLabel('bottom','time sample (ticks)')
            elif self.wtp == "frequency":
    
                self.topPlot.setLogMode(True, None)
                dbcPerHz = 10.0*np.log10(pdata)
                self.topPlot.plot(self.frqs,dbcPerHz)
                self.topPlot.setLabel('left','dBc/Hz')
                self.topPlot.setLabel('bottom','frequency (kHz)')

   #         tup = (self.iFreqResID, "{:,}".format(self.iFreqFreq), self.iFreqAtten)
   #         self.topPlot.setTitle("%4d %s %5.1f"%tup)
                
    def doTimer(self):
        n = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(n)[:-5]
        self.datetimeClock.setText(dText)

class RoachReader(QThread):
    signalFromRoachReader = pyqtSignal(dict)
    def __init__(self, parent, verbose=False):
        QThread.__init__(self, parent)
        self.parent = parent
        self.verbose = verbose
        self.keepAlive = True
        self.parent.signalToRoachReader.connect(self.getSignal)

    def getSignal(self,value):
        if value == "Stop":
            print "RoachReader:  Stop received"
            self.keepAlive = False
        elif value == "Running":
            self.isRunning = True
        elif value == "Paused":
            self.isRunning = False
        elif str(value).startswith("duration"):
            self.duration = float(str(value).split()[1])
            print "hello:  self.duration=",self.duration

    def run(self):
        nIter = 0
        nLoop = 0
        self.isRunning = False
        while self.keepAlive:
            nLoop += 1
            if self.isRunning:
                if roachData is True:             
                    rcVerbosity = self.parent.rc.roachController.verbose
                    self.parent.rc.roachController.verbose = False
                    self.signalFromRoachReader.emit({"nIter":nIter, "nLoop":nLoop, "callTakeData":datetime.datetime.now()})
                   #hostIP = self.parent.rc.config.get('HOST', 'hostIP')

                    # get the ipaddress of the roach board
                    ipaddress = self.parent.rc.config.get(self.parent.rc.roachString,'ipaddress')

                    # find the ip address of this computer that the roach board uses to talk back
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.connect((ipaddress,80))
                    hostIP = s.getsockname()[0]
                    port = int(self.parent.rc.config.get(self.parent.rc.roachString,'port'))
                    freqChan = self.parent.iFreqIndex
                    timestamp = datetime.datetime.now()
                    duration = self.duration
                    phases = self.parent.rc.roachController.takePhaseStreamDataOfFreqChannel(
                        freqChan=freqChan, # confirm that this does the right thing 
                       duration=duration, 
                        hostIP=hostIP, fabric_port=port)
                    self.parent.rc.roachController.verbose = rcVerbosity
                    freqs = self.parent.rc.roachController.freqChannels
                    
                else:
                    # test data for debugging
                    print Nevents
                    freqChan = 10
                    timestamp = datetime.datetime.now()
                    duration = 2.0
                    a=np.arange(0.,10.,10.0/Nevents)
                    freqs =range(100,150)
                    phases=10*np.random.randn(Nevents)+5.0*np.sin(np.pi*a)
                    time.sleep(1.)
                    
                # 2.  write data to queue, if writeData is True

                if self.parent.writeData is True:             
                    dqToWriter.append({
                        "fileNamePrefix":str(self.parent.fileNamePrefix.text()).strip(),
                        "recentPhases":phases,
                        "timestamp":timestamp,
                        "freqChan":freqChan,
                        "freqs":freqs,
                        "duration":duration
                        })
                    
                if self.parent.stream2KST == True :
                    dqs.append({"phases":phases})
                    
                dqToProcessor.append({"phases":phases})

                #self.signalFromWorker.emit(dictToEmit)

                #self.signalFromRoachReader.emit(dictToEmit)
                nIter += 1
                time.sleep(0.1)
            else:
                pass
                
            label = str(nIter)+str(nLoop)
            self.parent.loopLabel.setText(label)
            time.sleep(0.05)
        print "RoachReader:  all done"

class Writer(QThread):

    def __init__(self, parent, verbose=False):
        QThread.__init__(self, parent)
        self.parent = parent
        self.verbose = verbose
        self.keepAlive = True
        self.writeData = False
        self.parent.signalToWriter.connect(self.getSignal)

    def getSignal(self, value):
        print "Writer.getSignal:  value =",value
        if value == "Stop":
            self.keepAlive = False
    def run(self):
        while self.keepAlive:
            if self.parent.writeData is True:                        
                while len(dqToWriter) > 0:
                    data = dqToWriter.popleft()
                    fileNamePrefix = data['fileNamePrefix']
                    recentPhases = data['recentPhases']
                    timestamp = data['timestamp']
                    freqChan = data['freqChan']
                    freqs = data['freqs']
                    baseFileName = "%s-%s"%(fileNamePrefix, timestamp.strftime("%Y-%m-%dT%T.%f"))
                    duration = data['duration']
                    WritePhaseData.WritePhaseData(baseFileName, 'hdf5', freqChan, freqs, duration, recentPhases)
            time.sleep(0.01)


class Streamer(QThread):
    def __init__(self,parent):
        QThread.__init__(self,parent)
        self.parent = parent
        self.parent.signalToStreamer.connect(self.getSignal)
        self.streamToKST = False
        self.keepStreamAlive = True
        self.kstfile = parent.kstfile

    def getSignal(self, value):
        #print "Streamer.getSignal:  value =",value
        if value == "Stop":
            keepStreamAlive=False

    def run(self):
        while self.keepStreamAlive:
            print "---3"
            if self.parent.stream2KST is True :
                while len(dqs) > 0:
                    print "-----4"
                    sdata = dqs.pop()
                    dphases = sdata['phases']
                    phaseEnd=dphases[:1000]
                    np.savetxt(self.kstfile, phaseEnd)
            time.sleep(1.0)




def ssColor(color):
    retval = "QWidget {background-color:"
    retval += color
    retval +="; outline-color:"
    retval += color
    retval += "}"
    return retval

#-----------------------------------------------------------------------------------
class PlotProcessor(QThread):
    signalFromProcessor = pyqtSignal(dict)
    
    def __init__(self, parent):
        QThread.__init__(self, parent)
        self.parent = parent
        self.domain = 'time' # time or frequency
        self.mode = 'none'
        self.nEma = 0
        self.nCma = 0
        self.keepAlive = True

        self.parent.signalToProcessor.connect(self.getSignal)

    def getSignal(self, pdict):
        if 'wtp' in pdict:
            self.domain = str(pdict['wtp'])
        if 'amode' in pdict :
            self.mode = str(pdict['amode'])
        
        self.keepAlive= str(pdict['processorLive'])
        self.setMode(self.mode)

      
    def reset(self):
        self.nEma=0
        self.nCma = 0
        self.cma=0
        self.ema=0

        
        
    def setMode(self,mode):
        self.mode = mode
        if self.mode == "cma": # cumulative moving average
            self.nCma = 0
            self.cma=0
        elif self.mode == "ema":
            self.nEma = 0
            self.ema=0

    def calcCMA(self,x):
        if self.nCma == 0:
            self.cma = x
        else:
            self.cma = (x + self.nCma*self.cma)/(self.nCma+1)
        self.nCma += 1
        return self.cma
    
    def calcEMA(self,x):
        if self.nEma == 0:
            self.ema = x
        else:
            self.ema = self.alpha*x+ (1.0-self.alpha)*self.ema
        self.nEma += 1
        return self.ema  
    
                            
                 
    def run(self):
        while self.keepAlive:
            while(len(dqToProcessor) > 0) :
                timeDomainData=(dqToProcessor.pop())["phases"]
         
                self.alpha=0.1
                  
                retval = {
                    "domain":self.domain,
                    "mode":self.mode,
                    }
                  
                retval=[]
                frqs=[]
                if self.domain == 'time':
                    x = timeDomainData              
                   
                    if self.mode == 'none':
                        retval = x
                    elif self.mode == "cma":
                        
                        retval = self.calcCMA(timeDomainData)
                    
                    elif self.mode == 'ema':
                        
                        retval = self.calcEMA(timeDomainData)   
                    else:    
                        raise ValueError("teach me how to deal with mode =",self.mode)
                           
                elif self.domain == "frequency":
                    x =  timeDomainData
                    fs = 1e6 
                    window = 'hanning'
                    nperseg = len(x)
                    noverlap = 0
                    nfft = None
                    detrend = 'constant'
                    frqs,pxx = welch(x,fs,window,nperseg,noverlap,nfft,detrend,scaling='spectrum')
                    
                    if self.mode == 'none':
                        retval = pxx
                        
                    elif self.mode == 'cma':
                        retval= self.calcCMA(pxx)
                        
                    elif self.mode == 'ema':
                        retval = self.calcEMA(pxx)   
                        
                    else:    
                        raise ValueError("teach me how to deal with mode =",self.mode)
                else:
                    raise ValueError("teach me how to deal with domain =",self.domain)
                
                if len(retval) > 0:
                    retdict=({"domain":self.domain,"mode":self.mode,"values":retval,"freqs":frqs})
                    self.signalFromProcessor.emit(retdict)       
            time.sleep(0.01)

if __name__ == "__main__":
    app = QtGui.QApplication(sys.argv)
    rchc=100
    phasePlotWindow = PhasePlotWindow(rchc)
    print "--A"
    phasePlotWindow.show()
    print "--B"
    sys.exit(app.exec_())
    
 

        




