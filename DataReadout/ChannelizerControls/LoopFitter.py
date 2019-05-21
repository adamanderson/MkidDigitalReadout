import os
from collections import OrderedDict
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares, minimize
from scipy.signal import find_peaks

parameterNames = OrderedDict()
parameterNames["q"] = 0
parameterNames["f0"] = 1
parameterNames["a"] = 2
parameterNames["v"] = 3
parameterNames["c"] = 4
parameterNames["theta"] = 5
parameterNames["gi"] = 6
parameterNames["gq"] = 7
parameterNames["ic"] = 8
parameterNames["qc"] = 9

def mazinResonance(x, q, f0, a, v, c, theta, gi, gq, ic, qc):
    dx = (x-f0)/f0
    z = (2*q*dx)*1j
    f = (z/(1+z))
    f -= 0.5 
    f += c*dx 
    temp = np.exp(v*dx*1j)
    temp = 1-temp
    temp = a*temp
    f += temp
    f1 = gi*f.real + gq*(1j)*f.imag
    f2 = f1 * np.exp((1j)*theta)
    f3 = f2 + (ic + (1j)*qc)
    return f3

def firstGuess(fl, il, ql):
    fa = np.array(fl)
    ia = np.array(il)
    qa = np.array(ql)
    # The gains are the diameter of the loop
    gi = ia.max() - ia.min()
    gq = qa.max() - qa.min()
    # The center of the loop is the average of the min,max values
    ic = 0.5*(ia.max()+ia.min()) # or ia.mean()
    qc = 0.5*(qa.max()+qa.min()) # qa.mean()
    
    # get fc from the iq velocity vs frequency
    dia = ia[:-1]-ia[1:]
    dqa = qa[:-1]-qa[1:]
    iqv = np.sqrt(dia*dia+dqa*dqa)
    ff = 0.5*(fa[:-1]+fa[1:])
    try:
        fc = np.average(ff, weights=iqv)
    except ZeroDivisionError:
        fc = np.average(ff)
    # get the STD of the resonance peak; define q = fc/std (what about that factor of 2.something?)
    fmfc = ff-fc
    fmfc2 = fmfc**2
    var = np.average(fmfc2, weights=iqv)
    std = np.sqrt(var)
    q = fc/std
    
    # calculate theta.  Get average of ia and qa, weighted by iq velocity
    iaInterp = np.interp(ff, fa, ia)
    qaInterp = np.interp(ff, fa, qa)    
    wia = np.average(iaInterp, weights=iqv)
    wqa = np.average(qaInterp, weights=iqv)
    dx = wia-ic
    dy = wqa-qc
    
    theta = np.pi/2.0 + np.arctan2(dx, -dy)
    if theta < 0:
        theta += 2.0*np.pi
    #tl = 90+np.arctan2(xl, -yl)*180/np.pi
    #tl = np.where(tl>=0, tl, tl+360)

    retval = OrderedDict()
    retval['q'] =  q
    retval['f0'] = fc
    retval['a'] = 1 # Not bad for a starting point
    retval['v'] = 1000 
    retval['c'] = 1000
    retval['theta'] = theta
    retval['gi'] = gi
    retval['gq'] = gq
    retval['ic'] = ic
    retval['qc'] = qc
    #retval['wia'] = wia
    #retval['wqa'] = wqa

    return retval

def loopFitPlot(loopFit, nFit = 2000, pfn = "LoopFitterTest.png", sigma=0.0):
    fMin = loopFit['fValues'].min()
    fMax = loopFit['fValues'].max()
    df = 0.05*(fMax-fMin)
    fFit = np.linspace(fMin-df, fMax+df, nFit)
    fig,ax = plt.subplots(2,2)
    # get velocity, amplitude, and phase
    fvMeasured, vMeasured, aMeasured, pMeasured = \
        getFVAP(loopFit['fValues'], loopFit['iValues'], loopFit['qValues'])
    f0Guess    = loopFit['guess']['f0']
    # Plot measured
    ax[0,0].errorbar(loopFit['iValues'],loopFit['qValues'], 
                     sigma, sigma, fmt='b.')
    ax[0,0].set_xlabel("I")
    ax[0,0].set_ylabel("Q")
    
    #ax[0,0].plot(loopFit['iValues'],loopFit['qValues'], color='b')   
    #ax[1,0].plot(1e6*(fvMeasured-f0Guess), vMeasured, color='b')
    ax[1,0].plot((fvMeasured-f0Guess)/1e3, vMeasured,'bo')
    ax[1,0].set_xlabel("$\Delta$f (kHz)")
    ax[1,0].set_ylabel("velocity")
    #ax[0,1].plot(1e6*(loopFit['fValues']-f0Guess), aMeasured, label='measured')
    ax[0,1].plot((loopFit['fValues']-f0Guess)/1e3, aMeasured, 'bo')
    ax[0,1].set_xlabel("$\Delta$f (kHz)")
    ax[0,1].set_ylabel("amplitude")
    #ax[1,1].plot(1e6*(loopFit['fValues']-f0Guess), pMeasured, color='b')
    ax[1,1].plot((loopFit['fValues']-f0Guess)/1e3, pMeasured, 'bo')
    ax[1,1].set_xlabel("f (kHz)")
    ax[1,1].set_ylabel("phase")
    
    # Plot guess and fit loops
    lineColor = {"guess":'r', "fit":'g'}    
    for loopType in ["fit"]:
        if loopType == "guess":
            q     = loopFit['guess']['q']
            f0    = loopFit['guess']['f0']
            a     = loopFit['guess']['a']
            v     = loopFit['guess']['v']
            c     = loopFit['guess']['c']
            theta = loopFit['guess']['theta']
            gi    = loopFit['guess']['gi']
            gq    = loopFit['guess']['gq']
            ic    = loopFit['guess']['ic']
            qc    = loopFit['guess']['qc']
        else:
            param = loopFit['nsq'].x
            q     = param[0]
            f0    = param[1]
            a     = param[2]
            v     = param[3]
            c     = param[4]
            theta = param[5]
            gi    = param[6]
            gq    = param[7]
            ic    = param[8]
            qc    = param[9]
        iFit = np.zeros(len(fFit))
        qFit = np.zeros(len(fFit))
        for (i,f) in enumerate(fFit):
            iq = mazinResonance(f, q, f0, a, v, c, theta, gi, gq, ic, qc)
            iFit[i] = iq.real
            qFit[i] = iq.imag

        # Loop Plot
        ax[0,0].plot(iFit, qFit, color=lineColor[loopType])
        fvFit, vFit, aFit, pFit = getFVAP(fFit, iFit, qFit)
        # plot velocity
        ax[1,0].plot((fvFit-f0Guess)/1e3, vFit, color=lineColor[loopType])
        ax[1,0].axvline((f0-f0Guess)/1e3, color="r")
        
        # plot amplitude
        ax[0,1].plot((fFit-f0Guess)/1e3, aFit, color=lineColor[loopType], label=loopType)
        ax[0,1].axvline((f0-f0Guess)/1e3, color="r")
        ax[0,1].legend()
        # plot phase in degrees
        ax[1,1].plot((fFit-f0Guess)/1e3, pFit, color=lineColor[loopType])    
        ax[1,1].axvline((f0-f0Guess)/1e3, color="r")
        fig.suptitle(pfn)
        plt.tight_layout()
        plt.savefig(pfn, dpi=300)
        
        plt.close(fig)
        
def getFVAP(fa, ia, qa, iCenter=0, qCenter=0):
    df = fa[1]-fa[0]
    di = (ia[1:]-ia[:-1])/df
    dq = (qa[1:]-qa[:-1])/df
    v = np.sqrt(di*di+dq*dq)
    ff = 0.5*(fa[1:]+fa[:-1])
    iqs = ia + 1j*qa
    amps = np.absolute(iqs)
    iqsp = (ia-iCenter) + 1j*(qa-qCenter)
    phases = np.angle(iqsp, deg=True)
    return (ff,v,amps,phases)

def fittingFunction(parameters):
    global measuredFreqencies, measuredIQs
    (q, f0, a, v, c, theta, gi, gq, ic, qc) = parameters
    iq = mazinResonance(measuredFrequencies, q, f0, a, v, c, theta, gi, gq, ic, qc)
    retval = np.abs(iq-measuredIQs)
    return retval
    
def loopFitter(fValues, iValues, qValues, verbose=0, nFit=2000):
    global measuredFrequencies, measuredIQs
    retval = OrderedDict()
    retval['fValues'] = fValues
    retval['iValues'] = iValues
    retval['qValues'] = qValues
    guess = firstGuess(fValues, iValues, qValues)
    retval['guess'] = guess
    guessValues = guess.values()
    measuredFrequencies = fValues
    measuredIQs = iValues + 1j*qValues
    nsq = least_squares(fittingFunction, guessValues, verbose=verbose, x_scale='jac')
    retval['nsq'] = nsq
    if nFit > 0:
        fMin = retval['fValues'].min()
        fMax = retval['fValues'].max()
        df = 0.05*(fMax-fMin)
        fFit = np.linspace(fMin-df, fMax+df, nFit)
        retval['fFit'] = fFit
        param = retval['nsq'].x
        q     = param[0]
        f0    = param[1]
        a     = param[2]
        v     = param[3]
        c     = param[4]
        theta = param[5]
        gi    = param[6]
        gq    = param[7]
        ic    = param[8]
        qc    = param[9]
        iFit = np.zeros(nFit)
        qFit = np.zeros(nFit)
        for (i,f) in enumerate(fFit):
            iq = mazinResonance(f, q, f0, a, v, c, theta, gi, gq, ic, qc)
            iFit[i] = iq.real
            qFit[i] = iq.imag
        retval['iFit'] = iFit
        retval['qFit'] = qFit
    return retval

if __name__ == "__main__":
    print "Demonstrate how LoopFitter functions work"
    q = 789892.56
    f0 = 5.6930312E6 # frequency in kHz
    f0 = 5.0E6 # frequency in kHz
    a = 3.6921007
    v = 1738.3526
    c = 4849.9218
    theta = 0.43856595
    gi = 1202.1240
    gq = 1280.4136
    ic = 7164.7115
    qc = 11181.436

    df = 20.0
    freqs = np.linspace(f0-df, f0+df, 20)
    iqs = mazinResonance(freqs, q, f0, a, v, c, theta, gi, gq, ic, qc)
    ia = iqs.real
    qa = iqs.imag
    loopFit = loopFitter(freqs, ia, qa)
    loopFitPlot(loopFit)

    np.random.seed(1234567)
    sigma = 50
    df = 20.0
    freqs = np.linspace(f0-df, f0+df, 20)
    iqs = mazinResonance(freqs, q, f0, a, v, c, theta, gi, gq, ic, qc)
    ia = iqs.real + np.random.normal(scale=sigma)
    qa = iqs.imag + np.random.normal(scale=sigma)
    loopFit = loopFitter(freqs, ia, qa)
    loopFitPlot(loopFit, pfn="LoopFitterTestWithErrbar.png", sigma=sigma)

    nToFit = 100
    fits = np.zeros((10,nToFit))
    truth = np.array([q, f0, a, v, c, theta, gi, gq, ic, qc])
    tNames = ['q', 'f0', 'a', 'v', 'c', 'theta', 'gi', 'gq', 'ic', 'qc']
    for i in range(nToFit):
        ia = iqs.real + np.random.normal(scale=sigma)
        qa = iqs.imag + np.random.normal(scale=sigma)
        loopFit = loopFitter(freqs, ia, qa)
        for ipar in range(10):
            fits[ipar,i] = loopFit['nsq'].x[ipar] - truth[ipar]
    print "These should all be good:  mean of ",nToFit," results < 2 stds"
    for ipar in range(10):
        #print "ipar=",ipar, " mean=",fits[ipar,:].mean(), "std=",fits[ipar,:].std()
        mean = fits[ipar,:].mean()
        std = fits[ipar,:].std()
        if abs(mean) < 2*abs(std):
            result = "GOOD"
        else:
            result = "BAD"
        tpl = (result,tNames[ipar],truth[ipar],mean,std)
        print "%4s %6s truth=%11.3f deltaMean=%8.3f  std=%8.3f"%tpl

def iqRot(i,q,thetaDeg):
    ct = np.cos(np.radians(thetaDeg))
    st = np.sin(np.radians(thetaDeg))
    r = np.array([[ct,st],[-st,ct]])
    x = r.dot(np.array([i,q]))
    return x[0,:], x[1,:]

def funcToMinimize(thetaDegrees, io0, qo0, io1, qo1):
    io1r, qo1r = iqRot(io1,qo1,thetaDegrees[0])
    d = ((io0-io1r)**2 + (qo0-qo1r)**2).sum()
    #print "thetaDegrees[0],d",thetaDegrees[0],d
    return d

def findAndFitResonances(iqData, thresholdFraction=0.3, pfnRoot=None):
    print "find and fit resonances:  pfnRoot =",pfnRoot
    if pfnRoot is None:
        peaksPfn = None
    else:
        peaksPfn = pfnRoot+"-findPeaks.png"
    peaks = findPeaks(iqData, thresholdFraction, peaksPfn)
    print "number of peaks found:  ",len(peaks['peaks'])
    return peaks

def findPeaks(iqData, thresholdFraction=0.3, pfn=None):
    I = np.array(iqData['I'])
    Q = np.array(iqData['Q'])
    fo = np.array(iqData['freqOffsets'])
    freqList = np.array(iqData['freqList'])
    
    print "I", I.shape
    print "fo",fo.shape
    print "freqList",freqList.shape
    amps = np.empty(I.shape)
    phases = np.empty(I.shape)
    fas = np.empty(I.shape)
    iRotated = I.copy()
    qRotated = Q.copy()
    for iFreq,freq in enumerate(freqList):
        fa = freq + fo
        fas[iFreq,:] =  fa
        ia = I[iFreq, :]
        qa = Q[iFreq, :]
        ff,v,amps[iFreq,:],phases[iFreq,:] = getFVAP(fa,ia,qa)
    relativeGains = np.ones(len(freqList))
    for iFreq0 in range(len(freqList)-1):
        iFreq1 = iFreq0+1
        xMax = fas[iFreq0,:].max()
        xMin = fas[iFreq1,:].min()
        a0Mean = amps[iFreq0,fas[iFreq0,:]>=xMin].mean()
        a1Mean = amps[iFreq1,fas[iFreq1,:]<=xMax].mean()
        relativeGains[iFreq1] = a0Mean/a1Mean
        amps[iFreq1,:] *= relativeGains[iFreq1]

        # Rotate the i,q values for iFreq1 to match iFreq0 in the overlap
        fa0 = fas[iFreq0,:]
        fa1 = fas[iFreq1,:]
        inda = np.searchsorted(fa0,fa1[0])
        nOverlap = len(fa0)-inda
        f0 = fa0[inda:]
        f1 = fa1[:nOverlap]
        io0 = iRotated[iFreq0, inda:]
        qo0 = qRotated[iFreq0, inda:]
        io1 = iRotated[iFreq1, :nOverlap]
        qo1 = qRotated[iFreq1, :nOverlap]
        res = minimize(funcToMinimize, np.array([180.0]), args=(io0, qo0, io1, qo1))
        theta = res['x'][0]
        if iFreq1 < 3:
            print "iFreq0, iFreq1, theta",iFreq0, iFreq1, theta
        ir1,qr1 = iqRot(I[iFreq1, :], Q[iFreq1, :], theta)
        iRotated[iFreq1, :] = ir1
        qRotated[iFreq1, :] = qr1
    fMin = fas[0,0]
    df = iqData['LO_step']
    fMax = fas[-1,-1]+df
    print fMin,df,fMax
    nBins = int((fMax-fMin)/df)
    print "nBins =",nBins
    aSum = np.zeros(nBins)
    fSum = np.zeros(nBins)
    nSum = np.zeros(nBins)
    iSum = np.zeros(nBins)
    qSum = np.zeros(nBins)
    for iFreq in range(len(freqList)):
        for iSample,f in enumerate(fas[iFreq,:]):
            iBin = int((f-fMin)/df)
            nSum[iBin] += 1
            fSum[iBin] += f
            aSum[iBin] += amps[iFreq,iSample]
            iSum[iBin] += iRotated[iFreq, iSample]
            qSum[iBin] += qRotated[iFreq, iSample]
    #plt.plot(nSum[-300:])
    fAvg = fSum/nSum
    aAvg = aSum/nSum
    iAvg = iSum/nSum
    qAvg = qSum/nSum
    y = aAvg
    y = (y.max()-y)
    print "thresholdFraction",thresholdFraction,y
    hMin = thresholdFraction * y.max()
    peaks,_ = find_peaks(y, height=hMin)
    if pfn is not None:
        plt.clf()
        plt.plot(fAvg, aAvg)
        plt.plot(fAvg[peaks], aAvg[peaks], 'rx')
        plt.xlabel("Frequency (Hz)")
        plt.ylabel("Amplitude (ADUs)")
        plt.title(pfn)
        plt.savefig(pfn, dpi=300)

        plt.clf()
        fig,ax = plt.subplots(2,1,sharex=True)
        ax[0].plot(fAvg, iAvg)
        ax[0].set_ylabel("I (adu)")
        ax[1].plot(fAvg, qAvg)
        ax[1].set_ylabel("Q (adu)")
        ax[1].set_xlabel("f (Hz)")
        ffn = "%s-allIQ.png"%(os.path.splitext(pfn)[0])
        plt.suptitle(os.path.splitext(pfn)[0])
        plt.savefig(ffn,dpi=300)

        plt.clf()
        for iFreq in range(6):
            plt.plot(I[iFreq, :],Q[iFreq, :], label=iFreq)
        plt.legend()
        plt.title("IQ")
        plt.title(os.path.splitext(pfn)[0])
        plt.savefig(os.path.splitext(pfn)[0]+"-iqLoops.png",dpi=300)
        
        plt.clf()
        for iFreq in range(6):
            plt.plot(iRotated[iFreq, :], qRotated[iFreq, :], label=iFreq)
        #plt.legend()
        plt.title(os.path.splitext(pfn)[0]+" rotated")
        plt.savefig(os.path.splitext(pfn)[0]+"-iqrLoops.png",dpi=300)
    di = 15
    loopFits = []
    for iPeak,peak in enumerate(peaks):
        print "Now fit iPeak, peak =",iPeak, peak
        ff = fAvg[peak-di:peak+di]
        ii = iAvg[peak-di:peak+di]
        qq = qAvg[peak-di:peak+di]
        lf = loopFitter(ff, ii, qq)
        loopFits.append(lf)
        if pfn is not None:
            ffn = "%s-%03d.png"%(os.path.splitext(pfn)[0],iPeak)
            loopFitPlot(lf, pfn=ffn)
        if iPeak > 2: break
    return {"peaks":peaks, "loopFits":loopFits}
