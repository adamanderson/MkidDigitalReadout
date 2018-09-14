from collections import OrderedDict
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares
    
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
    fc = np.average(ff, weights=iqv)
    
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
    #ax[0,0].plot(loopFit['iValues'],loopFit['qValues'], color='b')   
    #ax[1,0].plot(1e6*(fvMeasured-f0Guess), vMeasured, color='b')
    ax[1,0].plot((fvMeasured-f0Guess)/1e3, vMeasured,'bo')
    #ax[0,1].plot(1e6*(loopFit['fValues']-f0Guess), aMeasured, label='measured')
    ax[0,1].plot((loopFit['fValues']-f0Guess)/1e3, aMeasured, 'bo')
    #ax[1,1].plot(1e6*(loopFit['fValues']-f0Guess), pMeasured, color='b')
    ax[1,1].plot((loopFit['fValues']-f0Guess)/1e3, pMeasured, 'bo')
    ax[1,1].set_xlabel("f (kHz)")
    
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
        iFit = np.zeros(nFit)
        qFit = np.zeros(nFit)
        for (i,f) in enumerate(fFit):
            iq = mazinResonance(f, q, f0, a, v, c, theta, gi, gq, ic, qc)
            iFit[i] = iq.real
            qFit[i] = iq.imag

        # Loop Plot
        ax[0,0].plot(iFit, qFit, color=lineColor[loopType])
        fvFit, vFit, aFit, pFit = getFVAP(fFit, iFit, qFit)
        # plot velocity
        ax[1,0].plot((fvFit-f0Guess)/1e3, vFit, color=lineColor[loopType])
        # plot amplitude
        ax[0,1].plot((fFit-f0Guess)/1e3, aFit, color=lineColor[loopType], label=loopType)
        ax[0,1].legend()
        # plot phase in degrees
        ax[1,1].plot((fFit-f0Guess)/1e3, pFit, color=lineColor[loopType])    
        plt.tight_layout()
        plt.savefig(pfn, dpi=300)

def getFVAP(fa, ia, qa):
    df = fa[1]-fa[0]
    di = (ia[1:]-ia[:-1])/df
    dq = (qa[1:]-qa[:-1])/df
    v = np.sqrt(di*di+dq*dq)
    ff = 0.5*(fa[1:]+fa[:-1])
    iqs = ia + 1j*qa
    amps = np.absolute(iqs)
    phases = np.angle(iqs, deg=True)
    return (ff,v,amps,phases)

def fittingFunction(parameters):
    global measuredFreqencies, measuredIQs
    (q, f0, a, v, c, theta, gi, gq, ic, qc) = parameters
    iq = mazinResonance(measuredFrequencies, q, f0, a, v, c, theta, gi, gq, ic, qc)
    retval = np.abs(iq-measuredIQs)
    return retval
    
def loopFitter(fValues, iValues, qValues, verbose=0):
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
    return retval

if __name__ == "__main__":
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
    for ipar in range(10):
        #print "ipar=",ipar, " mean=",fits[ipar,:].mean(), "std=",fits[ipar,:].std()
        mean = fits[ipar,:].mean()
        std = fits[ipar,:].std()
        tpl = (tNames[ipar],truth[ipar],mean,std)
        print "%6s truth=%11.3f deltaMean=%8.3f  std=%8.3f"%tpl

