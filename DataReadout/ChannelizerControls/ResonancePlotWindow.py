import datetime, time, os, json_tricks, pickle
from PyQt4 import QtGui, uic
from PyQt4.QtCore import QThread, pyqtSignal, QTimer
import numpy as np
from collections import deque
import H5IO
reload(H5IO)
import clTools
reload(clTools)
dq = deque()

class ResonancePlotWindow(QtGui.QMainWindow):
    signalToWorker = pyqtSignal(str)
    def __init__(self, rc):
        super(ResonancePlotWindow,self).__init__()
        self.stopping = False
        self.iqData = None
        self.rc = rc
        thisDir = os.path.dirname(os.path.abspath(__file__))
        uic.loadUi(os.path.join(thisDir,'ResonancePlotWidget.ui'), self)
        self.topPlot =    self.graphicsLayoutWidget.addPlot()
        self.graphicsLayoutWidget.nextRow()
        self.bottomPlot = self.graphicsLayoutWidget.addPlot()
        self.stop.clicked.connect(self.doStop)
        self.stop.setStyleSheet(ssColor("red"))
        self.runState.clicked.connect(self.doRunState)
        self.runState.setText("Running")
        self.doRunState()

        #self.setGeometry(300, 300, 250, 150)
        self.setWindowTitle('ResonancePlot')
        self.worker = Worker(self)
        self.worker.signalFromWorker.connect(self.signalFromWorker)

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
        self.recentIQData = None
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)
        self.show()


    def closeEvent(self, event):
        """
        Called when the window is closed.  Call doStop
        """
        self.doStop()

    def doStop(self):
        """
        Shut down the worker and close the window
        """
        if not self.stopping:
            self.stopping = True
            self.signalToWorker.emit("StopFromDoStop")
            self.timer.stop()
            self.close()

    def doRunState(self):
        """
        Connected to runState.clicked.  Toggle between "Running" and "Waiting",
        and then signal the worker the new state
        """
        if self.runState.text() == "Running":
            self.runState.setText("Waiting")
            self.runState.setStyleSheet(ssColor("lightPink"))
        else:
            self.runState.setText("Running")
            self.runState.setStyleSheet(ssColor("lightGreen"))
        self.signalToWorker.emit(self.runState.text())

    def iFreqChanged(self, index):
        self.iFreqIndex = index
        self.iFreqResID = self.rc.roachController.resIDs[index]
        self.iFreqFreq  = self.rc.roachController.freqList[index]
        self.iFreqAtten = self.rc.roachController.attenList[index]

    def signalFromWorker(self,data):
        print "begin signalFromWorker"
        print "type of data is ",type(data)
        print "data.keys()=",data.keys()

        handle = open('IQDataDict.json','w')
        json_tricks.dump(data, handle)
        handle.close()
        
    def whatToPlotChanged(self, index):
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.updatePlots()

    def updatePlots(self):
        # self.recentIQData is a dictionary of:  I and Q, where I and Q are 2d
        # I[iFreq][iPt] - iFreq is the frequency
        if self.recentIQData is not None:
            self.topPlot.clear()
            self.bottomPlot.clear()
            iList = self.recentIQData['I'][self.iFreqIndex]
            qList = self.recentIQData['Q'][self.iFreqIndex]
            if self.wtp == "IQ":
                self.topPlot.plot(iList)
                self.topPlot.setLabel('left','I (ADUs)')
                self.bottomPlot.plot(qList)
                self.bottomPlot.setLabel('left','Q (ADUs)')
            elif self.wtp == "MagPhase":
                iq = np.array(iList) + 1j*np.array(qList)
                amplitude = np.absolute(iq)
                angle = np.angle(iq,deg=True)
                self.topPlot.plot(amplitude)
                self.topPlot.setLabel('left','amplitude (ADUs)')
                self.bottomPlot.plot(angle)
                self.bottomPlot.setLabel('left','phase (degrees)')

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
        print "Worker.getSignal:  value=",value
        if value == "Running":
            timestamp = datetime.datetime.now()
            print "Now call clTools.performIQSweep"
            t0 = datetime.datetime.now()
            iqData = clTools.performIQSweep(self.parent.rc)
            t1 = datetime.datetime.now()
            dt = t1-t0
            print "dt =",dt
            data = {
                'timestamp':timestamp,
                'iqData':iqData
            }
            self.signalFromWorker.emit(data)

def ssColor(color):
    retval = "QWidget {background-color:"
    retval += color
    retval +="; outline-color:"
    retval += color
    retval += "}"
    return retval
