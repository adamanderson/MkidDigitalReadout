import datetime, json_tricks, os, pickle, sys, time, warnings
from PyQt4 import QtGui, uic, QtCore
from PyQt4.QtCore import QThread, pyqtSignal, QTimer, QRectF, QPointF
import numpy as np
from collections import deque
import H5IO
reload(H5IO)
import clTools
reload(clTools)
import LoopFitter
reload(LoopFitter)


if not sys.warnoptions:
    warnings.simplefilter("ignore")
dqToWorker = deque()
dqToToneGenerator = deque()

import pyqtgraph as pg
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

class PlotPhaseStreamWindow(QtGui.QMainWindow):
    signalToWorker = pyqtSignal(str)
    signalToToneGenerator = pyqtSignal(str)
    def __init__(self, rchc):
        super(PlotPhaseStreamWindow,self).__init__()
        self.stopping = False
        self.iqData = None
        self.rchc = rchc
        thisDir = os.path.dirname(os.path.abspath(__file__))
        uic.loadUi(os.path.join(thisDir,'PlotPhaseStreamWidget.ui'), self)

        self.vPen = pg.mkPen(color='k', style=QtCore.Qt.DashLine)
        self.setWindowTitle('FindResonances')
        
        self.stop.clicked.connect(self.doStop)
        self.stop.setStyleSheet(ssColor("red"))

        self.sweepState.clicked.connect(self.doSweep)
        self.sweepState.setStyleSheet(ssColor("lightGreen"))
        self.sweepState.setText("Ready to Sweep")

        self.sweepProgressBar.setMinimum(0)
        self.sweepProgressBar.setMaximum(100)
        self.sweepProgressBar.setValue(100)
        self.nSweepStep = 0

        self.generateToneState.clicked.connect(self.generateTone)
        self.generateToneState.setStyleSheet(ssColor("lightGreen"))
        self.generateToneState.setText("Ready to Generate Tone")
        
        self.worker = Worker(self)
        self.worker.signalFromWorker.connect(self.signalFromWorker)
        self.worker.start()

        self.toneGenerator = ToneGenerator(self)
        self.toneGenerator.signalFromToneGenerator\
                          .connect(self.signalFromToneGenerator)
        self.toneGenerator.start()

        self.timer=QTimer()
        self.timer.timeout.connect(self.doTimer)
        self.timer.start(200)

        self.setIFreqItems()

        self.symbolSize.currentIndexChanged.connect(self.updatePlots)
        self.iFreq.currentIndexChanged.connect(self.iFreqChanged)
        self.iFreq.setCurrentIndex(0)
        self.iFreqChanged(0)
        try:
            iqLoopData = rchc.recentIQData
            try:
                loFreqStr = str(rchc.recentIQData['LO_freq'])
            except:
                loFreqStr = "?"
            self.loFreqHz.setText(loFreqStr)
        except AttributeError:
            iqLoopData = None

        self.recentIQData = iqLoopData
            
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)
        print "init:  self.wtp =",self.wtp
        self.loSpanHz.editingFinished.connect(self.updateStepLabel)
        self.loStepHz.editingFinished.connect(self.updateStepLabel)
        self.updateStepLabel()

        self.graphicsLayoutWidget.scene().sigMouseMoved\
                                         .connect(self.mouseMoved)
        self.previousPlotState = None

        self.show()

        try:
            recentIQData = self.rchc.recentIQData
        except AttributeError:
            pass
        else:
            # plot the "old" recentIQData
            self.recentIQData = recentIQData
            self.updatePlots()
            
    def setIFreqItems(self):
        items = []
        self.iFreq.clear()
        try:
            for resID,resFreq,atten in zip(self.rchc.roachController.resIDs,
                                     self.rchc.roachController.freqList,
                                     self.rchc.roachController.attenList):
                item = "%4d %s %5.1f"%(resID, "{:,}".format(resFreq),atten)
                items.append(item)
            self.iFreq.addItems(items)
        except AttributeError: # If nothing is defined in the roachController
            pass
            
    def updateStepLabel(self):
        loSpan = float(self.loSpanHz.text())
        loStep = float(self.loStepHz.text())
        try:
            nStep = int(loSpan/loStep)
        except ZeroDivisionError:
            nStep = 0
        sec = nStep*0.4 # Expect 0.4 seconds per sweep step
        msg = "%d steps in %.0f seconds"%(nStep,sec)
        self.stepLabel.setText(msg)
        # used to update self.sweepProgressBar
        self.expectedSweepSeconds = sec
        self.nSweepStepToDo = nStep
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
            self.signalToWorker.emit("StopSign")
            self.signalToToneGenerator.emit("StopSign")
            self.timer.stop()
            self.close()

    def doSweep(self):
        self.tsSweep = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(self.tsSweep)[:-5]
        self.callIQTakeAvgTime.setText(dText)
        # Set to non-zero to tell the timer to keep score
        self.nSweepStep = self.nSweepStepToDo 
        self.sweepState.setText("Sweeping %d steps"%(int(self.nSweepStep)))
        self.sweepState.setStyleSheet(ssColor("lightPink"))
        self.sweepProgressBar.setValue(0)

        # Set values in rchc.config, which is what clTools.performIQSweep uses
        rchc = self.rchc
        try:
            sweeplospan = str(float(self.loSpanHz.text()))
            sweeplostep = str(float(self.loStepHz.text()))
            sweeplooffset = str(float(self.loOffsetHz.text()))
        except ValueError:
            return # one of the three values is not a good string
        rchc.config.set(rchc.roachString,'sweeplospan', sweeplospan)
        rchc.config.set(rchc.roachString,'sweeplostep', sweeplostep)
        rchc.config.set(rchc.roachString,'sweeplooffset', sweeplooffset)
        
        dqToWorker.append("PleaseDoASweep")

    def generateTone(self):
        self.tsToneGeneration = datetime.datetime.now()
        self.generatingTone = True
        try:
            loFreqHz = float(self.loFreqHz.text())
            fToneMin = float(self.fToneMin.text())        
            fToneMax = float(self.fToneMax.text())
            nTone = self.nTone.value()
        except ValueError:
            return
        gtMessage = {"loFreqHz":loFreqHz,
                     "fToneMin":fToneMin,
                     "fToneMax":fToneMax,
                     "nTone":nTone
        }
        self.generateToneState.setText("Generating Tone")
        self.generateToneState.setStyleSheet(ssColor("lightPink"))
        self.tsGenerateTone = datetime.datetime.now()
        self.iFreq.clear()
        print "FindResonancesWindow.generateTone:  gtMessage=",gtMessage
        dqToToneGenerator.append(gtMessage)

    def iFreqChanged(self, index):
        self.iFreqIndex = index
        try:
            self.iFreqResID = self.rchc.roachController.resIDs[index]
            self.iFreqFreq  = self.rchc.roachController.freqList[index]
            self.iFreqAtten = self.rchc.roachController.attenList[index]
            self.updatePlots()
        except AttributeError:
            self.iFreqResID = -1
            self.iFreqFreq = -1
            self.iFreqAtten = -1
            
    def signalFromWorker(self,data):
        #handle = open('IQDataDict.json','w')
        #json_tricks.dump(data, handle)
        #handle.close()
        self.recentIQData = data['iqData']
        self.rchc.recentIQData = self.recentIQData
        self.updatePlots()
        self.sweepState.setStyleSheet(ssColor("lightGreen"))
        self.sweepState.setText("Ready to Sweep")
        self.nSweepStep = 0
        
    def signalFromToneGenerator(self, data):
        self.generatingTone = False
        self.generateToneState.setStyleSheet(ssColor("lightGreen"))
        self.generateToneState.setText("Ready to Generate Tone")
        self.toneGenerationProgressBar.setValue(100)
        self.setIFreqItems()
        
    def whatToPlotChanged(self, index):
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.updatePlots()

    def mouseMoved(self, event):
        for i,item in enumerate(self.graphicsLayoutWidget.items()):
            if isinstance(item, pg.graphicsItems.ViewBox.ViewBox):
                sbr = item.sceneBoundingRect()
                tr = item.state['targetRange']
                qr = QRectF(QPointF(tr[0][0],tr[1][0]),\
                            QPointF(tr[0][1],tr[1][1]))
                mousePoint = item.mapSceneToView(event)
                contains = qr.contains(mousePoint)
                p = item.parentItem()
                a = p.getAxis('top')
                if contains:
                    setCursorLocationText(a, (mousePoint.x(), mousePoint.y()))
                else:
                    setCursorLocationText(a, None)
                    
    def updatePlots(self):
        # self.recentIQData is a dictionary of:  I and Q, where I and Q are 2d
        # I[iFreq][iPt] - iFreq is the frequency

        self.rchc.frw = self
        if self.recentIQData is not None:
            self.graphicsLayoutWidget.clear()

            if self.wtp == "IQ":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                setCursorLocationText(self.topPlot.getAxis('top'),None)
                self.bottomPlot = self.graphicsLayoutWidget.addPlot(1,0)
                setCursorLocationText(self.bottomPlot.getAxis('top'),None)
                self.topPlot.setXLink(self.bottomPlot)
            elif self.wtp == "MagPhase":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                setCursorLocationText(self.topPlot.getAxis('top'),None)
                self.bottomPlot = self.graphicsLayoutWidget.addPlot(1,0)
                setCursorLocationText(self.bottomPlot.getAxis('top'),None)
                self.topPlot.setXLink(self.bottomPlot)
            elif self.wtp == "LoopsAndVelocity":
                self.leftPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                setCursorLocationText(self.leftPlot.getAxis('top'),None)
                self.rightPlot = self.graphicsLayoutWidget.addPlot(0,1)
                setCursorLocationText(self.rightPlot.getAxis('top'),None)
            if self.wtp == "PeakFinder":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                setCursorLocationText(self.topPlot.getAxis('top'),None)
                
            iLists = self.recentIQData['I']
            qLists = self.recentIQData['Q']
            fLists = []
            for f in self.recentIQData['freqList']:
                fLists.append(f+self.recentIQData['freqOffsets'])
            symbolSize = int(self.symbolSize.currentText())
            pcs = "rgb"
            for index,iList,qList,fList in zip(range(len(iLists)),\
                                               iLists,qLists,fLists):
                pc = pcs[index%3]
                kwargs = {"symbol":'o',
                          "symbolSize":symbolSize,
                          "symbolBrush":pc,
                          "symbolPen":pc,
                          "pen":pc}
                if self.wtp == "IQ":
                    self.topPlot.plot(fList, iList, **kwargs)
                    self.topPlot.setLabel('left','I', 'ADUs')
                    self.topPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.bottomPlot.plot(fList, qList, **kwargs)
                    self.bottomPlot.setLabel('left','Q','ADUs')
                    self.bottomPlot.setLabel('bottom', 'Frequency', 'Hz')
                elif self.wtp == "MagPhase":
                    iq = np.array(iList) + 1j*np.array(qList)
                    amplitude = np.absolute(iq)
                    angle = np.angle(iq,deg=True)
                    self.topPlot.plot(fList, amplitude, **kwargs)
                    self.topPlot.setLabel('left','amplitude', 'ADUs')
                    self.topPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.bottomPlot.plot(fList, angle, **kwargs)
                    self.bottomPlot.setLabel('left','phase', 'degrees')
                    self.bottomPlot.setLabel('bottom', 'Frequency', 'Hz')
                elif self.wtp == "LoopsAndVelocity":
                    self.leftPlot.plot(iList, qList, **kwargs)
                    self.leftPlot.setLabel('left','Q', 'ADUs')
                    self.leftPlot.setLabel('bottom','I', 'ADUs')

                    dfs = fList[1:]-fList[:-1]
                    dis = iList[1:]-iList[:-1]
                    dqs = qList[1:]-qList[:-1]
                    vs = np.sqrt(dis*dis+dqs*dqs)/dfs
                    favgs = 0.5*(fList[1:]+fList[:-1])
                    self.rightPlot.plot(favgs, vs, **kwargs) 
                    self.rightPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.rightPlot.setLabel('left', "IQ Velocity", "ADUs/Hz")
                elif self.wtp == "PeakFinder":
                    dfs = fList[1:]-fList[:-1]
                    dis = iList[1:]-iList[:-1]
                    dqs = qList[1:]-qList[:-1]
                    vs = np.sqrt(dis*dis+dqs*dqs)/dfs
                    favgs = 0.5*(fList[1:]+fList[:-1])
                    self.topPlot.plot(favgs, vs, **kwargs) 
                    self.topPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.topPlot.setLabel('left', "IQ Velocity", "ADUs/Hz")

    def doTimer(self):
        n = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(n)[:-5]
        self.datetimeClock.setText(dText)
        # If a sweep is in progress, update the progress bar
        if self.nSweepStep == 0:
            self.sweepProgressBar.setValue(100)
        else:
            elapsedSweepTime = n - self.tsSweep
            percent = 100*elapsedSweepTime.total_seconds()
            percent /= self.expectedSweepSeconds
            self.sweepProgressBar.setValue(percent)
        # If tone generation is in progress, update toneGenerationProgressBar
        if self.generatingTone:
            try:
                elapsedToneTime = n - self.tsToneGeneration
            except AttributeError:
                print "in doTimer:  tsToneGeneration not set"
                elapsedToneTime = 0
            expectedToneTime = 120 # two minutes
            percent = 100*elapsedToneTime.total_seconds()/expectedToneTime
            self.toneGenerationProgressBar.setValue(percent)
            
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
        if value == "StopSign":
            self.keepAlive = False
        else:
            print "Worker.getSignal unknown signal:",value

    def run(self):
        while self.keepAlive:
            try:
                # Don't bother checking what the acutal message is.  Then only
                # message ever sent is "PleaseDoASweep"
                message = dqToWorker.popleft()
                self.doASweep()
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.1)
            except AttributeError:
                # protect against race condition when shutting down
                break
    def doASweep(self, verbose=True):
        if verbose: print "FindResonancesWindow.doASweep: begin"
        timestamp = datetime.datetime.now()
        rchc = self.parent.rchc
        t0 = datetime.datetime.now()
        if verbose:
            print "FindResonancesWindow.doASweep: call clTools.performIQSweep"
        iqData = clTools.performIQSweep(self.parent.rchc, \
                                        doLoopFit=False, verbose=True)
        if verbose:
            print "FindResonancesWindow.doASweep: done clTools.performIQSweep"
        t1 = datetime.datetime.now()
        dt = t1-t0
        data = {
            'timestamp':timestamp,
            'iqData':iqData
        }
        if verbose:
            print "FindResonancesWindow.doASweep: call signalFromWorker.emit"
        self.signalFromWorker.emit(data)
        if verbose:
            print "FindResonancesWindow.doASweep: done"

class ToneGenerator(QThread):
    signalFromToneGenerator = pyqtSignal(dict)
    def __init__(self, parent, verbose=False):
        QThread.__init__(self, parent)
        self.parent = parent
        self.verbose = verbose
        self.keepAlive = True
        self.parent.signalToToneGenerator.connect(self.getSignal)
        self.parent.generatingTone = False
        
    def getSignal(self, value):
        if value == "StopSign":
            print "ToneGenerator.getSignal:  value = ",value
            self.keepAlive = False
        else:
            print "ToneGenerator.getSignal unknown signal:",value

    def run(self):
        while self.keepAlive:
            try:
                message = dqToToneGenerator.popleft()
                self.generateTone(message)
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.2)
            # Protect against race condition when shutting down
            except AttributeError: 
                pass
        
    def generateTone(self, message):
        self.parent.generatingTone = True
        print "ToneGenerator.generateTone:  message=",message
        loFreqHz = message['loFreqHz']
        rchc = self.parent.rchc
        rchc.config.set(rchc.roachString, 'lo_freq', str(loFreqHz))
        #freqListIn = np.array([message['fToneHz']])
        freqListIn = np.linspace(message['fToneMin'],message['fToneMax'],
                                 message['nTone'], endpoint=False)
        print "now call clTools.setTones with freqListIn = ",freqListIn
        fullScaleFraction = 0.095
        print "WARNING:  fullScalFraction hardwired to ",fullScaleFraction
        toneData = clTools.setTones(self.parent.rchc,
                                    freqListIn = freqListIn,
                                    fullScaleFraction = fullScaleFraction)
        self.signalFromToneGenerator.emit(toneData)

def ssColor(color):
    retval = "QWidget {background-color:"
    retval += color
    retval +="; outline-color:"
    retval += color
    retval += "}"
    return retval

def setCursorLocationText(a, xy):
    #a = viewBox.parentItem().getAxis('top')
    a.style['showValues'] = False
    a.autoSIPrefix = False
    a.show()
    if xy is None:
        text = ""
    else:
        text = "%f %f"%(xy[0],xy[1])
    a.setLabel(text)
    a.showLabel()
