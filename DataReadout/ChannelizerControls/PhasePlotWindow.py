import datetime, time, os, socket
from PyQt4 import QtGui, uic
from PyQt4.QtCore import QThread, pyqtSignal, QTimer
import numpy as np
from collections import deque
import H5IO
reload(H5IO)
dq = deque()

class PhasePlotWindow(QtGui.QMainWindow):
    signalToWorker = pyqtSignal(str)
    signalToWriter = pyqtSignal(str)
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
        self.worker = Worker(self)
        self.worker.signalFromWorker.connect(self.signalFromWorker)
        self.worker.duration = float(self.duration.currentText())

        self.writer = Writer(self)
        
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
        self.recentPhaseData = None
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)
        self.show()
        self.writer.start()
        self.worker.start()


    def closeEvent(self, event):
        """
        Called when the window is closed.  Call doStop
        """
        self.doStop()

    def doStop(self):
        """
        Shut down the worker and close the window
        """
        self.signalToWorker.emit("Stop")
        self.signalToWriter.emit("Stop")
        self.timer.stop()
        self.close()

    def durationChanged(self, index):
        value = float(self.duration.itemText(index))
        print "duration: value =",value
        self.signalToWorker.emit("duration %f"%value)
        

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
        self.signalToWorker.emit(self.runState.text())

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

    def iFreqChanged(self, index):
        self.iFreqIndex = index
        self.iFreqResID = self.rc.roachController.resIDs[index]
        self.iFreqFreq  = self.rc.roachController.freqList[index]
        self.iFreqAtten = self.rc.roachController.attenList[index]

    def signalFromWorker(self,dict):
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
            # actual data collected!
            self.recentPhases = dict['phases']
            if self.writeData:
                dq.append({
                        "fileNamePrefix":str(self.fileNamePrefix.text()).strip(),
                        "recentPhases":self.recentPhases
                        })
            self.updatePlots()

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
                self.topPlot.plot(phases)
                self.topPlot.setLabel('left','radians')
                #self.bottomPlot.plot(qList)
                #self.bottomPlot.setLabel('left','Q (ADUs)')
            elif self.wtp == "MagPhase":
                iq = np.array(iList) + 1j*np.array(qList)
                amplitude = np.absolute(iq)
                angle = np.angle(iq,deg=True)
                self.topPlot.plot(amplitude)
                self.topPlot.setLabel('left','amplitude (ADUs)')
                #self.bottomPlot.plot(angle)
                #self.bottomPlot.setLabel('left','phase (degrees)')
            else:
                print "do not understand self.wtp =",self.wtp

            tup = (self.iFreqResID, "{:,}".format(self.iFreqFreq), self.iFreqAtten)
            self.topPlot.setTitle("%4d %s %5.1f"%tup)
                
    def doTimer(self):
        n = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(n)[:-5]
        self.datetimeClock.setText(dText)

class Worker(QThread):
    signalFromWorker = pyqtSignal(dict)
    def __init__(self, parent, verbose=False):
        QThread.__init__(self, parent)
        self.parent = parent
        self.verbose = verbose
        self.keepAlive = True
        self.parent.signalToWorker.connect(self.getSignal)

    def getSignal(self,value):
        if value == "Stop":
            print "Worker:  Stop received"
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
                self.signalFromWorker.emit({"nIter":nIter, "nLoop":nLoop, "callTakeData":datetime.datetime.now()})
                #hostIP = self.parent.rc.config.get('HOST', 'hostIP')

                # get the ipaddress of the roach board
                ipaddress = self.parent.rc.config.get(self.parent.rc.roachString,'ipaddress')

                # find the ip address of this computer that the roach board uses to talk back
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((ipaddress,80))
                hostIP = s.getsockname()[0]
                print "in PhasePlotWindow:  hostIP =",hostIP
                
                port = int(self.parent.rc.config.get(self.parent.rc.roachString,'port'))
                phases = self.parent.rc.roachController.takePhaseStreamDataOfFreqChannel(
                    freqChan=self.parent.iFreqIndex, # confirm that this does the right thing 
                    duration=self.duration, 
                    hostIP=hostIP, fabric_port=port)
                self.parent.rc.roachController.verbose = rcVerbosity
                self.signalFromWorker.emit({"nIter":nIter, "nLoop":nLoop, "phases":phases})
                nIter += 1
            else:
                time.sleep(1.0)
            self.signalFromWorker.emit({"nIter":nIter, "nLoop":nLoop})
        print "Worker:  all done"

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
        fileHandle = open("phaseData.txt",'wb')
        #h5Writer = H5IO.H5Writer()
        while self.keepAlive:
            while len(dq) > 0:
                data = dq.popleft()
                fileNamePrefix = data['fileNamePrefix']
                recentPhases = data['recentPhases']
                #h5Writer.write(recentPhases,fileNamePrefix)
                np.savetxt(fileHandle, recentPhases)
            time.sleep(1.0)
        print "Writer:  call h5Writer.close()"
        h5Writer.close()
        print "Writer:  all done"

def ssColor(color):
    retval = "QWidget {background-color:"
    retval += color
    retval +="; outline-color:"
    retval += color
    retval += "}"
    return retval
