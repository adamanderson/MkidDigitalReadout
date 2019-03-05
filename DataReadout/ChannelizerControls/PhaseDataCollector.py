import datetime, os, pickle
import clTools
from PyQt5.QtCore import QTimer

class PhaseDataCollector():
    def __init__(self, rchc, channel):
        self.rchc = rchc
        self.channel = channel
        self.tThread = QTimer()
        self.tThread.timeout.connect(self.tick)
    def go(self, nTick, tickPeriod, duration, baseName, stride=100):
        self.stride = stride
        self.baseName = baseName
        self.pdcFileName = baseName+"-pdc.pkl"
        if os.path.exists(self.pdcFileName):
            raise OSError("File exists %s"%self.pdcFileName)
        self.nDone = 0
        self.iTick = 0
        self.nTick = nTick
        self.duration = duration
        self.phases = []
        self.t0s = []
        self.tick()
        self.tThread.start(tickPeriod)
    def tick(self):
        if self.iTick <= 2:
            print "iTick = ",self.iTick,datetime.datetime.now()
        streamData = clTools.getPhaseStream(self.rchc, self.channel, self.duration)
        self.t0s.append(streamData['t0'])
        self.phases.append(streamData['data'].mean())
        self.iTick += 1
        print self.iTick,self.nTick,self.t0s[-1],self.phases[-1]
        #print self.iTick%stride
        if self.iTick >= self.nTick:
            print "done:  now write",self.pdcFileName
            self.tThread.stop()
            d = {"t0s":self.t0s,"phases":self.phases,"duration":self.duration,"channel":self.channel}
            pickle.dump(d,open(self.pdcFileName,'wb'))            
        elif self.iTick%self.stride == 0:
            d = {"t0s":self.t0s,"phases":self.phases,"duration":self.duration,"channel":self.channel}
            fn = "%s-%05d-pdc.pkl"%(self.baseName,self.iTick/self.stride)
            print "now write fn =",fn
            pickle.dump(d,open(fn,'wb'))
            fn = "%s-%05d-streamData.pkl"%(self.baseName,self.iTick/self.stride)
            print "now write fn =",fn
            pickle.dump(streamData,open(fn,'wb'))
            self.phases = []
            self.t0s = []
            
