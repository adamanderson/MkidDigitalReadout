import glob, os, pickle
import numpy as np
from numpy.polynomial.polynomial import Polynomial
import scipy.optimize

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
                    print("fit.coef=",fit.coef)
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
    
    def plotResidualVsTSync(self, channel, n):
        import matplotlib.pyplot as plt
        st  = self.syncInfo[channel]['syncTimes'][:n]
        stf = self.syncInfo[channel]['syncTimesFit'][:n]
        tmf = st - stf
        plt.scatter(stf, tmf, s=1, c='midnightblue')
        #plt.plot(stf,tmf,'o', color='midnightblue')
        #plt.plot(stf,tmf,'-', color='blue',alpha=0.1)
        dstf = stf[1]-stf[0]
        #plt.axhline(dstf/2.0, color='r')
        #plt.axhline(-dstf/2.0, color='r')
        plt.xlabel("syncTimesFit (sec)")
        plt.ylabel("syncTimes - syncTimesFit (sec)")
        plt.title("%s   channel=%d  n=%d"%(self.name, channel, n))
        plt.savefig("%s-residualVsTSync.png"%self.name,dpi=600)
   
    def phiPrepare(self, channel, ist, doPlot=True):
        t, p, dt, tMin, tMax, stf = self.getTrace(channel, ist, fraction=2.0, fractionOffset=0.0)
        dp = np.power(p[1:]-p[:-1],2)
        ndp = len(dp)
        at = 0.5*(t[1:]+t[:-1])
        syncFreq = self.syncInfo[channel]['syncFreq']
        arg0 = np.argmax(dp[:ndp//2])
        offset = at[arg0] - 1.0/syncFreq
        arg1 = np.argmax(dp[ndp//2:])+ndp//2
        offset0 = at[arg0] + 1/syncFreq/2.
        offset1 = at[arg1] - 1/syncFreq/2.
        fractionOffset = 0.5*(offset0+offset1)*syncFreq
        ts, ps, dts, tMins, tMaxs, stfs = self.getTrace(channel, ist, 
                                                        fraction=0.95, fractionOffset=fractionOffset)
        fitSine = fit_sin(ts,ps)
        self.syncInfo[channel]['rampFreq'] = fitSine['freq']
        self.syncInfo[channel]['fractionOffset'] = fractionOffset
        self.syncInfo[channel]['rCos'] = np.cos(2*np.pi*ts*fitSine['freq'])
        self.syncInfo[channel]['rSin'] = np.sin(2*np.pi*ts*fitSine['freq'])
                                                
        if doPlot:
            import matplotlib.pyplot as plt
            fig,ax = plt.subplots(2,1,sharex=True)
            ax[0].plot(at,dp)
            ax[0].axvline(0, color='r', linestyle=":")
            ax[0].axvline(-1/syncFreq/2.0, c='r', alpha=0.4)
            ax[0].axvline( 1/syncFreq/2.0, c='r', alpha=0.4)
            ax[0].plot(at[arg0],dp[arg0],'rx')
            ax[0].plot(at[arg1],dp[arg1],'rx')
            ax[0].set_ylabel("$(\Delta \Theta)^2$")
            ax[1].plot(t,p, label="all")
            ax[1].plot(ts,ps, label="selected")
            ax[1].plot(ts, fitSine['fitfunc'](ts), color='r',alpha=0.7, label='fit sine')
            ax[1].set_ylabel('$\Theta$')
            ax[1].legend()
            ax[0].set_title("%s fracOffset=%.4f fRamp=%.1f Hz"%(self.name, fractionOffset, fitSine['freq']))
            ax[1].set_xlabel("time-syncTimeFit (sec)")
            plt.savefig("%s-phiPrepare.png"%self.name,dpi=600)

    def getPhi(self, channel, ist, fraction = 0.8):
        tpt,tp,dt,tMin,tMax,stf = self.getTrace(channel, ist, fraction)
        num = (tp*(self.syncInfo[channel]['rCos'][:len(tp)])).sum()
        den = (tp*(self.syncInfo[channel]['rSin'][:len(tp)])).sum()
        phi = np.arctan2(num,den)
        return phi

    def getTrace(self, channel, ist, fraction = 0.8, fractionOffset=None):
        syncInfo = self.syncInfo
        if fractionOffset is None:
            fractionOffset = syncInfo[channel]['fractionOffset']
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

def fit_sin(tt, yy):
    '''Fit sin to the input time sequence, and return fitting parameters "amp", "omega", "phase", "offset", "freq", "period" and "fitfunc"'''
    tt = np.array(tt)
    yy = np.array(yy)
    ff = np.fft.fftfreq(len(tt), (tt[1]-tt[0]))   # assume uniform spacing
    Fyy = abs(np.fft.fft(yy))
    guess_freq = abs(ff[np.argmax(Fyy[1:])+1])   # excluding the zero frequency "peak", which is related to offset
    guess_amp = np.std(yy) * 2.**0.5
    guess_offset = np.mean(yy)
    guess = np.array([guess_amp, 2.*np.pi*guess_freq, 0., guess_offset])

    def sinfunc(t, A, w, p, c):  return A * np.sin(w*t + p) + c
    popt, pcov = scipy.optimize.curve_fit(sinfunc, tt, yy, p0=guess)
    A, w, p, c = popt
    f = w/(2.*np.pi)
    fitfunc = lambda t: A * np.sin(w*t + p) + c
    return {"amp": A, "omega": w, "phase": p, "offset": c, "freq": f, 
            "period": 1./f, "fitfunc": fitfunc, "maxcov": np.max(pcov), 
            "rawres": (guess,popt,pcov)}


