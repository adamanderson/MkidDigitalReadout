import glob
import numpy as np
from numpy.polynomial.polynomial import Polynomial
import unpackOneFramesFile
reload(unpackOneFramesFile)

class FluxRamp():
    def __init__(self, name, dataDir):
        self.name = name
        self.dataDir = dataDir
        self.binFnList = glob.glob("%s/*bin"%self.dataDir)
        self.binFnList.sort()
        self.allSyncTimes = None
        self.syncInfo = None

    def getSyncInfo(self):
        if self.syncInfo is None:
            allSyncTimes = np.empty(0)
            allSyncChannels = np.empty(0)
            allPhases = np.empty(0)
            allChannels = np.empty(0)
            allTimes = np.empty(0)
            for iFile,fileName in enumerate(self.binFnList):
                rv = unpackOneFramesFile.unpackOneFramesFile(fileName)
                allSyncTimes = np.append(allSyncTimes,rv['syncTimes'])
                allSyncChannels = np.append(allSyncChannels,rv['syncChannels'])
                
                allPhases = np.append(allPhases,rv['phases'])
                allChannels = np.append(allChannels,rv['channels'])
                allTimes =  np.append(allTimes,rv['times'])
            self.allSyncTimes = allSyncTimes
            self.allSyncChannels = allSyncChannels

            self.syncInfo = {}
            st0 = allSyncTimes[0]
            for channel in np.unique(allSyncChannels):                
                self.syncInfo[channel] = {}


                inds = np.where(allChannels == channel)[0]
                t = allTimes[inds] - st0
                self.syncInfo[channel]['times'] = t
                self.syncInfo[channel]['phases'] = allPhases[inds]

                inds = np.where(allSyncChannels == channel)[0]
                st = allSyncTimes[inds]-st0
                self.syncInfo[channel]['syncTimes'] = st
                x = np.arange(len(inds))
                fit = Polynomial.fit(x, st, 1)
                n = fit.domain[1]
                x,yFit = fit.linspace(n=n+1)
                resid = st-yFit
                syncFreq = 1/fit.convert().coef[1]
                self.syncInfo[channel]['fit'] = fit                
                self.syncInfo[channel]['syncTimes-fit'] = resid
                self.syncInfo[channel]['syncFreq'] = syncFreq
            return self.syncInfo
