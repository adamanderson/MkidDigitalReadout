import datetime, time, os, json_tricks, pickle
from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtCore import QThread, pyqtSignal, QTimer
import numpy as np
from collections import deque
import H5IO
reload(H5IO)
import clTools
reload(clTools)
import LoopFitter
reload(LoopFitter)

dqToWorker = deque()

import pyqtgraph as pg
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

class ResonancePlotWindow(QtGui.QMainWindow):
    signalToWorker = pyqtSignal(str)
    def __init__(self, rchc):
        super(ResonancePlotWindow,self).__init__()
        self.stopping = False
        self.iqData = None
        self.rchc = rchc
        thisDir = os.path.dirname(os.path.abspath(__file__))
        uic.loadUi(os.path.join(thisDir,'ResonancePlotWidget.ui'), self)
        #self.topPlot =    self.graphicsLayoutWidget.addPlot()
        #self.graphicsLayoutWidget.nextRow()
        #self.bottomPlot = self.graphicsLayoutWidget.addPlot()
        self.stop.clicked.connect(self.doStop)
        self.stop.setStyleSheet(ssColor("red"))

        self.sweepState.clicked.connect(self.doSweep)
        self.sweepState.setStyleSheet(ssColor("lightGreen"))
        self.sweepState.setText("Ready to Sweep")

        self.sweepProgressBar.setMinimum(0)
        self.sweepProgressBar.setMaximum(100)
        self.sweepProgressBar.setValue(100)
        self.nSweepStep = 0
        self.setWindowTitle('ResonancePlot')        
        self.worker = Worker(self)
        self.worker.signalFromWorker.connect(self.signalFromWorker)
        self.worker.start()
        self.timer=QTimer()
        self.timer.timeout.connect(self.doTimer)
        self.timer.start(200)
        
        items = []
        for resID,resFreq,atten in zip(rchc.roachController.resIDs,
                                 rchc.roachController.freqList,
                                 rchc.roachController.attenList):
            items.append("%4d %s %5.1f"%(resID, "{:,}".format(resFreq),atten))
        self.iFreq.addItems(items)
        self.iFreq.currentIndexChanged.connect(self.iFreqChanged)
        self.iFreq.setCurrentIndex(0)
        self.iFreqChanged(0)
        self.recentIQData = None
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)

        LO_span = self.rchc.config.getfloat(rchc.roachString,"sweeplospan")
        LO_step = self.rchc.config.getfloat(rchc.roachString,"sweeplostep")
        self.loStep.setValue(LO_step/1e3)
        self.loSpan.setValue(LO_span/1e3)
        self.loStep.valueChanged.connect(self.updateNStep)
        self.loSpan.valueChanged.connect(self.updateNStep)        
        self.updateNStep()
        self.show()

    def getNStepFromGui(self):
        loStep = self.loStep.value()
        loSpan = self.loSpan.value()
        self.rchc.config.set(self.rchc.roachString, "sweeplospan",str(loSpan*1e3))
        self.rchc.config.set(self.rchc.roachString, "sweeplostep",str(loStep*1e3))
        try:
            nStep = int(loSpan/loStep)
        except ZeroDivisionError:
            nStep = -1
        return nStep

    def updateNStep(self):
        msg = "nStep = %d"%self.getNStepFromGui()
        self.nStep.setText(msg)
        
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
            self.signalToWorker.emit("PleaseStop")
            self.timer.stop()
            self.close()

    def doSweep(self):
        self.nSweepStep = self.getNStepFromGui()
        self.expectedSweepSeconds = int(self.nSweepStep)*0.4 # Expect 0.4 seconds per sweep step
        self.tsSweep = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(self.tsSweep)[:-5]
        self.callIQTakeAvgTime.setText(dText)
        self.sweepState.setText("Sweeping %d steps"%(int(self.nSweepStep)))
        self.sweepState.setStyleSheet(ssColor("lightPink"))
        self.sweepProgressBar.setValue(0)
        dqToWorker.append("PleaseDoASweep")


    def iFreqChanged(self, index):
        self.iFreqIndex = index
        self.iFreqResID = self.rchc.roachController.resIDs[index]
        self.iFreqFreq  = self.rchc.roachController.freqList[index]
        self.iFreqAtten = self.rchc.roachController.attenList[index]

    def signalFromWorker(self,data):
        #handle = open('IQDataDict.json','w')
        #json_tricks.dump(data, handle)
        #handle.close()
        self.recentIQData = data['iqData']
        self.updatePlots()
        self.sweepState.setStyleSheet(ssColor("lightGreen"))
        self.sweepState.setText("Ready to Sweep")
        self.nSweepStep = 0
        
    def whatToPlotChanged(self, index):
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.updatePlots()

    def updatePlots(self):
        # self.recentIQData is a dictionary of:  I and Q, where I and Q are 2d
        # I[iFreq][iPt] - iFreq is the frequency

        # Here is documentation of options to the "plot" command
        # http://pyqtgraph.org/documentation/_modules/pyqtgraph/graphicsItems/PlotDataItem.html#PlotDataItem
        if self.recentIQData is not None:
            self.graphicsLayoutWidget.clear()
            iList = self.recentIQData['I'][self.iFreqIndex]
            qList = self.recentIQData['Q'][self.iFreqIndex]
            f0 = self.recentIQData['freqList'][self.iFreqIndex]
            freqOffsets = self.recentIQData['freqOffsets']
            if self.recentIQData.has_key("loopFits"):
                # fvap is a tuple of (interpolated frequency, iqVelocity, amplitude, phase) numpy arrays
                fFit = self.recentIQData['loopFits'][self.iFreqIndex]['fFit']
                iFit = self.recentIQData['loopFits'][self.iFreqIndex]['iFit']
                qFit = self.recentIQData['loopFits'][self.iFreqIndex]['qFit']
                fvap = LoopFitter.getFVAP(fFit, iFit, qFit)
            if self.wtp == "IQ":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                self.bottomPlot = self.graphicsLayoutWidget.addPlot(1,0)
                self.topPlot.plot(freqOffsets, iList, symbol='o', symbolPen='k', pen='k')
                self.topPlot.setLabel('left','I', 'ADUs')
                self.topPlot.setLabel('bottom', 'Frequency Offset', 'Hz')
                self.bottomPlot.plot(freqOffsets, qList, symbol='o', symbolPen='k', pen='k')
                self.bottomPlot.setLabel('left','Q','ADUs')
                self.bottomPlot.setLabel('bottom', 'Frequency Offset', 'Hz')
                if self.recentIQData.has_key("loopFits"):
                    self.leftPlot.plot(iFit, qFit, pen='r')
                    fFreqOffsets = fFit-f0
                    self.topPlot.plot(fFreqOffsets, iFit, pen='r')
                    self.bottomPlot.plot(fFreqOffsets, qFit, pen='r')
            elif self.wtp == "MagPhase":
                iq = np.array(iList) + 1j*np.array(qList)
                amplitude = np.absolute(iq)
                angle = np.angle(iq,deg=True)
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                self.bottomPlot = self.graphicsLayoutWidget.addPlot(1,0)
                self.topPlot.plot(freqOffsets, amplitude, symbol='o', symbolPen='k', pen='k')
                self.topPlot.setLabel('left','amplitude', 'ADUs')
                self.topPlot.setLabel('bottom', 'Frequency Offset', 'Hz')
                self.bottomPlot.plot(freqOffsets, angle, symbol='o', symbolPen='k', pen='k')
                self.bottomPlot.setLabel('left','phase', 'degrees')
                self.bottomPlot.setLabel('bottom', 'Frequency Offset', 'Hz')
                if self.recentIQData.has_key("loopFits"):
                    self.leftPlot.plot(iFit, qFit, pen='r')
                    fFreqOffsets = fFit-f0
                    self.topPlot.plot(fFreqOffsets, fvap[2], pen='r')
                    self.bottomPlot.plot(fFreqOffsets, fvap[3], pen='r')
            elif self.wtp == "LoopVelocity":
                self.leftPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                self.rightPlot = self.graphicsLayoutWidget.addPlot(0,1)
                self.leftPlot.plot(iList, qList, symbol='o', symbolPen='k', pen='k')
                self.leftPlot.setLabel('left','Q', 'ADUs')
                self.leftPlot.setLabel('bottom','I', 'ADUs')

                dfs = freqOffsets[1:]-freqOffsets[:-1]
                dis = iList[1:]-iList[:-1]
                dqs = qList[1:]-qList[:-1]
                vs = np.sqrt(dis*dis+dqs*dqs)/dfs
                favgs = 0.5*(freqOffsets[1:]+freqOffsets[:-1])
                self.rightPlot.plot(favgs, vs, symbol='o', symbolPen='k', pen='k')
                self.rightPlot.setLabel('bottom', 'Frequency Offset', 'Hz')
                self.rightPlot.setLabel('left', "IQ Velocity", "ADUs/Hz")
                if self.recentIQData.has_key("loopFits"):
                    self.leftPlot.plot(iFit, qFit, pen='r')
                    fFreqOffsets = fvap[0]-f0
                    v = fvap[1]
                    self.rightPlot.plot(fFreqOffsets, v, pen='r')
            #tup = (self.iFreqResID, "{:,}".format(self.iFreqFreq), self.iFreqAtten)
            #self.topPlot.setTitle("%4d %s %5.1f"%tup)
                
    def doTimer(self):
        n = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(n)[:-5]
        self.datetimeClock.setText(dText)
        # If a sweep is in progress, update the progress bar
        if self.nSweepStep == 0:
            self.sweepProgressBar.setValue(100)
        else:
            elapsedSweepTime = n - self.tsSweep
            percent = 100*elapsedSweepTime.total_seconds()/self.expectedSweepSeconds
            self.sweepProgressBar.setValue(percent)
            
class Worker(QThread):
    signalFromWorker = pyqtSignal(dict)
    def __init__(self, parent, verbose=False):
        QThread.__init__(self, parent)
        self.parent = parent
        self.verbose = verbose
        self.keepAlive = True
        self.parent.signalToWorker.connect(self.getSignal)

    def getSignal(self,value):
        if value == "PleaseStop":
            self.keepAlive = False
        else:
            print "Worker.getSignal unknown signal: ",value

    def run(self):
        while self.keepAlive:
            try:
                message = dqToWorker.popleft()
                self.doASweep()
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.1)
                
    def doASweep(self, verbose=False):
        if verbose: print "ResonancePlotWindow.doASweep: begin"
        timestamp = datetime.datetime.now()
        rchc = self.parent.rchc
        t0 = datetime.datetime.now()
        if verbose: print "ResonancePlotWindow.doASweep: call clTools.performIQSweep"
        iqData = clTools.performIQSweep(self.parent.rchc)
        if verbose: print "ResonancePlotWindow.doASweep: call back from performIQSweep"
        t1 = datetime.datetime.now()
        dt = t1-t0
        data = {
            'timestamp':timestamp,
            'iqData':iqData
        }
        if verbose: print "ResonancePlotWindow.doASweep: call signalFromWorker.emit"
        self.signalFromWorker.emit(data)
        if verbose: print "ResonancePlotWindow.doASweep: done"
        
def ssColor(color):
    retval = "QWidget {background-color:"
    retval += color
    retval +="; outline-color:"
    retval += color
    retval += "}"
    return retval
