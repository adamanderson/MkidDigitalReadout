import datetime, json_tricks, os, pickle, sys, time, warnings
from PyQt5 import QtGui, uic, QtCore
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, QRectF, QPointF
import numpy as np
from collections import deque
import H5IO
reload(H5IO)
import clTools
reload(clTools)
import LoopFitter
reload(LoopFitter)
from scipy.signal import decimate

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
        self.setWindowTitle('PlotPhaseStream')
        
        self.stop.clicked.connect(self.doStop)
        self.stop.setStyleSheet(ssColor("red"))

        self.streamState.clicked.connect(self.doStream)
        self.streamState.setStyleSheet(ssColor("lightGreen"))
        self.streamState.setText("Ready to Stream")

        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)
        print "init:  self.wtp =",self.wtp

        self.streamProgressBar.setMinimum(0)
        self.streamProgressBar.setMaximum(100)
        self.streamProgressBar.setValue(100)
        self.doingStream = False

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

        self.nMaxToPlot.currentIndexChanged.connect(self.updatePlots)
        self.symbolSize.currentIndexChanged.connect(self.updatePlots)
        self.iFreq.currentIndexChanged.connect(self.iFreqChanged)
        self.iFreq.setCurrentIndex(0)
        self.iFreqChanged(0)
        try:
            phaseStreamData = rchc.recentPhaseStreamData
            try:
                duration = rchc.recentPhaseStreamData['duration']
            except:
                duration = 1.0
            self.duration.setValue(duration)
        except AttributeError:
            phaseStreamData = None

        self.recentPhaseStreamData = phaseStreamData
            

        self.graphicsLayoutWidget.scene().sigMouseMoved\
                                         .connect(self.mouseMoved)
        self.previousPlotState = None

        self.show()

        try:
            recentPhaseStreamData = self.rchc.recentPhaseStreamData
        except AttributeError:
            pass
        else:
            # plot the "old" recentIQData
            self.recentPhaseStreamData = recentPhaseStreamData
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

    def doStream(self):
        self.tsStream = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(self.tsStream)[:-5]
        self.callGetPhaseStreamTime.setText(dText)
        duration = self.duration.value()
        channel = self.iFreq.currentIndex()
        self.expectedDuration = duration
        self.doingStream = True # Set to True to tell the timer to keep score
        self.streamState.setText("Streaming for %.2f sec"%(duration))
        self.streamState.setStyleSheet(ssColor("lightPink"))
        self.streamProgressBar.setValue(0)

        # Set values in rchc.config, which is what clTools.performIQSweep uses
        rchc = self.rchc
        dqToWorker.append({"duration":duration, "channel":channel})

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
            
    def signalFromWorker(self, phaseStreamData):
        self.recentPhaseStreamData = phaseStreamData
        self.rchc.recentPhaseStreamData = self.recentPhaseStreamData
        self.updatePlots()
        self.streamState.setStyleSheet(ssColor("lightGreen"))
        self.streamState.setText("Ready to Stream")
        self.doingStream = False
        
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
        # self.recentPhaseStreamData generated by clTools.getPhaseStream
        # is a dictionary of:  data, channel, resID, duration, t0, t1

        self.rchc.frw = self
        if self.recentPhaseStreamData is not None:
            self.graphicsLayoutWidget.clear()

            if self.wtp == "phases":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                setCursorLocationText(self.topPlot.getAxis('top'),None)
                
            phases = self.recentPhaseStreamData['data']
            symbolSize = int(self.symbolSize.currentText())

            pc = 'b'
            kwargs = {"symbol":'o',
                      "symbolSize":symbolSize,
                      "symbolBrush":pc,
                      "symbolPen":pc,
                      "pen":pc}
            if self.wtp == "phases":
                nMaxToPlot = int(float(self.nMaxToPlot.currentText()))
                downsamplingFactor = 1 + (len(phases)/nMaxToPlot)
                print "len(phases) =",len(phases)
                print "nMaxToPlot=",nMaxToPlot
                print "downsamplingFactor=",downsamplingFactor
                self.downsamplingFactor.setText(str(downsamplingFactor))
                if downsamplingFactor == 1:
                    times = 1e-6*np.arange(len(phases))
                    self.topPlot.plot(times, phases, **kwargs)
                else:
                    print datetime.datetime.now(),"begin decimate"
                    dPhases = decimate(phases, downsamplingFactor)
                    print datetime.datetime.now(),"ended decimate"
                    dTimes = 1e-6*downsamplingFactor*np.arange(len(dPhases))
                    self.topPlot.plot(dTimes, dPhases, **kwargs)
                                                    
                self.topPlot.setLabel('bottom', 'time', 's')
                self.topPlot.setLabel('left', "phase", "radians")

    def doTimer(self):
        n = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(n)[:-5]
        self.datetimeClock.setText(dText)
        # If a sweep is in progress, update the progress bar
        if not self.doingStream:
            self.streamProgressBar.setValue(100)
        else:
            elapsedSweepTime = (n - self.tsStream).total_seconds()
            percent = 100*elapsedSweepTime/self.expectedDuration
            self.streamProgressBar.setValue(percent)
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
        if value == "StopSign":
            self.keepAlive = False
        else:
            print "Warning:  Worker.getSignal unknown signal:",value

    def run(self):
        while self.keepAlive:
            try:
                message = dqToWorker.popleft()
                channel = message['channel']
                duration = message['duration']
                self.doAStream(channel, duration)
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.1)
            except AttributeError:
                # protect against race condition when shutting down
                break
    def doAStream(self, channel, duration, verbose=False):
        if verbose: print "PlotPhaseStreamWindow.doAStream: begin",channel, duration
        timestamp = datetime.datetime.now()
        rchc = self.parent.rchc
        if verbose:
            print "PlotPhaseStreamWindow.doAStream: began clTools.getPhaseStream"
        streamData = clTools.getPhaseStream(self.parent.rchc, channel=channel, duration=duration)
        if verbose:
            print "PlotPhaseStreamWindow.doAStream: ended clTools.getPhaseStream"
        self.signalFromWorker.emit(streamData)
        if verbose:
            print "PlotPhaseStreamWindow.doAStream: done"

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
            self.keepAlive = False
        else:
            print "Warning:  ToneGenerator.getSignal unknown signal:",value

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
