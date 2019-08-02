import glob, os, pickle
import numpy as np
from numpy.polynomial.polynomial import Polynomial
import unpackOneFramesFile
reload(unpackOneFramesFile)

class FluxRamp():
    def __init__(self, name, dataDir, if0=0, if1=1e9, loadPklFromDisk = True):
        """
        name -- a useful name for this data set
        dataDir -- where to find the .bin files
        """
        self.name = name
        self.dataDir = dataDir
        self.binFnList = glob.glob("%s/*bin"%self.dataDir)
        self.binFnList.sort()
        self.binFnList = self.binFnList[if0:if1]
        self.allSyncTimes = None
        self.syncInfoFn = "syncInfo-%s.pkl"%self.name
        if os.path.exists(self.syncInfoFn) & loadPklFromDisk:
            self.syncInfo = pickle.load(open(self.syncInfoFn,'rb'))
        else:
            self.syncInfo = None
            
    def getSyncInfo(self):
        """
        unpack everything

        return:  dictionary indexed by channel number
        """
        if self.syncInfo is None:
            l_allSyncTimes = []
            l_allSyncChannels = []
            
            l_allPhaseTimes = []
            l_allPhaseChannels = []
            l_allPhases = []
            for iFile,fileName in enumerate(self.binFnList):
                print iFile,len(self.binFnList),
                rv = unpackOneFramesFile.unpackOneFramesFile(fileName)
                l_allSyncTimes.append(rv['syncTimes'])
                l_allSyncChannels.append(rv['syncChannels'])
                l_allPhaseTimes.append(rv['times'])
                l_allPhaseChannels.append(rv['channels'])
                l_allPhases.append(rv['phases'])
            print "now call _ltoa on lists"
            allSyncTimes = _ltoa(l_allSyncTimes)
            allSyncChannels = _ltoa(l_allSyncChannels).astype(int)
            allPhaseTimes = _ltoa(l_allPhaseTimes)
            allPhaseChannels = _ltoa(l_allPhaseChannels)
            allPhases = _ltoa(l_allPhases)
            self.syncInfo = {}
            st0 = allSyncTimes[0]
            print "sort by channel"
            for channel in np.unique(allSyncChannels):
                if channel > 0:
                    print "channel =",channel
                    sic = {}
                    self.syncInfo[channel] = sic

                    inds = np.where(allSyncChannels == channel)[0]
                    st = allSyncTimes[inds]-st0
                    sic['syncTimes'] = st
                    x = np.arange(len(inds))
                    fit = Polynomial.fit(x, st, 1)
                    n = fit.domain[1]
                    x,yFit = fit.linspace(n=n+1)
                    resid = st-yFit
                    syncFreq = 1/fit.convert().coef[1]
                    sic['fit'] = fit                
                    sic['syncTimesFit'] = yFit
                    sic['syncFreq'] = syncFreq

                    inds = np.where(allPhaseChannels == channel)[0]
                    sic['phaseTimes'] = allPhaseTimes[inds] - st0
                    sic['phases'] = allPhases[inds]
            print "write", self.syncInfoFn
            
            pickle.dump(self.syncInfo,open(self.syncInfoFn,'wb'))
        return self.syncInfo

    def getTrace(self, channel, ist, fraction = 0.8, fractionOffset=0):
        syncInfo = self.syncInfo
        syncTimesFit = syncInfo[channel]['syncTimesFit']
        dt = syncTimesFit[1]-syncTimesFit[0]
        phaseTimes = syncInfo[channel]['phaseTimes']
        phases = syncInfo[channel]['phases']
        tMin = syncTimesFit[ist] - fraction*dt/2.0 + fractionOffset*dt
        tMax = syncTimesFit[ist] + fraction*dt/2.0 + fractionOffset*dt
        inds = np.where( (phaseTimes > tMin) & (phaseTimes < tMax) )
        tracePhaseTimes = phaseTimes[inds]-syncTimesFit[ist]
        tracePhases = phases[inds]
        return tracePhaseTimes,tracePhases, dt, tMin, tMax, syncTimesFit[ist]

                                            
def _ltoa(l):
    n = 0
    for a in l: n += len(a)
    retval = np.empty(n)
    i0 = 0
    for a in l:
        i1 = i0 + len(a)
        retval[i0:i1] = a
        i0 = i1
    return retval
