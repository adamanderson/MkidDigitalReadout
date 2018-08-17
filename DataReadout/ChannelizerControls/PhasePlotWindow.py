import datetime, time, os, socket
from PyQt4 import QtGui, uic
from PyQt4.QtGui import QPixmap
from PyQt4.QtCore import QThread, pyqtSignal, QTimer
import numpy as np
from collections import deque
from scipy.signal import welch
import sys
import WritePhaseData
reload(WritePhaseData)
import pdb
import pyqtgraph as pg

roachData = True
# True to read Roach data, False to test with generated events.
sFreq =1e6
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
        self.duration_value = float(self.duration.currentText())
        self.duration.currentIndexChanged.connect(self.durationChanged)
        self.runState.clicked.connect(self.doRunState)
        self.runState.setText("Running")
        self.doRunState()
        self.nPlot=5000
        # region = pg.LinearRegionItem()
        # region.setZValue(10)
        # self.topPlot.addItem(region, ignoreBounds=True)
        #self.topPlot.setAutoVisible(y=True)

        self.writeDataState.clicked.connect(self.doWriteDataState)
        self.writeDataState.setText("Writing Data")
        self.doWriteDataState()

        self.reset.clicked.connect(self.doReset)
        self.savePlot.clicked.connect(self.doSavePlot)

        self.setWindowTitle('PhasePlot')
        self.roachReader = RoachReader(self)
        self.roachReader.signalFromRoachReader.connect(self.signalFromRoachReader)
        self.roachReader.duration = float(self.duration.currentText())
        self.writer = Writer(self)

        self.horizScroll.setRange(0,1000)
        self.horizScroll.setPageStep(1000) # just to make the slider long
        self.horizScroll.setSingleStep(1)
        self.horizScroll.setTracking(True)
        self.horizScroll.valueChanged.connect(self.sliderMoved)
        
        self.plotZoom.setRange(1,100)
        self.plotZoom.setValue(100)
        self.plotZoom.valueChanged.connect(self.zoomChanged)
        
        self.plotprocessor = PlotProcessor(self)
        self.plotprocessor.signalFromProcessor.connect(self.updatePlots)

        # cursor position in the plot
        self.cursorXY.setText('')
        self.region = pg.LinearRegionItem()
        self.vLine = pg.InfiniteLine(angle=90, movable=False)
        self.hLine = pg.InfiniteLine(angle=0, movable=False)
        self.topPlot.addItem(self.vLine, ignoreBounds=True)
        self.topPlot.addItem(self.hLine, ignoreBounds=True)
        
        self.topPlot.scene().sigMouseMoved.connect(self.mouseMoved)
        self.topPlot.sigRangeChanged.connect(self.updateRegion)
        

        
	# stream data to a file to read by KST
        self.dNsamples.setText("")
        self.dNevents.setText("")

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
        self.domain = str(self.whatToPlot.currentText()).strip()
        self.whatToPlot.currentIndexChanged.connect(self.plotDomainChanged)
        self.amode = str(self.howToAve.currentText()).strip()
        self.howToAve.currentIndexChanged.connect(self.howToAveChanged)
        self.show()
        self.writer.start()
        self.streamer.start()
        self.roachReader.start()
        self.plotprocessor.start()

    def mouseMoved(self,evt):
        mousePoint = self.topPlot.vb.mapSceneToView(evt)
        self.vLine.setPos(mousePoint.x())
        self.hLine.setPos(mousePoint.y())
        if self.domain == 'time':
            self.cursorXY.setText("<span style='color: white'> t=%0.3fs  :  ph=%0.3fR </span>" %(mousePoint.x(),mousePoint.y()))
        else :
            frq=10.0**mousePoint.x()
            if frq < 1000. :
                self.cursorXY.setText("<span style='color: white'> f=%0.0fHz :  a=%0.3f </span>"%(frq,mousePoint.y()))
            else :
                self.cursorXY.setText("<span style='color: white'> f=%0.3fkHz :  a=%0.3f </span>"%(frq/1000.0,mousePoint.y()))

    def updateRegion(self,window, viewRange):
        rgn = viewRange[0]
        self.region.setRegion(rgn)
        

    def sliderMoved(self):
        self.signalToProcessor.emit({'slider':self.horizScroll.value()})

    def zoomChanged(self) :
        zmval= self.plotZoom.value()
        # just to make the lenth of the slider propotional to zoom factor, kind of works.
        pgstep=1000*float(zmval)/100  
        self.horizScroll.setPageStep(pgstep)
        
        self.signalToProcessor.emit({'zoom':zmval})
        
    def doSavePlot(self) :
        cwd=os.getcwd()
        p = QPixmap.grabWindow(self.winId())
        tn=datetime.datetime.now()
        filename="img_"+"{:%Y-%m-%d-%H:%M:%S.%f}".format(tn)[:-7]+".png"
        filename=os.path.join(cwd,filename)
        p.save(filename, 'png')
        print  "saved to file: %s"%filename 
        
        
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
        self.signalToProcessor.emit({'Stop':'stop'})
        self.timer.stop()        
        self.close()
        
    def doReset(self):
        self.signalToProcessor.emit({"reset":'reset'})

    def durationChanged(self, index):
        self.duration_value = float(self.duration.itemText(index))
    
        self.signalToRoachReader.emit("duration %f"%self.duration_value)
        self.signalToProcessor.emit({"duration":self.duration_value})
  #      self.processData()

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
        self.signalToProcessor.emit({"reset":'reset'})
        
    def signalFromWorker(self,dict):
        # The dict is defined as "dictToEmit" in the function "run" of the class "Worker
        pass
    
    def signalFromRoachReader(self,dict):
        pass
    
    def plotDomainChanged(self, index):
        self.domain = str(self.whatToPlot.currentText()).strip()
        self.signalToProcessor.emit({'domain':self.domain})

    def howToAveChanged(self, index):
        self.amode = str(self.howToAve.currentText()).strip()
        self.signalToProcessor.emit({'amode':self.amode})

    def processData(self):
        # self.recentPhases is a dictionary of:  phases
        prDict={'amode':self.amode}
        self.signalToProcessor.emit(prDict)

    def updatePlots(self,prcsEvts):

        self.domain = str(prcsEvts['domain'])
        self.mode = str(prcsEvts['mode'])
        self.yvalues = prcsEvts['Yvalues']
        self.xvalues = prcsEvts['Xvalues']
        self.nEvts=prcsEvts['nEvts']
        self.dNevents.setText(str(self.nEvts))
        
        if self.yvalues is not None:
            self.topPlot.clear()
            if self.domain == 'time':   
                self.topPlot.setLogMode(False, None)
                self.topPlot.plot(self.xvalues,self.yvalues)
                self.topPlot.setLabel('left','radians')
                self.topPlot.setLabel('bottom','seconds')
                
            elif self.domain == "frequency":
                self.topPlot.setLogMode(True, None)
                dbcPerHz = 10.0*np.log10(self.yvalues)
                self.topPlot.plot(self.xvalues,dbcPerHz)
                self.topPlot.setLabel('left','dBc/Hz')
                self.topPlot.setLabel('bottom','frequency (Hz)')
    

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
        self.duration = self.parent.duration_value
        self.Nevents=int(sFreq*self.duration)

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
            self.Nevents=int(sFreq*self.duration)

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
                    # generate test data for debugging
                    tBegin=time.time()
                    freqChan = 10          # some arbitary vales for generated data, 
                    freqs =range(100,150)  # some arbitary vales for generated data, 
                    timestamp = datetime.datetime.now()
                    duration = self.duration
                    Nevents=self.Nevents
                    a=np.linspace(0.,duration,Nevents)
                    phases=10*np.random.randn(Nevents)+5.0*np.sin(100*np.pi*a)
                    tEnd=time.time()
                    tWait=duration-(tEnd-tBegin)
                    if tWait > 0 :
                        time.sleep(tWait)
                    
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

                #  write data to queue for streaming        
                if self.parent.stream2KST == True :
                    dqs.append({"phases":phases})

                #  write data to queue forfor plotting    
                dqToProcessor.append({"phases":phases,"duration":duration})
                self.parent.dNsamples.setText(str(len(phases)))

                nIter += 1
                time.sleep(0.1)
            else:
                pass
                
            label = str(nIter)+ ' : ' + str(nLoop)
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
        print "Streamer.getSignal:  value =",value
        if value == "Stop":
            self.keepStreamAlive=False

    def run(self):
        while self.keepStreamAlive is True:
            if self.parent.stream2KST is True :
                while len(dqs) > 0:
                    sdata = dqs.pop()
                    dphases = sdata['phases']
                    phaseEnd=dphases[:10000]
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
        self.mode = 'none'   # none, cma or ema
        self.duration=self.parent.duration_value
        self.nEma = 0
        self.nCma = 0
        self.Nevents=sFreq*self.duration
        self.sliderPos = 0
        self.zoomVal = 1
        
        self.keepAlive = True

        self.parent.signalToProcessor.connect(self.getSignal)
        
    def getSignal(self, pdict):
        if 'domain' in pdict:
            self.domain = str(pdict['domain'])
            self.reset()
        if 'amode' in pdict :
            self.mode = str(pdict['amode'])
            self.reset()
        if 'duration' in pdict :
            self.duration = float(pdict['duration'])
            self.Nevents=sFreq*self.duration
            self.reset()
        if 'Stop' in pdict :
            self.keepAlive = False 
        if 'reset' in pdict:
            self.reset()
        if 'slider' in pdict:
            self.sliderPos = float(pdict['slider'])/1000

        if 'zoom' in pdict :
            self.zoomVal = float(pdict['zoom'])/100                               
            
            
       
    def reset(self):
        self.nEma=0
        self.nCma = 0
        self.cma=0
        self.ema=0


    def calcCMA(self,x):  # cumulative moving average
        if self.nCma == 0:
            self.cma = x
            self.nCma += 1
        else:
            try :
                self.cma = (x + self.nCma*self.cma)/(self.nCma+1)
                self.nCma += 1
            except :
                err = sys.exc_info()[0]
                print err
        return self.cma, self.nCma
    
    def calcEMA(self,x):  # cumulative moving average
        if self.nEma == 0:
            self.ema = x
            self.nEma += 1
        else:
            try :
                self.ema = self.alpha*x+ (1.0-self.alpha)*self.ema
                self.nEma += 1
            except :
                err = sys.exc_info()[0]
                print err
                
        return self.ema, self.nEma 
                    
    def run(self):
        while self.keepAlive:
            while(len(dqToProcessor) > 1) : 
                phaseData = dqToProcessor.pop()
                timeDomainData = phaseData["phases"]
                durationData  = phaseData["duration"]

                if durationData == self.duration :
                    # make data was taken with the latest value for duration
                    #given in GUI. Otherwise will crash when calculating averages
                    nevtsPlot=int(0.9*self.Nevents)
                    if len(timeDomainData) > nevtsPlot :
                        plotData=timeDomainData[:nevtsPlot]

                        self.alpha=0.1
                          
                        retval = {
                            "domain":self.domain,
                            "mode":self.mode,
                            }
                          
                        retval=[]
                        frqs=[]
                        if self.domain == 'time':
                            x = plotData              
                            if self.mode == 'none':
                                retval = x
                                nEvts=1
                            elif self.mode == 'cma':
                                
                                retval, nEvts = self.calcCMA(plotData)         
                            
                            elif self.mode == 'ema':
                                
                                retval, nEvts = self.calcEMA(plotData)   
                            else:    
                                raise ValueError('teach me how to deal with mode =',self.mode)
                                   
                        elif self.domain == 'frequency':
                            x =  plotData
                            fs = sFreq
                            window = 'hanning'
                            nperseg = len(x)
                            noverlap = 0
                            nfft = None
                            detrend = 'constant'
                            frqs,pxx = welch(x,fs,window,nperseg,noverlap,nfft,detrend,scaling='spectrum')
                            if self.mode == 'none':
                                retval = pxx
                                nEvts=1
                                
                            elif self.mode == 'cma':
                                retval, nEvts = self.calcCMA(pxx)
                                
                            elif self.mode == 'ema':
                                retval, nEvts = self.calcEMA(pxx)   
                                
                            else:    
                                raise ValueError("teach me how to deal with mode =",self.mode)
                        else:
                            raise ValueError("teach me how to deal with domain =",self.domain)
                        
                        if len(retval) > 0:
                            nPlot=self.parent.nPlot
                            nValues=len(retval)
                            plValues=max(nPlot,int(nValues*self.zoomVal))
                            sValue=int(self.sliderPos*(nValues-plValues))

                        
                            I=np.arange(sValue,sValue+plValues,int(plValues/nPlot))

                            
                            plotValues=retval[I]
                            if self.domain == "frequency":
                                plotX=frqs[I]
                            else:
                                tvalues=np.linspace(0,self.duration,nValues)
                                plotX = tvalues[I]
                            
                            retdict=({"domain":self.domain,"mode":self.mode,"Yvalues":plotValues,"Xvalues":plotX,
                                      "nEvts":nEvts})
                            self.signalFromProcessor.emit(retdict)
            time.sleep(.1)                

if __name__ == "__main__":
    roachData=False # True to read Roach data, False to test with generated events.
    
    app = QtGui.QApplication(sys.argv)
    rchc=100
    
    phasePlotWindow = PhasePlotWindow(rchc)
    phasePlotWindow.show()
    sys.exit(app.exec_())
    
 
