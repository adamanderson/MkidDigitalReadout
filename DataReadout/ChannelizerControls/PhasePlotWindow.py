import datetime, time, os, socket
from PyQt4 import QtGui, uic
from PyQt4.QtCore import QThread, pyqtSignal, QTimer
import numpy as np
from collections import deque
from scipy.signal import welch
import WritePhaseData
reload(WritePhaseData)
dq = deque()
dqs = deque()
dqToWriter = deque()

class PhasePlotWindow(QtGui.QMainWindow):
    signalToRoachReader = pyqtSignal(str)
    signalToWriter = pyqtSignal(str)
    signalToStreamer = pyqtSignal(str)
 
    def __init__(self, rc):
        super(PhasePlotWindow,self).__init__()
        self.rc = rc
        thisDir = os.path.dirname(os.path.abspath(__file__))
        uic.loadUi(os.path.join(thisDir,'PhasePlotWidget.ui'), self)
        self.topPlot =    self.graphicsLayoutWidget.addPlot()
        #self.graphicsLayoutWidget.nextRow()
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
        #self.setGeometry(300, 300, 250, 150)
        self.setWindowTitle('PhasePlot')
        self.roachReader = RoachReader(self)
        self.roachReader.signalFromRoachReader.connect(self.signalFromRoachReader)
        self.roachReader.duration = float(self.duration.currentText())

        self.writer = Writer(self)

	# stream data to a file to read by KST

        self.streamToKST.clicked.connect(self.doStreamToKST)
        self.streamToKST.setText("streaming paused")
        self.stream2KST=False
        self.kstfile=open("phase2kst.dat","wb")
        self.streamer = Streamer(self)


        
        self.timer=QTimer()
        self.timer.timeout.connect(self.doTimer)
        self.timer.start(500) 
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
        self.show()
        self.writer.start()
        #self.worker.start()
        self.streamer.start()
        self.roachReader.start()
        

    def closeEvent(self, event):
        """
        Called when the window is closed.  Call doStop
        """
        self.doStop()

    def doStop(self):
        """
        Shut down the worker and close the window
        """
        self.signalToRoachReader.emit("Stop")
        self.signalToWriter.emit("Stop")
        self.signalToStreamer.emit("Stop")
        self.timer.stop()
        
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
        self.iFreqResID = self.rc.roachController.resIDs[index]
        self.iFreqFreq  = self.rc.roachController.freqList[index]
        self.iFreqAtten = self.rc.roachController.attenList[index]

    def signalFromWorker(self,dict):
        # The dict is defined as "dictToEmit" in the function "run" of the class "Worker
        pass
    def signalFromRoachReader(self,dict):
        # The dict is defined as "dictToEmit" in the function "run" of the class "RoachReader"
        if "nIter" in dict.keys():
            label = str(dict['nIter'])
            if "nLoop" in dict.keys():
                label += "/"+str(dict['nLoop'])
                self.loopLabel.setText(label)
        if "callTakeData" in dict.keys():
            n = dict["callTakeData"]
            dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(n)[:-5]
            self.callTakeData.setText(dText)
        if "phases" in dict.keys():
            # actual data collected, so do two things:
            # 1. plot data
            self.recentPhases = dict['phases']
            self.updatePlots()

            # 2. send to the write data queue, if writeData is True
            if self.writeData:
                dq.append({
                        "fileNamePrefix":str(self.fileNamePrefix.text()).strip(),
                        "recentPhases":self.recentPhases,
                        "timestamp":dict['timestamp'],
                        "freqChan":dict['freqChan'],
                        "freqs":dict['freqs'],
                        "duration":dict['duration']
                        })

            if self.stream2KST:
                dqs.append({"phases":self.recentPhases})

            # 2. send to the write data queue, if writeData is True
            if self.writeData:
                dqToWriter.append({
                    "fileNamePrefix":str(self.fileNamePrefix.text()).strip(),
                    "recentPhases":self.recentPhases,
                    "timestamp":dict['timestamp'],
                    "freqChan":dict['freqChan'],
                    "freqs":dict['freqs'],
                    "duration":dict['duration']
                })

    def whatToPlotChanged(self, index):
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.updatePlots()

    def updatePlots(self):
        # self.recentPhases is a dictionary of:  phases
        # where phases is a 1d numpy array of phases in radians
        if self.recentPhases is not None:
            self.topPlot.clear()
            #self.bottomPlot.clear()
            phases = self.recentPhases
            if self.wtp == "time":
                self.topPlot.setLogMode(None, None)
                self.topPlot.plot(phases)
                self.topPlot.setLabel('left','radians')
                self.topPlot.setLabel('bottom','time sample (ticks)')
            elif self.wtp == "frequency":
                self.topPlot.setLogMode(True, None)
                x = phases
                fs = 1e6 # Gustavo told us this is the sampling frequency.
                window = 'hanning'
                nperseg = len(x)
                noverlap = 0
                nfft = None
                detrend = 'constant'
                f,pxx = welch(x,fs,window,nperseg,noverlap,nfft,detrend,scaling='spectrum')
                dbcPerHz = 10.0*np.log10(pxx)
                self.topPlot.plot(f/1e3,dbcPerHz)
                self.topPlot.setLabel('left','dBc/Hz')
                self.topPlot.setLabel('bottom','frequency (kHz)')
            else:
                print "do not understand self.wtp =",self.wtp

            tup = (self.iFreqResID, "{:,}".format(self.iFreqFreq), self.iFreqAtten)
            self.topPlot.setTitle("%4d %s %5.1f"%tup)
                
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
                dictToEmit = {"nIter":nIter, "nLoop":nLoop, "phases":phases,
                              "timestamp":timestamp, "freqs":freqs, "duration":duration,
                              "freqChan":freqChan
                }
                #self.signalFromWorker.emit(dictToEmit)

                self.signalFromRoachReader.emit(dictToEmit)
                nIter += 1
            else:
                time.sleep(1.0)
            self.signalFromRoachReader.emit({"nIter":nIter, "nLoop":nLoop})
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
            time.sleep(1.0)


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
            while len(dqs) > 0:
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
