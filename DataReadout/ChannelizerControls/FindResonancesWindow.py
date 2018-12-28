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
print "FindResonancesWindow:  done with import and reloads"

dqToWorker = deque()
dqToToneGenerator = deque()

import pyqtgraph as pg
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

class FindResonancesWindow(QtGui.QMainWindow):
    signalToWorker = pyqtSignal(str)
    signalToToneGenerator = pyqtSignal(str)
    def __init__(self, rchc, iqLoopData=None):
        super(FindResonancesWindow,self).__init__()
        self.stopping = False
        self.iqData = None
        self.rchc = rchc
        thisDir = os.path.dirname(os.path.abspath(__file__))
        uic.loadUi(os.path.join(thisDir,'FindResonancesWidget.ui'), self)

        self.vPen = pg.mkPen(color='r', style=QtCore.Qt.DashLine)
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

        self.generateTonesState.clicked.connect(self.generateTones)
        self.generateTonesState.setStyleSheet(ssColor("lightGreen"))
        self.generateTonesState.setText("Ready to Generate Tones")
        
        self.worker = Worker(self)
        self.worker.signalFromWorker.connect(self.signalFromWorker)
        self.worker.start()

        self.toneGenerator = ToneGenerator(self)
        self.toneGenerator.signalFromToneGenerator.connect(self.signalFromToneGenerator)
        self.toneGenerator.start()

        self.timer=QTimer()
        self.timer.timeout.connect(self.doTimer)
        self.timer.start(200)

        self.setIFreqItems()

        self.concatenate.stateChanged.connect(self.updatePlots)
        self.iFreq.currentIndexChanged.connect(self.iFreqChanged)
        self.iFreq.setCurrentIndex(0)
        self.iFreqChanged(0)
        self.recentIQData = iqLoopData
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.whatToPlotChanged)

        self.nStep.valueChanged.connect(self.updateNStep)
        self.updateNStep()
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
                items.append("%4d %s %5.1f"%(resID, "{:,}".format(resFreq),atten))
            self.iFreq.addItems(items)
        except AttributeError: # If nothing is defined in the roachController
            pass
            
    def getNStepFromGui(self):
        nStep = self.nStep.value()
        return nStep

    def updateNStep(self):
        try:
            freqList = np.sort(self.rchc.roachController.freqList)
        except AttributeError:
            freqList = []
        if len(freqList) > 1:
            dfMax = (freqList[1:]-freqList[:-1]).max()
        else:
            dfMax = 1e6
        nStepNoOverlap = float(self.getNStepFromGui())
        sweeplospanNoOverlap = dfMax
        sweeplostep = sweeplospanNoOverlap/nStepNoOverlap
        nOverlap = float(self.nOverlap.value())
        sweeplospan = sweeplospanNoOverlap + nOverlap*sweeplostep
        self.rchc.config.set(self.rchc.roachString, "sweeplospan",str(sweeplospan))
        self.rchc.config.set(self.rchc.roachString, "sweeplostep",str(sweeplostep))
        msg = "df = %.1f kHz"%(sweeplostep/1000.0)
        self.df.setText(msg)
        sec = (nStepNoOverlap+nOverlap)*0.4 # Expect 0.4 seconds per sweep step
        msg = "sec/scan = %.1f"%sec
        self.secPerSweep.setText(msg)
        # used to update self.sweepProgressBar
        self.expectedSweepSeconds = sec
        self.nSweepStepToDo = nStepNoOverlap+nOverlap

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
            self.signalToToneGenerator.emit("PleaseStop")
            self.timer.stop()
            self.close()

    def doSweep(self):
        self.tsSweep = datetime.datetime.now()
        dText = "{:%Y-%m-%d %H:%M:%S.%f}".format(self.tsSweep)[:-5]
        self.callIQTakeAvgTime.setText(dText)
        self.nSweepStep = self.nSweepStepToDo # Set this to non-zero to tell the timer to keep score
        self.sweepState.setText("Sweeping %d steps"%(int(self.nSweepStep)))
        self.sweepState.setStyleSheet(ssColor("lightPink"))
        self.sweepProgressBar.setValue(0)                        
        dqToWorker.append("PleaseDoASweep")

    def generateTones(self):
        self.tsToneGeneration = datetime.datetime.now()
        self.generatingTones = True
        fMin = self.fMin.value()
        fMax = self.fMax.value()
        nTones = int(self.nTones.currentText())
        gtMessage = {"fMin":fMin, "fMax":fMax, "nTones":nTones}
        self.generateTonesState.setText("Generating Tones")
        self.generateTonesState.setStyleSheet(ssColor("lightPink"))
        self.tsGenerateTones = datetime.datetime.now()
        self.iFreq.clear()
        print "FindResonancesWindow.generateTones:  gtMessage=",gtMessage
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
        print "FindResonancesWindow.signalFromToneGenerator:  data.keys() =",data.keys()
        self.generatingTones = False
        self.generateTonesState.setStyleSheet(ssColor("lightGreen"))
        self.generateTonesState.setText("Ready to Generate Tones")
        self.toneGenerationProgressBar.setValue(100)
        self.setIFreqItems()
        
    def whatToPlotChanged(self, index):
        self.wtp = str(self.whatToPlot.currentText()).strip()
        self.updatePlots()

    def updatePlots(self):
        # self.recentIQData is a dictionary of:  I and Q, where I and Q are 2d
        # I[iFreq][iPt] - iFreq is the frequency

        # repackage this with cltools.concatenateSweep for I, Q, and freqs
        print "FindResonancesWindow.updatePlots"
        concatenate = self.concatenate.isChecked()
        print "FindResonancesWindow.updatePlots concatenate=",concatenate
        if self.recentIQData is not None:
            self.graphicsLayoutWidget.clear()

            if self.wtp == "IQ":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                self.bottomPlot = self.graphicsLayoutWidget.addPlot(1,0)
            elif self.wtp == "MagPhase":
                self.topPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                self.bottomPlot = self.graphicsLayoutWidget.addPlot(1,0)
            elif self.wtp == "LoopVelocity":
                self.leftPlot =    self.graphicsLayoutWidget.addPlot(0,0)
                self.rightPlot = self.graphicsLayoutWidget.addPlot(0,1)
                
            if concatenate:
                print "updatePlots: call concatenate with continuousIQ=False"
                catIQData = clTools.concatenateSweep(self.recentIQData, continuousIQ=False)
                iLists = [catIQData['I']]
                qLists = [catIQData['Q']]
                fLists = [catIQData['freqs']]
            else:
                iLists = self.recentIQData['I']
                qLists = self.recentIQData['Q']
                fLists = []
                for f in self.recentIQData['freqList']:
                    fLists.append(f+self.recentIQData['freqOffsets'])
            for iList,qList,fList in zip(iLists,qLists,fLists):
                if self.wtp == "IQ":
                    self.topPlot.plot(fList, iList, symbol='o', symbolPen='k', pen='k')
                    self.topPlot.setLabel('left','I', 'ADUs')
                    self.topPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.bottomPlot.plot(fList, qList, symbol='o', symbolPen='k', pen='k')
                    self.bottomPlot.setLabel('left','Q','ADUs')
                    self.bottomPlot.setLabel('bottom', 'Frequency', 'Hz')
                elif self.wtp == "MagPhase":
                    iq = np.array(iList) + 1j*np.array(qList)
                    amplitude = np.absolute(iq)
                    angle = np.angle(iq,deg=True)
                    self.topPlot.plot(fList, amplitude, symbol='o', symbolPen='k', pen='k')
                    self.topPlot.setLabel('left','amplitude', 'ADUs')
                    self.topPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.bottomPlot.plot(fList, angle, symbol='o', symbolPen='k', pen='k')
                    self.bottomPlot.setLabel('left','phase', 'degrees')
                    self.bottomPlot.setLabel('bottom', 'Frequency', 'Hz')
                elif self.wtp == "LoopVelocity":
                    self.leftPlot.plot(iList, qList, symbol='o', symbolPen='k', pen='k')
                    self.leftPlot.setLabel('left','Q', 'ADUs')
                    self.leftPlot.setLabel('bottom','I', 'ADUs')

                    dfs = fList[1:]-fList[:-1]
                    dis = iList[1:]-iList[:-1]
                    dqs = qList[1:]-qList[:-1]
                    vs = np.sqrt(dis*dis+dqs*dqs)/dfs
                    favgs = 0.5*(fList[1:]+fList[:-1])
                    self.rightPlot.plot(favgs, vs, symbol='o', symbolPen='k', pen='k')
                    self.rightPlot.setLabel('bottom', 'Frequency', 'Hz')
                    self.rightPlot.setLabel('left', "IQ Velocity", "ADUs/Hz")
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
        # If tone generation is in progress, update toneGenerationProgressBar
        if self.generatingTones:
            elapsedToneTime = n - self.tsToneGeneration
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
        if value == "PleaseStop":
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
        if verbose: print "FindResonancesWindow.doASweep: call clTools.performIQSweep"
        iqData = clTools.performIQSweep(self.parent.rchc, doLoopFit=False, verbose=True)
        if verbose: print "FindResonancesWindow.doASweep: call back from performIQSweep"
        t1 = datetime.datetime.now()
        dt = t1-t0
        data = {
            'timestamp':timestamp,
            'iqData':iqData
        }
        if verbose: print "FindResonancesWindow.doASweep: call signalFromWorker.emit"
        self.signalFromWorker.emit(data)
        if verbose: print "FindResonancesWindow.doASweep: done"

class ToneGenerator(QThread):
    signalFromToneGenerator = pyqtSignal(dict)
    def __init__(self, parent, verbose=False):
        QThread.__init__(self, parent)
        self.parent = parent
        self.verbose = verbose
        self.keepAlive = True
        self.parent.signalToToneGenerator.connect(self.getSignal)
        self.parent.generatingTones = False
        
    def getSignal(self, value):
        if value == "PleaseStop":
            self.keepAlive = False
        else:
            print "ToneGenerator.getSignal unknown signal:",value

    def run(self):
        while self.keepAlive:
            try:
                message = dqToToneGenerator.popleft()
                self.generateTones(message)
                dqToWorker.clear()
            except IndexError:
                time.sleep(0.2)
            except AttributeError: # Protect against race condition when shutting down
                time.sleep(0.1)
        
    def generateTones(self, message):
        self.parent.generatingTones = True
        print "ToneGenerator.generateTones:  message=",message
        freqListIn = np.linspace(message['fMin']*1e9, message['fMax']*1e9, num=message['nTones'],
                                 endpoint=False)
        toneData = clTools.setTones(self.parent.rchc, freqListIn = freqListIn)
        self.signalFromToneGenerator.emit(toneData)

def ssColor(color):
    retval = "QWidget {background-color:"
    retval += color
    retval +="; outline-color:"
    retval += color
    retval += "}"
    return retval
